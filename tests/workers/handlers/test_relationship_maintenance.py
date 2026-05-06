"""Relationship Maintenance handler — weekly stale-contact reminder."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from workers.handlers.context import HandlerContext
from workers.handlers.relationship_maintenance import (
    handle, _filter_stale_contacts,
)


@pytest.fixture
def ctx():
    return HandlerContext(trace_id="rm-1",
                           now=datetime(2026, 4, 26, 18, 0, tzinfo=timezone.utc))


def test_filter_excludes_recent_contacts(ctx):
    """Anyone messaged within 42 days is excluded."""
    fresh_ts = (ctx.now - timedelta(days=10)).timestamp()
    contacts = {
        "fresh@x.com": {"last_contact_ts": fresh_ts, "contact_count": 5},
    }
    assert _filter_stale_contacts(contacts, ctx.now) == []


def test_filter_excludes_one_offs(ctx):
    """Less than 3 prior contacts → excluded (avoids spam noise)."""
    stale_ts = (ctx.now - timedelta(days=60)).timestamp()
    contacts = {
        "oneoff@x.com": {"last_contact_ts": stale_ts, "contact_count": 1},
    }
    assert _filter_stale_contacts(contacts, ctx.now) == []


@pytest.mark.asyncio
async def test_relationship_emits_with_week_dedup(ctx):
    captured = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(dedup_key)
    stale_ts = (ctx.now - timedelta(days=60)).timestamp()
    with patch("workers.handlers.relationship_maintenance._compute_last_contact_map",
               AsyncMock(return_value={
                   "x@y.com": {"last_contact_ts": stale_ts, "contact_count": 5},
               })), \
         patch("workers.handlers.relationship_maintenance._compose_message",
               AsyncMock(return_value="ping x@y.com")), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
    # 2026-04-26 is Sunday in ISO week 17
    assert captured[0] == "relationship_maintenance:2026-W17"
