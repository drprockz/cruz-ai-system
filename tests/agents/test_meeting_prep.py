"""MeetingPrepAgent — SP5 §4.3.

warn-only; 25-35min event window; attendee thread + Notion notes context.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.meeting_prep.meeting_prep_agent import MeetingPrepAgent
from services.proactive_engine import GateDecision


@pytest.fixture(autouse=True)
def _reset_proactive_engine_singleton():
    import services.proactive_engine as mod

    mod._instance = None
    yield
    mod._instance = None


@pytest.fixture
def agent():
    return MeetingPrepAgent()


def _iso_in(seconds_from_now: float) -> str:
    """Build an ISO-8601 UTC string `seconds_from_now` from now."""
    dt = datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now)
    # Drop microseconds for clarity; .isoformat() with tzinfo includes "+00:00".
    return dt.replace(microsecond=0).isoformat()


def _evt(event_id: str, seconds_from_now: float, summary: str = "Standup"):
    return {
        "id": event_id,
        "summary": summary,
        "start": {"dateTime": _iso_in(seconds_from_now)},
        "attendees": [{"email": "ateet@ama.com"}],
    }


def test_class_attrs_match_spec(agent):
    assert agent.KNOWLEDGE_RINGS == ["cruz_activities", "cruz_projects_docs"]
    assert agent.TRIGGERS == ["webhook.google-calendar"]
    assert agent.CRITICAL_REASONS == {}


@pytest.mark.asyncio
async def test_filters_to_25_to_35min_window(agent):
    """Events outside the 25-35min window are NOT emitted; events inside are."""
    events = [
        _evt("too-soon", 10 * 60, "Too soon"),     # 10min → outside (below)
        _evt("in-window", 30 * 60, "In window"),  # 30min → inside
        _evt("too-far", 60 * 60, "Too far"),      # 60min → outside (above)
    ]
    emit_calls = []

    async def fake_emit(severity, reason, dedup_key, payload):
        emit_calls.append((severity, reason, dedup_key))
        return GateDecision.ALLOW

    with patch(
        "agents.meeting_prep.meeting_prep_agent._fetch_upcoming_events",
        AsyncMock(return_value=events),
    ), patch(
        "agents.meeting_prep.meeting_prep_agent.fetch_recent_with_attendee",
        AsyncMock(return_value=[]),
    ), patch(
        "agents.meeting_prep.meeting_prep_agent._fetch_meeting_notes",
        AsyncMock(return_value=None),
    ), patch(
        "agents.meeting_prep.meeting_prep_agent._compose_telegram_body",
        AsyncMock(return_value="body"),
    ), patch(
        "agents.meeting_prep.meeting_prep_agent.get_kb_service",
        return_value=MagicMock(record_agent_activity=AsyncMock()),
    ), patch.object(agent, "emit", fake_emit):
        result = await agent.process({
            "task": "event:webhook.google-calendar",
            "context": {"event": {"trigger": "webhook.google-calendar",
                                  "data": {"headers": {}, "resource_state": "exists"}}},
            "trace_id": "tr-1",
            "conversation_id": "",
        })

    assert result["success"] is True
    dedup_keys = [d for _, _, d in emit_calls]
    assert dedup_keys == ["meeting:in-window"], (
        f"expected only the 30min event to fire; got {dedup_keys!r}"
    )


@pytest.mark.asyncio
async def test_dedup_per_event_id(agent):
    """Two passes with the same event_id produce the same dedup_key."""
    event = _evt("evt-XYZ", 30 * 60)
    captured: list[str] = []

    async def fake_emit(severity, reason, dedup_key, payload):
        captured.append(dedup_key)
        return GateDecision.ALLOW

    with patch(
        "agents.meeting_prep.meeting_prep_agent._fetch_upcoming_events",
        AsyncMock(return_value=[event]),
    ), patch(
        "agents.meeting_prep.meeting_prep_agent.fetch_recent_with_attendee",
        AsyncMock(return_value=[]),
    ), patch(
        "agents.meeting_prep.meeting_prep_agent._fetch_meeting_notes",
        AsyncMock(return_value=None),
    ), patch(
        "agents.meeting_prep.meeting_prep_agent._compose_telegram_body",
        AsyncMock(return_value="body"),
    ), patch(
        "agents.meeting_prep.meeting_prep_agent.get_kb_service",
        return_value=MagicMock(record_agent_activity=AsyncMock()),
    ), patch.object(agent, "emit", fake_emit):
        for _ in range(2):
            await agent.process({
                "task": "event:webhook.google-calendar",
                "context": {"event": {"trigger": "webhook.google-calendar",
                                      "data": {}}},
                "trace_id": "tr",
                "conversation_id": "",
            })

    assert captured == ["meeting:evt-XYZ", "meeting:evt-XYZ"], captured


@pytest.mark.asyncio
async def test_emits_at_warn_never_critical(agent):
    """CRITICAL_REASONS is empty; agent must only ever request severity=warn."""
    event = _evt("evt-1", 30 * 60)
    sev_seen: list[str] = []

    async def fake_emit(severity, reason, dedup_key, payload):
        sev_seen.append(severity)
        # Reason must be None when severity != critical (gate would reject otherwise).
        assert severity != "critical", (
            "MeetingPrepAgent must never attempt a critical emit"
        )
        return GateDecision.ALLOW

    with patch(
        "agents.meeting_prep.meeting_prep_agent._fetch_upcoming_events",
        AsyncMock(return_value=[event]),
    ), patch(
        "agents.meeting_prep.meeting_prep_agent.fetch_recent_with_attendee",
        AsyncMock(return_value=[]),
    ), patch(
        "agents.meeting_prep.meeting_prep_agent._fetch_meeting_notes",
        AsyncMock(return_value=None),
    ), patch(
        "agents.meeting_prep.meeting_prep_agent._compose_telegram_body",
        AsyncMock(return_value="body"),
    ), patch(
        "agents.meeting_prep.meeting_prep_agent.get_kb_service",
        return_value=MagicMock(record_agent_activity=AsyncMock()),
    ), patch.object(agent, "emit", fake_emit):
        await agent.process({
            "task": "event:webhook.google-calendar",
            "context": {"event": {"trigger": "webhook.google-calendar",
                                  "data": {}}},
            "trace_id": "tr",
            "conversation_id": "",
        })

    assert sev_seen == ["warn"]


@pytest.mark.asyncio
async def test_gmail_helper_smoke():
    """Smoke test for the new fetch_recent_with_attendee helper added to
    gmail_client. Empty email short-circuits to []; the API client is not
    constructed."""
    from agents.reply_triage.gmail_client import _fetch_recent_with_attendee_sync

    assert _fetch_recent_with_attendee_sync("", 5) == []
