from __future__ import annotations

import os
import pathlib
import shlex
import sys
import uuid
from dataclasses import dataclass
from typing import Optional, Union

from ..model.models import CodingAgentConfig, TaskStatus
from .utils import ExecutorUtil


@dataclass
class SubprocessRunResult:
    pid: int


class SubprocessCodingAgentRunner:
    """Runner that executes the agent locally via Python subprocess.

    It prepares a workspace (same semantics as Docker runner), then starts a
    detached entrypoint process that runs the actual agent command and writes
    stdout/stderr/exit code to files in the workspace.
    """

    def __init__(
        self,
        task_id: Optional[str] = None,
        workspace_path: Optional[Union[str, pathlib.Path]] = None,
        command_base: Optional[str] = None,
    ) -> None:
        self.task_id = task_id or str(uuid.uuid4())
        cfg = CodingAgentConfig.from_env()

        if workspace_path is not None:
            self.workspace = pathlib.Path(workspace_path)
        else:
            self.workspace = pathlib.Path(cfg.workspace_root) / self.task_id
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.command_base = command_base or os.getenv(
            "AI_PLATFORM_SUBPROCESS_COMMAND", os.getenv("COMPOSE_COMMAND", "opencode run")
        )
        self.command: list[str] = shlex.split(self.command_base)

        self.task_status = TaskStatus.create(task_id=self.task_id)
        self.task_status.metadata["workspace_path"] = self.workspace.resolve().as_posix()
        self.task_status.metadata["backend"] = "subprocess"

        # Log/exit-code files
        self.stdout_file = self.workspace / "stdout.log"
        self.stderr_file = self.workspace / "stderr.log"
        self.exit_code_file = self.workspace / ".exit_code"

        self.task_status.metadata["stdout_path"] = self.stdout_file.as_posix()
        self.task_status.metadata["stderr_path"] = self.stderr_file.as_posix()
        self.task_status.metadata["exit_code_path"] = self.exit_code_file.as_posix()

    def prepare_workspace(
        self,
        initial_files: Optional[dict[str, str]] = None,
        source_paths: Optional[list[pathlib.Path]] = None,
    ) -> None:
        if initial_files:
            ExecutorUtil.add_data(initial_files, self.workspace)
        if source_paths:
            ExecutorUtil.add_files(source_paths, self.workspace)

    @classmethod
    async def create_runner(
        cls,
        prompt: str,
        task_id: Optional[str] = None,
        source_paths: Optional[list[pathlib.Path]] = None,
        workspace_path: Optional[Union[str, pathlib.Path]] = None,
        detach: bool = True,
        command_base: Optional[str] = None,
        **_kwargs,
    ) -> "SubprocessCodingAgentRunner":
        runner = cls(task_id=task_id, workspace_path=workspace_path, command_base=command_base)
        if prompt:
            runner.command = [*runner.command, prompt]
        runner.prepare_workspace(source_paths=source_paths)
        return runner

    def run(self) -> SubprocessRunResult:
        # Spawn entrypoint wrapper which will run the actual agent command.
        entrypoint_cmd = [
            sys.executable,
            "-m",
            "ai_platform_samplelib.application.autonomous.core.subprocess_entrypoint",
            "--workspace",
            self.workspace.as_posix(),
            "--exit-code-file",
            self.exit_code_file.as_posix(),
            "--stdout-file",
            self.stdout_file.as_posix(),
            "--stderr-file",
            self.stderr_file.as_posix(),
            "--",
            *self.command,
        ]

        import subprocess  # local import to keep module lightweight

        proc = subprocess.Popen(
            entrypoint_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        self.task_status.metadata["pid"] = int(proc.pid)
        return SubprocessRunResult(pid=int(proc.pid))
