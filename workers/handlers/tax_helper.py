"""
Tax Helper handler — runs at cron.quarterly.1st.10:00 (Apr/Jul/Oct/Jan).

Computes the current quarter's GST + income-tax checklist from expense
data, drafts a Notion page for the user to review, and surfaces a
Telegram digest with the checklist body.

Per spec §5.

# Rule 8 override:
# Charter Rule 2 (default agents to Qwen 14B) is overridden here. Tax
# preparation is a high-stakes, accuracy-sensitive workflow run only
# four times a year — the cost difference of using Claude Sonnet 4.6
# versus Qwen is bounded at ≤ ₹4/quarter, while the accuracy upside
# (catching a missed deduction or a misclassified expense) easily
# justifies it. The LLM call lives behind `_compose_tax_checklist`
# until Chunk 8 wires the model client.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from workers.handlers.context import HandlerContext, HandlerResult

logger = logging.getLogger("cruz.workers.handlers.tax_helper")

HANDLER_NAME = "tax_helper"


async def _fetch_quarter_expenses(
    context: HandlerContext, year: int, quarter: int
) -> List[Dict[str, Any]]:
    """Fetch all expenses for the given calendar quarter.

    Stubbed until Chunk 8 wiring connects the expense data source.
    """
    raise NotImplementedError("connect expense source in Chunk 8 wiring")


async def _compose_tax_checklist(
    expenses: List[Dict[str, Any]], quarter_label: str
) -> str:
    """Compose the GST + income-tax quarterly checklist.

    Stubbed until Chunk 8 wiring connects the LLM client.

    # Rule 8 override:
    # Uses Claude Sonnet 4.6 (not the default Qwen 14B). See module
    # docstring for the cost/accuracy rationale.
    """
    raise NotImplementedError("connect LLM checklist composer in Chunk 8 wiring")


async def _create_notion_page_draft(text: str, title: str) -> str:
    """Create a draft Notion page with the checklist text.

    Stubbed until Chunk 8 wiring connects the Notion integration.

    Returns the URL of the created page.
    """
    raise NotImplementedError("connect Notion in Chunk 8 wiring")


async def handle(payload: Dict[str, Any], context: HandlerContext) -> HandlerResult:
    """Run the quarterly tax helper.

    Args:
        payload: ARQ-supplied payload (unused for cron-triggered handlers)
        context: HandlerContext with kb/db/trace_id/now/emit_info
    """
    year = context.now.year
    quarter = (context.now.month - 1) // 3 + 1
    quarter_label = f"Q{quarter} {year}"
    dedup_key = f"{HANDLER_NAME}:{year}-Q{quarter}"

    fetch_failed = False
    compose_failed = False
    notion_failed = False

    try:
        expenses = await _fetch_quarter_expenses(context, year, quarter)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tax_helper: expense fetch failed: %s", exc)
        expenses = []
        fetch_failed = True

    try:
        checklist = await _compose_tax_checklist(expenses, quarter_label)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tax_helper: compose failed: %s", exc)
        checklist = "Tax checklist unavailable (compose failed)."
        compose_failed = True

    notion_url: Optional[str] = None
    try:
        notion_url = await _create_notion_page_draft(
            checklist, f"Tax checklist — {quarter_label}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("tax_helper: notion draft failed: %s", exc)
        notion_failed = True

    text_parts = [
        f"🧾 *Tax helper — {quarter_label}*",
        "",
        f"Expenses considered: {len(expenses)}",
    ]
    if notion_url:
        text_parts.append(f"Notion draft: {notion_url}")
    text_parts.extend(["", checklist])
    text = "\n".join(text_parts)

    decision = await context.emit_info(
        handler_name=HANDLER_NAME,
        reason="quarterly_tax_checklist",
        dedup_key=dedup_key,
        payload={"text": text, "trace_id": context.trace_id},
    )
    decision_label = getattr(decision, "value", str(decision))

    any_failed = fetch_failed or compose_failed or notion_failed
    error: Optional[str] = None
    if any_failed:
        failed_parts = []
        if fetch_failed:
            failed_parts.append("fetch")
        if compose_failed:
            failed_parts.append("compose")
        if notion_failed:
            failed_parts.append("notion")
        error = f"fetch_failed:{','.join(failed_parts)}"

    result_kwargs: Dict[str, Any] = {
        "handler_name": HANDLER_NAME,
        "success": not any_failed,
        "summary": (
            f"emitted: {decision_label}, "
            f"expenses={len(expenses)}, quarter={quarter_label}"
        ),
        "metadata": {
            "expense_count": len(expenses),
            "quarter": quarter,
            "year": year,
            "notion_url": notion_url,
            "fetch_failed": fetch_failed,
            "compose_failed": compose_failed,
            "notion_failed": notion_failed,
        },
    }
    if error:
        result_kwargs["error"] = error
    return HandlerResult(**result_kwargs)
