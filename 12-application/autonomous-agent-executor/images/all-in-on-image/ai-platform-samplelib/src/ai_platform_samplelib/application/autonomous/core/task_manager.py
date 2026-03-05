from typing import Optional, ClassVar
import os, pathlib
import json

from ..model.models import TaskStatus

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
        cls.save_tasks()

    @classmethod
    def get_all_tasks(cls) -> dict[str, TaskStatus]:
        return cls.tasks
    
    @classmethod
    def remove_task(cls, task_id: str):
        if task_id in cls.tasks:
            del cls.tasks[task_id]
        cls.save_tasks()

    @classmethod
    def save_tasks(cls):
        """現在のタスク状態をファイルに保存する"""
        with open(TaskManager.get_tasks_file_path(), "w") as f:
            data = {k: v.model_dump(mode='json') for k, v in TaskManager.get_all_tasks().items()}
            json.dump(data, f, indent=2)

    @classmethod
    def load_tasks(cls):
        """ファイルからタスク状態を復元する"""
        if TaskManager.get_tasks_file_path().exists():
            with open(TaskManager.get_tasks_file_path(), "r") as f:
                data = json.load(f)
                for k, v in data.items():
                    cls.tasks[k] = TaskStatus(**v)
    