import asyncio
from pathlib import Path
from contextlib import contextmanager

from abc import ABC, abstractmethod

from pathlib import Path

# 内部パッケージのインポート
from ..core.runner import ComposeRunner
from ..model.models import TaskStatus, ComposeConfig

class AbstractActions(ABC):
    @abstractmethod
    def after_start_task_action(self, tid: str) -> None:
        pass

    @abstractmethod
    def after_start_detach_task_action(self, tid: str) -> None:
        pass

    @abstractmethod
    async def progress_action(
            self, tid: str, loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event, 
            last_line_count: int, last_stderr_count: int) -> TaskStatus:
        pass

    @abstractmethod
    def after_complete_action(
            self, tid: str, config: ComposeConfig, dest: Path) -> None:
        pass
    @abstractmethod
    def after_task_not_found_action(self) -> None:
        pass
    @abstractmethod
    def after_list_action(self, table: list) -> None:
        pass
    @abstractmethod
    def after_cancel_action(self, task_id: str) -> None:
        pass
    @abstractmethod
    def after_get_status_action(self, task_id: str, status_data: TaskStatus) -> None:
        pass
    @abstractmethod
    def before_pull_action(self, runner: ComposeRunner) -> None:
        pass
    @abstractmethod
    @contextmanager
    def pull_progress_action(self, runner: ComposeRunner, dest: Path):
        yield

    @abstractmethod
    @contextmanager
    def prune_progress_action(self):
        yield 