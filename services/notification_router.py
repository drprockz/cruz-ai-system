# services/notification_router.py
"""
NotificationRouter — per-severity dispatch over a pluggable channel registry.

SP5 ships exactly one channel: TelegramChannel (built in Task 3.2).
SP3 will register IMessageChannel (criticals only).
SP7 will register FCMChannel (warns + criticals) and VoiceDaemonChannel.

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.3
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger("cruz.services.notification_router")


@runtime_checkable
class Channel(Protocol):
    """One notification target — Telegram, iMessage, FCM, voice daemon."""

    name: str
    handles_severities: set[str]

    async def send(self, severity: str, payload: dict) -> None: ...


class NotificationRouter:
    """Fan-out router. Routes one (severity, payload) to all channels
    that declare they handle that severity. Channel failures are logged
    and do not abort the route — other channels still receive the call."""

    def __init__(self) -> None:
        self._channels: list[Channel] = []

    def register(self, channel: Channel) -> None:
        """Replaces any existing channel with the same `name` and emits a warning."""
        if any(c.name == channel.name for c in self._channels):
            logger.warning("channel %s already registered, replacing", channel.name)
            self._channels = [c for c in self._channels if c.name != channel.name]
        self._channels.append(channel)

    async def route(self, severity: str, payload: dict) -> None:
        """Dispatch one message to every channel that handles `severity`."""
        for ch in self._channels:
            if severity not in ch.handles_severities:
                continue
            try:
                await ch.send(severity, payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "notification channel %s failed (non-fatal): %s",
                    ch.name, exc,
                )


_instance: Optional[NotificationRouter] = None


def get_notification_router() -> NotificationRouter:
    """Return the process-wide singleton NotificationRouter."""
    global _instance
    if _instance is None:
        _instance = NotificationRouter()
    return _instance
