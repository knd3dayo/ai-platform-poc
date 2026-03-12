import asyncio
from pathlib import Path
from typing import AsyncGenerator, Optional

import pytest

from ai_platform_samplelib.application.autonomous.core.abstract_agent_runner import AbstractAgentRunner
from ai_platform_samplelib.application.autonomous.core.abstract_actions import AbstractActions
from ai_platform_samplelib.application.autonomous.core.abstract_task_service import AbstractTaskService
from ai_platform_samplelib.application.autonomous.core.task_manager import TaskManager
from ai_platform_samplelib.application.autonomous.model.models import TaskStatus


class _DummyActions(AbstractActions):
    def __init__(self) -> None:
        self.started: list[str] = []
        self.started_detach: list[str] = []
        self.completed: list[str] = []

    def after_start_task_action(self, tid: str) -> None:
        self.started.append(tid)

    def after_start_detach_task_action(self, tid: str) -> None:
        self.started_detach.append(tid)

    async def progress_action(self, tid: str) -> TaskStatus:
        return TaskStatus(task_id=tid)

    def after_complete_action(self, runner) -> None:
        self.completed.append(runner.get_task_status().task_id)

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


class _DummyRunner(AbstractAgentRunner):
    def __init__(self, tid: str) -> None:
        self._status = TaskStatus.create(task_id=tid)
        self._ws = Path("/tmp")

    def start(self):
        return {"started": True}

    def get_task_status(self) -> TaskStatus:
        return self._status

    def get_workspace_path(self) -> Path:
        return self._ws


class _DummyService(AbstractTaskService):
    def __init__(self) -> None:
        self._runner: Optional[_DummyRunner] = None
        self.spawned: list[tuple[str, int]] = []
        self.prepared: dict[str, object] = {}

    async def prepare(
        self,
        prompt: str,
        sources: Optional[list[Path]],
        task_id: Optional[str],
        workspace_path: Optional[Path] = None,
        extra_env: Optional[dict[str, str]] = None,
    ) -> None:
        self.prepared = {
            "prompt": prompt,
            "sources": sources,
            "task_id": task_id,
            "workspace_path": workspace_path,
            "extra_env": extra_env,
        }
        self._runner = _DummyRunner(task_id or "dummy")

    def start(self, *, wait: bool, timeout: int) -> TaskStatus:
        assert self._runner is not None
        self._runner.start()
        st = self._runner.get_task_status()
        if wait:
            st.starting_foregrond()
        else:
            st.starting_background()
        return st

    def get_agent_runner(self) -> AbstractAgentRunner:
        assert self._runner is not None
        return self._runner

    def spawn_detached_monitor(self, task_id: str, timeout: int) -> None:
        self.spawned.append((task_id, timeout))

    def cancel_task(self, task: TaskStatus) -> None:
        task.cancelled()

    async def monitor(self, timeout: int) -> AsyncGenerator[TaskStatus, None]:
        assert self._runner is not None
        st = self._runner.get_task_status()
        st.completed()
        yield st


def test_task_manager_wait_false_spawns_detached_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _DummyService()
    actions = _DummyActions()

    # Avoid touching filesystem-backed task storage.
    monkeypatch.setattr(TaskManager, "save_tasks", lambda: None)
    monkeypatch.setattr(TaskManager, "load_tasks", lambda: None)

    asyncio.run(
        TaskManager.run_task(
            task_service=service,
            actions=actions,
            prompt="hello",
            sources=None,
            task_id="tid",
            timeout=5,
            wait=False,
        )
    )

    assert actions.started_detach == ["tid"]
    assert service.spawned == [("tid", 5)]


def test_task_manager_wait_true_consumes_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _DummyService()
    actions = _DummyActions()

    monkeypatch.setattr(TaskManager, "save_tasks", lambda: None)
    monkeypatch.setattr(TaskManager, "load_tasks", lambda: None)

    # Make progress_action stop quickly.
    async def _done(_tid: str) -> AsyncGenerator[TaskStatus, None]:
        st = TaskStatus(task_id=_tid, status="exited", sub_status="completed")
        yield st

    monkeypatch.setattr(TaskManager, "progress_action", classmethod(lambda cls, tid: _done(tid)))

    asyncio.run(
        TaskManager.run_task(
            task_service=service,
            actions=actions,
            prompt="hello",
            sources=None,
            task_id="tid2",
            timeout=5,
            wait=True,
        )
    )

    assert actions.started == ["tid2"]
