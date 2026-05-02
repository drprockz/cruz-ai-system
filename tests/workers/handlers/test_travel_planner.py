"""Travel Planner handler — webhook-triggered logistics digest."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from workers.handlers.context import HandlerContext
from workers.handlers.travel_planner import handle


@pytest.fixture
def ctx():
    return HandlerContext(trace_id="tp-1",
                          now=datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_travel_planner_emits_logistics_for_out_of_town_event(ctx, monkeypatch):
    monkeypatch.setenv("HOME_CITY", "Bangalore")
    captured = []

    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append({"dedup_key": dedup_key, "payload": payload})

    with patch("workers.handlers.travel_planner._compose_logistics",
               AsyncMock(return_value="flight + weather + packing")), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle(
            {"id": "evt-1", "location": "Tokyo", "summary": "Conference"},
            ctx,
        )
    assert result.success is True
    assert len(captured) == 1
    assert captured[0]["dedup_key"] == "travel_planner:evt-1"


@pytest.mark.asyncio
async def test_travel_planner_skips_local_events(ctx, monkeypatch):
    monkeypatch.setenv("HOME_CITY", "Bangalore")
    captured = []

    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(payload)

    with patch("workers.handlers.travel_planner._compose_logistics",
               AsyncMock(return_value="should not be called")), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle(
            {"id": "evt-2", "location": "Bangalore Office", "summary": "Standup"},
            ctx,
        )
    assert result.success is True
    assert len(captured) == 0


def test_is_outside_home_city(monkeypatch):
    from workers.handlers.travel_planner import _is_outside_home_city
    monkeypatch.setenv("HOME_CITY", "Bangalore")
    assert _is_outside_home_city("Tokyo, Japan") is True
    assert _is_outside_home_city("Bangalore Office") is False
    assert _is_outside_home_city("bangalore koramangala") is False  # case-insensitive
    assert _is_outside_home_city("") is False  # empty location → not travel
