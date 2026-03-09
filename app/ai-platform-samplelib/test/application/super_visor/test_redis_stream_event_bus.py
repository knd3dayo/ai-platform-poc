import json

from ai_platform_samplelib.application.autonomous.model.models import TaskStatus
from ai_platform_samplelib.event_bus.redis_stream import (
    RedisStreamConsumer,
    RedisStreamEventBus,
    RedisStreamSettings,
)


class FakeRedis:
    def __init__(self) -> None:
        self._streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self._seq = 0

    def xadd(
        self,
        name: str,
        fields: dict[str, str],
        id: str = "*",
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> str:
        self._seq += 1
        msg_id = f"0-{self._seq}"
        self._streams.setdefault(name, []).append((msg_id, dict(fields)))
        if isinstance(maxlen, int) and maxlen > 0:
            self._streams[name] = self._streams[name][-maxlen:]
        return msg_id

    def xread(
        self,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
    ):
        # Minimal xread for a single stream.
        (name, last_id), *_ = list(streams.items())
        items = self._streams.get(name, [])

        def _gt(a: str, b: str) -> bool:
            # Fake IDs are "0-n".
            return int(a.split("-", 1)[1]) > int(b.split("-", 1)[1])

        filtered = [(mid, f) for mid, f in items if _gt(mid, last_id)]
        if isinstance(count, int):
            filtered = filtered[:count]
        return [(name, filtered)] if filtered else []


def test_redis_stream_event_bus_publish_and_consume_roundtrip():
    fake = FakeRedis()
    settings = RedisStreamSettings(url="redis://fake", stream="test.stream", maxlen=None)

    bus = RedisStreamEventBus(settings=settings, redis_client=fake)
    status = TaskStatus(task_id="t1", trace_id="tr1", status="running", sub_status="running-foreground")
    bus.publish_task_status(status, attributes={"phase": "progress"})

    consumer = RedisStreamConsumer(settings=settings, redis_client=fake)
    events = consumer.read(count=10, block_ms=0)
    assert len(events) == 1
    assert events[0].task_status.task_id == "t1"
    assert events[0].task_status.trace_id == "tr1"
    assert events[0].attributes["phase"] == "progress"


def test_fake_payload_is_valid_json_schema():
    fake = FakeRedis()
    settings = RedisStreamSettings(url="redis://fake", stream="test.stream", maxlen=None)
    bus = RedisStreamEventBus(settings=settings, redis_client=fake)

    status = TaskStatus(task_id="t1", status="running", sub_status="running-foreground")
    bus.publish_task_status(status)

    # Verify stored fields contain JSON payload
    stored = fake._streams[settings.stream][0][1]
    payload = stored["payload"]
    data = json.loads(payload)
    assert data["event_type"] == "task_status_updated"
    assert data["task_status"]["task_id"] == "t1"
