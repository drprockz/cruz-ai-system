"""
ARQ task handlers for inbound webhook payloads.

Webhook endpoints in backend/api/main.py verify signatures, then enqueue
one of these functions so the HTTP handler can return 200 immediately.
Each task parses the payload, logs a structured summary, and returns
a dict. Real-world downstream actions (dispatching to SENTINEL on PR
open, updating deploy status, refreshing calendar) can be layered on
top without changing the webhook contract.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("cruz.workers.webhooks")


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
    return {
        "event": event,
        "action": action,
        "pr_number": pr_number,
        "repo": repo,
    }


async def process_vercel_webhook(
    ctx: Dict[str, Any], payload: Dict[str, Any]
) -> Dict[str, Any]:
    kind = payload.get("type")
    project = (payload.get("payload") or {}).get("project", {}).get("name")
    url = (payload.get("payload") or {}).get("url")
    logger.info("vercel webhook type=%s project=%s url=%s", kind, project, url)
    return {"type": kind, "project": project, "url": url}


async def process_google_calendar_webhook(
    ctx: Dict[str, Any], headers: Dict[str, str]
) -> Dict[str, Any]:
    state = headers.get("X-Goog-Resource-State") or headers.get("x-goog-resource-state")
    channel_id = headers.get("X-Goog-Channel-ID") or headers.get("x-goog-channel-id")
    logger.info(
        "google-calendar webhook state=%s channel=%s", state, channel_id,
    )
    return {"resource_state": state, "channel_id": channel_id}
