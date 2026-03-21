from ai_platform_samplelib.event_bus import get_event_bus, get_in_memory_event_bus
from autonomous_agent_util.model.models import TaskStatus


def test_in_memory_event_bus_collects_events(monkeypatch):
    monkeypatch.setenv("SV_EVENT_BUS_TYPE", "memory")

    bus = get_event_bus()
    status = TaskStatus(task_id="t1", status="running", sub_status="running-foreground")
    bus.publish_task_status(status, attributes={"phase": "progress"})

    mem = get_in_memory_event_bus()
    events = mem.list_events()
    assert len(events) >= 1
    assert events[-1].task_status.task_id == "t1"
    assert events[-1].attributes["phase"] == "progress"
