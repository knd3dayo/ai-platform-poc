import asyncio
from pathlib import Path
from typing import Optional
import shutil
import signal

import shutil
from pathlib import Path
from python_on_whales import docker as whales

# 内部パッケージのインポート
from ..core.abstract_actions import AbstractActions
from ..core.runner import ComposeRunner
from ..model.models import ComposeConfig
from ..core.task_manager import TaskManager

# --- Logic Layer: Typerに依存しないサービス ---
class TaskService:
    def __init__(self, actions: AbstractActions):
        self.actions = actions
    
    async def run_task(self, prompt: str, src_path: Optional[Path], task_id: Optional[str],
                       timeout: int, dest: Path, detach: bool) -> None:
        """タスクの開始、監視、完了後の同期までを一括管理"""
        config = ComposeConfig.from_env()
        params = {
            "background_tasks": None,
            "compose_config": config,
            "prompt": prompt,
            "task_id": task_id,
            "timeout": timeout
        }
        if src_path and src_path.exists():
            params["source_path"] = src_path

        tid = await ComposeRunner.create_and_run(**params)
        TaskManager.save_tasks()
        self.actions.after_start_task_action(tid)

        if detach:
            self.actions.after_start_detach_task_action(tid)
            return

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        def handle_interrupt(): stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_interrupt)

        status_data = await self.actions.progress_action(tid, loop, stop_event, 0, 0)

        if status_data.status == "completed":
            self.actions.after_complete_action(tid, config, dest)

        TaskManager.save_tasks()

    def list_tasks(self):
        """タスクの一覧表示"""
        TaskManager.load_tasks()
        tasks = TaskManager.get_all_tasks()
        if not tasks:
            self.actions.after_task_not_found_action()
            return
        
        table = [[tid, t.status, t.created_at.strftime("%Y-%m-%d %H:%M")] 
                 for tid, t in tasks.items()]
        self.actions.after_list_action(table)

    async def show_status(self, task_id: str, tail: int):
        """ステータスとログの表示（async版に統一）"""
        data = await ComposeRunner.get_status(task_id, tail=tail)
        self.actions.after_get_status_action(task_id, data)

    async def cancel_task(self, task_id: str):
        """タスクのキャンセル（async版に統一）"""
        await ComposeRunner.cancel_task(task_id)
        TaskManager.remove_task(task_id)
        self.actions.after_cancel_action(task_id)

    def pull_artifacts(self, task_id: str, dest: Path):
        """成果物の同期ロジックを一本化"""
        runner = ComposeRunner(compose_config=ComposeConfig.from_env(), task_id=task_id)
        self.actions.before_pull_action(runner)
        with self.actions.pull_progress_action(runner, dest): 
            shutil.copytree(runner.task_dir, dest, dirs_exist_ok=True)

    def prune_containers(self):
        """掃除ロジック"""
        containers = whales.container.list(filters={"label": "managed_by=executor-service"})
        with self.actions.prune_progress_action():
            if not containers:
                return []
            for c in containers:
                c.remove(force=True)
            return containers
