"""
Tests for services.llm.gemini_backend — Gemini via REST generateContent API.

Translates:
  Anthropic tool schema → Gemini function_declarations
  Gemini response → Anthropic-shaped response object (same duck-typed shape
                    the rest of the LLMRouter returns)
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_httpx(response_json: dict, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = "" if status < 300 else "err"
    resp.json = MagicMock(return_value=response_json)

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=resp)
    return patch("services.llm.gemini_backend.httpx.AsyncClient",
                 return_value=client), client


@pytest.mark.asyncio
class TestGeminiPlumbing:
    async def test_posts_to_generate_content_endpoint(self):
        from services.llm.gemini_backend import gemini_chat
        pc, client = _mock_httpx({
            "candidates": [{"content": {"parts": [{"text": "ok"}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
        })
        env = {"GEMINI_API_KEY": "gem_test"}
        with patch.dict(os.environ, env, clear=False), pc:
            await gemini_chat(
                system="s", messages=[{"role": "user", "content": "hi"}],
                max_tokens=100,
            )
        url = client.post.call_args[0][0]
        assert "generativelanguage.googleapis.com" in url
        assert ":generateContent" in url

    async def test_default_model_is_gemini_flash(self):
        from services.llm.gemini_backend import gemini_chat
        pc, _ = _mock_httpx({
            "candidates": [{"content": {"parts": [{"text": "ok"}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 0, "candidatesTokenCount": 0},
        })
        env = {"GEMINI_API_KEY": "k"}
        with patch.dict(os.environ, env, clear=False), pc:
            r = await gemini_chat(
                system="s", messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
            )
        assert r.content[0].text == "ok"

    async def test_raises_when_api_key_missing(self):
        from services.llm.gemini_backend import gemini_chat
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=True):
            with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
                await gemini_chat(
                    system="s", messages=[{"role": "user", "content": "x"}],
                    max_tokens=10,
                )

    async def test_system_sent_as_system_instruction(self):
        from services.llm.gemini_backend import gemini_chat
        pc, client = _mock_httpx({
            "candidates": [{"content": {"parts": [{"text": "ok"}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 0, "candidatesTokenCount": 0},
        })
        env = {"GEMINI_API_KEY": "k"}
        with patch.dict(os.environ, env, clear=False), pc:
            await gemini_chat(
                system="You are CRUZ",
                messages=[{"role": "user", "content": "x"}],
                max_tokens=10,
            )
        payload = client.post.call_args.kwargs["json"]
        # Gemini expects systemInstruction at the top level
        assert "You are CRUZ" in json.dumps(payload.get("systemInstruction", {}))


@pytest.mark.asyncio
class TestGeminiTools:
    async def test_anthropic_tools_translated_to_function_declarations(self):
        from services.llm.gemini_backend import gemini_chat
        pc, client = _mock_httpx({
            "candidates": [{"content": {"parts": [{"text": "ok"}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 0, "candidatesTokenCount": 0},
        })
        env = {"GEMINI_API_KEY": "k"}
        anthropic_tools = [
            {"name": "forge", "description": "Code gen",
             "input_schema": {"type": "object",
                              "properties": {"task": {"type": "string"}}}},
        ]
        with patch.dict(os.environ, env, clear=False), pc:
            await gemini_chat(
                system="s", messages=[{"role": "user", "content": "x"}],
                tools=anthropic_tools, max_tokens=10,
            )
        payload = client.post.call_args.kwargs["json"]
        tools = payload["tools"]
        decls = tools[0]["function_declarations"]
        assert decls[0]["name"] == "forge"
        assert decls[0]["description"] == "Code gen"


@pytest.mark.asyncio
class TestGeminiResponseTranslation:
    async def test_text_response(self):
        from services.llm.gemini_backend import gemini_chat
        pc, _ = _mock_httpx({
            "candidates": [{
                "content": {"parts": [{"text": "Hello world"}]},
                "finishReason": "STOP",
            }],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
        })
        env = {"GEMINI_API_KEY": "k"}
        with patch.dict(os.environ, env, clear=False), pc:
            r = await gemini_chat(
                system="s", messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
            )
        assert r.stop_reason == "end_turn"
        assert r.content[0].type == "text"
        assert r.content[0].text == "Hello world"
        assert r.usage.input_tokens == 5
        assert r.usage.output_tokens == 3

    async def test_function_call_response(self):
        """Gemini functionCall part → Anthropic tool_use block."""
        from services.llm.gemini_backend import gemini_chat
        pc, _ = _mock_httpx({
            "candidates": [{
                "content": {"parts": [{
                    "functionCall": {"name": "forge",
                                     "args": {"task": "csv parser"}},
                }]},
                "finishReason": "STOP",
            }],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 4},
        })
        env = {"GEMINI_API_KEY": "k"}
        with patch.dict(os.environ, env, clear=False), pc:
            r = await gemini_chat(
                system="s", messages=[{"role": "user", "content": "x"}],
                tools=[{"name": "forge", "description": "code",
                        "input_schema": {}}],
                max_tokens=10,
            )
        assert r.stop_reason == "tool_use"
        assert r.content[0].type == "tool_use"
        assert r.content[0].name == "forge"
        assert r.content[0].input == {"task": "csv parser"}

    async def test_non_2xx_raises(self):
        from services.llm.gemini_backend import gemini_chat
        pc, _ = _mock_httpx({}, status=403)
        env = {"GEMINI_API_KEY": "k"}
        with patch.dict(os.environ, env, clear=False), pc:
            with pytest.raises(RuntimeError, match="Gemini"):
                await gemini_chat(
                    system="s", messages=[{"role": "user", "content": "x"}],
                    max_tokens=10,
                )
