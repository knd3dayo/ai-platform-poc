from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path
from typing import Optional, AsyncGenerator

from ai_platform_samplelib.util.logging import get_application_logger

from ..model.models import TaskStatus
from .abstract_actions import AbstractActions
from .subprocess_coding_agent_runner import SubprocessCodingAgentRunner

logger = get_application_logger()


class TaskService:
    """Task service implementation for local subprocess backend."""

    def __init__(self) -> None:
        self.runner: Optional[SubprocessCodingAgentRunner] = None

    def _spawn_detached_monitor(self, task_id: str, timeout: int) -> None:
        # Reuse the existing monitor command, which calls TaskManager.get_status().
        # TaskManager.get_status() for subprocess backend can determine final outcome
        # via the exit_code file written by subprocess_entrypoint.
        if os.getenv("AI_PLATFORM_DISABLE_DETACH_MONITOR") == "1":
            return

        import subprocess
        import sys

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

    async def prepare(self, prompt: str, sources: Optional[list[Path]], task_id: Optional[str]):
        params = {"prompt": prompt, "task_id": task_id}
        if sources:
            params["source_paths"] = sources

        self.runner = await SubprocessCodingAgentRunner.create_runner(**params)

    def get_runner_status(self) -> TaskStatus:
        if self.runner:
            return self.runner.task_status
        raise RuntimeError("Runner not initialized")

    def cancel_task(self, task: TaskStatus) -> None:
        md = task.metadata or {}
        pid = md.get("pid")
        if isinstance(pid, int) and pid > 1:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                return

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
        from .task_manager import TaskManager

        TaskManager.load_tasks()
        normalized_sources: Optional[list[Path]] = None
        if sources:
            normalized_sources = [Path(p) for p in sources]

        task_service = cls()
        await task_service.prepare(prompt, normalized_sources, task_id)

        async for status in cls._run(task_service, timeout=timeout, wait=wait):
            if status.sub_status in ("starting", "running-foreground"):
                actions.after_start_task_action(status.task_id)
            elif status.sub_status == "running-background":
                actions.after_start_detach_task_action(status.task_id)
                return
            elif status.sub_status == "completed":
                if task_service.runner is not None:
                    actions.after_complete_action(task_service.runner)
                return

            await actions.progress_action(status.task_id)

    @classmethod
    async def _run(cls, task_service: "TaskService", timeout: int, wait: bool) -> AsyncGenerator[TaskStatus, None]:
        from .task_manager import TaskManager

        if task_service.runner is None:
            raise RuntimeError("Runner not initialized")

        result = task_service.runner.run()
        task_status = task_service.runner.task_status
        task_status.metadata["pid"] = result.pid

        if wait:
            task_status.starting_foregrond()
        else:
            task_status.starting_background()

        TaskManager.upsert_task(task_status)

        if not wait:
            task_service._spawn_detached_monitor(task_status.task_id, timeout)
            yield task_status
            return

        yield task_status

        # Wait for exit_code file to appear or timeout.
        loop = asyncio.get_running_loop()
        start = loop.time()
        exit_path = task_service.runner.exit_code_file

        while True:
            if exit_path.exists():
                try:
                    rc = int(exit_path.read_text(encoding="utf-8").strip())
                except Exception:
                    rc = 1

                if rc == 0:
                    task_status.completed()
                else:
                    task_status.failed()

                # Read full logs on completion.
                try:
                    task_status.stdout = task_service.runner.stdout_file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    task_status.stdout = task_status.stdout or ""
                try:
                    task_status.stderr = task_service.runner.stderr_file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    task_status.stderr = task_status.stderr or ""

                # Artifacts
                try:
                    artifacts = [
                        str(p.relative_to(task_service.runner.workspace).as_posix())
                        for p in task_service.runner.workspace.rglob("*")
                        if p.is_file()
                    ]
                    task_status.artifacts = artifacts
                except Exception:
                    pass

                TaskManager.upsert_task(task_status)
                yield task_status
                return

            if loop.time() - start > timeout:
                task_service.cancel_task(task_status)
                task_status.timeouted(timeout)
                TaskManager.upsert_task(task_status)
                yield task_status
                return

            await asyncio.sleep(1.0)
