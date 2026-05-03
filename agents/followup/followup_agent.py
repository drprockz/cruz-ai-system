"""
FollowupAgent — chases outbound messages that didn't get a reply within 5d.

Two triggers:
  - webhook.gmail.outbound_sent: appends the new outbound to a JSONB queue.
  - cron.daily.10:00: scans the queue, drops replied threads, fires a
    critical alert for unreplied threads >= 5d old that have a known client.

Critical reasons (whitelist for the gate):
  - followup_due_5d: outbound to a client received no reply in 5d
  - client_promised_deliverable_overdue: a deliverable promised to a client
    is past its committed date (Plane.so backed, optional)

# TODO(SP5): wire client_promised_deliverable_overdue once Plane.so
# integration lands. The reason is whitelisted in CRITICAL_REASONS so the
# gate accepts it, but no logic yet evaluates due_date_iso against Plane.

State schema:
  agent_state(followup, "queue") = JSONB array of:
    {thread_id, client_email, sent_at_ts, project_id, due_date_iso}

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §4.x
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agents.base_agent import AgentInput, AgentOutput
from agents.event_driven_agent import EventDrivenAgent
from agents.reply_triage.gmail_client import fetch_thread_replied
from services.agent_state import get_state_service

logger = logging.getLogger("cruz.agents.followup")

_QUEUE_KEY = "queue"
_FOLLOWUP_THRESHOLD_DAYS = 5
_FOLLOWUP_THRESHOLD_SECONDS = _FOLLOWUP_THRESHOLD_DAYS * 86400


class FollowupAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS = ["cruz_activities", "cruz_user_patterns"]
    TRIGGERS = ["cron.daily.10:00", "webhook.gmail.outbound_sent"]
    CRITICAL_REASONS = {
        "followup_due_5d":
            "Outbound message to a client received no reply in 5 days",
        "client_promised_deliverable_overdue":
            "A deliverable promised to a client is past its committed date",
    }

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        trace_id = input["trace_id"]
        try:
            event = input["context"].get("event", {})
            trigger = event.get("trigger", "")
            data = event.get("data", {}) or {}
            state = get_state_service()

            if trigger == "webhook.gmail.outbound_sent":
                await self._on_outbound_sent(state, data, trace_id)
            else:
                # Treat anything else (including cron.daily.10:00) as the
                # daily scan — keeps behaviour predictable if the trigger
                # string evolves.
                await self._scan_queue(state, trace_id)

            return AgentOutput(
                success=True, result=None, agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0, error=None,
                requires_approval=False, approval_prompt=None,
            )
        except Exception as exc:
            logger.exception("[%s] followup failed: %s", trace_id, exc)
            return AgentOutput(
                success=False, result=None, agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0, error=str(exc),
                requires_approval=False, approval_prompt=None,
            )

    async def _on_outbound_sent(
        self, state: Any, data: dict, trace_id: str,
    ) -> None:
        thread_id = data.get("thread_id")
        if not thread_id:
            logger.warning("[%s] outbound_sent event missing thread_id", trace_id)
            return
        queue: list[dict] = await state.get(self.name, _QUEUE_KEY) or []
        # Idempotent: skip if this thread is already enqueued.
        if any(entry.get("thread_id") == thread_id for entry in queue):
            return
        new_entry = {
            "thread_id":    thread_id,
            "client_email": data.get("to", ""),
            "sent_at_ts":   data.get("sent_at_ts") or time.time(),
            "project_id":   data.get("project_id"),
            "due_date_iso": data.get("due_date_iso"),
        }
        queue.append(new_entry)
        await state.set(self.name, _QUEUE_KEY, queue)

    async def _scan_queue(self, state: Any, trace_id: str) -> None:
        queue: list[dict] = await state.get(self.name, _QUEUE_KEY) or []
        if not queue:
            return
        now = time.time()
        keep: list[dict] = []
        for entry in queue:
            thread_id = entry.get("thread_id")
            if not thread_id:
                continue
            try:
                replied = await fetch_thread_replied(thread_id)
            except Exception as exc:
                # Conservative: keep entry; retry next cron tick.
                logger.warning(
                    "[%s] fetch_thread_replied(%s) raised %s; keeping entry",
                    trace_id, thread_id, exc,
                )
                keep.append(entry)
                continue
            if replied:
                # Drop from queue — closed loop.
                continue
            age_seconds = now - float(entry.get("sent_at_ts") or now)
            client_email = entry.get("client_email") or ""
            if age_seconds >= _FOLLOWUP_THRESHOLD_SECONDS and client_email:
                # Positional call so test fake_emit signatures
                # (severity, reason, dedup_key, payload) bind correctly,
                # while still working against the real EventDrivenAgent.emit.
                await self.emit(
                    "critical",
                    "followup_due_5d",
                    f"thread:{thread_id}",
                    {
                        "text": _format_telegram_text(entry, age_seconds),
                        "trace_id": trace_id,
                    },
                )
            keep.append(entry)
        if len(keep) != len(queue):
            await state.set(self.name, _QUEUE_KEY, keep)


def _format_telegram_text(entry: dict, age_seconds: float) -> str:
    age_days = int(age_seconds / 86400)
    return (
        f"📬 *Followup due*\n"
        f"To:     `{entry.get('client_email', '?')}`\n"
        f"Thread: `{entry.get('thread_id', '?')}`\n"
        f"Age:    {age_days}d • no reply"
    )
