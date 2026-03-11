from __future__ import annotations

import pathlib
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Optional, Protocol

from langchain_core.messages import HumanMessage
from langgraph.graph import MessagesState

from ..model.hitl_session import HitlSession
from .agent import run_executor_local
from .agent import LangGraphNodes
from .hitl_utils import (
    build_user_input_with_context,
    extract_tasks_from_plan_text,
    raw_summary_from_results,
    session_default_dir,
    session_file_path,
)


HitlAction = Literal["a", "s", "p"]


@dataclass(frozen=True)
class HitlContext:
    idx: int
    total: int
    task: str
    trace_id: str
    session_path: pathlib.Path


class HitlUi(Protocol):
    async def on_trace(self, trace_id: str) -> None: ...

    async def on_plan(self, plan_text: str, tasks: list[str]) -> None: ...

    async def confirm_start(self) -> bool: ...

    async def on_task_start(self, ctx: HitlContext) -> None: ...

    async def choose_action(self, ctx: HitlContext, *, default: HitlAction) -> HitlAction: ...

    async def on_task_result(self, ctx: HitlContext, result: dict[str, Any]) -> None: ...

    async def on_paused(self, session_path: pathlib.Path) -> None: ...

    async def on_final_report(self, final_text: str) -> None: ...


class _NoopUi:
    async def on_trace(self, trace_id: str) -> None:
        return None

    async def on_plan(self, plan_text: str, tasks: list[str]) -> None:
        return None

    async def confirm_start(self) -> bool:
        return True

    async def on_task_start(self, ctx: HitlContext) -> None:
        return None

    async def choose_action(self, ctx: HitlContext, *, default: HitlAction) -> HitlAction:
        return default

    async def on_task_result(self, ctx: HitlContext, result: dict[str, Any]) -> None:
        return None

    async def on_paused(self, session_path: pathlib.Path) -> None:
        return None

    async def on_final_report(self, final_text: str) -> None:
        return None


@dataclass(frozen=True)
class HitlRunResult:
    status: Literal["paused", "completed", "cancelled"]
    trace_id: str
    session_path: pathlib.Path


def _skipped_result(*, task: str) -> dict[str, Any]:
    now = time.time()
    return {
        "task": task,
        "started_at": now,
        "ended_at": now,
        "elapsed_sec": 0.0,
        "tool": None,
        "result": {
            "status": "exited",
            "sub_status": "cancelled",
            "stdout": "Skipped by user (HITL deny).",
            "stderr": None,
        },
    }


async def run_integrated_agent_hitl(
    *,
    message: str,
    source_dirs: list[pathlib.Path],
    session_dir: pathlib.Path | None = None,
    resume_from: pathlib.Path | None = None,
    auto_approve: bool = False,
    trace_id: Optional[str] = None,
    ui: HitlUi | None = None,
) -> HitlRunResult | None:
    """UI非依存のHITLコア（停止→保存→resume）。

    - 計画作成: planner
    - 実行: サブタスクを逐次実行
    - HITL: サブタスクごとに a/s/p を選択
    - p の場合はセッションJSONを書き出して終了
    """

    effective_ui: HitlUi = ui or _NoopUi()

    # --------------------
    # resume or new session
    # --------------------
    if resume_from is not None:
        session_path = resume_from
        session = HitlSession.load_json(session_path)
        original_request = session.original_request
        trace_id = session.trace_id or trace_id or str(uuid.uuid4())
        tasks = session.tasks
        results: list[dict[str, Any]] = list(session.results)
        start_index = int(session.next_task_index or 0)
        if session.source_dirs:
            source_dirs = [pathlib.Path(p) for p in session.source_dirs]
        session_dir = session_path.parent
    else:
        session_id = str(uuid.uuid4())
        trace_id = trace_id or str(uuid.uuid4())
        if session_dir is None:
            session_dir = session_default_dir(source_dirs)
        session_path = session_file_path(session_dir, session_id)

        original_request = build_user_input_with_context(message, source_dirs)

        plan_state: MessagesState = {"messages": [HumanMessage(content=original_request)]}
        planned = await LangGraphNodes.planner_node(plan_state)
        plan_msg = planned["messages"][-1]
        plan_text = getattr(plan_msg, "content", "") or ""

        tasks = extract_tasks_from_plan_text(plan_text)
        if not tasks:
            return None

        await effective_ui.on_plan(plan_text, tasks)
        if not await effective_ui.confirm_start():
            return HitlRunResult(status="cancelled", trace_id=trace_id, session_path=session_path)

        results = []
        start_index = 0
        session = HitlSession(
            session_id=session_id,
            status="paused",
            original_request=original_request,
            trace_id=trace_id,
            source_dirs=[str(p.resolve()) for p in source_dirs],
            tasks=tasks,
            next_task_index=0,
            results=[],
        )

    await effective_ui.on_trace(trace_id)

    # 逐次実行
    for idx in range(start_index, len(tasks)):
        task = (tasks[idx] or "").strip()
        if not task:
            continue

        ctx = HitlContext(idx=idx, total=len(tasks), task=task, trace_id=trace_id, session_path=session_path)

        await effective_ui.on_task_start(ctx)

        prompt = (
            "あなたは実行担当の自律型コーディングエージェントです。\n"
            "次のサブタスクを実行してください。必要ならファイルを読み、結果を日本語で報告してください。\n\n"
            f"[サブタスク]\n{task}\n\n"
            f"[元の依頼]\n{original_request}\n"
        )

        if auto_approve:
            action = "a"
        else:
            action = await effective_ui.choose_action(ctx, default="a")

        if action == "p":
            session.next_task_index = idx
            session.results = results
            session.status = "paused"
            session.save_json(session_path)
            await effective_ui.on_paused(session_path)
            return HitlRunResult(status="paused", trace_id=trace_id, session_path=session_path)

        if action == "s":
            results.append(_skipped_result(task=task))
        else:
            tool_args: dict[str, Any] = {"prompt": prompt, "timeout": 600}
            if source_dirs:
                tool_args["source_dirs"] = [str(p) for p in source_dirs]
            if trace_id:
                tool_args["trace_id"] = trace_id

            started_at = time.time()
            result = await run_executor_local.ainvoke(tool_args)
            ended_at = time.time()
            results.append(
                {
                    "task": task,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "elapsed_sec": round(ended_at - started_at, 3),
                    "tool": getattr(run_executor_local, "name", "run_executor_local"),
                    "result": result,
                }
            )

        await effective_ui.on_task_result(ctx, results[-1])

        # 進捗を都度保存（落ちても再開できるように）
        session.next_task_index = idx + 1
        session.results = results
        session.status = "paused"
        session.save_json(session_path)

    raw_summary = raw_summary_from_results(results=results, max_parallel=1)
    summary_msg = await LangGraphNodes.planner_summarize_results(
        original_request=original_request,
        results=results,
        raw_summary=raw_summary,
    )
    final_text = (getattr(summary_msg, "content", "") or "").strip()
    if raw_summary:
        final_text = f"{final_text}\n\n---\n[詳細サマリ]\n{raw_summary}".strip()

    await effective_ui.on_final_report(final_text)

    session.status = "completed"
    session.next_task_index = len(tasks)
    session.results = results
    session.save_json(session_path)
    return HitlRunResult(status="completed", trace_id=trace_id, session_path=session_path)
