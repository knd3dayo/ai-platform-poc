from __future__ import annotations

import argparse
import asyncio
import pathlib
from dataclasses import dataclass
from typing import Any, Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, RichLog, Static, TextArea

from ..core.hitl_core import HitlAction, HitlContext, HitlUi, run_integrated_agent_hitl


def _parse_source_dirs(text: str) -> list[pathlib.Path]:
    raw = (text or "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",")]
    return [pathlib.Path(p) for p in parts if p]


class TraceMessage(Message):
    def __init__(self, trace_id: str) -> None:
        super().__init__()
        self.trace_id = trace_id


class PlanMessage(Message):
    def __init__(self, plan_text: str, tasks: list[str]) -> None:
        super().__init__()
        self.plan_text = plan_text
        self.tasks = tasks


class PromptConfirmStart(Message):
    pass


class TaskStartMessage(Message):
    def __init__(self, ctx: HitlContext) -> None:
        super().__init__()
        self.ctx = ctx


class PromptAction(Message):
    def __init__(self, ctx: HitlContext) -> None:
        super().__init__()
        self.ctx = ctx


class TaskResultMessage(Message):
    def __init__(self, ctx: HitlContext, record: dict[str, Any]) -> None:
        super().__init__()
        self.ctx = ctx
        self.record = record


class PausedMessage(Message):
    def __init__(self, session_path: pathlib.Path) -> None:
        super().__init__()
        self.session_path = session_path


class FinalReportMessage(Message):
    def __init__(self, final_text: str) -> None:
        super().__init__()
        self.final_text = final_text


@dataclass
class _Pending:
    confirm_future: Optional[asyncio.Future[bool]] = None
    action_future: Optional[asyncio.Future[HitlAction]] = None
    action_ctx: Optional[HitlContext] = None


class _TextualHitlUi(HitlUi):
    def __init__(self, app: "SuperVisorTuiApp") -> None:
        self._app = app

    async def on_trace(self, trace_id: str) -> None:
        self._app.post_message(TraceMessage(trace_id))

    async def on_plan(self, plan_text: str, tasks: list[str]) -> None:
        self._app.post_message(PlanMessage(plan_text, tasks))

    async def confirm_start(self) -> bool:
        fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._app._pending.confirm_future = fut
        self._app.post_message(PromptConfirmStart())
        return await fut

    async def on_task_start(self, ctx: HitlContext) -> None:
        self._app.post_message(TaskStartMessage(ctx))

    async def choose_action(self, ctx: HitlContext, *, default: HitlAction) -> HitlAction:
        fut: asyncio.Future[HitlAction] = asyncio.get_running_loop().create_future()
        self._app._pending.action_ctx = ctx
        self._app._pending.action_future = fut
        self._app.post_message(PromptAction(ctx))
        try:
            return await fut
        finally:
            self._app._pending.action_ctx = None
            self._app._pending.action_future = None

    async def on_task_result(self, ctx: HitlContext, result: dict[str, Any]) -> None:
        self._app.post_message(TaskResultMessage(ctx, result))

    async def on_paused(self, session_path: pathlib.Path) -> None:
        self._app.post_message(PausedMessage(session_path))

    async def on_final_report(self, final_text: str) -> None:
        self._app.post_message(FinalReportMessage(final_text))


class SetupScreen(Screen[None]):
    BINDINGS = [
        ("ctrl+c", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="setup"):
            yield Label("Message")
            yield TextArea(id="message", text="")
            yield Label("Source dirs (comma-separated paths)")
            yield Input(id="source_dirs", placeholder="例: ./app/ai-platform-samplelib, ./docs")
            yield Label("Session dir (optional)")
            yield Input(id="session_dir", placeholder="省略時: 推測したルート配下 .sv_sessions")
            yield Label("Resume from (optional session json)")
            yield Input(id="resume_from", placeholder="例: /path/to/.sv_sessions/sv_hitl_<id>.json")
            with Horizontal():
                yield Button("Run", id="run", variant="primary")
                yield Button("Resume", id="resume")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run":
            self.app.action_start_run(resume=False)
        elif event.button.id == "resume":
            self.app.action_start_run(resume=True)


class RunScreen(Screen[None]):
    BINDINGS = [
        ("a", "approve", "Approve"),
        ("s", "skip", "Skip"),
        ("p", "pause", "Pause"),
        ("y", "yes", "Yes"),
        ("n", "no", "No"),
        ("q", "quit_to_setup", "Back"),
    ]

    trace_id: reactive[str] = reactive("")
    status: reactive[str] = reactive("idle")

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="run"):
            yield Static("", id="trace")
            yield Static("", id="status")
            with Horizontal():
                with Container(id="left"):
                    yield Label("Plan")
                    yield TextArea(id="plan", read_only=True)
                    yield Label("Tasks")
                    yield ListView(id="tasks")
                with Container(id="right"):
                    yield Label("Log")
                    yield RichLog(id="log", wrap=True, markup=False)
        yield Footer()

    def watch_trace_id(self, value: str) -> None:
        self.query_one("#trace", Static).update(f"trace_id: {value}")

    def watch_status(self, value: str) -> None:
        self.query_one("#status", Static).update(value)

    def action_quit_to_setup(self) -> None:
        self.app.pop_screen()

    def _set_action(self, action: HitlAction) -> None:
        fut = self.app._pending.action_future
        if fut is not None and not fut.done():
            fut.set_result(action)

    def action_approve(self) -> None:
        self._set_action("a")

    def action_skip(self) -> None:
        self._set_action("s")

    def action_pause(self) -> None:
        self._set_action("p")

    def action_yes(self) -> None:
        fut = self.app._pending.confirm_future
        if fut is not None and not fut.done():
            fut.set_result(True)

    def action_no(self) -> None:
        fut = self.app._pending.confirm_future
        if fut is not None and not fut.done():
            fut.set_result(False)


class SuperVisorTuiApp(App[None]):
    CSS = """
    #setup, #run { padding: 1; }
    #left { width: 1fr; }
    #right { width: 1fr; }
    TextArea { height: 8; }
    #plan { height: 12; }
    #tasks { height: 12; }
    #log { height: 1fr; }
    """

    def __init__(self, *, initial_message: str = "", initial_source_dirs: str = "", initial_resume: str = "") -> None:
        super().__init__()
        self._pending = _Pending()
        self._ui = _TextualHitlUi(self)
        self._initial_message = initial_message
        self._initial_source_dirs = initial_source_dirs
        self._initial_resume = initial_resume

    def on_mount(self) -> None:
        self.push_screen(SetupScreen())
        setup = self.screen
        setup.query_one("#message", TextArea).text = self._initial_message
        setup.query_one("#source_dirs", Input).value = self._initial_source_dirs
        setup.query_one("#resume_from", Input).value = self._initial_resume

    def action_start_run(self, *, resume: bool) -> None:
        setup = self.screen
        message = setup.query_one("#message", TextArea).text
        source_dirs_text = setup.query_one("#source_dirs", Input).value
        session_dir_text = setup.query_one("#session_dir", Input).value
        resume_from_text = setup.query_one("#resume_from", Input).value

        source_dirs = _parse_source_dirs(source_dirs_text)
        session_dir = pathlib.Path(session_dir_text).expanduser() if session_dir_text.strip() else None

        resume_from = None
        if resume or resume_from_text.strip():
            resume_from = pathlib.Path(resume_from_text).expanduser() if resume_from_text.strip() else None

        self.push_screen(RunScreen())
        self.run_worker(
            self._run_core(message=message, source_dirs=source_dirs, session_dir=session_dir, resume_from=resume_from),
            exclusive=True,
            name="hitl",
        )

    async def _run_core(
        self,
        *,
        message: str,
        source_dirs: list[pathlib.Path],
        session_dir: pathlib.Path | None,
        resume_from: pathlib.Path | None,
    ) -> None:
        run_screen = self.screen_stack[-1]
        if isinstance(run_screen, RunScreen):
            run_screen.status = "planning..."

        try:
            await run_integrated_agent_hitl(
                message=message,
                source_dirs=source_dirs,
                session_dir=session_dir,
                resume_from=resume_from,
                auto_approve=False,
                trace_id=None,
                ui=self._ui,
            )
        except Exception as e:
            if isinstance(run_screen, RunScreen):
                log = run_screen.query_one("#log", RichLog)
                log.write(f"ERROR: {e!r}")

    def _run_screen(self) -> RunScreen | None:
        if self.screen_stack and isinstance(self.screen_stack[-1], RunScreen):
            return self.screen_stack[-1]
        return None

    def on_trace_message(self, msg: TraceMessage) -> None:
        run = self._run_screen()
        if run:
            run.trace_id = msg.trace_id

    def on_plan_message(self, msg: PlanMessage) -> None:
        run = self._run_screen()
        if not run:
            return
        run.status = "plan ready (press y to start / n to cancel)"
        run.query_one("#plan", TextArea).text = msg.plan_text
        lv = run.query_one("#tasks", ListView)
        lv.clear()
        for t in msg.tasks:
            lv.append(ListItem(Label(t)))

    def on_prompt_confirm_start(self, msg: PromptConfirmStart) -> None:
        run = self._run_screen()
        if run:
            run.status = "confirm start: y=yes / n=no"

    def on_task_start_message(self, msg: TaskStartMessage) -> None:
        run = self._run_screen()
        if not run:
            return
        run.status = f"task {msg.ctx.idx+1}/{msg.ctx.total}: waiting decision (a/s/p)"

        lv = run.query_one("#tasks", ListView)
        try:
            lv.index = msg.ctx.idx
        except Exception:
            pass

        log = run.query_one("#log", RichLog)
        log.write(f"[TaskStart] {msg.ctx.idx+1}/{msg.ctx.total}: {msg.ctx.task}")

    def on_prompt_action(self, msg: PromptAction) -> None:
        run = self._run_screen()
        if run:
            run.status = "choose action: a=approve / s=skip / p=pause"

    def on_task_result_message(self, msg: TaskResultMessage) -> None:
        run = self._run_screen()
        if not run:
            return
        run.status = f"task {msg.ctx.idx+1}/{msg.ctx.total}: finished"
        rec = msg.record
        res = rec.get("result") if isinstance(rec, dict) else None
        stdout = res.get("stdout") if isinstance(res, dict) else None
        tail = ""
        if isinstance(stdout, str) and stdout.strip():
            lines = stdout.strip().splitlines()
            tail = "\n".join(lines[-30:])

        log = run.query_one("#log", RichLog)
        log.write(f"[TaskEnd] {msg.ctx.idx+1}/{msg.ctx.total}: {rec.get('tool')} elapsed={rec.get('elapsed_sec')}s")
        if tail:
            log.write("--- stdout (tail) ---")
            log.write(tail)

    def on_paused_message(self, msg: PausedMessage) -> None:
        run = self._run_screen()
        if run:
            run.status = f"paused: {msg.session_path}"
            run.query_one("#log", RichLog).write(f"[Paused] session saved: {msg.session_path}")

    def on_final_report_message(self, msg: FinalReportMessage) -> None:
        run = self._run_screen()
        if run:
            run.status = "completed"
            log = run.query_one("#log", RichLog)
            log.write("[FinalReport]")
            log.write(msg.final_text)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Super-Visor Textual TUI (HITL)")
    parser.add_argument("--message", default="", help="Initial message")
    parser.add_argument(
        "--source-dirs",
        default="",
        help="Comma-separated host paths to include in workspace context",
    )
    parser.add_argument("--resume-from", default="", help="Path to HITL session json")
    args = parser.parse_args(argv)

    SuperVisorTuiApp(
        initial_message=args.message,
        initial_source_dirs=args.source_dirs,
        initial_resume=args.resume_from,
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
