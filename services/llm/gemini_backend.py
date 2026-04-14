"""
Gemini backend — REST call to generativelanguage.googleapis.com
generateContent with tool function calling.

Translates:
  Anthropic tool schema   → Gemini function_declarations
  Gemini response parts   → Anthropic-shaped ChatResponse

Env:
  GEMINI_API_KEY — required
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from services.llm.types import ChatResponse, ContentBlock, Usage

logger = logging.getLogger("cruz.services.llm.gemini")

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_MODEL = "gemini-2.5-flash"


async def gemini_chat(
    system: str,
    messages: List[Dict[str, Any]],
    max_tokens: int,
    tools: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
) -> ChatResponse:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set — cannot route LLM calls to Gemini."
        )

    model_name = model or _DEFAULT_MODEL
    url = f"{_API_BASE}/{model_name}:generateContent?key={api_key}"

    payload: Dict[str, Any] = {
        "contents": _to_gemini_contents(messages),
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if system:
        payload["systemInstruction"] = {
            "parts": [{"text": system}],
        }
    if tools:
        payload["tools"] = [{
            "function_declarations": _to_gemini_function_decls(tools),
        }]

    async with httpx.AsyncClient(
        timeout=60.0,
        headers={"Content-Type": "application/json"},
    ) as client:
        resp = await client.post(url, json=payload)

    if resp.status_code >= 300:
        raise RuntimeError(
            f"Gemini chat failed: HTTP {resp.status_code} — {resp.text[:300]}"
        )

    return _gemini_response_to_anthropic(resp.json())


# ── Translation: Anthropic → Gemini ──────────────────────────────────────

def _to_gemini_function_decls(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    decls: List[Dict[str, Any]] = []
    for t in tools:
        decls.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("input_schema", {"type": "object"}),
        })
    return decls


def _to_gemini_contents(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert Anthropic messages to Gemini contents.

    Gemini uses role="user" and role="model"; text is under parts[].text.
    Function responses and calls need richer mapping — we keep the
    minimum shape here to get text round-tripping working end-to-end.
    """
    out: List[Dict[str, Any]] = []
    for msg in messages:
        role = "model" if msg.get("role") == "assistant" else "user"
        content = msg.get("content", "")
        if isinstance(content, str):
            out.append({"role": role, "parts": [{"text": content}]})
        elif isinstance(content, list):
            # Collect readable text from blocks; skip complex tool_use for now
            parts: List[Dict[str, Any]] = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append({"text": block.get("text", "")})
                    elif block.get("type") == "tool_result":
                        parts.append({"text": str(block.get("content", ""))})
                else:
                    text = getattr(block, "text", None)
                    if text:
                        parts.append({"text": text})
            if parts:
                out.append({"role": role, "parts": parts})
    return out


# ── Translation: Gemini → Anthropic ──────────────────────────────────────

def _gemini_response_to_anthropic(raw: Dict[str, Any]) -> ChatResponse:
    candidates = raw.get("candidates") or []
    first = candidates[0] if candidates else {}
    content = first.get("content", {})
    parts = content.get("parts") or []

    blocks: List[ContentBlock] = []
    stop_reason = "end_turn"

    for part in parts:
        if "text" in part and part.get("text"):
            blocks.append(ContentBlock(type="text", text=part["text"]))
        elif "functionCall" in part:
            fc = part["functionCall"]
            blocks.append(ContentBlock(
                type="tool_use",
                name=fc.get("name", ""),
                input=fc.get("args", {}) or {},
                id=fc.get("name", ""),  # Gemini has no id; reuse name
            ))
            stop_reason = "tool_use"

    usage_meta = raw.get("usageMetadata", {})
    return ChatResponse(
        content=blocks,
        stop_reason=stop_reason,
        usage=Usage(
            input_tokens=int(usage_meta.get("promptTokenCount", 0) or 0),
            output_tokens=int(usage_meta.get("candidatesTokenCount", 0) or 0),
        ),
    )
