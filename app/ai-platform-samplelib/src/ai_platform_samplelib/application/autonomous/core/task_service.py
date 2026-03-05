import asyncio
from pathlib import Path
from typing import Optional, AsyncGenerator, Generator
import shutil
import signal

import shutil
from pathlib import Path
from python_on_whales import docker as whales, Container

# 内部パッケージのインポート
from ..core.runner import ComposeRunner
from ..model.models import ComposeConfig, TaskStatus
from ..core.task_manager import TaskManager

# --- Logic Layer: Typerに依存しないサービス ---
class TaskService:
    def __init__(self):
        pass

    async def run_task(self, prompt: str, src_path: Optional[Path], task_id: Optional[str],
                       timeout: int, dest: Path, wait: bool) -> AsyncGenerator[TaskStatus, None]:
        """タスクの開始、監視、完了後の同期までを一括管理"""
        config = ComposeConfig.from_env()
        params = {
            "background_tasks": None,
            "compose_config": config,
            "prompt": prompt,
            "task_id": task_id,
            "timeout": timeout,
        }
        if src_path and src_path.exists():
            params["source_path"] = src_path

        tid = await ComposeRunner.create_and_run(**params)
        task_status = TaskManager.get_task(tid)
        if task_status is None:
            raise RuntimeError(f"Task {tid} not found after starting in detach mode")
        
        task_status.sub_status = "starting"
        TaskManager.upsert_task(tid, task_status)
        yield task_status
        # self.actions.after_start_task_action(tid)

        if wait:
            task_status.sub_status = "running-foreground"
            TaskManager.upsert_task(tid, task_status)
        else:
            # self.actions.after_start_detach_task_action(tid)
            task_status.sub_status = "running-background"
            TaskManager.upsert_task(tid, task_status)
            yield task_status
            return

        async for status in self.progress_action(tid):
            yield status

        
    async def progress_action(self, tid: str) -> AsyncGenerator[TaskStatus, None]:

            loop = asyncio.get_running_loop()
            stop_event = asyncio.Event()
            def handle_interrupt(): stop_event.set()
            try:

                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.add_signal_handler(sig, handle_interrupt)

                while not stop_event.is_set():
                    status_data = await ComposeRunner.get_status(tid, tail=1000)
                    yield status_data
                    # 終了判定
                    if status_data.status not in ["running", "pending"]:
                        break
                    
                    await asyncio.sleep(1.5)
                
                # 最終状態を一度取得してから終了
                status_data = await ComposeRunner.get_status(tid, tail=1000)
                yield status_data
                return

            finally:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.remove_signal_handler(sig)


    def list_tasks(self) -> list[TaskStatus]:
        """タスクの一覧表示"""
        TaskManager.load_tasks()
        tasks = TaskManager.get_all_tasks()
        if not tasks:
            # self.actions.after_task_not_found_action()
            return []
        
        table = [[tid, t.status, t.created_at.strftime("%Y-%m-%d %H:%M")] 
                 for tid, t in tasks.items()]
        return list(tasks.values())

    async def show_status(self, task_id: str, tail: int) -> TaskStatus:
        """ステータスとログの表示（async版に統一）"""
        data = await ComposeRunner.get_status(task_id, tail=tail)
        return data
    
    async def cancel_task(self, task_id: str):
        """タスクのキャンセル（async版に統一）"""
        await ComposeRunner.cancel_task(task_id)
        TaskManager.remove_task(task_id)
        # self.actions.after_cancel_action(task_id)

    def pull_artifacts(self, task_id: str, dest: Path):
        """成果物の同期ロジックを一本化"""
        runner = ComposeRunner(compose_config=ComposeConfig.from_env(), task_id=task_id)
        if not runner.task_dir.exists():
            raise FileNotFoundError(f"Task directory for {task_id} not found")
        shutil.copytree(runner.task_dir, dest, dirs_exist_ok=True)

    def prune_containers(self) -> Generator[str, None, None]:
        """掃除ロジック"""
        compose_config = ComposeConfig.from_env()
        containers = whales.container.list(filters={"label": f"managed_by={compose_config.service_name}"})
        for c in containers:
            c.remove(force=True)
            yield f"Removed container {c.id[:12]}"
