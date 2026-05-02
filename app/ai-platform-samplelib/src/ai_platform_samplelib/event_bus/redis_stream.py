from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple

from pydantic import BaseModel, Field

from autonomous_agent_util.model.models import TaskStatus
from ai_platform_samplelib.event_bus.task_status import TaskStatusEvent, TaskStatusEventBus


class RedisClient(Protocol):
    def xadd(
        self,
        name: str,
        fields: Dict[str, str],
        id: str = "*",
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> str: ...

    def xread(
        self,
        streams: Dict[str, str],
        count: int | None = None,
        block: int | None = None,
    ) -> List[Tuple[str, List[Tuple[str, Dict[str, str]]]]]: ...


class RedisStreamSettings(BaseModel):
    url: str = Field(default="redis://localhost:6379/0")
    stream: str = Field(default="sv.task_status")
    maxlen: int | None = Field(default=10_000)
    approximate_trim: bool = Field(default=True)
    socket_timeout_sec: float | None = Field(default=5.0)
    socket_connect_timeout_sec: float | None = Field(default=5.0)

    @classmethod
    def load_from_env(cls) -> "RedisStreamSettings":
        in_container = os.path.exists("/.dockerenv")

        # Prefer explicit override first.
        url = (os.getenv("SV_EVENT_BUS_REDIS_URL") or "").strip()
        if not url:
            # Container-aware URLs (similar intent to llm_base_url_in_container)
            if in_container:
                url = (
                    (os.getenv("SV_EVENT_BUS_REDIS_URL_IN_CONTAINER") or "").strip()
                    or (os.getenv("SV_REDIS_URL_IN_CONTAINER") or "").strip()
                )
            else:
                url = (
                    (os.getenv("SV_EVENT_BUS_REDIS_URL_IN_HOST") or "").strip()
                    or (os.getenv("SV_REDIS_URL_IN_HOST") or "").strip()
                )

        if not url:
            url = (
                (os.getenv("SV_REDIS_URL") or "").strip()
                or (os.getenv("REDIS_URL") or "").strip()
                or "redis://localhost:6379/0"
            )

        stream = os.getenv("SV_EVENT_BUS_REDIS_STREAM") or os.getenv("SV_REDIS_STREAM") or "sv.task_status"

        maxlen_raw = (os.getenv("SV_EVENT_BUS_REDIS_STREAM_MAXLEN") or "").strip()
        maxlen: int | None
        if not maxlen_raw:
            maxlen = 10_000
        else:
            maxlen = None if maxlen_raw.lower() in {"none", "null", "0"} else int(maxlen_raw)

        approx = (os.getenv("SV_EVENT_BUS_REDIS_STREAM_APPROX") or "true").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }

        return cls(url=url, stream=stream, maxlen=maxlen, approximate_trim=approx)


def _create_redis_client(settings: RedisStreamSettings) -> RedisClient:
    try:
        import redis  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "redis EventBus を使うには Python パッケージ 'redis' が必要です。"
            " 依存関係に redis を追加してください。"
        ) from e

    return redis.Redis.from_url(  # type: ignore
        settings.url,
        decode_responses=True,
        socket_timeout=settings.socket_timeout_sec,
        socket_connect_timeout=settings.socket_connect_timeout_sec,
        health_check_interval=30,
    )


class RedisStreamEventBus(TaskStatusEventBus):
    """Redis Streams を使った TaskStatus の逐次通知。

    - publish: `XADD <stream> ...` に JSON を格納
    - consume: `xread()` で last_id 以降を読む

    PoC での「非同期連携基盤へ Push」を最小構成で実現する目的。
    """

    def __init__(self, *, settings: RedisStreamSettings | None = None, redis_client: RedisClient | None = None) -> None:
        self._settings = settings or RedisStreamSettings.load_from_env()
        self._redis: RedisClient = redis_client or _create_redis_client(self._settings)

    @property
    def settings(self) -> RedisStreamSettings:
        return self._settings

    def publish_task_status(self, status: TaskStatus, *, attributes: Optional[Dict[str, Any]] = None) -> None:
        ev = TaskStatusEvent(task_status=status, attributes=attributes or {})
        payload = json.dumps(ev.model_dump(mode="json"), ensure_ascii=False)

        fields: Dict[str, str] = {
            "event_id": ev.event_id,
            "event_type": ev.event_type,
            "occurred_at": str(ev.occurred_at),
            "task_id": status.task_id,
            "trace_id": statustrace_id or "",
            "payload": payload,
        }

        self._redis.xadd(
            self._settings.stream,
            fields,
            maxlen=self._settings.maxlen,
            approximate=self._settings.approximate_trim,
        )


class RedisStreamConsumer:
    def __init__(
        self,
        *,
        settings: RedisStreamSettings | None = None,
        redis_client: RedisClient | None = None,
        last_id: str = "0-0",
    ) -> None:
        self._settings = settings or RedisStreamSettings.load_from_env()
        self._redis: RedisClient = redis_client or _create_redis_client(self._settings)
        self._last_id = last_id

    @property
    def last_id(self) -> str:
        return self._last_id

    def read(
        self,
        *,
        count: int = 100,
        block_ms: int | None = 0,
    ) -> List[TaskStatusEvent]:
        """last_id 以降を読み取り、last_id を進める。"""

        # Redis Streams の XREAD は `BLOCK 0` が「無限待ち」になる。
        # このユーティリティでは block_ms=0 を「ブロックしない（BLOCK指定なし）」として扱う。
        if block_ms is None or block_ms <= 0:
            block = None
        else:
            block = int(block_ms)
        resp = self._redis.xread({self._settings.stream: self._last_id}, count=count, block=block)

        events: List[TaskStatusEvent] = []
        for _stream_name, items in resp or []:
            for msg_id, fields in items:
                self._last_id = msg_id
                ev = _parse_task_status_event(fields)
                if ev is not None:
                    events.append(ev)
        return events

    def iter_events(
        self,
        *,
        count: int = 100,
        block_ms: int | None = 1_000,
    ) -> Iterable[TaskStatusEvent]:
        while True:
            for ev in self.read(count=count, block_ms=block_ms):
                yield ev


def _parse_task_status_event(fields: Dict[str, str]) -> TaskStatusEvent | None:
    payload = fields.get("payload")
    if not payload:
        return None
    try:
        data = json.loads(payload)
        return TaskStatusEvent.model_validate(data)
    except Exception:
        return None
