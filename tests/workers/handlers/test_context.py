"""HandlerContext — info-only emission surface for SP5 handlers.

Per spec §5: handlers cannot fire warn/critical. The HandlerContext type
deliberately exposes only emit_info(); the full emit() exists only on
EventDrivenAgent. This is structural enforcement, not convention.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services.proactive_engine import GateDecision
from workers.handlers.context import HandlerContext, HandlerResult


@pytest.fixture
def ctx():
    return HandlerContext(trace_id="trace-1", now=datetime.now(timezone.utc))


def test_handler_context_exposes_only_emit_info_method(ctx):
    """The whole point: no emit_warn or emit_critical method exists."""
    assert hasattr(ctx, "emit_info")
    assert not hasattr(ctx, "emit_warn")
    assert not hasattr(ctx, "emit_critical")
    assert not hasattr(ctx, "emit")


@pytest.mark.asyncio
async def test_emit_info_routes_through_gate_at_info_severity(ctx):
    captured = []
    async def fake_allow(req):
        captured.append(req)
        return GateDecision.ALLOW
    fake_router = AsyncMock()
    with patch("workers.handlers.context.get_proactive_engine") as eng, \
         patch("workers.handlers.context.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=fake_allow)
        router.return_value = fake_router
        result = await ctx.emit_info(
            handler_name="daily_briefing",
            reason="daily_summary",
            dedup_key="2026-04-26",
            payload={"text": "hi"},
        )
    assert result == GateDecision.ALLOW
    assert captured[0].severity == "info"
    assert captured[0].agent == "daily_briefing"
    fake_router.route.assert_awaited_once_with("info", {
        "text": "hi", "agent": "daily_briefing", "dedup_key": "2026-04-26",
    })


@pytest.mark.asyncio
async def test_emit_info_suppress_does_not_route(ctx):
    fake_router = AsyncMock()
    with patch("workers.handlers.context.get_proactive_engine") as eng, \
         patch("workers.handlers.context.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=AsyncMock(return_value=GateDecision.SUPPRESS))
        router.return_value = fake_router
        await ctx.emit_info("h", "r", "k", {"text": "x"})
    fake_router.route.assert_not_awaited()


def test_handler_result_dataclass_shape():
    r = HandlerResult(handler_name="x", success=True, summary="done")
    assert r.handler_name == "x"
    assert r.success is True
    assert r.summary == "done"
    assert r.error is None


def test_handler_context_has_kb_and_db_accessors(ctx):
    """kb and db are lazily initialised — verify accessors exist without
    instantiating the real singletons (which would require a live DB)."""
    assert hasattr(ctx, "kb")
    assert hasattr(ctx, "db")
