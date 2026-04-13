"""
DeviceHandoffService — Redis-backed cross-device tracking.

Tracks the last known device per conversation so CruzAgent can detect
when the user switches devices (phone → iPad → ThinkPad) and proactively
surface relevant context in the next response.

Redis key:      "cruz:device:{conversation_id}"
Pub/sub channel: "cruz:device_switch"
TTL:             1800 seconds (30-minute conversation timeout)

Usage:
    from services.device_handoff import DeviceHandoffService
    from services.redis_client import get_redis_service

    svc = DeviceHandoffService(get_redis_service())
    switched, last_device = await svc.detect_switch(conversation_id, current_device)
    if switched:
        await svc.publish_switch(conversation_id, last_device, current_device)
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Tuple

logger = logging.getLogger("cruz.services.device_handoff")

_KEY_TEMPLATE = "cruz:device:{conv_id}"
_SWITCH_CHANNEL = "cruz:device_switch"
_TTL = 1800  # 30 minutes — matches conversation timeout


class DeviceHandoffService:
    """
    Tracks the last device per conversation in Redis.

    All methods are async — call from within a running event loop.
    """

    def __init__(self, redis: object) -> None:
        self._redis = redis

    async def get_last_device(self, conversation_id: str) -> Optional[str]:
        """Return the previously stored device name, or None if not set."""
        key = _KEY_TEMPLATE.format(conv_id=conversation_id)
        value = await self._redis.get(key)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else value

    async def set_device(self, conversation_id: str, device: str) -> None:
        """Store the current device in Redis with the conversation TTL."""
        key = _KEY_TEMPLATE.format(conv_id=conversation_id)
        await self._redis.set(key, device, ttl=_TTL)

    async def detect_switch(
        self, conversation_id: str, current_device: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Detect whether the user has switched devices.

        Returns (switched, last_device):
          - (False, None)       — first visit for this conversation
          - (False, device)     — same device as before
          - (True,  last_device) — device has changed

        Always updates the stored device to current_device.
        """
        last_device = await self.get_last_device(conversation_id)
        switched = last_device is not None and last_device != current_device
        await self.set_device(conversation_id, current_device)
        return switched, last_device

    async def publish_switch(
        self, conversation_id: str, from_device: str, to_device: str
    ) -> None:
        """Publish a device-switch event to the Redis pub/sub channel."""
        message = json.dumps({
            "conversation_id": conversation_id,
            "from": from_device,
            "to": to_device,
        })
        await self._redis.publish(_SWITCH_CHANNEL, message)
        logger.info(
            "Device switch published: %s → %s (conv=%s)",
            from_device, to_device, conversation_id,
        )
