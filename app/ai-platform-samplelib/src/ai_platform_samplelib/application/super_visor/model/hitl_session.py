from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


HitlSessionStatus = Literal["paused", "completed", "cancelled"]


class HitlSession(BaseModel):
    session_id: str
    status: HitlSessionStatus = "paused"

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    original_request: str
    # SV実行全体の相関ID（pause/resumeで維持する）
    trace_id: Optional[str] = None
    source_dirs: List[str] = Field(default_factory=list)

    tasks: List[str]
    next_task_index: int = 0

    # Execution results (append-only)
    results: List[Dict[str, Any]] = Field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def save_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.touch()
        path.write_text(self.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load_json(cls, path: Path) -> "HitlSession":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
