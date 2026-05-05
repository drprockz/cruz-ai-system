"""Integration tests: CRUZ ↔ screen_perception tool + runtime-context injection."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agents.cruz.cruz_agent import CRUZ_TOOLS, CruzAgent
from services.screen_perception import (
    ActiveWindow,
    ScreenAnalysis,
    ScreenPerceptionError,
)


def test_screen_perception_tool_registered() -> None:
    """CRUZ_TOOLS must contain a `screen_perception` entry with an
    optional `question` string parameter."""
    matches = [t for t in CRUZ_TOOLS if t["name"] == "screen_perception"]
    assert len(matches) == 1, "screen_perception not registered in CRUZ_TOOLS"
    tool = matches[0]
    assert "question" in tool["input_schema"]["properties"]
    assert tool["input_schema"]["properties"]["question"]["type"] == "string"
    # question is optional — not in required list
    assert "question" not in tool["input_schema"].get("required", [])
