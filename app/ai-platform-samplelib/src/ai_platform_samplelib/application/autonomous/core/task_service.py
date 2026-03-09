import asyncio
import subprocess
import sys
import os
import pathlib
import tempfile
from datetime import datetime
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
from ..core.abstract_actions import AbstractActions
# --- Logic Layer: Typerに依存しないサービス ---
class TaskService:
    @classmethod
    def _spawn_detached_monitor(cls, task_id: str, timeout: int) -> None:
        """wait=False の場合でも tasks_db.json が自動更新されるよう、別プロセスで monitor を起動する。"""
        if os.getenv("AI_PLATFORM_DISABLE_DETACH_MONITOR") == "1":
            return

        # timeout に少し余裕を持たせる（ログ保存・docker の状態反映の遅延吸収）
        max_seconds = max(int(timeout) + 60, 120)
        interval = float(os.getenv("AI_PLATFORM_DETACH_MONITOR_INTERVAL", "2.0"))

        cmd = [
            sys.executable,
            "-m",
            "ai_platform_samplelib.application.autonomous.cli.main",
            "monitor",
            task_id,
            "--interval",
            str(interval),
            "--max-seconds",
            str(max_seconds),
            "--quiet",
        ]

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )

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
                        task.timeouted(timeout)
                    return
                await asyncio.sleep(1)

            # 終了コードの取得
            exit_code = container.state.exit_code
            
            # ログ取得 (whales では直接 logs() が呼べ、文字列で返ります)
            out_logs = container.logs()
            
            artifacts = [str(f.relative_to(runner.workspace)) for f in runner.workspace.glob("**/*") if f.is_file()]
            task = TaskManager.get_task(runner.task_id)
            if task:
                if exit_code == 0:
                    task.completed()
                else:
                    task.failed()
                task.stdout = out_logs
                task.artifacts = artifacts
                TaskManager.upsert_task(task)

        except Exception as e:
            task = TaskManager.get_task(runner.task_id)
            if task:
                task.failed()
                task.stderr = f"Monitor Error: {str(e)}"
                TaskManager.upsert_task(task)
        finally:
            # 既に remove=True で起動しているが、念のため
            try: container.remove(force=True)
            except: pass

    @classmethod
    async def run(
            cls,
            actions: AbstractActions,
            prompt: str,
            sources: Optional[list[Path]],
            task_id: Optional[str] ,
            timeout: int = 300,
            wait: bool = True
    ):
        """新しいタスクを実行します。"""
        TaskManager.load_tasks()
        params = {
            "prompt": prompt,
            "task_id": task_id,
        }
        if sources:
            params["source_paths"] = sources

        runner = await CodingAgentRunner.create_runner(**params)
        async for status in TaskService.run_task(runner, timeout, wait):
            if status.sub_status == "starting":
                actions.after_start_task_action(status.task_id)
            elif status.sub_status == "running-background":
                actions.after_start_detach_task_action(status.task_id)
                break  # バックグラウンドで走らせる場合はここでループを抜ける
            elif status.status == "completed":
                actions.after_complete_action(runner)
                break  # 完了したらループを抜ける
            
            await actions.progress_action(status.task_id)    
        

    @classmethod
    async def run_task(cls, runner: CodingAgentRunner,
                       timeout: int, wait: bool) -> AsyncGenerator[TaskStatus, None]:
        """タスクの開始、監視、完了後の同期までを一括管理"""
        container = runner.run()
        # container_id が無いと logs/状態取得ができず、running のまま固まるため必ず保存する
        runner.task_status.container_id = getattr(container, "id", None)
        
        if wait:
            runner.task_status.starting_foregrond()
            TaskManager.upsert_task(runner.task_status)
            # wait=True の CLI 実行では monitor_container を同一イベントループ内で走らせて完了検知する
            asyncio.create_task(cls.monitor_container(container, runner, timeout))
            yield runner.task_status
        else:
            # self.actions.after_start_detach_task_action(tid)
            runner.task_status.starting_background()
            TaskManager.upsert_task(runner.task_status)
            # 呼び出し側が 1 回目の yield で break しても確実に起動するよう、yield 前に monitor を起動する
            cls._spawn_detached_monitor(runner.task_status.task_id, timeout)
            yield runner.task_status
            return

        async for status in cls.progress_action(runner.task_status.task_id):
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
