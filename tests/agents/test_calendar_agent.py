"""Unit tests for CalendarAgent."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.calendar.calendar_agent import CalendarAgent


def _input(task: str, **context):
    return {
        "task": task,
        "context": context,
        "trace_id": "trace-1",
        "conversation_id": "conv-1",
    }


# ── KNOWLEDGE_RINGS declared per Charter Rule 3 ───────────────────────


def test_knowledge_rings_declared() -> None:
    assert CalendarAgent.KNOWLEDGE_RINGS == [
        "cruz_activities",
        "cruz_user_patterns",
    ]


def test_agent_name() -> None:
    a = CalendarAgent()
    assert a.name == "CALENDAR"


# ── find_free_slot — pure algorithm ───────────────────────────────────


@pytest.mark.asyncio
async def test_find_free_slot_no_busy_returns_first_window() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.list_events = AsyncMock(return_value=[])

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        out = await agent.process(_input(
            task="find_free_slot",
            tool="calendar_find_free_slot",
            duration_minutes=60,
            earliest_iso="2026-05-01T09:00:00",
            latest_iso="2026-05-01T18:00:00",
        ))

    assert out["success"] is True
    assert out["result"]["start_iso"] == "2026-05-01T09:00:00"
    assert out["result"]["end_iso"] == "2026-05-01T10:00:00"


@pytest.mark.asyncio
async def test_find_free_slot_skips_busy_block() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.list_events = AsyncMock(return_value=[
        {"start": {"dateTime": "2026-05-01T09:00:00"},
         "end":   {"dateTime": "2026-05-01T10:30:00"}},
    ])

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        out = await agent.process(_input(
            task="find_free_slot",
            tool="calendar_find_free_slot",
            duration_minutes=60,
            earliest_iso="2026-05-01T09:00:00",
            latest_iso="2026-05-01T18:00:00",
        ))

    assert out["result"]["start_iso"] == "2026-05-01T10:30:00"
    assert out["result"]["end_iso"] == "2026-05-01T11:30:00"


@pytest.mark.asyncio
async def test_find_free_slot_no_gap_returns_failure() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    # One huge meeting fills the whole window.
    fake_gcal.list_events = AsyncMock(return_value=[
        {"start": {"dateTime": "2026-05-01T09:00:00"},
         "end":   {"dateTime": "2026-05-01T18:00:00"}},
    ])
    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        out = await agent.process(_input(
            task="find_free_slot",
            tool="calendar_find_free_slot",
            duration_minutes=60,
            earliest_iso="2026-05-01T09:00:00",
            latest_iso="2026-05-01T18:00:00",
        ))
    assert out["success"] is False
    assert "no free slot" in out["error"].lower()


@pytest.mark.asyncio
async def test_find_free_slot_kb_hooks_fire() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="## Your patterns\n- prefers mornings")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.list_events = AsyncMock(return_value=[])
    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        await agent.process(_input(
            task="find_free_slot for 60min tomorrow morning",
            tool="calendar_find_free_slot",
            duration_minutes=60,
            earliest_iso="2026-05-01T09:00:00",
            latest_iso="2026-05-01T18:00:00",
        ))
    fake_kb.build_agent_context.assert_awaited_once()
    fake_kb.record_agent_activity.assert_awaited_once()
    args = fake_kb.build_agent_context.await_args
    assert args.args[1] == ["cruz_activities", "cruz_user_patterns"]
