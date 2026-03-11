from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import AsyncGenerator, Optional

from ai_platform_samplelib.util.logging import get_application_logger

from ...model.models import TaskStatus
from ..abstract_agent_runner import AbstractAgentRunner
from ..abstract_task_service import AbstractTaskService
from .subprocess_coding_agent_runner import SubprocessCodingAgentRunner

logger = get_application_logger()


class SubprocessTaskService(AbstractTaskService):
    """Task service implementation for local subprocess backend."""

    def __init__(self) -> None:
        self.runner: Optional[SubprocessCodingAgentRunner] = None

    async def prepare(
        self,
        prompt: str,
        sources: Optional[list[Path]],
        task_id: Optional[str],
        workspace_path: Optional[Path] = None,
    ) -> None:
        params: dict[str, object] = {"prompt": prompt, "task_id": task_id}
        if sources:
            params["source_paths"] = sources
        if workspace_path is not None:
            params["workspace_path"] = workspace_path

        self.runner = await SubprocessCodingAgentRunner.create_runner(**params)  # type: ignore[arg-type]

    def get_agent_runner(self) -> AbstractAgentRunner:
        if self.runner is None:
            raise RuntimeError("Runner not initialized")
        return self.runner

    def spawn_detached_monitor(self, task_id: str, timeout: int) -> None:
        if os.getenv("AI_PLATFORM_DISABLE_DETACH_MONITOR") == "1":
            return

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

    def cancel_task(self, task: TaskStatus) -> None:
        md = task.metadata if isinstance(task.metadata, dict) else {}
        pid = md.get("pid")
        if isinstance(pid, int) and pid > 1:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                return

    def start(self, *, wait: bool, timeout: int) -> TaskStatus:
        if self.runner is None:
            raise RuntimeError("Runner not initialized")

        run_result = self.runner.start()
        task_status = self.runner.get_task_status()
        task_status.metadata["pid"] = getattr(run_result, "pid", None)

        if wait:
            task_status.starting_foregrond()
        else:
            task_status.starting_background()

        return task_status

    async def monitor(self, timeout: int) -> AsyncGenerator[TaskStatus, None]:
        if self.runner is None:
            return

        loop = asyncio.get_running_loop()
        start = loop.time()

        exit_path = self.runner.exit_code_file
        while True:
            if exit_path.exists():
                try:
                    rc = int(exit_path.read_text(encoding="utf-8").strip())
                except Exception:
                    rc = 1

                task_status = self.runner.get_task_status()
                if rc == 0:
                    task_status.completed()
                else:
                    task_status.failed()

                try:
                    task_status.stdout = self.runner.stdout_file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    task_status.stdout = task_status.stdout or ""
                try:
                    task_status.stderr = self.runner.stderr_file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    task_status.stderr = task_status.stderr or ""

                try:
                    base = self.runner.get_workspace_path()
                    task_status.artifacts = [
                        str(p.relative_to(base).as_posix())
                        for p in base.rglob("*")
                        if p.is_file()
                    ]
                except Exception:
                    pass

                yield task_status
                return

            if loop.time() - start > timeout:
                task_status = self.runner.get_task_status()
                self.cancel_task(task_status)
                task_status.timeouted(timeout)
                yield task_status
                return

            await asyncio.sleep(1.0)
