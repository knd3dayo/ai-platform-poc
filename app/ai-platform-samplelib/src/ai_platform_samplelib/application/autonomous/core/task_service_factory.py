from __future__ import annotations

import os

from .abstract_task_service import AbstractTaskService
from .docker.docker_task_service import DockerTaskService
from .subprocess.subprocess_task_service import SubprocessTaskService


def select_task_service(backend: str | None = None) -> AbstractTaskService:
    b = (backend or os.getenv("AI_PLATFORM_TASK_BACKEND") or "docker").strip().lower()
    if b in ("docker", "compose"):
        return DockerTaskService()
    if b in ("subprocess", "process"):
        return SubprocessTaskService()
    raise ValueError(f"Unknown AI_PLATFORM_TASK_BACKEND: {b}")
