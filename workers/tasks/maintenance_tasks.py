"""
SP5 maintenance crons:

  cron.daily.06:00  gmail_watch_resubscribe   — Google requires re-watch /7d
  cron.daily.04:30  agent_state_cleanup       — delete expired rows
  cron.5min.gmail_poll                        — fallback for Gmail-watch lapses
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from agents.event_driven_agent import EVENT_REGISTRY
from agents.reply_triage.gmail_client import list_recent_inbound
from services.agent_state import get_state_service
from workers.tasks.webhook_tasks import _get_arq_pool

logger = logging.getLogger("cruz.workers.maintenance")


async def gmail_watch_resubscribe(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Re-register Gmail watch on the user's mailbox.

    Google's Gmail push subscriptions expire every 7 days. This cron runs
    daily so we always have a fresh watch (at most 1 day old).

    All exceptions are swallowed and logged as warnings — Google API outages
    must not crash the cron loop.
    """
    topic = os.environ.get("GMAIL_PUBSUB_TOPIC", "")
    if not topic:
        logger.warning("GMAIL_PUBSUB_TOPIC not set; skipping resubscribe")
        return {"success": False, "reason": "no_topic"}
    try:
        from agents.reply_triage.gmail_client import _get_service
        svc = _get_service()
        result = svc.users().watch(
            userId="me",
            body={"topicName": topic, "labelIds": ["INBOX"]},
        ).execute()
        return {
            "success": True,
            "history_id": result.get("historyId"),
            "expiration": result.get("expiration"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("gmail_watch_resubscribe failed: %s", exc)
        return {"success": False, "error": str(exc)}


async def agent_state_cleanup(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Delete agent_state rows whose expires_at has passed.

    Exceptions are NOT swallowed — if the DB is down the cron should fail
    loudly so the on_job_end alerter fires.
    """
    deleted = await get_state_service().cleanup_expired()
    return {"success": True, "deleted": deleted}


async def gmail_poll_fallback(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Pull last 20 inbound message IDs; dispatch new ones via EVENT_REGISTRY.

    Provides redundancy for the Gmail watch subscription — if push delivery
    lapses (e.g. between watch expiry and the daily resubscribe), this cron
    catches missed messages every 5 minutes.

    Dedup state lives in agent_state under (`_gmail_poll`, `last_seen_ids`)
    with a 24h TTL — a rolling window of the last 100 IDs.
    """
    state = get_state_service()
    seen: list[str] = await state.get("_gmail_poll", "last_seen_ids", default=[])
    seen_set = set(seen)
    try:
        ids = await list_recent_inbound(limit=20)
    except Exception as exc:  # noqa: BLE001
        logger.warning("gmail_poll_fallback list failed: %s", exc)
        return {"success": False, "error": str(exc)}

    new_ids = [i for i in ids if i not in seen_set]
    if not new_ids:
        return {"success": True, "new": 0}

    classes = EVENT_REGISTRY.get("webhook.gmail.new_message", [])
    if classes:
        pool = await _get_arq_pool()
        for msg_id in new_ids:
            for cls in classes:
                await pool.enqueue_job(
                    "dispatch_event_to_agent",
                    cls.__module__,
                    cls.__name__,
                    {
                        "trigger": "webhook.gmail.new_message",
                        "data": {"message_id": msg_id, "source": "poll"},
                    },
                )

    # Store the last 100 IDs (rolling window) with 24h TTL — newest first.
    merged = (list(new_ids) + list(seen))[:100]
    await state.set("_gmail_poll", "last_seen_ids", merged, ttl_seconds=86400)
    return {"success": True, "new": len(new_ids)}
