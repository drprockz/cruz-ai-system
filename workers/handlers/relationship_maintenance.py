"""
Relationship Maintenance handler — runs at cron.weekly.sunday.18:00.

Surfaces up to 3 contacts the user hasn't messaged in over 6 weeks who
have a track record of regular prior contact (≥3 messages). One info-
tier Telegram message per week, dedup-keyed by ISO year-week.

Per spec §5. The contact-history fetch and the LLM message composer
are stubs until Chunk 8 wiring; the staleness filter is a real, pure
function used directly by tests.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from workers.handlers.context import HandlerContext, HandlerResult

logger = logging.getLogger("cruz.workers.handlers.relationship_maintenance")

HANDLER_NAME = "relationship_maintenance"

# Charter knobs
STALE_THRESHOLD_DAYS = 42  # 6 weeks
MIN_PRIOR_CONTACTS = 3     # excludes one-offs (cold leads, vendors)
MAX_SUGGESTIONS = 3        # surface only the 3 most overdue contacts


async def _compute_last_contact_map(
    context: HandlerContext,
) -> Dict[str, Dict[str, Any]]:
    """Build {email: {last_contact_ts, contact_count}} from comms history.

    Stubbed until Chunk 8 wiring connects Gmail/Calendar/Slack history.
    """
    raise NotImplementedError("connect contact history in Chunk 8 wiring")


def _filter_stale_contacts(
    contact_map: Dict[str, Dict[str, Any]], now: datetime
) -> List[Dict[str, Any]]:
    """Return contacts overdue for outreach, sorted by most-overdue first.

    Pure function. A contact is "stale" when:
      - last_contact_ts is more than STALE_THRESHOLD_DAYS ago, AND
      - contact_count is at least MIN_PRIOR_CONTACTS

    Each result entry has shape:
        {"email": str, "last_contact_ts": float,
         "contact_count": int, "days_since": int}
    """
    now_ts = now.timestamp()
    stale: List[Dict[str, Any]] = []
    for email, info in contact_map.items():
        last_ts = info.get("last_contact_ts")
        count = info.get("contact_count", 0)
        if last_ts is None:
            continue
        days_since = int((now_ts - last_ts) / 86400)
        if days_since <= STALE_THRESHOLD_DAYS:
            continue
        if count < MIN_PRIOR_CONTACTS:
            continue
        stale.append({
            "email": email,
            "last_contact_ts": last_ts,
            "contact_count": count,
            "days_since": days_since,
        })
    # Most-overdue first → deterministic ordering
    stale.sort(key=lambda c: c["days_since"], reverse=True)
    return stale


async def _compose_message(stale_contacts: List[Dict[str, Any]]) -> str:
    """Compose the Telegram message body listing stale contacts.

    Stubbed until Chunk 8 wiring connects the LLM client.
    """
    raise NotImplementedError("connect LLM message composer in Chunk 8 wiring")


async def handle(payload: Dict[str, Any], context: HandlerContext) -> HandlerResult:
    """Run the weekly relationship-maintenance check.

    Args:
        payload: ARQ-supplied payload (unused for cron-triggered handlers)
        context: HandlerContext with kb/db/trace_id/now/emit_info
    """
    week_label = context.now.strftime("%G-W%V")

    fetch_failed = False
    compose_failed = False

    try:
        contact_map = await _compute_last_contact_map(context)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "relationship_maintenance: contact map fetch failed: %s", exc
        )
        contact_map = {}
        fetch_failed = True

    stale = _filter_stale_contacts(contact_map, context.now)
    suggestions = stale[:MAX_SUGGESTIONS]

    try:
        body = await _compose_message(suggestions)
    except Exception as exc:  # noqa: BLE001
        logger.warning("relationship_maintenance: compose failed: %s", exc)
        body = "Relationship reminder body unavailable (compose failed)."
        compose_failed = True

    text = (
        f"🤝 *Relationship maintenance — week {week_label}*\n\n"
        f"Stale contacts surfaced: {len(suggestions)} "
        f"(of {len(stale)} eligible)\n\n"
        f"{body}"
    )

    decision = await context.emit_info(
        handler_name=HANDLER_NAME,
        reason="weekly_relationship_check",
        dedup_key=f"{HANDLER_NAME}:{week_label}",
        payload={"text": text, "trace_id": context.trace_id},
    )
    decision_label = getattr(decision, "value", str(decision))

    any_failed = fetch_failed or compose_failed
    error: Optional[str] = None
    if any_failed:
        failed_parts = []
        if fetch_failed:
            failed_parts.append("fetch")
        if compose_failed:
            failed_parts.append("compose")
        error = f"fetch_failed:{','.join(failed_parts)}"

    result_kwargs: Dict[str, Any] = {
        "handler_name": HANDLER_NAME,
        "success": not any_failed,
        "summary": (
            f"emitted: {decision_label}, "
            f"suggestions={len(suggestions)}, eligible={len(stale)}"
        ),
        "metadata": {
            "suggestion_count": len(suggestions),
            "eligible_count": len(stale),
            "contact_map_size": len(contact_map),
            "fetch_failed": fetch_failed,
            "compose_failed": compose_failed,
        },
    }
    if error:
        result_kwargs["error"] = error
    return HandlerResult(**result_kwargs)
