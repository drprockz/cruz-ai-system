"""Verify _dispatch_tool forwards calendar tool names to CalendarAgent via context.

`_dispatch_tool` reads `_TOOL_AGENT_MAP` at call time, so we patch the map (not
the `CalendarAgent` class name) — patching the class name does not affect
already-bound references in the map. The registry tests in
`test_cruz_tools_registry.py::test_calendar_in_tool_agent_map` separately
verify that the real map points to `CalendarAgent` for these tool names.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.cruz.cruz_agent import CruzAgent


def _fake_agent_output(result):
    return {
        "success": True,
        "result": result,
        "agent": "CALENDAR",
        "duration_ms": 1,
        "tokens_used": 0,
        "error": None,
        "requires_approval": False,
        "approval_prompt": None,
    }


def _calendar_tool_map(fake_cls):
    return {
        "calendar_create_event": fake_cls,
        "calendar_list_events": fake_cls,
        "calendar_find_free_slot": fake_cls,
    }


@pytest.mark.asyncio
async def test_dispatch_calendar_create_event_passes_tool_name_in_context() -> None:
    cruz = CruzAgent()
    fake_agent = MagicMock()
    fake_agent.process = AsyncMock(return_value=_fake_agent_output({"id": "x"}))
    fake_cls = MagicMock(return_value=fake_agent)
    with patch("agents.cruz.cruz_agent._TOOL_AGENT_MAP", _calendar_tool_map(fake_cls)):
        await cruz._dispatch_tool(
            tool_name="calendar_create_event",
            tool_input={
                "title": "Block",
                "start_iso": "2026-05-01T10:00:00",
                "end_iso": "2026-05-01T12:00:00",
            },
            trace_id="t1",
            conversation_id="c1",
        )
    args = fake_agent.process.await_args.args[0]
    assert args["context"]["tool"] == "calendar_create_event"
    assert args["context"]["title"] == "Block"


@pytest.mark.asyncio
async def test_dispatch_calendar_list_events_forwards_tool_name() -> None:
    cruz = CruzAgent()
    fake_agent = MagicMock()
    fake_agent.process = AsyncMock(return_value=_fake_agent_output([]))
    fake_cls = MagicMock(return_value=fake_agent)
    with patch("agents.cruz.cruz_agent._TOOL_AGENT_MAP", _calendar_tool_map(fake_cls)):
        await cruz._dispatch_tool(
            tool_name="calendar_list_events",
            tool_input={
                "start_iso": "2026-05-01T00:00:00",
                "end_iso": "2026-05-02T00:00:00",
            },
            trace_id="t1",
            conversation_id="c1",
        )
    args = fake_agent.process.await_args.args[0]
    assert args["context"]["tool"] == "calendar_list_events"
    assert args["context"]["start_iso"] == "2026-05-01T00:00:00"


@pytest.mark.asyncio
async def test_dispatch_calendar_find_free_slot_forwards_tool_name() -> None:
    cruz = CruzAgent()
    fake_agent = MagicMock()
    fake_agent.process = AsyncMock(
        return_value=_fake_agent_output({"start_iso": "...", "end_iso": "..."})
    )
    fake_cls = MagicMock(return_value=fake_agent)
    with patch("agents.cruz.cruz_agent._TOOL_AGENT_MAP", _calendar_tool_map(fake_cls)):
        await cruz._dispatch_tool(
            tool_name="calendar_find_free_slot",
            tool_input={
                "duration_minutes": 60,
                "earliest_iso": "2026-05-01T09:00:00",
                "latest_iso": "2026-05-01T18:00:00",
            },
            trace_id="t1",
            conversation_id="c1",
        )
    args = fake_agent.process.await_args.args[0]
    assert args["context"]["tool"] == "calendar_find_free_slot"
