import asyncio
import pathlib
import tempfile
from datetime import datetime
import os
from pathlib import Path
from typing import Optional, AsyncGenerator, Generator, Union
import shutil
import signal

from fastapi import UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from python_on_whales import docker as whales, Container

from ..model.models import TaskStatus, ComposeConfig, CodingAgentConfig
from .utils import ExecutorUtil
from .task_manager import TaskManager

from ai_platform_samplelib.util.logging import get_application_logger

logger = get_application_logger()

# 内部パッケージのインポート
from ..core.coding_agent_runner import CodingAgentRunner
from ..model.models import ComposeConfig, TaskStatus, CodingAgentConfig
from ..core.task_manager import TaskManager

# --- Logic Layer: Typerに依存しないサービス ---
class TaskService:
    def __init__(self):
        pass

    @classmethod
    async def monitor_container(cls, container: Container, runner: CodingAgentRunner, timeout: int):
        # debug用: container設定/引数は秘匿情報(ENV)を含みうるため、デフォルトでは出さない。
        if os.getenv("AI_PLATFORM_DEBUG_CONTAINER") == "1":
            try:
                cfg = getattr(container, "config", None)
                args = getattr(container, "args", None)

                safe_env = None
                env_list = getattr(cfg, "env", None) if cfg is not None else None
                if isinstance(env_list, list):
                    safe_env = []
                    for item in env_list:
                        if not isinstance(item, str) or "=" not in item:
                            safe_env.append(item)
                            continue
                        key, value = item.split("=", 1)
                        upper = key.upper()
                        if any(k in upper for k in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                            safe_env.append(f"{key}=***")
                        else:
                            safe_env.append(item)

                logger.debug(
                    "container.debug id=%s image=%s cmd=%s entrypoint=%s env=%s",
                    getattr(container, "id", None),
                    getattr(cfg, "image", None) if cfg is not None else None,
                    getattr(cfg, "cmd", None) if cfg is not None else None,
                    getattr(cfg, "entrypoint", None) if cfg is not None else None,
                    safe_env,
                )
                logger.debug("container.args=%s", args)
            except Exception:
                # デバッグログの失敗で本処理を落とさない
                pass
        try:
            start_time = asyncio.get_event_loop().time()
            while True:
                # reload() で最新の状態（state）を同期
                container.reload()
                # debug用
                # print(f"Monitoring container {container.id[:12]}: status={container.state.status}, elapsed={int(asyncio.get_event_loop().time() - start_time)}s")
                # whales のコンテナ状態チェック
                if container.state.status == 'exited':
                    break
                
                if (asyncio.get_event_loop().time() - start_time) > timeout:
                    container.kill()
                    task = TaskManager.get_task(runner.task_id)
                    if task:
                        TaskManager.upsert_task(runner.task_id, TaskStatus(
                            task_id=runner.task_id,
                            status="failed",
                            created_at=task.created_at,
                            container_id=container.id,
                            stderr=f"Task timed out after {timeout} seconds"
                        ))
                    return
                await asyncio.sleep(1)

            # 終了コードの取得
            exit_code = container.state.exit_code
            
            # ログ取得 (whales では直接 logs() が呼べ、文字列で返ります)
            out_logs = container.logs()
            
            artifacts = [str(f.relative_to(runner.workspace)) for f in runner.workspace.glob("**/*") if f.is_file()]
            task = TaskManager.get_task(runner.task_id)
            if task:
                task.status = "completed" if exit_code == 0 else "failed"
                task.stdout = out_logs
                task.artifacts = artifacts
                TaskManager.upsert_task(runner.task_id, task)

        except Exception as e:
            task = TaskManager.get_task(runner.task_id)
            if task:
                TaskManager.upsert_task(runner.task_id, TaskStatus(
                    task_id=runner.task_id,
                    status="failed",
                    created_at=task.created_at,
                    container_id=container.id,
                    stderr=f"Monitor Error: {str(e)}"
                ))
        finally:
            # 既に remove=True で起動しているが、念のため
            try: container.remove(force=True)
            except: pass


    @classmethod
    async def run_task(cls, runner: CodingAgentRunner,
                       timeout: int, dest: Path, wait: bool) -> AsyncGenerator[TaskStatus, None]:
        """タスクの開始、監視、完了後の同期までを一括管理"""
        tid = runner.task_id
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

        async for status in cls.progress_action(tid):
            yield status

    @classmethod
    async def progress_action(cls, tid: str) -> AsyncGenerator[TaskStatus, None]:

            loop = asyncio.get_running_loop()
            stop_event = asyncio.Event()
            def handle_interrupt(): stop_event.set()
            try:

                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.add_signal_handler(sig, handle_interrupt)

                while not stop_event.is_set():
                    status_data = await TaskManager.get_status(tid, tail=1000)
                    yield status_data
                    # 終了判定
                    if status_data.status not in ["running", "pending"]:
                        break
                    
                    await asyncio.sleep(1.5)
                
                # 最終状態を一度取得してから終了
                status_data = await TaskManager.get_status(tid, tail=1000)
                yield status_data
                return

            finally:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.remove_signal_handler(sig)

    @classmethod
    async def download_artifacts_zip(cls, task_id: str):
        """タスクの作業用ディレクトリをZIP化して返します。"""
        task_dir =  TaskManager.get_projects_root() / task_id
        if not task_dir.exists() or not task_dir.is_dir():
            raise HTTPException(status_code=404, detail="Artifacts directory not found")

        # 実行中は結果が不安定になり得るので、原則 completed のみ許可
        task = TaskManager.get_task(task_id)
        if task and task.status not in ("completed", "failed"):
            raise HTTPException(status_code=409, detail=f"Task is {task.status}, artifacts may not be ready for download")

        # 一時ファイルへZIPを作成し、FileResponseで返す（レスポンス完了後に削除）
        tmp = tempfile.NamedTemporaryFile(prefix=f"{task_id}-", suffix=".zip", delete=False)
        tmp_path = pathlib.Path(tmp.name)
        tmp.close()

        try:
            ExecutorUtil.make_zip_from_dir(task_dir, tmp_path)
        except Exception:
            ExecutorUtil.cleanup_file(str(tmp_path))
            raise

        filename = f"{task_id}.zip"
        return FileResponse(
            path=str(tmp_path),
            media_type="application/zip",
            filename=filename,
            background=BackgroundTask(ExecutorUtil.cleanup_file, str(tmp_path)),
        )

    @classmethod
    def pull_artifacts(cls, task_id: str, dest: Path):
        """成果物の同期ロジックを一本化"""
        runner = CodingAgentRunner(compose_config=ComposeConfig.from_env(), coding_agent_config=CodingAgentConfig.from_env(), task_id=task_id)
        if not runner.workspace.exists():
            raise FileNotFoundError(f"Task directory for {task_id} not found")
        shutil.copytree(runner.workspace, dest, dirs_exist_ok=True)
