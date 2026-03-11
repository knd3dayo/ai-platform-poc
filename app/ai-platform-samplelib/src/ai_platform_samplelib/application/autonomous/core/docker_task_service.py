import asyncio
import subprocess
import sys
import os
from pathlib import Path
from typing import Optional, AsyncGenerator, Generator
import signal


from python_on_whales import docker as whales, Container


from ai_platform_samplelib.util.logging import get_application_logger

logger = get_application_logger()

# 内部パッケージのインポート
from .docker_coding_agent_runner import CodingAgentRunner
from ..model.models import TaskStatus
from .abstract_actions import AbstractActions

# --- Logic Layer: Typerに依存しないサービス ---
class TaskService:

    def __init__(self):
        self.runner: Optional[CodingAgentRunner] = None
        self.container: Optional[Container] = None

    def _spawn_detached_monitor(self, task_id: str, timeout: int) -> None:
        """wait=False の場合でも tasks_db.json が自動更新されるよう、別プロセスで monitor を起動する。"""
        if os.getenv("AI_PLATFORM_DISABLE_DETACH_MONITOR") == "1":
            return

        # timeout に少し余裕を持たせる（ログ保存・docker の状態反映の遅延吸収）
        max_seconds = max(int(timeout) + 60, 120)
        interval = float(os.getenv("AI_PLATFORM_DETACH_MONITOR_INTERVAL", "2.0"))

        cmd = [
            sys.executable,
            "-m",
            "ai_platform_samplelib.application.autonomous.cli.docker_main",
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

    @classmethod
    def print_confg(cls, container: Container) -> None:
        """Container の設定をデバッグ出力する（ENVは秘匿して出す）。"""
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
                    key, _value = item.split("=", 1)
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
    
    async def monitor(self, timeout: int) -> AsyncGenerator[TaskStatus, None]:
        if not self.container or not self.runner:
            return
        async for status in TaskService.monitor_container(self.container, self.runner, timeout):
            yield status

    @classmethod
    async def monitor_container(cls, container: Container, runner: CodingAgentRunner, timeout: int) -> AsyncGenerator[TaskStatus, None]:
        # debug用: container設定/引数は秘匿情報(ENV)を含みうるため、デフォルトでは出さない。
        if os.getenv("AI_PLATFORM_DEBUG_CONTAINER") == "1":
            cls.print_confg(container)
        try:
            loop = asyncio.get_running_loop()
            start_time = loop.time()
            while True:
                # reload() で最新の状態（state）を同期
                container.reload()
                # debug用
                # print(f"Monitoring container {container.id[:12]}: status={container.state.status}, elapsed={int(asyncio.get_event_loop().time() - start_time)}s")
                # whales のコンテナ状態チェック
                if container.state.status == 'exited':
                    break
                
                if (loop.time() - start_time) > timeout:
                    container.kill()
                    task  = runner.task_status
                    if task:
                        task.timeouted(timeout)
                    if task:
                        yield task
                    return
                await asyncio.sleep(1)

            # 終了コードの取得
            exit_code = container.state.exit_code
            
            # ログ取得 (whales では直接 logs() が呼べ、文字列で返ります)
            out_logs = container.logs()
            
            artifacts = [str(f.relative_to(runner.workspace)) for f in runner.workspace.glob("**/*") if f.is_file()]
            task  = runner.task_status
            if task:
                if exit_code == 0:
                    task.completed()
                else:
                    task.failed()
                task.stdout = out_logs
                task.artifacts = artifacts
                yield task
 
        except Exception as e:
            task  = runner.task_status
            if task:
                task.failed()
                task.stderr = f"Monitor Error: {str(e)}"
                yield task
        finally:
            # 既に remove=True で起動しているが、念のため
            try: container.remove(force=True)
            except: pass

    @classmethod
    def prune_containers(cls, compose_service_name: str) -> Generator[str, None, None]:
        """掃除ロジック"""
        containers = whales.container.list(filters={"label": f"managed_by={compose_service_name}"})
        for c in containers:
            c.remove(force=True)
            yield f"Removed container {c.id[:12]}"

    def cancel_task(self, task: TaskStatus) -> None:
        if task.status != "running" or not task.container_id:
            return
        whales.container.kill(task.container_id)

    def get_runner_status(self) -> TaskStatus:
        if self.runner:
            return self.runner.task_status
        raise RuntimeError("Runner not initialized")

    async def prepare(self,
        prompt: str,
        sources: Optional[list[Path]],
        task_id: Optional[str] ,
    ):
        params = {
            "prompt": prompt,
            "task_id": task_id,
        }
        if sources:
            params["source_paths"] = sources

        self.runner = await CodingAgentRunner.create_runner(**params)
        self.container = self.runner.run()
        # container_id が無いと logs/状態取得ができず、running のまま固まるため必ず保存する
        self.runner.task_status.container_id = getattr(self.container, "id", None)

    @classmethod
    async def run(
        cls,
        actions: AbstractActions,
        prompt: str,
        sources: Optional[list[Path]] = None,
        task_id: Optional[str] = None,
        timeout: int = 300,
        wait: bool = True,
    ) -> None:
        """CLI/呼び出し層向け: Runner作成〜実行までをまとめる。"""
        # 循環import回避のため遅延import
        from .task_manager import TaskManager

        # CLI はコマンドごとに別プロセスで起動されるため、永続ストアから都度復元する。
        TaskManager.load_tasks()

        normalized_sources: Optional[list[Path]] = None
        if sources:
            normalized_sources = [Path(p) for p in sources]

        runner = await CodingAgentRunner.create_runner(
            prompt=prompt,
            task_id=task_id,
            source_paths=normalized_sources,
        )

        async for status in cls.run_task(runner, timeout=timeout, wait=wait):
            if status.sub_status in ("starting", "running-foreground"):
                actions.after_start_task_action(status.task_id)
            elif status.sub_status == "running-background":
                actions.after_start_detach_task_action(status.task_id)
                return
            elif status.sub_status == "completed":
                actions.after_complete_action(runner)
                return

            await actions.progress_action(status.task_id)

    @classmethod
    async def run_task(
        cls,
        runner: CodingAgentRunner,
        timeout: int = 300,
        wait: bool = True,
    ) -> AsyncGenerator[TaskStatus, None]:
        """Runnerを実行し TaskStatus を逐次返す（wait=False は起動だけして終了）。"""
        # 循環import回避のため遅延import
        from .task_manager import TaskManager

        container = runner.run()
        runner.task_status.container_id = getattr(container, "id", None)

        task_status = runner.task_status
        if wait:
            task_status.starting_foregrond()
        else:
            task_status.starting_background()
        TaskManager.upsert_task(task_status)

        if not wait:
            # 呼び出し側が最初の yield で抜けても monitor を確実に起動する
            cls()._spawn_detached_monitor(task_status.task_id, timeout)
            yield task_status
            return

        # wait=True の場合は、開始状態を返した後にコンテナ終了を待って最終状態を返す
        yield task_status
        async for final_status in cls.monitor_container(container, runner, timeout):
            if final_status:
                TaskManager.upsert_task(final_status)
                yield final_status


