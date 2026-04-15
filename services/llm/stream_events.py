"""Stream event dataclasses for CRUZ's streaming LLM layer."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class UsageInfo:
    input_tokens: int
    output_tokens: int


@dataclass
class TextDeltaEvent:
    delta: str


@dataclass
class ToolUseEvent:
    tool_use_id: str
    name: str
    input: Dict[str, Any]


@dataclass
class ToolResultEvent:
    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass
class DoneEvent:
    stop_reason: str
    usage: UsageInfo
