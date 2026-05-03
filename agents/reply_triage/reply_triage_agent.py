"""
ReplyTriageAgent — classifies inbound Gmail messages and fires a critical
alert only when ALL of these conditions hold:
  - label == "needs_reply"
  - urgency in {"now", "today"}
  - client_match is not None
  - email age > 72h

Otherwise emits at info or warn (severity per a small decision matrix).

Default model: Qwen qwen2.5-coder:14b (per Charter Rule 2). Day-1
calibration test (scripts/calibrate_reply_triage.py) determines whether
to keep Qwen or flip to Claude Sonnet 4.6. If flipped, set
AGENT_MODEL_REPLY_TRIAGE env var; agent reads it on each classify call.

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §4.1
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

from agents.base_agent import AgentInput, AgentOutput
from agents.event_driven_agent import EventDrivenAgent

from agents.reply_triage.gmail_client import fetch_message
from services.agent_state import get_state_service
from services.db import get_db_service
from services.knowledge_base import get_kb_service
from services.llm import chat as llm_chat

logger = logging.getLogger("cruz.agents.reply_triage")

_DEFAULT_MODEL = "qwen2.5-coder:14b"
_CACHE_TTL_DAYS = 30


class ReplyTriageAgent(EventDrivenAgent):
    """SP5 event-driven agent that triages inbound Gmail messages."""

    KNOWLEDGE_RINGS = ["cruz_activities", "cruz_user_patterns"]
    TRIGGERS = ["webhook.gmail.new_message", "cron.5min.gmail_poll"]
    CRITICAL_REASONS = {
        "client_email_unanswered_72h":
            "Email from a known client requires reply, age >72h",
    }

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        trace_id = input["trace_id"]
        try:
            event = input["context"].get("event", {}).get("data", {})
            message_id = event.get("message_id")
            if not message_id:
                return self._fail("no message_id in event", trace_id, start)

            # 1. Cache check
            state = get_state_service()
            cached = await state.get(self.name, f"last_classified:{message_id}")
            if cached:
                logger.debug(
                    "[%s] reply_triage: using cached classification for %s",
                    trace_id, message_id,
                )
                classification = cached
                # still fetch for emit metadata (subject/from/date)
                msg = await fetch_message(message_id)
            else:
                # 2. Fetch message
                msg = await fetch_message(message_id)

                # 3. Build KB context (Rule 3)
                kb_context = await get_kb_service().build_agent_context(
                    task=msg.get("subject", "")
                    + "\n\n"
                    + msg.get("body", "")[:500],
                    rings=self.KNOWLEDGE_RINGS,
                    trace_id=trace_id,
                )

                # 4. Classify (LLM call)
                classification = await _classify_email(msg, kb_context)
                # 5. Resolve client_match against projects.email_domains
                classification["client_match"] = await _resolve_client_match(
                    msg.get("from", "")
                )

                # 6. Cache
                await state.set(
                    self.name,
                    f"last_classified:{message_id}",
                    classification,
                    ttl_seconds=_CACHE_TTL_DAYS * 86400,
                )

            # 7. Decide severity (deterministic, NOT a model call)
            age_hours = _email_age_hours(msg.get("date", ""))
            severity, reason_code = _decide_severity(classification, age_hours)

            # 8. Emit
            decision = await self.emit(
                severity,
                reason_code,
                f"email:{message_id}",
                {
                    "text": _format_telegram_text(
                        msg, classification, age_hours, severity
                    ),
                    "trace_id": trace_id,
                },
            )

            # 9. Record activity (Rule 3)
            await get_kb_service().record_agent_activity(
                agent_name=self.name,
                task=f"triage:{msg.get('subject', '')[:80]}",
                result_summary=(
                    f"{classification['label']}/{classification['urgency']} "
                    f"→ {severity} ({decision.value})"
                ),
                success=True,
                trace_id=trace_id,
                project_id=classification.get("client_match"),
            )

            return AgentOutput(
                success=True,
                result=classification,
                agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0,
                error=None,
                requires_approval=False,
                approval_prompt=None,
            )
        except Exception as exc:
            return self._fail(str(exc), trace_id, start, exc)

    def _fail(
        self,
        reason: str,
        trace_id: str,
        start: float,
        exc: Exception | None = None,
    ) -> AgentOutput:
        if exc:
            logger.exception("[%s] reply_triage failed: %s", trace_id, reason)
        else:
            logger.warning("[%s] reply_triage skipped: %s", trace_id, reason)
        return AgentOutput(
            success=False,
            result=None,
            agent=self.name,
            duration_ms=int((time.monotonic() - start) * 1000),
            tokens_used=0,
            error=reason,
            requires_approval=False,
            approval_prompt=None,
        )


# ── Module-level helpers (testable in isolation) ────────────────────────


def _decide_severity(
    classification: dict, age_hours: int
) -> tuple[str, Optional[str]]:
    """Map (classification, age_hours) → (severity, reason_code).

    Critical fires only when ALL conditions hold:
      label == 'needs_reply' AND urgency in {now, today}
      AND client_match is not None AND age_hours > 72.
    Otherwise: needs_reply → warn; everything else → info.
    """
    label = classification.get("label")
    urgency = classification.get("urgency")
    client_match = classification.get("client_match")

    if (
        label == "needs_reply"
        and urgency in ("now", "today")
        and client_match is not None
        and age_hours > 72
    ):
        return ("critical", "client_email_unanswered_72h")
    if label == "needs_reply":
        return ("warn", None)
    return ("info", None)


def _email_age_hours(date_header: str) -> int:
    """Parse RFC 2822 date header → age in hours from now (UTC)."""
    if not date_header:
        return 0
    try:
        dt = parsedate_to_datetime(date_header)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return max(0, int(delta.total_seconds() / 3600))
    except Exception as exc:
        logger.debug("could not parse date header %r: %s", date_header, exc)
        return 0


async def _classify_email(msg: dict, kb_context: str = "") -> dict:
    """LLM call returning {label, urgency, client_match, confidence, reason}."""
    model = os.environ.get("AGENT_MODEL_REPLY_TRIAGE", _DEFAULT_MODEL)
    backend = _backend_for_model(model)
    prompt = (
        f"{kb_context}\n\n"
        "Classify this email. Return JSON ONLY with fields:\n"
        '  label: "needs_reply" | "fyi" | "spam" | "promo"\n'
        '  urgency: "now" | "today" | "this_week" | "later"\n'
        "  client_match: null (you cannot resolve clients — leave null)\n"
        "  confidence: 0.0-1.0\n"
        "  reason: short explanation (≤15 words)\n\n"
        f"From: {msg.get('from', '')}\n"
        f"Subject: {msg.get('subject', '')}\n"
        f"Body (first 1500 chars):\n{msg.get('body', '')[:1500]}\n"
    )
    response = await llm_chat(
        system="",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        backend=backend,
        model=model,
    )
    text = ""
    for block in response.content:
        if hasattr(block, "type") and block.type == "text":
            text = block.text
            break
    return _parse_classification_json(text)


def _backend_for_model(model: str) -> str:
    """Map a model identifier to its services.llm backend.

    Local Ollama models contain a colon (e.g. 'qwen2.5-coder:14b'); cloud
    Anthropic models start with 'claude'. Anything else falls through to
    the LLM_BACKEND env default.
    """
    if ":" in model:
        return "ollama"
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("gemini"):
        return "gemini"
    # let services.llm.router resolve from env
    return os.environ.get("LLM_BACKEND", "anthropic")


def _parse_classification_json(text: str) -> dict:
    """Strip markdown fences if any, parse JSON, fall back to safe default."""
    text = text.strip()
    if text.startswith("```"):
        # strip ```json ... ``` fences
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        d = json.loads(text)
    except Exception:
        logger.warning(
            "classification JSON parse failed; defaulting to fyi/later. raw=%r",
            text[:200],
        )
        return {
            "label": "fyi",
            "urgency": "later",
            "client_match": None,
            "confidence": 0.0,
            "reason": "parse failed",
        }
    return {
        "label": d.get("label", "fyi"),
        "urgency": d.get("urgency", "later"),
        "client_match": d.get("client_match"),
        "confidence": float(d.get("confidence", 0.5)),
        "reason": d.get("reason", ""),
    }


async def _resolve_client_match(from_header: str) -> Optional[str]:
    """Match the email's domain against projects.email_domains.

    Returns project_id (UUID) or None. Uses the email_domains TEXT[]
    column added by migration 0006.
    """
    if not from_header or "@" not in from_header:
        return None
    domain = from_header.rsplit("@", 1)[-1].rstrip(">").lower().strip()
    if not domain:
        return None
    db = get_db_service()
    row = await db.fetchrow(
        "SELECT id FROM projects WHERE $1 = ANY(email_domains) "
        "AND status='active' LIMIT 1",
        domain,
    )
    return row["id"] if row else None


def _format_telegram_text(
    msg: dict, classification: dict, age_hours: int, severity: str
) -> str:
    """Compose the human-readable Telegram message body."""
    sev_emoji = {"info": "📥", "warn": "⚠️", "critical": "🚨"}[severity]
    return (
        f"{sev_emoji} *{classification['label']}/{classification['urgency']}*\n"
        f"From: `{msg.get('from', '?')}`\n"
        f"Subject: {msg.get('subject', '?')}\n"
        f"Age: {age_hours}h • {classification.get('reason', '')}"
    )
