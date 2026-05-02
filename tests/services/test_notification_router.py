# tests/services/test_notification_router.py
"""NotificationRouter — pluggable channel registry, per-severity dispatch."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from services.notification_router import (
    NotificationRouter,
    TelegramChannel,
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
    caplog.set_level(logging.WARNING, logger="cruz.services.notification_router")
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


@pytest.mark.asyncio
async def test_telegram_info_uses_silent_notification():
    ch = TelegramChannel(bot_token="t", chat_id="123", feed_topic_id="42")
    fake_post = AsyncMock(return_value=AsyncMock(status_code=200, json=lambda: {"ok": True}))
    with patch("services.notification_router._http_post", fake_post):
        await ch.send("info", {"text": "hello", "trace_id": "tr-1"})
    args = fake_post.await_args.kwargs
    body = args["json"]
    assert body["chat_id"] == "123"
    assert body["text"] == "hello"
    assert body["disable_notification"] is True
    assert body["message_thread_id"] == 42


@pytest.mark.asyncio
async def test_telegram_warn_normal_message_no_button():
    ch = TelegramChannel(bot_token="t", chat_id="123")
    fake_post = AsyncMock(return_value=AsyncMock(status_code=200, json=lambda: {"ok": True}))
    with patch("services.notification_router._http_post", fake_post):
        await ch.send("warn", {"text": "alert"})
    body = fake_post.await_args.kwargs["json"]
    assert body["disable_notification"] is False
    assert "reply_markup" not in body


@pytest.mark.asyncio
async def test_telegram_critical_includes_false_alarm_button():
    ch = TelegramChannel(bot_token="t", chat_id="123")
    fake_post = AsyncMock(return_value=AsyncMock(status_code=200, json=lambda: {"ok": True}))
    payload = {
        "text": "URGENT", "trace_id": "tr-2",
        "agent": "reply_triage", "dedup_key": "email:abc",
    }
    with patch("services.notification_router._http_post", fake_post):
        await ch.send("critical", payload)
    body = fake_post.await_args.kwargs["json"]
    assert body["disable_notification"] is False
    markup = body["reply_markup"]
    assert "inline_keyboard" in markup
    btn = markup["inline_keyboard"][0][0]
    assert "False alarm" in btn["text"]
    # callback_data encodes (agent, dedup_key) for the false-alarm endpoint
    assert "reply_triage" in btn["callback_data"]
    assert "email:abc" in btn["callback_data"]


@pytest.mark.asyncio
async def test_telegram_send_swallows_http_error_logs_warning(caplog):
    import logging
    caplog.set_level(logging.WARNING, logger="cruz.services.notification_router")
    ch = TelegramChannel(bot_token="t", chat_id="123")
    fake_post = AsyncMock(side_effect=RuntimeError("network down"))
    with patch("services.notification_router._http_post", fake_post):
        # Must not raise — router relies on this to continue with other channels
        await ch.send("warn", {"text": "x"})
    assert "telegram" in caplog.text.lower()


def test_telegram_handles_severities_includes_all_three():
    ch = TelegramChannel(bot_token="t", chat_id="123")
    assert ch.handles_severities == {"info", "warn", "critical"}
