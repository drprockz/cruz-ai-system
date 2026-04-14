"""
Anthropic backend — thin passthrough to the official Anthropic SDK.

Returns the raw SDK response unchanged, since its duck-typed shape
(.content, .stop_reason, .usage.{input,output}_tokens) is exactly
what our normalised types emulate.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import anthropic

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
