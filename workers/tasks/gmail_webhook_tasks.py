"""
process_gmail_webhook — Pub/Sub push handler for Gmail new-message
notifications. Decodes the Pub/Sub envelope, resolves historyId to
message IDs via the Gmail History API, then dispatches one
webhook.gmail.new_message event per message.

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.5

Gmail watch resubscription happens in workers/tasks/maintenance_tasks.py
(Chunk 8) on a daily cron — Google requires re-watching every 7 days.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, List

from agents.event_driven_agent import EVENT_REGISTRY
from workers.tasks.webhook_tasks import _get_arq_pool

logger = logging.getLogger("cruz.workers.gmail")


async def _fetch_new_message_ids(history_id: str) -> List[str]:
    """Resolve a Gmail historyId to the list of new message IDs since.

    Delegates to agents.reply_triage.gmail_client.fetch_history_since,
    which wraps google-api-python-client. Tests in
    tests/workers/test_gmail_webhook_tasks.py monkey-patch this function
    directly, so the real client is not exercised there.

    See:
      https://developers.google.com/gmail/api/guides/sync#partial
    """
    from agents.reply_triage.gmail_client import fetch_history_since
    return await fetch_history_since(history_id)


async def process_gmail_webhook(
    ctx: Dict[str, Any], pubsub_message: Dict[str, Any]
) -> Dict[str, Any]:
    """Decode Pub/Sub envelope, fetch new message IDs, dispatch each."""
    # Pub/Sub message data is base64-encoded JSON
    raw_data = pubsub_message.get("data", "")
    try:
        payload = json.loads(base64.b64decode(raw_data).decode())
    except Exception as exc:  # noqa: BLE001
        logger.warning("gmail webhook: could not decode pubsub data: %s", exc)
        return {"queued": 0, "error": "decode"}

    history_id = payload.get("historyId")
    if not history_id:
        logger.warning("gmail webhook: missing historyId in payload: %s", payload)
        return {"queued": 0, "error": "no_history_id"}

    try:
        message_ids = await _fetch_new_message_ids(str(history_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("gmail webhook: history fetch failed: %s", exc)
        return {"queued": 0, "error": "history_fetch"}

    classes = EVENT_REGISTRY.get("webhook.gmail.new_message", [])
    if not classes or not message_ids:
        return {"queued": 0}

    pool = await _get_arq_pool()
    queued = 0
    for msg_id in message_ids:
        for cls in classes:
            await pool.enqueue_job(
                "dispatch_event_to_agent",
                cls.__module__,
                cls.__name__,
                {
                    "trigger": "webhook.gmail.new_message",
                    "data": {"message_id": msg_id, "history_id": history_id},
                },
            )
            queued += 1
    return {"queued": queued}
