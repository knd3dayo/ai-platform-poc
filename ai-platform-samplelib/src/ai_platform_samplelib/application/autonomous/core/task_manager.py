from typing import Optional, ClassVar
import os, pathlib

from .model import TaskStatus

# --- 設定：環境に合わせて調整 ---
HOST_PROJECTS_ROOT = os.getenv("HOST_PROJECTS_ROOT", "/home/user/ai-platform/data/projects")
TASKS_FILE = pathlib.Path(HOST_PROJECTS_ROOT) / "tasks_db.json"


class TaskManager:
    """タスク管理クラス（シングルトン）"""
    tasks: ClassVar[dict[str, TaskStatus]] = {}
    
    @classmethod
    def get_projects_root(cls) -> pathlib.Path:
        return pathlib.Path(HOST_PROJECTS_ROOT)
    
    @classmethod
    def get_tasks_file_path(cls) -> pathlib.Path:
        return TASKS_FILE
    
    @classmethod
    def get_task(cls, task_id: str) -> Optional[TaskStatus]:
        return cls.tasks.get(task_id)
    
    @classmethod
    def upsert_task(cls, task_id: str, status: TaskStatus):
        cls.tasks[task_id] = status

    @classmethod
    def get_all_tasks(cls) -> dict[str, TaskStatus]:
        return cls.tasks
    
    @classmethod
    def remove_task(cls, task_id: str):
        if task_id in cls.tasks:
            del cls.tasks[task_id]