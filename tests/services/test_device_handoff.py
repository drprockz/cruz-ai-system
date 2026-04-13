"""
Tests for DeviceHandoffService — Redis-backed cross-device tracking.

Responsibilities:
  - get_last_device(conversation_id) → stored device or None
  - set_device(conversation_id, device, ttl=1800)
  - detect_switch(conversation_id, current_device) → (switched, last_device)
  - publish_switch(conversation_id, from_device, to_device) → Redis pub/sub

Redis key: "cruz:device:{conversation_id}"
Pub/sub channel: "cruz:device_switch"
TTL: 1800 seconds (30 min conversation timeout)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_redis(get_value: bytes | None = None) -> MagicMock:
    r = MagicMock()
    r.get = AsyncMock(return_value=get_value)
    r.set = AsyncMock()
    r.publish = AsyncMock()
    return r


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class TestDeviceHandoffInterface:
    def test_can_be_imported(self):
        from services.device_handoff import DeviceHandoffService
        assert DeviceHandoffService is not None

    def test_accepts_redis_service(self):
        from services.device_handoff import DeviceHandoffService
        redis = _make_redis()
        svc = DeviceHandoffService(redis)
        assert svc is not None

    def test_get_last_device_is_coroutine(self):
        import asyncio
        from services.device_handoff import DeviceHandoffService
        svc = DeviceHandoffService(_make_redis())
        assert asyncio.iscoroutinefunction(svc.get_last_device)

    def test_set_device_is_coroutine(self):
        import asyncio
        from services.device_handoff import DeviceHandoffService
        svc = DeviceHandoffService(_make_redis())
        assert asyncio.iscoroutinefunction(svc.set_device)

    def test_detect_switch_is_coroutine(self):
        import asyncio
        from services.device_handoff import DeviceHandoffService
        svc = DeviceHandoffService(_make_redis())
        assert asyncio.iscoroutinefunction(svc.detect_switch)

    def test_publish_switch_is_coroutine(self):
        import asyncio
        from services.device_handoff import DeviceHandoffService
        svc = DeviceHandoffService(_make_redis())
        assert asyncio.iscoroutinefunction(svc.publish_switch)


# ---------------------------------------------------------------------------
# get_last_device
# ---------------------------------------------------------------------------

class TestGetLastDevice:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_device_stored(self):
        from services.device_handoff import DeviceHandoffService
        svc = DeviceHandoffService(_make_redis(get_value=None))
        result = await svc.get_last_device("conv-001")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_device_string_when_stored(self):
        from services.device_handoff import DeviceHandoffService
        svc = DeviceHandoffService(_make_redis(get_value=b"ipad"))
        result = await svc.get_last_device("conv-001")
        assert result == "ipad"

    @pytest.mark.asyncio
    async def test_uses_correct_redis_key(self):
        from services.device_handoff import DeviceHandoffService
        redis = _make_redis()
        svc = DeviceHandoffService(redis)
        await svc.get_last_device("conv-abc")
        redis.get.assert_called_once_with("cruz:device:conv-abc")


# ---------------------------------------------------------------------------
# set_device
# ---------------------------------------------------------------------------

class TestSetDevice:
    @pytest.mark.asyncio
    async def test_sets_device_in_redis(self):
        from services.device_handoff import DeviceHandoffService
        redis = _make_redis()
        svc = DeviceHandoffService(redis)
        await svc.set_device("conv-001", "phone")
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_correct_key_and_value(self):
        from services.device_handoff import DeviceHandoffService
        redis = _make_redis()
        svc = DeviceHandoffService(redis)
        await svc.set_device("conv-001", "thinkpad")
        call_args = redis.set.call_args
        assert "cruz:device:conv-001" in call_args[0]
        assert "thinkpad" in call_args[0]

    @pytest.mark.asyncio
    async def test_sets_30_minute_ttl(self):
        from services.device_handoff import DeviceHandoffService
        redis = _make_redis()
        svc = DeviceHandoffService(redis)
        await svc.set_device("conv-001", "mac_mini")
        call_kwargs = redis.set.call_args[1]
        assert call_kwargs.get("ttl") == 1800


# ---------------------------------------------------------------------------
# detect_switch
# ---------------------------------------------------------------------------

class TestDetectSwitch:
    @pytest.mark.asyncio
    async def test_no_switch_on_first_visit(self):
        """First visit (no stored device) → (False, None)."""
        from services.device_handoff import DeviceHandoffService
        svc = DeviceHandoffService(_make_redis(get_value=None))
        switched, last = await svc.detect_switch("conv-001", "phone")
        assert switched is False
        assert last is None

    @pytest.mark.asyncio
    async def test_no_switch_when_same_device(self):
        """Same device as last time → (False, "phone")."""
        from services.device_handoff import DeviceHandoffService
        svc = DeviceHandoffService(_make_redis(get_value=b"phone"))
        switched, last = await svc.detect_switch("conv-001", "phone")
        assert switched is False
        assert last == "phone"

    @pytest.mark.asyncio
    async def test_switch_detected_when_device_changes(self):
        """Different device → (True, "phone")."""
        from services.device_handoff import DeviceHandoffService
        svc = DeviceHandoffService(_make_redis(get_value=b"phone"))
        switched, last = await svc.detect_switch("conv-001", "ipad")
        assert switched is True
        assert last == "phone"

    @pytest.mark.asyncio
    async def test_updates_stored_device_after_detection(self):
        """After detect_switch, the new device must be persisted."""
        from services.device_handoff import DeviceHandoffService
        redis = _make_redis(get_value=b"phone")
        svc = DeviceHandoffService(redis)
        await svc.detect_switch("conv-001", "ipad")
        redis.set.assert_called_once()
        call_args = redis.set.call_args[0]
        assert "ipad" in call_args


# ---------------------------------------------------------------------------
# publish_switch
# ---------------------------------------------------------------------------

class TestPublishSwitch:
    @pytest.mark.asyncio
    async def test_publishes_to_redis_channel(self):
        from services.device_handoff import DeviceHandoffService
        redis = _make_redis()
        svc = DeviceHandoffService(redis)
        await svc.publish_switch("conv-001", "phone", "ipad")
        redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_publishes_to_correct_channel(self):
        from services.device_handoff import DeviceHandoffService
        redis = _make_redis()
        svc = DeviceHandoffService(redis)
        await svc.publish_switch("conv-001", "phone", "ipad")
        channel = redis.publish.call_args[0][0]
        assert channel == "cruz:device_switch"

    @pytest.mark.asyncio
    async def test_message_contains_conversation_id(self):
        from services.device_handoff import DeviceHandoffService
        redis = _make_redis()
        svc = DeviceHandoffService(redis)
        await svc.publish_switch("conv-xyz", "phone", "ipad")
        message = redis.publish.call_args[0][1]
        data = json.loads(message)
        assert data["conversation_id"] == "conv-xyz"

    @pytest.mark.asyncio
    async def test_message_contains_from_and_to_device(self):
        from services.device_handoff import DeviceHandoffService
        redis = _make_redis()
        svc = DeviceHandoffService(redis)
        await svc.publish_switch("conv-001", "phone", "thinkpad")
        message = redis.publish.call_args[0][1]
        data = json.loads(message)
        assert data["from"] == "phone"
        assert data["to"] == "thinkpad"
