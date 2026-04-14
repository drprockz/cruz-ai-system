"""
Normalised response types shared by every LLM backend.

Existing agents (CruzAgent, FORGE, SENTINEL, etc.) were built against
Anthropic's SDK return shape:

    response.content      — list of blocks, each with .type = "text" | "tool_use"
    response.stop_reason  — "end_turn" | "tool_use" | …
    response.usage.input_tokens / .output_tokens

We keep that shape and give the Ollama + Gemini backends simple
dataclass stand-ins. The Anthropic backend passes the real SDK object
through unchanged — same duck-typed access works either way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ContentBlock:
    """A single block in the assistant response.

    For type="text":     text is set
    For type="tool_use": name + input + id are set
    """

    type: str
    text: str = ""
    name: str = ""
    input: Dict[str, Any] = field(default_factory=dict)
    id: str = ""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ChatResponse:
    content: List[ContentBlock] = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)
