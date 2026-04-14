"""
Tests for services.llm.anthropic_backend — thin passthrough to Anthropic SDK.

The anthropic backend is intentionally minimal: it constructs an
AsyncAnthropic client, forwards the normalized args to messages.create(),
and returns the raw SDK response. This preserves the existing shape
that CruzAgent, FORGE, SENTINEL, and GeneralAgent already use.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
class TestAnthropicBackend:
    async def test_forwards_to_messages_create(self):
        from services.llm.anthropic_backend import anthropic_chat
        fake_client = MagicMock()
        fake_client.messages = MagicMock()
        fake_client.messages.create = AsyncMock(return_value=MagicMock())
        with patch("services.llm.anthropic_backend.anthropic.AsyncAnthropic",
                   return_value=fake_client):
            await anthropic_chat(
                system="You are CRUZ",
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"name": "forge", "description": "code", "input_schema": {}}],
                max_tokens=4096,
            )
        fake_client.messages.create.assert_awaited_once()
        call = fake_client.messages.create.call_args.kwargs
        assert call["system"] == "You are CRUZ"
        assert call["messages"][0]["content"] == "hi"
        assert call["tools"][0]["name"] == "forge"
        assert call["max_tokens"] == 4096

    async def test_uses_default_model_when_not_specified(self):
        from services.llm.anthropic_backend import anthropic_chat
        fake_client = MagicMock()
        fake_client.messages = MagicMock()
        fake_client.messages.create = AsyncMock(return_value=MagicMock())
        with patch("services.llm.anthropic_backend.anthropic.AsyncAnthropic",
                   return_value=fake_client):
            await anthropic_chat(
                system="s", messages=[{"role": "user", "content": "x"}],
                max_tokens=100,
            )
        model = fake_client.messages.create.call_args.kwargs["model"]
        assert "claude" in model.lower()

    async def test_custom_model_override(self):
        from services.llm.anthropic_backend import anthropic_chat
        fake_client = MagicMock()
        fake_client.messages = MagicMock()
        fake_client.messages.create = AsyncMock(return_value=MagicMock())
        with patch("services.llm.anthropic_backend.anthropic.AsyncAnthropic",
                   return_value=fake_client):
            await anthropic_chat(
                system="s", messages=[{"role": "user", "content": "x"}],
                max_tokens=100, model="claude-haiku-4-5-20251001",
            )
        assert fake_client.messages.create.call_args.kwargs["model"] \
            == "claude-haiku-4-5-20251001"

    async def test_reads_api_key_from_env(self):
        from services.llm.anthropic_backend import anthropic_chat
        fake_client = MagicMock()
        fake_client.messages = MagicMock()
        fake_client.messages.create = AsyncMock(return_value=MagicMock())
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=False), \
             patch("services.llm.anthropic_backend.anthropic.AsyncAnthropic",
                   return_value=fake_client) as mock_cls:
            await anthropic_chat(
                system="s", messages=[{"role": "user", "content": "x"}],
                max_tokens=10,
            )
        # AsyncAnthropic was constructed with api_key from env
        ctor_kwargs = mock_cls.call_args.kwargs
        assert ctor_kwargs.get("api_key") == "sk-test"

    async def test_returns_sdk_response_as_is(self):
        """No translation for anthropic — the raw SDK object is returned."""
        from services.llm.anthropic_backend import anthropic_chat
        sdk_resp = MagicMock()
        sdk_resp.stop_reason = "end_turn"
        fake_client = MagicMock()
        fake_client.messages = MagicMock()
        fake_client.messages.create = AsyncMock(return_value=sdk_resp)
        with patch("services.llm.anthropic_backend.anthropic.AsyncAnthropic",
                   return_value=fake_client):
            r = await anthropic_chat(
                system="s", messages=[{"role": "user", "content": "x"}],
                max_tokens=10,
            )
        assert r is sdk_resp
