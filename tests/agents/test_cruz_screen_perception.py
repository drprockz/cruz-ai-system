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


@pytest.mark.asyncio
async def test_dispatch_screen_perception_success() -> None:
    """Successful analyze() → AgentOutput.success=True, result is the
    sanitized answer string (NOT a dict)."""
    cruz = CruzAgent()
    aw = ActiveWindow(app="Code", window_title="x.py", captured_at=0.0)
    sa = ScreenAnalysis(
        answer="Editing x.py.",
        active_window=aw,
        image_bytes_len=512,
        duration_ms=200,
        tokens_used=120,
    )
    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp:
        mock_get_sp.return_value.analyze = AsyncMock(return_value=sa)
        out = await cruz._dispatch_screen_perception_tool(
            tool_input={}, trace_id="t1",
        )
    assert out["success"] is True
    assert out["result"] == "Editing x.py."   # plain string, not a dict
    assert out["agent"] == cruz.name
    assert out["error"] is None
    assert out["requires_approval"] is False


@pytest.mark.asyncio
async def test_dispatch_screen_perception_with_question() -> None:
    """`question` from tool_input is forwarded to analyze()."""
    cruz = CruzAgent()
    aw = ActiveWindow(app="Code", window_title=None, captured_at=0.0)
    sa = ScreenAnalysis(
        answer="A connection error.", active_window=aw,
        image_bytes_len=1, duration_ms=1, tokens_used=1,
    )
    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp:
        mock_get_sp.return_value.analyze = AsyncMock(return_value=sa)
        await cruz._dispatch_screen_perception_tool(
            tool_input={"question": "what's the error?"}, trace_id="t1",
        )
    mock_get_sp.return_value.analyze.assert_awaited_once_with(
        question="what's the error?"
    )


@pytest.mark.asyncio
async def test_dispatch_screen_perception_failure_returns_error_output() -> None:
    """ScreenPerceptionError → AgentOutput.success=False with error text."""
    cruz = CruzAgent()
    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp:
        mock_get_sp.return_value.analyze = AsyncMock(
            side_effect=ScreenPerceptionError("vision call failed: 503")
        )
        out = await cruz._dispatch_screen_perception_tool(
            tool_input={}, trace_id="t1",
        )
    assert out["success"] is False
    assert out["result"] is None
    assert "vision call failed: 503" in out["error"]
    assert out["requires_approval"] is False


@pytest.mark.asyncio
async def test_dispatch_tool_routes_screen_perception_correctly() -> None:
    """_dispatch_tool routes name='screen_perception' to the new method."""
    cruz = CruzAgent()
    with patch.object(
        cruz, "_dispatch_screen_perception_tool", new=AsyncMock(
            return_value={"success": True, "result": "x", "agent": "CRUZ",
                          "duration_ms": 0, "tokens_used": 0, "error": None,
                          "requires_approval": False, "approval_prompt": None},
        ),
    ) as mock_method:
        await cruz._dispatch_tool(
            tool_name="screen_perception",
            tool_input={"question": "q"},
            trace_id="t",
            conversation_id="c",
        )
    mock_method.assert_awaited_once_with({"question": "q"}, "t")
