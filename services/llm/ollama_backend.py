"""
Ollama backend — uses Ollama's OpenAI-compatible /v1/chat/completions
endpoint with tool-calling support on qwen2.5-coder:14b.

Translates:
  Anthropic tool schema → OpenAI tool schema (at call time)
  OpenAI response      → Anthropic-shaped ChatResponse (on return)

This keeps callers (CruzAgent, FORGE, SENTINEL, GeneralAgent) unchanged
when LLM_BACKEND=ollama — they read .content blocks, .stop_reason,
and .usage the same way as before.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from services.llm.types import ChatResponse, ContentBlock, Usage

logger = logging.getLogger("cruz.services.llm.ollama")

_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
_DEFAULT_MODEL = "qwen2.5-coder:14b"


async def ollama_chat(
    system: str,
    messages: List[Dict[str, Any]],
    max_tokens: int,
    tools: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
) -> ChatResponse:
    payload: Dict[str, Any] = {
        "model": model or _DEFAULT_MODEL,
        "messages": _anthropic_msgs_to_openai(system, messages),
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = _anthropic_tools_to_openai(tools)

    base_url = os.getenv("OLLAMA_URL", _OLLAMA_URL).rstrip("/")
    async with httpx.AsyncClient(
        timeout=120.0,
        headers={"Content-Type": "application/json"},
    ) as client:
        resp = await client.post(f"{base_url}/v1/chat/completions", json=payload)

    if resp.status_code >= 300:
        raise RuntimeError(
            f"Ollama chat failed: HTTP {resp.status_code} — {resp.text[:300]}"
        )

    return _openai_response_to_anthropic(resp.json())


# ── Translation: Anthropic → OpenAI ───────────────────────────────────────

def _anthropic_tools_to_openai(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Anthropic tool spec ({name, description, input_schema}) → OpenAI function spec."""
    out: List[Dict[str, Any]] = []
    for t in tools:
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object"}),
            },
        })
    return out


def _anthropic_msgs_to_openai(
    system: str, messages: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Convert Anthropic message list into OpenAI format.

    System is prepended as first message. Assistant tool_use blocks become
    tool_calls. User tool_result entries become tool-role messages with
    tool_call_id.
    """
    out: List[Dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Plain string — pass through
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        # List of blocks — need per-role handling
        if isinstance(content, list):
            if role == "assistant":
                # Assistant blocks may contain text and tool_use
                tool_calls: List[Dict[str, Any]] = []
                text_parts: List[str] = []
                for block in content:
                    b_type = _block_attr(block, "type")
                    if b_type == "tool_use":
                        tool_calls.append({
                            "id": _block_attr(block, "id", ""),
                            "type": "function",
                            "function": {
                                "name": _block_attr(block, "name", ""),
                                "arguments": json.dumps(
                                    _block_attr(block, "input", {})
                                ),
                            },
                        })
                    elif b_type == "text":
                        text_parts.append(_block_attr(block, "text", ""))
                assistant_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": "\n".join(text_parts) if text_parts else None,
                }
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                out.append(assistant_msg)

            elif role == "user":
                # User may carry tool_result blocks alongside text
                other_parts: List[str] = []
                for block in content:
                    b_type = _block_attr(block, "type")
                    if b_type == "tool_result":
                        out.append({
                            "role": "tool",
                            "tool_call_id": _block_attr(block, "tool_use_id", ""),
                            "content": str(_block_attr(block, "content", "")),
                        })
                    elif b_type == "text":
                        other_parts.append(_block_attr(block, "text", ""))
                    else:
                        # Unknown block — stringify to keep the message
                        other_parts.append(str(block))
                if other_parts:
                    out.append({"role": "user", "content": "\n".join(other_parts)})
            else:
                # Unknown role with list content — flatten to string
                out.append({"role": role, "content": str(content)})
    return out


def _block_attr(block: Any, attr: str, default: Any = None) -> Any:
    """Read attr from either a dict-shaped block or a duck-typed object."""
    if isinstance(block, dict):
        return block.get(attr, default)
    return getattr(block, attr, default)


# ── Translation: OpenAI → Anthropic ───────────────────────────────────────

def _openai_response_to_anthropic(raw: Dict[str, Any]) -> ChatResponse:
    choices = raw.get("choices") or [{}]
    first = choices[0]
    message = first.get("message", {})
    finish = first.get("finish_reason", "stop")
    usage = raw.get("usage", {})

    blocks: List[ContentBlock] = []
    text = message.get("content") or ""
    if text:
        blocks.append(ContentBlock(type="text", text=text))

    for call in message.get("tool_calls") or []:
        fn = call.get("function", {})
        args_raw = fn.get("arguments", "{}")
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except json.JSONDecodeError:
            args = {"_raw": args_raw}
        blocks.append(ContentBlock(
            type="tool_use",
            name=fn.get("name", ""),
            input=args if isinstance(args, dict) else {"value": args},
            id=call.get("id", ""),
        ))

    stop_reason = "tool_use" if finish == "tool_calls" else "end_turn"

    return ChatResponse(
        content=blocks,
        stop_reason=stop_reason,
        usage=Usage(
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
        ),
    )
