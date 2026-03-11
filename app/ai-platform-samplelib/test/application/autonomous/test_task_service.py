import asyncio
from pathlib import Path

import pytest

from ai_platform_samplelib.application.autonomous.core.docker_task_service import TaskService
from ai_platform_samplelib.application.autonomous.model.models import TaskStatus
from ai_platform_samplelib.application.autonomous.core import docker_task_service as task_service_module
from ai_platform_samplelib.application.autonomous.core.abstract_actions import AbstractActions

class _DummyActions(AbstractActions):
    def __init__(self) -> None:
        self.started: list[str] = []
        self.started_detach: list[str] = []

    def after_start_task_action(self, tid: str) -> None:
        self.started.append(tid)

    def after_start_detach_task_action(self, tid: str) -> None:
        self.started_detach.append(tid)

    async def progress_action(self, tid: str) -> TaskStatus:
        return TaskStatus(task_id=tid)

    def after_complete_action(self, runner) -> None:
        return
    
    def after_task_not_found_action(self) -> None:
        return

    def after_list_action(self, table: list) -> None:
        return
    
    def after_cancel_action(self, task_id: str) -> None:
        return
    
    def after_get_status_action(self, task_id: str, status_data: TaskStatus) -> None:
        return

    def prune_progress_action(self, generator) -> None:
        for _ in generator:
            pass
        return

def test_task_service_run_does_not_pass_background_tasks_and_normalizes_source_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_create_runner(*, prompt: str, task_id: str | None = None, source_paths=None, **kwargs):
        captured["prompt"] = prompt
        captured["task_id"] = task_id
        captured["source_paths"] = source_paths
        captured["extra_kwargs"] = kwargs

        class _Runner:
            def __init__(self, tid: str) -> None:
                self.task_id = tid

        return _Runner(task_id or "dummy")

    async def fake_run_task(runner, timeout: int, wait: bool):
        yield TaskStatus(task_id=runner.task_id, status="running", sub_status="starting")
        yield TaskStatus(task_id=runner.task_id, status="exited", sub_status="completed")

    # Avoid touching filesystem-backed task storage in this unit test.
    monkeypatch.setattr(task_service_module.TaskManager, "load_tasks", lambda: None)

    # Patch runner creation and execution path to keep test fast and hermetic.
    monkeypatch.setattr(task_service_module.CodingAgentRunner, "create_runner", fake_create_runner)
    monkeypatch.setattr(TaskService, "run_task", fake_run_task)

    actions = _DummyActions()

    asyncio.run(
        TaskService.run(
            actions=actions,
            prompt="hello",
            sources=[tmp_path],
            task_id="tid",
            timeout=1,
            wait=True
        )
    )

    assert captured["prompt"] == "hello"
    assert captured["task_id"] == "tid"

    # Key regression: ensure src is passed as list[pathlib.Path]
    assert captured["source_paths"] == [tmp_path]

    # Key regression: no legacy FastAPI background_tasks should leak into CLI run
    assert captured["extra_kwargs"] == {}


def test_run_task_detached_spawns_monitor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    spawned: dict[str, object] = {}

    class _DummyContainer:
        id = "dummy-container"

        def reload(self):
            return

    class _DummyRunner:
        def __init__(self) -> None:
            self.task_status = TaskStatus(task_id="tid")

        def run(self):
            return _DummyContainer()

    def fake_upsert_task(status: TaskStatus):
        return

    def fake_popen(cmd, **kwargs):
        spawned["cmd"] = cmd
        spawned["kwargs"] = kwargs

        class _P:
            pid = 123

        return _P()

    monkeypatch.setattr(task_service_module.TaskManager, "upsert_task", fake_upsert_task)
    monkeypatch.setattr(task_service_module.subprocess, "Popen", fake_popen)

    async def _consume_once():
        agen = TaskService.run_task(_DummyRunner(), timeout=1, wait=False)
        status = await anext(agen)
        assert status.sub_status == "running-background"

    asyncio.run(_consume_once())

    cmd = spawned.get("cmd")
    assert isinstance(cmd, list)
    assert "monitor" in cmd
