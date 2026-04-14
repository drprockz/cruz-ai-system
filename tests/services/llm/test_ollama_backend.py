"""
Tests for services.llm.ollama_backend — Ollama via OpenAI-compat endpoint.

Ollama exposes an OpenAI-compatible /v1/chat/completions endpoint that
supports tool calling on qwen2.5-coder:14b. This backend translates:

  Anthropic tool schema → OpenAI tool schema
  OpenAI response → Anthropic-shaped response object

The duck-typed response has .content (list of blocks with .type/.text/.name/
.input/.id), .stop_reason, and .usage.{input_tokens,output_tokens} so
existing callers don't change.
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_httpx(response_json: dict, status: int = 200):
    """Patch httpx.AsyncClient so POST returns a response with the given JSON."""
    resp = MagicMock()
    resp.status_code = status
    resp.text = "" if status < 300 else "err"
    resp.json = MagicMock(return_value=response_json)

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=resp)
    return patch("services.llm.ollama_backend.httpx.AsyncClient",
                 return_value=client), client


# ---------------------------------------------------------------------------
# URL + model defaults
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestOllamaBackendPlumbing:
    async def test_posts_to_openai_compat_endpoint(self):
        from services.llm.ollama_backend import ollama_chat
        pc, client = _mock_httpx({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })
        with pc:
            await ollama_chat(
                system="s", messages=[{"role": "user", "content": "x"}],
                max_tokens=100,
            )
        url = client.post.call_args[0][0]
        assert "/v1/chat/completions" in url

    async def test_default_model_is_qwen_coder(self):
        from services.llm.ollama_backend import ollama_chat
        pc, client = _mock_httpx({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        })
        with pc:
            await ollama_chat(
                system="s", messages=[{"role": "user", "content": "x"}],
                max_tokens=10,
            )
        payload = client.post.call_args.kwargs["json"]
        assert "qwen" in payload["model"].lower()

    async def test_prepends_system_as_message(self):
        """OpenAI format has system as the first message, not a separate field."""
        from services.llm.ollama_backend import ollama_chat
        pc, client = _mock_httpx({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        })
        with pc:
            await ollama_chat(
                system="You are CRUZ.",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
            )
        msgs = client.post.call_args.kwargs["json"]["messages"]
        assert msgs[0]["role"] == "system"
        assert "CRUZ" in msgs[0]["content"]
        assert msgs[1]["role"] == "user"


# ---------------------------------------------------------------------------
# Tool schema translation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestOllamaBackendTools:
    async def test_anthropic_tools_translated_to_openai_format(self):
        from services.llm.ollama_backend import ollama_chat
        pc, client = _mock_httpx({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        })
        anthropic_tools = [
            {
                "name": "forge",
                "description": "Code generation",
                "input_schema": {
                    "type": "object",
                    "properties": {"task": {"type": "string"}},
                    "required": ["task"],
                },
            },
        ]
        with pc:
            await ollama_chat(
                system="s", messages=[{"role": "user", "content": "x"}],
                tools=anthropic_tools, max_tokens=10,
            )
        sent_tools = client.post.call_args.kwargs["json"]["tools"]
        assert sent_tools[0]["type"] == "function"
        assert sent_tools[0]["function"]["name"] == "forge"
        assert sent_tools[0]["function"]["description"] == "Code generation"
        assert sent_tools[0]["function"]["parameters"]["type"] == "object"

    async def test_empty_tools_sends_no_tools_field(self):
        from services.llm.ollama_backend import ollama_chat
        pc, client = _mock_httpx({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        })
        with pc:
            await ollama_chat(
                system="s", messages=[{"role": "user", "content": "x"}],
                tools=None, max_tokens=10,
            )
        payload = client.post.call_args.kwargs["json"]
        assert "tools" not in payload


# ---------------------------------------------------------------------------
# Response translation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestOllamaResponseTranslation:
    async def test_text_response_mapped_to_content_block(self):
        from services.llm.ollama_backend import ollama_chat
        pc, _ = _mock_httpx({
            "choices": [
                {"message": {"content": "Here is the answer."},
                 "finish_reason": "stop"},
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7},
        })
        with pc:
            r = await ollama_chat(
                system="s", messages=[{"role": "user", "content": "x"}],
                max_tokens=10,
            )
        # Anthropic-shaped response
        assert r.stop_reason == "end_turn"
        assert r.content[0].type == "text"
        assert r.content[0].text == "Here is the answer."
        assert r.usage.input_tokens == 12
        assert r.usage.output_tokens == 7

    async def test_tool_call_mapped_to_tool_use_block(self):
        """OpenAI tool_calls → Anthropic-style tool_use blocks."""
        from services.llm.ollama_backend import ollama_chat
        pc, _ = _mock_httpx({
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_abc",
                                "type": "function",
                                "function": {
                                    "name": "forge",
                                    "arguments": json.dumps(
                                        {"task": "write a csv parser"}
                                    ),
                                },
                            },
                        ],
                    },
                    "finish_reason": "tool_calls",
                },
            ],
            "usage": {"prompt_tokens": 40, "completion_tokens": 15},
        })
        with pc:
            r = await ollama_chat(
                system="s", messages=[{"role": "user", "content": "x"}],
                tools=[{"name": "forge", "description": "code",
                        "input_schema": {"type": "object"}}],
                max_tokens=10,
            )
        assert r.stop_reason == "tool_use"
        block = r.content[0]
        assert block.type == "tool_use"
        assert block.name == "forge"
        assert block.input == {"task": "write a csv parser"}
        assert block.id == "call_abc"

    async def test_mixed_text_and_tool_call_translated(self):
        """If the model emits both text and a tool call, both map to blocks."""
        from services.llm.ollama_backend import ollama_chat
        pc, _ = _mock_httpx({
            "choices": [
                {
                    "message": {
                        "content": "Let me help with that.",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "forge",
                                    "arguments": json.dumps({"task": "x"}),
                                },
                            },
                        ],
                    },
                    "finish_reason": "tool_calls",
                },
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 8},
        })
        with pc:
            r = await ollama_chat(
                system="s", messages=[{"role": "user", "content": "x"}],
                tools=[{"name": "forge", "description": "code",
                        "input_schema": {}}],
                max_tokens=10,
            )
        # Should have 2 blocks: text + tool_use
        types = [b.type for b in r.content]
        assert "text" in types
        assert "tool_use" in types


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestOllamaErrors:
    async def test_non_2xx_raises_runtime_error(self):
        from services.llm.ollama_backend import ollama_chat
        pc, _ = _mock_httpx({}, status=500)
        with pc:
            with pytest.raises(RuntimeError, match="Ollama"):
                await ollama_chat(
                    system="s", messages=[{"role": "user", "content": "x"}],
                    max_tokens=10,
                )


# ---------------------------------------------------------------------------
# Tool-result round-trip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestOllamaToolResultRoundTrip:
    async def test_assistant_with_tool_use_blocks_translated_back(self):
        """
        When CruzAgent feeds back an 'assistant' message containing the
        tool_use blocks it already emitted (Anthropic shape), the Ollama
        backend must translate those blocks into the OpenAI shape with
        `tool_calls` on the assistant message.
        """
        from services.llm.ollama_backend import ollama_chat
        pc, client = _mock_httpx({
            "choices": [{"message": {"content": "done"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        })
        # Simulate the Anthropic-shaped message history from CruzAgent
        tool_use_block = MagicMock()
        tool_use_block.type = "tool_use"
        tool_use_block.id = "call_abc"
        tool_use_block.name = "forge"
        tool_use_block.input = {"task": "build"}
        messages = [
            {"role": "user", "content": "build me a thing"},
            {"role": "assistant", "content": [tool_use_block]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "call_abc", "content": "done"},
            ]},
        ]
        with pc:
            await ollama_chat(
                system="s", messages=messages,
                tools=[{"name": "forge", "description": "code", "input_schema": {}}],
                max_tokens=10,
            )
        sent = client.post.call_args.kwargs["json"]["messages"]
        # Assistant with tool_calls should come through
        assistant = [m for m in sent if m["role"] == "assistant"][0]
        assert "tool_calls" in assistant
        assert assistant["tool_calls"][0]["function"]["name"] == "forge"
        # Tool result → role=tool message with tool_call_id
        tool_msg = [m for m in sent if m.get("role") == "tool"][0]
        assert tool_msg["tool_call_id"] == "call_abc"
