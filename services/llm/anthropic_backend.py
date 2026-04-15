"""
Anthropic backend — thin passthrough to the official Anthropic SDK.

Returns the raw SDK response unchanged, since its duck-typed shape
(.content, .stop_reason, .usage.{input,output}_tokens) is exactly
what our normalised types emulate.
"""

from __future__ import annotations

import json as _json
import os
from typing import Any, AsyncIterator, Dict, List, Optional

import anthropic

from services.llm.stream_events import (
    DoneEvent,
    TextDeltaEvent,
    ToolUseEvent,
    UsageInfo,
)

_DEFAULT_MODEL = "claude-sonnet-4-6"


async def anthropic_chat(
    system: str,
    messages: List[Dict[str, Any]],
    max_tokens: int,
    tools: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
) -> Any:
    client = anthropic.AsyncAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
    kwargs: Dict[str, Any] = {
        "model": model or _DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
    return await client.messages.create(**kwargs)


# ── Streaming variant ─────────────────────────────────────────────


async def anthropic_chat_stream(
    system: str,
    messages: List[Dict[str, Any]],
    max_tokens: int = 1024,
    tools: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
) -> AsyncIterator[Any]:
    """
    Yield stream events from Anthropic:
      - TextDeltaEvent(delta)
      - ToolUseEvent(tool_use_id, name, input)  (emitted on content_block_stop)
      - DoneEvent(stop_reason, usage)
    """
    client = anthropic.AsyncAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
    _model = model or os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL)

    kwargs: Dict[str, Any] = dict(
        model=_model, max_tokens=max_tokens, system=system, messages=messages,
    )
    if tools:
        kwargs["tools"] = tools

    tool_use_accum: Dict[int, Dict[str, Any]] = {}
    input_tokens = 0
    output_tokens = 0
    stop_reason = "end_turn"

    async with client.messages.stream(**kwargs) as stream:
        async for event in stream:
            t = getattr(event, "type", None)
            if t == "content_block_start":
                block = getattr(event, "content_block", None)
                if getattr(block, "type", None) == "tool_use":
                    tool_use_accum[event.index] = {
                        "id": block.id, "name": block.name, "json": "",
                    }
            elif t == "content_block_delta":
                d = event.delta
                dtype = getattr(d, "type", None)
                if dtype == "text_delta":
                    yield TextDeltaEvent(delta=d.text)
                elif dtype == "input_json_delta":
                    if event.index in tool_use_accum:
                        tool_use_accum[event.index]["json"] += d.partial_json
            elif t == "content_block_stop":
                if event.index in tool_use_accum:
                    acc = tool_use_accum[event.index]
                    try:
                        parsed = _json.loads(acc["json"]) if acc["json"] else {}
                    except Exception:
                        parsed = {}
                    yield ToolUseEvent(
                        tool_use_id=acc["id"], name=acc["name"], input=parsed,
                    )
            elif t == "message_delta":
                sr = getattr(event.delta, "stop_reason", None)
                if sr:
                    stop_reason = sr
                usage = getattr(event, "usage", None)
                if usage is not None:
                    input_tokens = getattr(usage, "input_tokens", 0) or input_tokens
                    output_tokens = getattr(usage, "output_tokens", 0) or output_tokens

    yield DoneEvent(
        stop_reason=stop_reason,
        usage=UsageInfo(input_tokens=input_tokens, output_tokens=output_tokens),
    )
