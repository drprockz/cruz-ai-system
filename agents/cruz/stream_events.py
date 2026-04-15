"""Event dataclasses emitted by CruzAgent.stream_response()."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Text:
    content: str           # a full sentence ready for TTS


@dataclass
class ToolStart:
    agent: str
    summary: str            # short human-readable, e.g. "Running tests..."


@dataclass
class ToolFinish:
    agent: str
    result_preview: str


@dataclass
class ApprovalRequired:
    agent: str
    prompt: str
    payload: Dict[str, Any]


@dataclass
class Done:
    tokens_used: int
    duration_ms: int
