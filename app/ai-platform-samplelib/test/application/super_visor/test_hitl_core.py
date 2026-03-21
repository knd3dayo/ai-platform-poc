import pathlib
import asyncio
from typing import Any

import pytest

from super_visor_agent_util.core.hitl_core import run_integrated_agent_hitl


class _UiAutoApprove:
    async def on_trace(self, trace_id: str) -> None:
        return None

    async def on_plan(self, plan_text: str, tasks: list[str]) -> None:
        return None

    async def confirm_start(self) -> bool:
        return True

    async def on_task_start(self, ctx: Any) -> None:
        return None

    async def choose_action(self, ctx: Any, *, default: str) -> str:
        return "a"

    async def on_task_result(self, ctx: Any, result: dict[str, Any]) -> None:
        return None

    async def on_paused(self, session_path: pathlib.Path) -> None:
        return None

    async def on_final_report(self, final_text: str) -> None:
        return None


def test_hitl_uses_mcp_executor_workspace_path(monkeypatch, tmp_path: pathlib.Path) -> None:
    # Avoid hitting the real planner & summarizer; keep test local and deterministic.
    from super_visor_agent_util.core import hitl_core

    async def _fake_planner_node(state: Any) -> Any:
        class _Msg:
            content = "- task: do something"

        return {"messages": [_Msg()]}

    def _fake_extract_tasks(plan_text: str) -> list[str]:
        return ["dummy task"]

    async def _fake_planner_summarize_results(**kwargs: Any) -> Any:
        class _Msg:
            content = "summary"

        return _Msg()

    captured: dict[str, Any] = {}

    class _DummyTool:
        name = "run_autonomous_agent_executor"

        async def ainvoke(self, args: dict[str, Any]) -> dict[str, Any]:
            captured.update(args)
            return {"status": "exited", "sub_status": "completed", "stdout": "ok", "stderr": None}

    monkeypatch.setattr(hitl_core.LangGraphNodes, "planner_node", _fake_planner_node)
    monkeypatch.setattr(hitl_core, "extract_tasks_from_plan_text", _fake_extract_tasks)
    monkeypatch.setattr(hitl_core.LangGraphNodes, "planner_summarize_results", _fake_planner_summarize_results)
    monkeypatch.setattr(hitl_core.Tools, "run_autonomous_agent_executor", _DummyTool())

    source_dirs = [tmp_path]
    res = asyncio.run(
        run_integrated_agent_hitl(
            message="hello",
            source_dirs=source_dirs,
            session_dir=tmp_path,
            resume_from=None,
            auto_approve=True,
            trace_id="trace-1",
            ui=_UiAutoApprove(), # type: ignore
        )
    )

    assert res is not None
    assert res.status == "completed"
    assert captured["workspace_path"] == str(tmp_path.resolve())
    assert captured["prompt"]
    assert captured["timeout"] == 600
    assert captured["trace_id"] == "trace-1"
