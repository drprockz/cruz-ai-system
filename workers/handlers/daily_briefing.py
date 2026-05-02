"""
Daily Briefing handler — runs at cron.daily.07:00.

Aggregates yesterday's agent activity from agent_logs and emits one
info-tier Telegram digest. Folds info-tier pings from other agents
into a single message so the user doesn't see piecewise spam.

Per spec §5, §10. Replaces the cross-agent synthesis value the cut
Orchestrator agent was reaching for.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict

from workers.handlers.context import HandlerContext, HandlerResult

logger = logging.getLogger("cruz.workers.handlers.daily_briefing")

HANDLER_NAME = "daily_briefing"


async def handle(payload: Dict[str, Any], context: HandlerContext) -> HandlerResult:
    """Run the daily briefing.

    Args:
        payload: ARQ-supplied payload (unused for cron-triggered handlers;
                 reserved for future use)
        context: HandlerContext with kb/db/trace_id/now/emit_info
    """
    today = context.now.strftime("%Y-%m-%d")

    # Pull last-24h agent_logs rows. Note: SQL uses NOW() not context.now
    # — Daily Briefing runs against live time. context.now is used only
    # for dedup-key formatting and labelling.
    # Verified in Chunk 1+: services.db.DatabaseService exposes
    #   async def fetch(query: str, *args) -> list[asyncpg.Record]
    try:
        rows = await context.db.fetch(
            """
            SELECT agent, action, status
            FROM agent_logs
            WHERE created_at >= NOW() - INTERVAL '24 hours'
              AND agent NOT IN ('_gate', '_global')
            """,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("daily_briefing: db query failed: %s", exc)
        rows = []

    by_agent: Counter = Counter()
    by_status: Counter = Counter()
    gate_demotions = 0

    for r in rows:
        by_agent[r["agent"]] += 1
        by_status[r["status"]] += 1
        if r["action"] == "gate_decision" and r["status"] in ("demote_warn", "suppress"):
            gate_demotions += 1

    if not rows:
        text = "📋 *CRUZ daily briefing — " + today + "*\n\nNo agent activity in the last 24h."
    else:
        agent_lines = "\n".join(
            f"  • {agent}: {n}" for agent, n in by_agent.most_common(10)
        )
        text = (
            f"📋 *CRUZ daily briefing — {today}*\n\n"
            f"*Activity by agent*:\n{agent_lines}\n\n"
            f"*Gate stats*: {gate_demotions} pings demoted/suppressed by safety rails."
        )

    decision = await context.emit_info(
        handler_name=HANDLER_NAME,
        reason="daily_summary",
        dedup_key=f"{HANDLER_NAME}:{today}",
        payload={"text": text, "trace_id": context.trace_id},
    )
    decision_label = getattr(decision, "value", str(decision))
    return HandlerResult(
        handler_name=HANDLER_NAME,
        success=True,
        summary=f"emitted: {decision_label}, rows={len(rows)}",
        metadata={"row_count": len(rows), "agent_breakdown": dict(by_agent)},
    )
