from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest
from agents.health_guardian.health_guardian_agent import (
    HealthGuardianAgent, _parse_journal, _compute_streaks,
)
from services.proactive_engine import GateDecision


@pytest.fixture(autouse=True)
def _reset_proactive_engine_singleton():
    import services.proactive_engine as mod
    mod._instance = None
    yield
    mod._instance = None


@pytest.fixture
def agent():
    return HealthGuardianAgent()


def test_parses_journal_entries():
    text = (
        "2026-04-26: sleep=Y commitments=N relationship=Y\n"
        "2026-04-25: sleep=N commitments=N relationship=Y\n"
    )
    entries = _parse_journal(text)
    assert len(entries) == 2
    assert entries[0]["sleep"] == "Y"
    assert entries[1]["commitments"] == "N"


def test_compute_streaks_counts_consecutive_ns():
    entries = [
        {"date": "2026-04-26", "sleep": "N", "commitments": "Y", "relationship": "Y"},
        {"date": "2026-04-25", "sleep": "N", "commitments": "Y", "relationship": "Y"},
        {"date": "2026-04-24", "sleep": "N", "commitments": "Y", "relationship": "Y"},
        {"date": "2026-04-23", "sleep": "Y", "commitments": "Y", "relationship": "N"},
    ]
    streaks = _compute_streaks(entries)
    assert streaks["sleep"] == 3
    assert streaks["commitments"] == 0
    assert streaks["relationship"] == 0


@pytest.mark.asyncio
async def test_streak_3_fires_critical_with_whitelisted_reason(agent, tmp_path):
    journal = tmp_path / "h.md"
    journal.write_text(
        "2026-04-26: sleep=N commitments=Y relationship=Y\n"
        "2026-04-25: sleep=N commitments=Y relationship=Y\n"
        "2026-04-24: sleep=N commitments=Y relationship=Y\n"
    )
    agent.JOURNAL_PATH = str(journal)
    emit_calls = []
    async def fake_emit(severity, reason, dedup_key, payload):
        emit_calls.append((severity, reason))
        return GateDecision.ALLOW
    state = AsyncMock(get=AsyncMock(return_value=[]), set=AsyncMock())
    with patch("agents.health_guardian.health_guardian_agent.get_state_service",
               return_value=state), \
         patch("agents.health_guardian.health_guardian_agent._draft_intervention",
               AsyncMock(return_value="rest up")), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({"task": "event", "context": {"event": {}},
                              "trace_id": "tr", "conversation_id": ""})
    assert ("critical", "health_3n_streak") in emit_calls


@pytest.mark.asyncio
async def test_streak_below_3_emits_info_not_critical(agent, tmp_path):
    journal = tmp_path / "h.md"
    journal.write_text(
        "2026-04-26: sleep=N commitments=Y relationship=Y\n"
        "2026-04-25: sleep=N commitments=Y relationship=Y\n"
        "2026-04-24: sleep=Y commitments=Y relationship=Y\n"
    )
    agent.JOURNAL_PATH = str(journal)
    emit_calls = []
    async def fake_emit(severity, reason, dedup_key, payload):
        emit_calls.append((severity, reason))
        return GateDecision.ALLOW
    state = AsyncMock(get=AsyncMock(return_value=[]), set=AsyncMock())
    with patch("agents.health_guardian.health_guardian_agent.get_state_service",
               return_value=state), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({"task": "event", "context": {"event": {}},
                              "trace_id": "tr", "conversation_id": ""})
    assert all(sev != "critical" for sev, _ in emit_calls)


@pytest.mark.asyncio
async def test_dedup_per_week_iso(agent, tmp_path):
    journal = tmp_path / "h.md"
    journal.write_text(
        "2026-04-26: sleep=N commitments=Y relationship=Y\n"
        "2026-04-25: sleep=N commitments=Y relationship=Y\n"
        "2026-04-24: sleep=N commitments=Y relationship=Y\n"
    )
    agent.JOURNAL_PATH = str(journal)
    captured = []
    async def fake_emit(severity, reason, dedup_key, payload):
        captured.append(dedup_key)
        return GateDecision.ALLOW
    state = AsyncMock(get=AsyncMock(return_value=[]), set=AsyncMock())
    with patch("agents.health_guardian.health_guardian_agent.get_state_service",
               return_value=state), \
         patch("agents.health_guardian.health_guardian_agent._draft_intervention",
               AsyncMock(return_value="x")), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({"task": "event", "context": {"event": {}},
                              "trace_id": "tr", "conversation_id": ""})
    # Dedup must be of the form "streak:<dim>:<YYYY-Www>"
    assert any(":W" in k for k in captured)
