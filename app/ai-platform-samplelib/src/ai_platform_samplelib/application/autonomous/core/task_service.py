"""Task service entrypoint.

This module provides a stable import path for the task service.
Today it re-exports the Docker-based implementation.
In the future, this can become an abstract façade that selects between
Docker and subprocess-based executors.
"""

from __future__ import annotations

import os
import subprocess

from .docker_coding_agent_runner import CodingAgentRunner
from .task_manager import TaskManager
from .subprocess_coding_agent_runner import SubprocessCodingAgentRunner


def _select_task_service_class():
    """Select TaskService implementation.

    The long-term intent is to make TaskManager independent of the execution backend
    (Docker containers vs local subprocess). For now we only ship the Docker backend.
    """

    backend = (os.getenv("AI_PLATFORM_TASK_BACKEND") or "docker").strip().lower()
    if backend in ("docker", "compose"):
        from .docker_task_service import TaskService as DockerTaskService

        return DockerTaskService

    if backend in ("subprocess", "process"):
        from .subprocess_task_service import TaskService as SubprocessTaskService

        return SubprocessTaskService

    raise ValueError(f"Unknown AI_PLATFORM_TASK_BACKEND: {backend}")


# Stable export name expected by callers/tests.
TaskService = _select_task_service_class()

__all__ = [
    "TaskService",
    "TaskManager",
    "CodingAgentRunner",
    "SubprocessCodingAgentRunner",
    "subprocess",
]
