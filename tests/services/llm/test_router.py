"""
Tests for services.llm.router — LLM backend abstraction.

The router picks a backend based on LLM_BACKEND env var (or explicit
backend=... arg) and delegates to a backend-specific implementation.
Every backend returns a normalised response shape that mimics Anthropic's
messages.create() return object so existing agents can use it unchanged:

    response.content      — list of ContentBlock (type="text"|"tool_use")
    response.stop_reason  — "end_turn" | "tool_use" | other
    response.usage.input_tokens + .output_tokens — ints

This file tests the router's dispatch logic. Individual backend
translations (anthropic/ollama/gemini) have their own test files.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class TestRouterInterface:
    def test_chat_is_importable(self):
        from services.llm import chat  # noqa: F401

    def test_chat_is_coroutine(self):
        import asyncio
        from services.llm import chat
        assert asyncio.iscoroutinefunction(chat)

    def test_default_backend_is_anthropic(self):
        from services.llm.router import _resolve_backend
        with patch.dict(os.environ, {}, clear=True):
            assert _resolve_backend(None) == "anthropic"

    def test_env_override_respected(self):
        from services.llm.router import _resolve_backend
        with patch.dict(os.environ, {"LLM_BACKEND": "ollama"}, clear=True):
            assert _resolve_backend(None) == "ollama"

    def test_explicit_arg_beats_env(self):
        from services.llm.router import _resolve_backend
        with patch.dict(os.environ, {"LLM_BACKEND": "ollama"}, clear=False):
            assert _resolve_backend("gemini") == "gemini"

    def test_unknown_backend_raises(self):
        from services.llm.router import _resolve_backend
        with pytest.raises(ValueError, match="LLM_BACKEND"):
            _resolve_backend("klingon-ai")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRouterDispatch:
    async def test_anthropic_backend_invoked(self):
        from services.llm import chat
        fake_resp = MagicMock()
        with patch("services.llm.router.anthropic_chat",
                   new_callable=AsyncMock) as mock_anthropic:
            mock_anthropic.return_value = fake_resp
            r = await chat(
                system="sys", messages=[{"role": "user", "content": "hi"}],
                backend="anthropic",
            )
        mock_anthropic.assert_awaited_once()
        assert r is fake_resp

    async def test_ollama_backend_invoked(self):
        from services.llm import chat
        fake_resp = MagicMock()
        with patch("services.llm.router.ollama_chat",
                   new_callable=AsyncMock) as mock_ollama:
            mock_ollama.return_value = fake_resp
            r = await chat(
                system="sys", messages=[{"role": "user", "content": "hi"}],
                backend="ollama",
            )
        mock_ollama.assert_awaited_once()
        assert r is fake_resp

    async def test_gemini_backend_invoked(self):
        from services.llm import chat
        fake_resp = MagicMock()
        with patch("services.llm.router.gemini_chat",
                   new_callable=AsyncMock) as mock_gemini:
            mock_gemini.return_value = fake_resp
            r = await chat(
                system="sys", messages=[{"role": "user", "content": "hi"}],
                backend="gemini",
            )
        mock_gemini.assert_awaited_once()
        assert r is fake_resp

    async def test_env_var_controls_dispatch_when_no_arg(self):
        from services.llm import chat
        with patch.dict(os.environ, {"LLM_BACKEND": "ollama"}, clear=False), \
             patch("services.llm.router.ollama_chat",
                   new_callable=AsyncMock) as mock_ollama, \
             patch("services.llm.router.anthropic_chat",
                   new_callable=AsyncMock) as mock_anthropic:
            mock_ollama.return_value = MagicMock()
            await chat(system="s", messages=[{"role": "user", "content": "x"}])
        mock_ollama.assert_awaited_once()
        mock_anthropic.assert_not_called()
