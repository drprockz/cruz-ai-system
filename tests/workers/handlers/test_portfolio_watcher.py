"""Portfolio Watcher handler — weekly per-client tech-news digest."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from workers.handlers.context import HandlerContext
from workers.handlers.portfolio_watcher import handle


@pytest.fixture
def ctx():
    # 2026-04-24 is a Friday in ISO week 17
    return HandlerContext(trace_id="pw-1",
                           now=datetime(2026, 4, 24, 17, 0, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_portfolio_watcher_emits_with_week_dedup(ctx):
    captured = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(dedup_key)
    with patch("workers.handlers.portfolio_watcher._fetch_active_projects",
               AsyncMock(return_value=[{"id": "p1", "name": "AMA",
                                        "slug": "ama-solutions",
                                        "tech_stack": ["nextjs"]}])), \
         patch("workers.handlers.portfolio_watcher._fetch_rss",
               AsyncMock(return_value=[{"title": "Next.js 16 released"}])), \
         patch("workers.handlers.portfolio_watcher._compose_digest",
               AsyncMock(return_value="weekly tech")), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
    assert captured[0] == "portfolio_watcher:2026-W17"


@pytest.mark.asyncio
async def test_portfolio_watcher_handles_no_articles(ctx):
    async def fake_emit(*args, **kwargs):
        pass
    with patch("workers.handlers.portfolio_watcher._fetch_active_projects",
               AsyncMock(return_value=[])), \
         patch("workers.handlers.portfolio_watcher._fetch_rss",
               AsyncMock(return_value=[])), \
         patch("workers.handlers.portfolio_watcher._compose_digest",
               AsyncMock(return_value="quiet week")), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
