"""
LLM Router — single entry point for all LLM calls across CRUZ.

Usage:
    from services.llm import chat

    response = await chat(
        system="You are CRUZ...",
        messages=[{"role": "user", "content": "hi"}],
        tools=[...],            # Anthropic-style tool schema
        max_tokens=4096,
        backend=None,           # None → read LLM_BACKEND env var
    )
    # response.content (list of ContentBlock), response.stop_reason,
    # response.usage.input_tokens, response.usage.output_tokens
    # Shape is the same whichever backend was used.

Env:
    LLM_BACKEND — "anthropic" (default) | "ollama" | "gemini"
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from services.llm.anthropic_backend import anthropic_chat
from services.llm.gemini_backend import gemini_chat
from services.llm.ollama_backend import ollama_chat

logger = logging.getLogger("cruz.services.llm.router")

_SUPPORTED = ("anthropic", "ollama", "gemini")


def _resolve_backend(backend: Optional[str]) -> str:
    name = (backend or os.environ.get("LLM_BACKEND", "anthropic")).strip().lower()
    if name not in _SUPPORTED:
        raise ValueError(
            f"Unknown LLM_BACKEND '{name}'. "
            f"Supported: {', '.join(_SUPPORTED)}."
        )
    return name


async def chat(
    system: str,
    messages: List[Dict[str, Any]],
    max_tokens: int = 4096,
    tools: Optional[List[Dict[str, Any]]] = None,
    backend: Optional[str] = None,
    model: Optional[str] = None,
) -> Any:
    """
    Route a chat request to the configured LLM backend.

    The return value is duck-typed to match Anthropic's SDK response so
    existing callers can continue to read .content / .stop_reason /
    .usage.input_tokens / .usage.output_tokens without changes.
    """
    resolved = _resolve_backend(backend)
    logger.debug("LLM router: dispatching to backend=%s", resolved)

    if resolved == "anthropic":
        return await anthropic_chat(
            system=system, messages=messages, max_tokens=max_tokens,
            tools=tools, model=model,
        )
    if resolved == "ollama":
        return await ollama_chat(
            system=system, messages=messages, max_tokens=max_tokens,
            tools=tools, model=model,
        )
    if resolved == "gemini":
        return await gemini_chat(
            system=system, messages=messages, max_tokens=max_tokens,
            tools=tools, model=model,
        )
    # Unreachable — _resolve_backend raises for unknown names
    raise RuntimeError(f"router fell through for backend={resolved!r}")
