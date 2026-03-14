from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field

from autonomous_agent_util.model.models import TaskStatus


class TaskStatusEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = "task_status_updated"
    occurred_at: float = Field(default_factory=lambda: time.time())
    task_status: TaskStatus
    attributes: Dict[str, Any] = Field(default_factory=dict)


class TaskStatusEventBus(Protocol):
    def publish_task_status(self, status: TaskStatus, *, attributes: Optional[Dict[str, Any]] = None) -> None: ...


class NoopEventBus:
    def publish_task_status(self, status: TaskStatus, *, attributes: Optional[Dict[str, Any]] = None) -> None:
        return


class StdoutEventBus:
    """モック用: 標準出力へ JSON を出す。"""

    def publish_task_status(self, status: TaskStatus, *, attributes: Optional[Dict[str, Any]] = None) -> None:
        ev = TaskStatusEvent(task_status=status, attributes=attributes or {})
        # ensure_ascii=False で日本語が潰れないようにする
        print(json.dumps(ev.model_dump(mode="json"), ensure_ascii=False))


class InMemoryEventBus:
    """モック用: プロセス内メモリへ蓄積する（テスト/デバッグ用）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: List[TaskStatusEvent] = []

    def publish_task_status(self, status: TaskStatus, *, attributes: Optional[Dict[str, Any]] = None) -> None:
        ev = TaskStatusEvent(task_status=status, attributes=attributes or {})
        with self._lock:
            self._events.append(ev)

    def list_events(self) -> List[TaskStatusEvent]:
        with self._lock:
            return list(self._events)


_memory_bus: InMemoryEventBus | None = None


def get_in_memory_event_bus() -> InMemoryEventBus:
    global _memory_bus
    if _memory_bus is None:
        _memory_bus = InMemoryEventBus()
    return _memory_bus


def get_event_bus(event_bus_type: str | None = None) -> TaskStatusEventBus:
    """EventBus を取得する。

    Redis 等に依存しないモック実装を優先する。

    Args:
        event_bus_type: "noop" | "stdout" | "memory" | "redis"
            None の場合は環境変数 `SV_EVENT_BUS_TYPE` を参照する。
    """

    typ = (event_bus_type or os.getenv("SV_EVENT_BUS_TYPE") or "noop").strip().lower()

    if typ == "stdout":
        return StdoutEventBus()
    if typ == "memory":
        return get_in_memory_event_bus()
    if typ == "redis":
        from ai_platform_samplelib.event_bus.redis_stream import RedisStreamEventBus

        return RedisStreamEventBus()

    return NoopEventBus()
