"""Unit tests for CalendarAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.calendar.calendar_agent import CalendarAgent
from services.gcal import GCalError
from services.mac_controller import MacControllerError


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


# ── list_events ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_events_returns_passthrough() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.list_events = AsyncMock(return_value=[
        {"id": "e1", "summary": "Standup"},
        {"id": "e2", "summary": "Client call"},
    ])
    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        out = await agent.process(_input(
            task="list events tomorrow",
            tool="calendar_list_events",
            start_iso="2026-05-01T00:00:00",
            end_iso="2026-05-02T00:00:00",
        ))
    assert out["success"] is True
    assert len(out["result"]) == 2
    assert out["result"][0]["id"] == "e1"
    assert out["requires_approval"] is False


@pytest.mark.asyncio
async def test_list_events_uses_calendar_id_override() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.list_events = AsyncMock(return_value=[])
    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        await agent.process(_input(
            task="list",
            tool="calendar_list_events",
            start_iso="2026-05-01T00:00:00",
            end_iso="2026-05-02T00:00:00",
            calendar_id="ama-shared@group.calendar.google.com",
        ))
    fake_gcal.list_events.assert_awaited_once_with(
        "2026-05-01T00:00:00",
        "2026-05-02T00:00:00",
        calendar_id="ama-shared@group.calendar.google.com",
    )


@pytest.mark.asyncio
async def test_list_events_propagates_gcal_error() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.list_events = AsyncMock(side_effect=GCalError("Google API error 401"))
    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        out = await agent.process(_input(
            task="list",
            tool="calendar_list_events",
            start_iso="2026-05-01T00:00:00",
            end_iso="2026-05-02T00:00:00",
        ))
    assert out["success"] is False
    assert "401" in out["error"]


# ── create_event — self-only auto-create ──────────────────────────────


@pytest.mark.asyncio
async def test_create_event_self_only_writes_google_and_mirrors() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_kb.observe_interaction = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.create_event = AsyncMock(return_value={
        "id": "ev1", "htmlLink": "https://...", "summary": "Deep work",
    })
    fake_mac = MagicMock()
    fake_mac._calendar_create_local = AsyncMock(return_value=None)

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal), \
         patch("agents.calendar.calendar_agent.get_mac_controller_service", return_value=fake_mac):
        out = await agent.process(_input(
            task="block 10am-12pm tomorrow for AMA",
            tool="calendar_create_event",
            title="Deep work",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T12:00:00",
        ))

    assert out["success"] is True
    assert out["requires_approval"] is False
    assert out["result"]["id"] == "ev1"
    fake_gcal.create_event.assert_awaited_once()
    fake_mac._calendar_create_local.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_event_self_only_observes_hour_pattern() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_kb.observe_interaction = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.create_event = AsyncMock(return_value={"id": "ev1"})
    fake_mac = MagicMock()
    fake_mac._calendar_create_local = AsyncMock()

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal), \
         patch("agents.calendar.calendar_agent.get_mac_controller_service", return_value=fake_mac):
        await agent.process(_input(
            task="block 10am-12pm",
            tool="calendar_create_event",
            title="x",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T12:00:00",
        ))

    fake_kb.observe_interaction.assert_awaited_once_with(
        "calendar", "preferred_block_hour", "10",
    )


@pytest.mark.asyncio
async def test_create_event_mirror_failure_is_non_fatal() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_kb.observe_interaction = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.create_event = AsyncMock(return_value={"id": "ev1"})
    fake_mac = MagicMock()
    fake_mac._calendar_create_local = AsyncMock(
        side_effect=MacControllerError("Calendar.app not running"),
    )

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal), \
         patch("agents.calendar.calendar_agent.get_mac_controller_service", return_value=fake_mac):
        out = await agent.process(_input(
            task="block",
            tool="calendar_create_event",
            title="x",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T11:00:00",
        ))

    assert out["success"] is True  # Google succeeded → call succeeds
    assert out["result"]["id"] == "ev1"
    assert out["result"].get("mirror_warning") is not None


@pytest.mark.asyncio
async def test_create_event_google_failure_is_fatal() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_kb.observe_interaction = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.create_event = AsyncMock(side_effect=GCalError("quota exceeded"))
    fake_mac = MagicMock()
    fake_mac._calendar_create_local = AsyncMock()

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal), \
         patch("agents.calendar.calendar_agent.get_mac_controller_service", return_value=fake_mac):
        out = await agent.process(_input(
            task="block",
            tool="calendar_create_event",
            title="x",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T11:00:00",
        ))

    assert out["success"] is False
    assert "quota" in out["error"]
    fake_mac._calendar_create_local.assert_not_awaited()


# ── create_event — attendees → approval gate ──────────────────────────


@pytest.mark.asyncio
async def test_create_event_with_attendees_requires_approval_by_default() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_kb.observe_interaction = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.create_event = AsyncMock()
    fake_mac = MagicMock()

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal), \
         patch("agents.calendar.calendar_agent.get_mac_controller_service", return_value=fake_mac):
        out = await agent.process(_input(
            task="set up sync with Acme",
            tool="calendar_create_event",
            title="Sync",
            start_iso="2026-05-01T15:00:00",
            end_iso="2026-05-01T15:30:00",
            attendees=["client@acme.com"],
        ))

    assert out["requires_approval"] is True
    assert out["success"] is True
    assert "client@acme.com" in out["approval_prompt"]
    fake_gcal.create_event.assert_not_awaited()  # nothing sent


@pytest.mark.asyncio
async def test_create_event_with_attendees_send_true_actually_sends() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_kb.observe_interaction = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.create_event = AsyncMock(return_value={"id": "ev2"})
    fake_mac = MagicMock()
    fake_mac._calendar_create_local = AsyncMock()

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal), \
         patch("agents.calendar.calendar_agent.get_mac_controller_service", return_value=fake_mac):
        out = await agent.process(_input(
            task="confirmed — send the invite",
            tool="calendar_create_event",
            title="Sync",
            start_iso="2026-05-01T15:00:00",
            end_iso="2026-05-01T15:30:00",
            attendees=["client@acme.com"],
            send=True,
        ))

    assert out["requires_approval"] is False
    assert out["success"] is True
    fake_gcal.create_event.assert_awaited_once()
    body_kwargs = fake_gcal.create_event.await_args.kwargs
    assert body_kwargs["attendees"] == ["client@acme.com"]
    # observe_interaction must NOT fire on attendees-present path
    # (KB pattern learning is gated to self-only successful creates).
    fake_kb.observe_interaction.assert_not_awaited()
