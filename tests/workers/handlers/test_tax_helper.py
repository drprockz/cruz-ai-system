"""Tax Helper handler — quarterly GST/income-tax checklist."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from workers.handlers.context import HandlerContext
from workers.handlers.tax_helper import handle


@pytest.fixture
def ctx():
    return HandlerContext(trace_id="th-1",
                           now=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_tax_helper_emits_with_quarter_dedup_and_creates_notion_draft(ctx):
    captured_dedup = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured_dedup.append(dedup_key)
    notion_calls = []
    async def fake_notion(text, title):
        notion_calls.append((text, title))
        return "https://notion.so/page-id"

    with patch("workers.handlers.tax_helper._fetch_quarter_expenses",
               AsyncMock(return_value=[{"amount": 1000, "category": "software"}])), \
         patch("workers.handlers.tax_helper._compose_tax_checklist",
               AsyncMock(return_value="checklist...")), \
         patch("workers.handlers.tax_helper._create_notion_page_draft",
               fake_notion), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)

    assert result.success is True
    # Apr 1 → Q2 (since Apr is month 4 → (4-1)//3 + 1 = 2)
    assert captured_dedup[0] == "tax_helper:2026-Q2"
    assert len(notion_calls) == 1


@pytest.mark.asyncio
async def test_tax_helper_handles_no_expenses(ctx):
    async def fake_emit(*args, **kwargs): pass
    async def fake_notion(*args): return "url"
    with patch("workers.handlers.tax_helper._fetch_quarter_expenses",
               AsyncMock(return_value=[])), \
         patch("workers.handlers.tax_helper._compose_tax_checklist",
               AsyncMock(return_value="no expenses")), \
         patch("workers.handlers.tax_helper._create_notion_page_draft",
               fake_notion), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
