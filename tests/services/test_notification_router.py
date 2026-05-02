# tests/services/test_notification_router.py
"""NotificationRouter — pluggable channel registry, per-severity dispatch."""

from __future__ import annotations

from typing import Any

import pytest

from services.notification_router import (
    Channel,
    NotificationRouter,
    get_notification_router,
)


class FakeChannel:
    def __init__(self, name: str, sevs: set[str]) -> None:
        self.name = name
        self.handles_severities = sevs
        self.calls: list[tuple[str, dict]] = []

    async def send(self, severity: str, payload: dict) -> None:
        self.calls.append((severity, payload))


class FailingChannel:
    name = "failing"
    handles_severities = {"info", "warn", "critical"}

    async def send(self, severity: str, payload: dict) -> None:
        raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def _reset_router_singleton():
    import services.notification_router as mod
    mod._instance = None
    yield
    mod._instance = None


@pytest.fixture
def router():
    return NotificationRouter()


@pytest.mark.asyncio
async def test_register_then_route_calls_channel(router):
    ch = FakeChannel("c1", {"warn", "critical"})
    router.register(ch)
    await router.route("warn", {"text": "hi"})
    assert ch.calls == [("warn", {"text": "hi"})]


@pytest.mark.asyncio
async def test_route_skips_channel_for_unhandled_severity(router):
    ch = FakeChannel("crit_only", {"critical"})
    router.register(ch)
    await router.route("info", {"text": "x"})
    assert ch.calls == []


@pytest.mark.asyncio
async def test_route_calls_all_matching_channels(router):
    a = FakeChannel("a", {"info"})
    b = FakeChannel("b", {"info", "warn"})
    router.register(a)
    router.register(b)
    await router.route("info", {"x": 1})
    assert a.calls == [("info", {"x": 1})]
    assert b.calls == [("info", {"x": 1})]


@pytest.mark.asyncio
async def test_failing_channel_does_not_block_others(router, caplog):
    fail = FailingChannel()
    ok = FakeChannel("ok", {"warn"})
    router.register(fail)
    router.register(ok)
    await router.route("warn", {"x": 1})
    assert ok.calls == [("warn", {"x": 1})]
    assert "failing" in caplog.text.lower() or "boom" in caplog.text.lower()


@pytest.mark.asyncio
async def test_register_same_name_replaces_existing(router, caplog):
    """Idempotent registration: re-registering by the same name swaps in
    the new instance (only it receives subsequent route() calls) and
    emits a warning so accidental double-registers are visible."""
    import logging
    caplog.set_level(logging.WARNING, logger="cruz.services.notification_router")
    first = FakeChannel("dup", {"warn"})
    second = FakeChannel("dup", {"warn"})
    router.register(first)
    router.register(second)
    await router.route("warn", {"x": 1})
    assert first.calls == []
    assert second.calls == [("warn", {"x": 1})]
    assert "already registered" in caplog.text.lower()


@pytest.mark.asyncio
async def test_get_notification_router_returns_singleton():
    a = get_notification_router()
    b = get_notification_router()
    assert a is b
