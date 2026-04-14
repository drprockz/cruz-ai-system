"""
Tests for AlertService — Telegram + Sentry notification wrapper.

Contract:
  await svc.notify(severity, title, message) -> dict
    severity ∈ {"critical", "warning", "info"}
    - Sends to Telegram if TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID set.
    - Also sends to Sentry if SENTRY_DSN set (capture_message with level).
    - Silent no-op if neither channel configured.
    - Non-fatal on failure: returns {"telegram": False, "sentry": False, "error": "..."}
      rather than raising.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_tg_response(status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = "ok" if status < 300 else "bad"
    return resp


def _patch_httpx(response):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)
    return patch("services.alerts.httpx.AsyncClient", return_value=client), client


class TestAlertServiceInterface:
    def test_can_be_imported(self):
        from services.alerts import AlertService  # noqa

    def test_notify_is_coroutine(self):
        import asyncio
        from services.alerts import AlertService
        assert asyncio.iscoroutinefunction(AlertService().notify)


class TestAlertServiceNoOp:
    @pytest.mark.asyncio
    async def test_silent_when_nothing_configured(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        from services.alerts import AlertService
        result = await AlertService().notify("info", "title", "msg")
        assert result == {"telegram": False, "sentry": False}


class TestAlertServiceTelegram:
    @pytest.mark.asyncio
    async def test_sends_to_telegram(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok123")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        patcher, client = _patch_httpx(_mock_tg_response(200))
        with patcher:
            from services.alerts import AlertService
            result = await AlertService().notify("critical", "Deploy failed", "body")
        assert result["telegram"] is True
        assert result["sentry"] is False
        client.post.assert_awaited_once()
        call = client.post.await_args
        url = call.args[0]
        assert "api.telegram.org/bottok123/sendMessage" in url
        payload = call.kwargs.get("json") or call.args[1]
        assert payload["chat_id"] == "456"
        assert "Deploy failed" in payload["text"]
        assert "body" in payload["text"]
        # severity shown
        assert "critical" in payload["text"].lower() or "🔴" in payload["text"]

    @pytest.mark.asyncio
    async def test_telegram_failure_is_non_fatal(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        patcher, _ = _patch_httpx(_mock_tg_response(500))
        with patcher:
            from services.alerts import AlertService
            result = await AlertService().notify("warning", "t", "m")
        assert result["telegram"] is False
        assert "error" in result


class TestAlertServiceSentry:
    @pytest.mark.asyncio
    async def test_calls_sentry_capture_message(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        monkeypatch.setenv("SENTRY_DSN", "https://abc@sentry.io/1")
        mock_sentry = MagicMock()
        with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
            from services.alerts import AlertService
            result = await AlertService().notify("critical", "Boom", "stack")
        assert result["sentry"] is True
        mock_sentry.capture_message.assert_called_once()
        args, kwargs = mock_sentry.capture_message.call_args
        assert "Boom" in args[0]
        assert kwargs.get("level") in ("error", "fatal", "critical")

    @pytest.mark.asyncio
    async def test_sentry_level_mapping(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.setenv("SENTRY_DSN", "https://abc@sentry.io/1")
        mock_sentry = MagicMock()
        with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
            from services.alerts import AlertService
            await AlertService().notify("warning", "t", "m")
            await AlertService().notify("info", "t", "m")
        levels = [c.kwargs.get("level") for c in mock_sentry.capture_message.call_args_list]
        assert "warning" in levels
        assert "info" in levels
