"""
Expense Auditor handler — runs at cron.monthly.1st.09:00.

Aggregates last-30d vendor receipts from Gmail with the Notion expense
log, categorizes them, and surfaces missing receipts as a single
info-tier Telegram digest.

Per spec §5. The Gmail/Notion fetchers + LLM summarizer are stubs until
Chunk 8 wires the integrations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from workers.handlers.context import HandlerContext, HandlerResult

logger = logging.getLogger("cruz.workers.handlers.expense_auditor")

HANDLER_NAME = "expense_auditor"

LOOKBACK_DAYS = 30


async def _fetch_gmail_receipts(context: HandlerContext, days: int) -> List[Dict[str, Any]]:
    """Fetch vendor receipt emails from Gmail over the last `days` days.

    Stubbed until Chunk 8 wiring connects the Gmail integration.
    """
    raise NotImplementedError("connect Gmail/Notion in Chunk 8 wiring")


async def _fetch_notion_expenses(context: HandlerContext, days: int) -> List[Dict[str, Any]]:
    """Fetch expense rows from the Notion expense log over the last `days` days.

    Stubbed until Chunk 8 wiring connects the Notion integration.
    """
    raise NotImplementedError("connect Gmail/Notion in Chunk 8 wiring")


async def _compose_summary(
    receipts: List[Dict[str, Any]],
    notion_expenses: List[Dict[str, Any]],
) -> str:
    """Compose the digest body summarizing categories + missing receipts.

    Stubbed until Chunk 8 wiring connects the LLM call.
    """
    raise NotImplementedError("connect Gmail/Notion in Chunk 8 wiring")


async def handle(payload: Dict[str, Any], context: HandlerContext) -> HandlerResult:
    """Run the monthly expense audit.

    Args:
        payload: ARQ-supplied payload (unused for cron-triggered handlers)
        context: HandlerContext with kb/db/trace_id/now/emit_info
    """
    month_label = context.now.strftime("%Y-%m")

    gmail_failed = False
    notion_failed = False
    compose_failed = False

    try:
        receipts = await _fetch_gmail_receipts(context, LOOKBACK_DAYS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("expense_auditor: gmail fetch failed: %s", exc)
        receipts = []
        gmail_failed = True

    try:
        notion_expenses = await _fetch_notion_expenses(context, LOOKBACK_DAYS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("expense_auditor: notion fetch failed: %s", exc)
        notion_expenses = []
        notion_failed = True

    try:
        summary_body = await _compose_summary(receipts, notion_expenses)
    except Exception as exc:  # noqa: BLE001
        logger.warning("expense_auditor: compose failed: %s", exc)
        summary_body = "Expense summary unavailable (compose failed)."
        compose_failed = True

    text = (
        f"💸 *Expense audit — {month_label}*\n\n"
        f"Gmail receipts: {len(receipts)}\n"
        f"Notion expenses: {len(notion_expenses)}\n\n"
        f"{summary_body}"
    )

    decision = await context.emit_info(
        handler_name=HANDLER_NAME,
        reason="monthly_expense_audit",
        dedup_key=f"{HANDLER_NAME}:{month_label}",
        payload={"text": text, "trace_id": context.trace_id},
    )
    decision_label = getattr(decision, "value", str(decision))

    any_failed = gmail_failed or notion_failed or compose_failed
    error: Optional[str] = None
    if any_failed:
        failed_parts = []
        if gmail_failed:
            failed_parts.append("gmail")
        if notion_failed:
            failed_parts.append("notion")
        if compose_failed:
            failed_parts.append("compose")
        error = f"fetch_failed:{','.join(failed_parts)}"

    result_kwargs: Dict[str, Any] = {
        "handler_name": HANDLER_NAME,
        "success": not any_failed,
        "summary": (
            f"emitted: {decision_label}, "
            f"receipts={len(receipts)}, notion={len(notion_expenses)}"
        ),
        "metadata": {
            "receipt_count": len(receipts),
            "notion_count": len(notion_expenses),
            "gmail_failed": gmail_failed,
            "notion_failed": notion_failed,
            "compose_failed": compose_failed,
        },
    }
    if error:
        result_kwargs["error"] = error
    return HandlerResult(**result_kwargs)
