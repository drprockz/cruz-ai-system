"""
MeetingPrepAgent — surfaces a Telegram-friendly prep card 25-35 minutes
before each upcoming calendar event.

Trigger:
  - webhook.google-calendar: Google Calendar push notification. The payload
    contains only resource metadata (channel + state) — no event details —
    so the agent always re-queries the calendar for events starting in the
    25-35min window.

Critical reasons (whitelist for the gate):
  - {} — meeting-prep noise is never worth interrupting the user with a
    critical alert. Emits are always at "warn".

Per-event flow:
  1. Build dedup_key = f"meeting:{event_id}".
  2. For each attendee, fetch recent Gmail thread snippets.
  3. Look up Notion meeting notes for the event (best-effort).
  4. Compose a short Telegram body and emit at "warn".
  5. Record the activity into cruz_activities (Rule 3).

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §4.3

Notes:
  - `_fetch_upcoming_events` is a thin in-module helper because there is
    no `services.calendar` module yet. Tests monkey-patch it; production
    wiring lands when the calendar service is built (see TODO below).
  - `_fetch_meeting_notes` and `_compose_telegram_body` are likewise
    monkey-patchable so tests don't hit Notion or Ollama.
"""

from __future__ import annotations

import logging
import time

from agents.base_agent import AgentInput, AgentOutput
from agents.event_driven_agent import EventDrivenAgent
from agents.reply_triage.gmail_client import fetch_recent_with_attendee
from services.knowledge_base import get_kb_service

logger = logging.getLogger("cruz.agents.meeting_prep")

_WINDOW_LOWER_MIN = 25
_WINDOW_UPPER_MIN = 35


class MeetingPrepAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_activities", "cruz_projects_docs"]
    TRIGGERS         = ["webhook.google-calendar"]
    CRITICAL_REASONS = {}   # never fires critical — meeting-prep noise isn't worth interruption

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        trace_id = input["trace_id"]
        try:
            # Calendar webhook payload contains only headers + resource_state;
            # we always re-query the calendar for the upcoming-events window.
            events = await _fetch_upcoming_events(window_minutes=_WINDOW_UPPER_MIN)
            now_ts = time.time()
            window_lo = now_ts + _WINDOW_LOWER_MIN * 60
            window_hi = now_ts + _WINDOW_UPPER_MIN * 60

            emitted: list[str] = []
            for ev in events or []:
                event_id = ev.get("id")
                if not event_id:
                    continue
                start_ts = _event_start_ts(ev)
                if start_ts is None:
                    continue
                if not (window_lo <= start_ts <= window_hi):
                    continue

                attendee_threads: dict[str, list[dict]] = {}
                for att in _attendee_emails(ev):
                    try:
                        attendee_threads[att] = await fetch_recent_with_attendee(att)
                    except Exception as exc:
                        logger.warning(
                            "[%s] fetch_recent_with_attendee(%s) failed: %s",
                            trace_id, att, exc,
                        )
                        attendee_threads[att] = []

                try:
                    notes = await _fetch_meeting_notes(ev)
                except Exception as exc:
                    logger.warning(
                        "[%s] _fetch_meeting_notes failed for %s: %s",
                        trace_id, event_id, exc,
                    )
                    notes = None

                body = await _compose_telegram_body(
                    event=ev,
                    attendee_threads=attendee_threads,
                    notes=notes,
                )

                dedup_key = f"meeting:{event_id}"
                await self.emit(
                    "warn",
                    None,
                    dedup_key,
                    {
                        "text": body,
                        "trace_id": trace_id,
                    },
                )
                emitted.append(event_id)

                # Rule 3: record activity in cruz_activities.
                try:
                    await get_kb_service().record_agent_activity(
                        agent_name=self.name,
                        task=f"meeting_prep:{ev.get('summary', '')[:80]}",
                        result_summary=(
                            f"emitted prep for event {event_id} "
                            f"({len(attendee_threads)} attendee(s))"
                        ),
                        success=True,
                        trace_id=trace_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "[%s] record_agent_activity failed (non-fatal): %s",
                        trace_id, exc,
                    )

            return AgentOutput(
                success=True,
                result={"emitted": emitted, "considered": len(events or [])},
                agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0,
                error=None,
                requires_approval=False,
                approval_prompt=None,
            )
        except Exception as exc:
            logger.exception("[%s] meeting_prep failed: %s", trace_id, exc)
            return AgentOutput(
                success=False,
                result=None,
                agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0,
                error=str(exc),
                requires_approval=False,
                approval_prompt=None,
            )


# ── Module-level helpers (monkey-patchable from tests) ───────────────────


async def _fetch_upcoming_events(window_minutes: int = 35) -> list[dict]:
    """Return events starting within the next `window_minutes` from now.

    Each event is a dict with at least: ``id``, ``start`` (ISO-8601 string
    or ``{"dateTime": ...}``), ``attendees`` (list of ``{"email": ...}``),
    and ``summary``.

    Production wiring is pending — see TODO. Returns ``[]`` so the agent
    is a no-op until a calendar service is added. Tests monkey-patch this
    helper directly.
    """
    # TODO(SP5): wire to services.calendar once that module is created.
    # The plan flags this as the spot where production wiring will land.
    logger.debug(
        "_fetch_upcoming_events stub returning [] (window=%dm); "
        "calendar service not yet wired",
        window_minutes,
    )
    return []


async def _fetch_meeting_notes(event: dict) -> dict | None:
    """Return Notion meeting-notes context for this calendar event, or None.

    No standard Notion → calendar event linkage exists yet. Returns ``None``
    so the agent still emits a useful prep card (without Notion notes).
    Tests monkey-patch this helper directly.
    """
    # TODO(SP5): once a Notion meeting-notes database id is configured,
    # query NotionService for pages whose title or properties reference
    # event.get("id") or event.get("summary").
    return None


async def _compose_telegram_body(
    event: dict,
    attendee_threads: dict[str, list[dict]],
    notes: dict | None,
) -> str:
    """Compose the human-readable Telegram message body.

    v1 uses a deterministic Python format string rather than calling Qwen.
    The agent is fired ~once per scheduled meeting and the format is short
    and templated; an LLM call is overkill and adds latency + flakiness.
    Swap in a Qwen call here if/when richer prose is wanted.
    """
    summary = event.get("summary") or "(no title)"
    start = _event_start_str(event)
    lines = [
        f"📅 *Meeting in ~30min*",
        f"*{summary}*",
        f"Start: {start}" if start else None,
    ]
    if attendee_threads:
        lines.append("")
        lines.append("Recent threads with attendees:")
        for att, msgs in attendee_threads.items():
            count = len(msgs or [])
            if count == 0:
                lines.append(f"  • {att}: no recent mail")
            else:
                latest = msgs[0] if msgs else {}
                subj = (latest.get("subject") or "")[:60]
                lines.append(f"  • {att}: {count} msg(s); latest: {subj}")
    if notes:
        title = notes.get("title") if isinstance(notes, dict) else None
        url = notes.get("url") if isinstance(notes, dict) else None
        if title or url:
            lines.append("")
            lines.append(f"Notes: {title or ''} {url or ''}".strip())
    return "\n".join(line for line in lines if line is not None)


# ── Internal pure helpers ───────────────────────────────────────────────


def _attendee_emails(event: dict) -> list[str]:
    """Pull attendee email addresses from a Google Calendar event dict."""
    attendees = event.get("attendees") or []
    out: list[str] = []
    for a in attendees:
        if isinstance(a, dict):
            email = a.get("email")
        else:
            email = None
        if email:
            out.append(email)
    return out


def _event_start_ts(event: dict) -> float | None:
    """Best-effort: extract event start as a unix timestamp (UTC).

    Accepts either a Google Calendar ``start`` dict (``{"dateTime": ...}``
    or ``{"date": ...}``) or a raw ISO-8601 string. Returns ``None`` when
    the start cannot be parsed — callers treat that as "skip this event".
    """
    from datetime import datetime, timezone

    start = event.get("start")
    iso: str | None = None
    if isinstance(start, dict):
        iso = start.get("dateTime") or start.get("date")
    elif isinstance(start, str):
        iso = start
    if not iso:
        return None
    # Allow "Z" suffix (Python <3.11 doesn't accept it natively in fromisoformat).
    iso_norm = iso.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_norm)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _event_start_str(event: dict) -> str:
    """Human-friendly start string for the Telegram body."""
    start = event.get("start")
    if isinstance(start, dict):
        return start.get("dateTime") or start.get("date") or ""
    if isinstance(start, str):
        return start
    return ""
