import os

from ai_platform_samplelib.event_bus.redis_stream import RedisStreamSettings


def test_load_from_env_prefers_explicit_url(monkeypatch):
    monkeypatch.setenv("SV_EVENT_BUS_REDIS_URL", "redis://explicit:6379/0")
    monkeypatch.setenv("SV_EVENT_BUS_REDIS_URL_IN_HOST", "redis://host:6379/0")

    settings = RedisStreamSettings.load_from_env()
    assert settings.url == "redis://explicit:6379/0"


def test_load_from_env_uses_host_url_when_not_in_container(monkeypatch):
    monkeypatch.delenv("SV_EVENT_BUS_REDIS_URL", raising=False)
    monkeypatch.setenv("SV_EVENT_BUS_REDIS_URL_IN_HOST", "redis://host:6379/0")
    monkeypatch.setenv("SV_EVENT_BUS_REDIS_URL_IN_CONTAINER", "redis://container:6379/0")

    monkeypatch.setattr(os.path, "exists", lambda p: False)
    settings = RedisStreamSettings.load_from_env()
    assert settings.url == "redis://host:6379/0"


def test_load_from_env_uses_container_url_when_in_container(monkeypatch):
    monkeypatch.delenv("SV_EVENT_BUS_REDIS_URL", raising=False)
    monkeypatch.setenv("SV_EVENT_BUS_REDIS_URL_IN_HOST", "redis://host:6379/0")
    monkeypatch.setenv("SV_EVENT_BUS_REDIS_URL_IN_CONTAINER", "redis://container:6379/0")

    monkeypatch.setattr(os.path, "exists", lambda p: True)
    settings = RedisStreamSettings.load_from_env()
    assert settings.url == "redis://container:6379/0"
