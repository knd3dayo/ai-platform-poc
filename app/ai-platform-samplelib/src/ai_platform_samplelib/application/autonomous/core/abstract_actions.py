from typing import Callable, Generator
from pathlib import Path

from abc import ABC, abstractmethod

from pathlib import Path

# 内部パッケージのインポート
from ..core.coding_agent_runner import CodingAgentRunner
from ..model.models import TaskStatus, ComposeConfig

class AbstractActions(ABC):
    @abstractmethod
    def after_start_task_action(self, tid: str) -> None:
        pass

    @abstractmethod
    def after_start_detach_task_action(self, tid: str) -> None:
        pass

    @abstractmethod
    async def progress_action(self, tid: str) -> TaskStatus:
        pass

    @abstractmethod
    def after_complete_action(
            self, runner: CodingAgentRunner, dest: Path) -> None:
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
    def before_pull_action(self, runner: CodingAgentRunner) -> None:
        pass
    @abstractmethod
    def pull_progress_action(self, func: Callable, dest: Path):
        pass

    @abstractmethod
    def prune_progress_action(self, generator: Generator[str, None, None]):
        pass