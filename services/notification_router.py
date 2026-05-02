# services/notification_router.py
"""
NotificationRouter — per-severity dispatch over a pluggable channel registry.

SP5 ships exactly one channel: TelegramChannel (built in Task 3.2).
SP3 will register IMessageChannel (criticals only).
SP7 will register FCMChannel (warns + criticals) and VoiceDaemonChannel.

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.3
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Optional, Protocol, runtime_checkable

import httpx

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


async def _http_post(url: str, *, json: dict, timeout: float = 10.0) -> Any:
    """Thin httpx wrapper — separated so tests can monkeypatch it."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(url, json=json)


class TelegramChannel:
    """Telegram bot channel — only channel shipped in SP5.

    Severity mapping:
      info     → silent message, posted to feed topic if configured
      warn     → normal message
      critical → notification + inline "False alarm" button

    Env vars (all may also be passed as constructor args for testing):
      TELEGRAM_BOT_TOKEN       — required
      TELEGRAM_CHAT_ID         — required (the user's CRUZ chat)
      TELEGRAM_FEED_TOPIC_ID   — optional; if set, info messages go to that
                                 topic in a forum-mode chat
    """

    name = "telegram"
    handles_severities = {"info", "warn", "critical"}

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        feed_topic_id: str | int | None = None,
    ) -> None:
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        topic = feed_topic_id if feed_topic_id is not None \
                else os.environ.get("TELEGRAM_FEED_TOPIC_ID")
        self.feed_topic_id = int(topic) if topic else None
        if not self.bot_token or not self.chat_id:
            logger.warning(
                "TelegramChannel: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID — "
                "send() will be a no-op until configured"
            )

    async def send(self, severity: str, payload: dict) -> None:
        """Send a message to Telegram.

        info     → disable_notification=True, routed to feed_topic_id if set
        warn     → normal notification
        critical → notification + inline False-alarm button for user ack
        """
        if not self.bot_token or not self.chat_id:
            logger.debug("telegram not configured — dropping %s message", severity)
            return

        text = payload.get("text", "")
        body: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_notification": severity == "info",
            "parse_mode": "Markdown",
        }

        if severity == "info" and self.feed_topic_id is not None:
            body["message_thread_id"] = self.feed_topic_id

        if severity == "critical":
            agent = payload.get("agent", "?")
            dedup_key = payload.get("dedup_key", "?")
            # Telegram callback_data hard limit: 64 bytes.
            # Format: "fa|<agent>|<key>" (or "fa|<agent>|h:<sha8>" if too long).
            raw = f"fa|{agent}|{dedup_key}"
            if len(raw.encode("utf-8")) <= 64:
                cb = raw
            else:
                h = hashlib.sha1(dedup_key.encode("utf-8")).hexdigest()[:8]
                cb = f"fa|{agent}|h:{h}"
                logger.info(
                    "telegram callback_data hashed (raw was %d bytes): %s -> %s",
                    len(raw.encode("utf-8")), dedup_key, cb,
                )
            body["reply_markup"] = {
                "inline_keyboard": [[
                    {"text": "❌ False alarm", "callback_data": cb}
                ]]
            }

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            response = await _http_post(url, json=body)
            if hasattr(response, "status_code") and response.status_code >= 400:
                logger.warning(
                    "telegram send returned %s: %s",
                    response.status_code,
                    getattr(response, "text", ""),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram send failed (non-fatal): %s", exc)
