"""Daily Briefing handler — 7am digest of yesterday's agent activity."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from workers.handlers.context import HandlerContext
from workers.handlers.daily_briefing import handle


@pytest.fixture
def ctx():
    return HandlerContext(trace_id="db-trace-1",
                           now=datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_daily_briefing_emits_summary_with_pings_count(ctx):
    """Handler queries agent_logs for last 24h, builds digest, emits info."""
    # Fake DB returns 5 successful agent logs + 1 false_critical ack
    fake_db_rows = [
        {"agent": "reply_triage", "action": "process", "status": "success"},
        {"agent": "reply_triage", "action": "process", "status": "success"},
        {"agent": "followup", "action": "process", "status": "success"},
        {"agent": "health_guardian", "action": "gate_decision", "status": "allow"},
        {"agent": "reply_triage", "action": "gate_decision", "status": "demote_warn"},
    ]
    captured_emit: list[dict] = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured_emit.append({"handler": handler_name, "payload": payload})

    with patch.object(ctx, "_db", AsyncMock(fetch=AsyncMock(return_value=fake_db_rows))), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)

    assert result.success is True
    assert len(captured_emit) == 1
    text = captured_emit[0]["payload"]["text"]
    # Must mention agent breakdown
    assert "reply_triage" in text
    # Must mention gate prevention
    assert "demote" in text.lower() or "prevented" in text.lower()


@pytest.mark.asyncio
async def test_daily_briefing_dedup_key_is_date():
    """Same date = same dedup key — re-running on same day suppresses."""
    ctx = HandlerContext(trace_id="t",
                          now=datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc))
    captured = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(dedup_key)
    with patch.object(ctx, "_db",
                      AsyncMock(fetch=AsyncMock(return_value=[]))), \
         patch.object(ctx, "emit_info", fake_emit):
        await handle({}, ctx)
    assert captured[0] == "daily_briefing:2026-04-26"


@pytest.mark.asyncio
async def test_daily_briefing_handles_empty_window_gracefully(ctx):
    """No agent activity in last 24h → still emits digest saying so."""
    captured: list[str] = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(payload["text"])
    with patch.object(ctx, "_db",
                      AsyncMock(fetch=AsyncMock(return_value=[]))), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
    assert any("no activity" in t.lower() or "0" in t for t in captured)


@pytest.mark.asyncio
async def test_daily_briefing_marks_failure_when_db_query_throws():
    """DB failure → result.success is False, error is set, but we still emit
    a digest so the user isn't left in silence."""
    ctx = HandlerContext(trace_id="t",
                          now=datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc))
    captured = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(payload)

    bad_db = AsyncMock()
    bad_db.fetch = AsyncMock(side_effect=RuntimeError("postgres unreachable"))
    with patch.object(ctx, "_db", bad_db), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)

    assert result.success is False
    assert result.error == "db_query_failed"
    assert result.metadata.get("db_failed") is True
    assert len(captured) == 1  # still emitted a digest
