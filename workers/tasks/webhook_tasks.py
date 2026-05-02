"""
ARQ task handlers for inbound webhook payloads.

Each task:
  1. Parses + logs the payload (v1 behavior — unchanged)
  2. Looks up the trigger in EVENT_REGISTRY
  3. Enqueues dispatch_event_to_agent for each registered agent (SP5 addition)

The signature-verification step happens in backend/api/main.py's webhook
endpoints; tasks here trust the payload they receive.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from arq import create_pool
from arq.connections import RedisSettings

from agents.event_driven_agent import EVENT_REGISTRY

logger = logging.getLogger("cruz.workers.webhooks")


async def _get_arq_pool():
    """Open an ARQ Redis pool. Separated so tests can monkey-patch it."""
    return await create_pool(
        RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379"))
    )


async def _dispatch_to_registered(trigger: str, event_payload: Dict[str, Any]) -> None:
    """For every agent registered against `trigger`, enqueue a dispatch."""
    classes = EVENT_REGISTRY.get(trigger, [])
    if not classes:
        return
    pool = await _get_arq_pool()
    for cls in classes:
        await pool.enqueue_job(
            "dispatch_event_to_agent",
            cls.__module__,
            cls.__name__,
            event_payload,
        )


# ─────────────────────────────────────────────────────────────────────────
# v1 webhook tasks — logging behavior preserved; dispatch added at the end.
# ─────────────────────────────────────────────────────────────────────────

async def process_github_webhook(
    ctx: Dict[str, Any], event: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    action = payload.get("action")
    pr_number = (payload.get("pull_request") or {}).get("number")
    repo = (payload.get("repository") or {}).get("full_name")
    logger.info(
        "github webhook event=%s action=%s repo=%s pr=%s",
        event, action, repo, pr_number,
    )
    summary = {
        "event": event,
        "action": action,
        "pr_number": pr_number,
        "repo": repo,
    }
    await _dispatch_to_registered(
        "webhook.github",
        {"trigger": "webhook.github", "data": payload, "github_event": event},
    )
    return summary


async def process_vercel_webhook(
    ctx: Dict[str, Any], payload: Dict[str, Any]
) -> Dict[str, Any]:
    kind = payload.get("type")
    project = (payload.get("payload") or {}).get("project", {}).get("name")
    url = (payload.get("payload") or {}).get("url")
    logger.info("vercel webhook type=%s project=%s url=%s", kind, project, url)
    summary = {"type": kind, "project": project, "url": url}
    await _dispatch_to_registered(
        "webhook.vercel",
        {"trigger": "webhook.vercel", "data": payload},
    )
    return summary


async def process_google_calendar_webhook(
    ctx: Dict[str, Any], headers: Dict[str, str]
) -> Dict[str, Any]:
    state = headers.get("X-Goog-Resource-State") or headers.get("x-goog-resource-state")
    channel_id = headers.get("X-Goog-Channel-ID") or headers.get("x-goog-channel-id")
    logger.info("google-calendar webhook state=%s channel=%s", state, channel_id)
    summary = {"resource_state": state, "channel_id": channel_id}
    await _dispatch_to_registered(
        "webhook.google-calendar",
        {"trigger": "webhook.google-calendar", "data": {"headers": headers,
                                                         "resource_state": state,
                                                         "channel_id": channel_id}},
    )
    return summary
