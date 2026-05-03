"""
Thin Gmail API wrapper for Reply Triage and gmail-webhook task.

Reads OAuth credentials from GMAIL_CREDENTIALS_PATH and GMAIL_TOKEN_PATH
(introduced in SP5 — must be added to .env before Reply Triage / calibration
can run). Tests monkey-patch the public functions; the underlying client
is lazily constructed.
"""

from __future__ import annotations

import base64
import html
import logging
import os
import re
from typing import Any, List

logger = logging.getLogger("cruz.agents.reply_triage.gmail_client")

_USER_ID = "me"
_SERVICE_CACHE: Any = None


def _get_service():
    from google.oauth2.credentials import Credentials  # type: ignore
    from googleapiclient.discovery import build  # type: ignore

    global _SERVICE_CACHE
    if _SERVICE_CACHE is not None:
        return _SERVICE_CACHE
    creds_path = os.environ.get("GMAIL_CREDENTIALS_PATH", "")
    token_path = os.environ.get("GMAIL_TOKEN_PATH", "")
    if not creds_path or not token_path:
        raise RuntimeError(
            "GMAIL_CREDENTIALS_PATH/GMAIL_TOKEN_PATH not set — "
            "Reply Triage cannot read Gmail"
        )
    creds = Credentials.from_authorized_user_file(token_path)
    _SERVICE_CACHE = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return _SERVICE_CACHE


async def fetch_message(message_id: str) -> dict:
    """Return the parsed message envelope: {id, subject, from, date, body, thread_id}."""
    import asyncio
    return await asyncio.to_thread(_fetch_message_sync, message_id)


def _fetch_message_sync(message_id: str) -> dict:
    svc = _get_service()
    msg = svc.users().messages().get(
        userId=_USER_ID, id=message_id, format="full",
    ).execute()
    payload = msg.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    body = _extract_text_body(payload)
    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId"),
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "date": headers.get("date", ""),
        "body": body,
        "labelIds": msg.get("labelIds", []),
    }


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _extract_text_body(payload: dict) -> str:
    """Walk MIME parts; prefer text/plain, fall back to text/html with tags
    stripped. Returns the empty string when no textual part is found."""
    plain = _find_part_body(payload, "text/plain")
    if plain:
        return plain
    raw_html = _find_part_body(payload, "text/html")
    if raw_html:
        return html.unescape(_HTML_TAG_RE.sub("", raw_html)).strip()
    return ""


def _find_part_body(payload: dict, mime: str) -> str:
    """Recursively search payload for the first part whose mimeType
    starts with `mime`. Returns the decoded text, or "" if none found."""
    if payload.get("mimeType", "").startswith(mime):
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        text = _find_part_body(part, mime)
        if text:
            return text
    return ""


async def fetch_history_since(history_id: str) -> List[str]:
    """Return list of new message IDs since `history_id`."""
    import asyncio
    return await asyncio.to_thread(_fetch_history_sync, history_id)


def _fetch_history_sync(history_id: str) -> List[str]:
    svc = _get_service()
    try:
        history = svc.users().history().list(
            userId=_USER_ID,
            startHistoryId=history_id,
            historyTypes=["messageAdded"],
        ).execute()
    except Exception as exc:
        logger.warning("gmail history fetch failed: %s", exc)
        return []
    msg_ids: list[str] = []
    for h in history.get("history", []):
        for added in h.get("messagesAdded", []):
            mid = added.get("message", {}).get("id")
            if mid:
                msg_ids.append(mid)
    return msg_ids


async def list_recent_inbound(limit: int = 50) -> List[str]:
    """For the calibration script — returns latest `limit` inbound message IDs."""
    import asyncio
    return await asyncio.to_thread(_list_recent_sync, limit)


def _list_recent_sync(limit: int) -> List[str]:
    svc = _get_service()
    res = svc.users().messages().list(
        userId=_USER_ID, q="-from:me category:primary", maxResults=limit,
    ).execute()
    return [m["id"] for m in res.get("messages", [])]


async def fetch_thread_replied(thread_id: str) -> bool:
    """Return True iff the thread has at least one outbound message
    AFTER the latest inbound message (i.e. user/agent has replied).

    Implementation: fetch the thread, sort messages by internalDate,
    find the latest inbound (no SENT label), check if any later
    message has the SENT label.

    On Gmail API failure: returns False (conservative — won't suppress
    a legit follow-up alert because of transient API issues).
    """
    import asyncio
    return await asyncio.to_thread(_fetch_thread_replied_sync, thread_id)


def _fetch_thread_replied_sync(thread_id: str) -> bool:
    svc = _get_service()
    try:
        thread = svc.users().threads().get(
            userId=_USER_ID, id=thread_id, format="metadata",
            metadataHeaders=["From", "To"],
        ).execute()
    except Exception as exc:
        logger.warning("gmail thread fetch failed for %s: %s", thread_id, exc)
        return False
    messages = thread.get("messages", [])
    if not messages:
        return False
    # Sort by internalDate (ms since epoch, string).
    messages.sort(key=lambda m: int(m.get("internalDate", "0")))
    last_inbound_idx = -1
    for i, m in enumerate(messages):
        if "SENT" not in m.get("labelIds", []):
            last_inbound_idx = i
    if last_inbound_idx < 0:
        # No inbound messages at all (we sent first, no reply ever).
        # Treat as "not replied" — the followup is to chase the client's reply.
        return False
    # Any message AFTER the latest inbound that we sent counts as a reply.
    for m in messages[last_inbound_idx + 1:]:
        if "SENT" in m.get("labelIds", []):
            return True
    return False
