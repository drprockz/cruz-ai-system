"""Expense Auditor handler — monthly Gmail receipts + Notion log digest."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from workers.handlers.context import HandlerContext
from workers.handlers.expense_auditor import handle


@pytest.fixture
def ctx():
    return HandlerContext(trace_id="ea-1",
                           now=datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_expense_auditor_emits_with_month_dedup(ctx):
    captured = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(dedup_key)
    with patch("workers.handlers.expense_auditor._fetch_gmail_receipts",
               AsyncMock(return_value=[{"id": "r1", "amount": 100}])), \
         patch("workers.handlers.expense_auditor._fetch_notion_expenses",
               AsyncMock(return_value=[])), \
         patch("workers.handlers.expense_auditor._compose_summary",
               AsyncMock(return_value="reviewed")), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
    assert captured[0] == "expense_auditor:2026-05"


@pytest.mark.asyncio
async def test_expense_auditor_handles_no_input(ctx):
    captured = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(payload["text"])
    with patch("workers.handlers.expense_auditor._fetch_gmail_receipts",
               AsyncMock(return_value=[])), \
         patch("workers.handlers.expense_auditor._fetch_notion_expenses",
               AsyncMock(return_value=[])), \
         patch("workers.handlers.expense_auditor._compose_summary",
               AsyncMock(return_value="no expenses found")), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
