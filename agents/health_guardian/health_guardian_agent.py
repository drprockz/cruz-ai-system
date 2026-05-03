"""
HealthGuardianAgent — watches docs/personal/health-journal.md for 3-N
streaks across three dimensions (sleep, commitments, relationship) and
fires a critical alert with a personalized intervention.

Triggers:
  - cron.daily.21:00 (end-of-day check after the journal is written)
  - filewatch.health_journal (immediate re-check when the journal changes)

Critical reasons (whitelist for the gate):
  - health_3n_streak: 3+ consecutive Ns in any single dimension over the
    rolling 7-day window.

State schema:
  agent_state(health_guardian, "streak:sleep_n")        = int
  agent_state(health_guardian, "streak:commitments_n")  = int
  agent_state(health_guardian, "streak:relationship_n") = int
  agent_state(health_guardian, "intervention_history")  = list of
    {at_ts, type, dedup_key}

Charter Rule 2 override: the intervention message is drafted by Claude
Sonnet 4.6 (NOT Qwen). Frequency is rare (≤1/week per dimension) and
quality of the message materially affects whether the user acts on it.

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §4.6
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.base_agent import AgentInput, AgentOutput
from agents.event_driven_agent import EventDrivenAgent
from services.agent_state import get_state_service
from services.llm import chat as llm_chat

logger = logging.getLogger("cruz.agents.health_guardian")

_DIMENSIONS = ("sleep", "commitments", "relationship")
_STREAK_THRESHOLD = 3
_INTERVENTION_MODEL = "claude-sonnet-4-6"
_INTERVENTION_HISTORY_KEY = "intervention_history"
_INTERVENTION_RECENT_DAYS = 7
_JOURNAL_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}):\s*"
    r"sleep=([YN])\s+"
    r"commitments=([YN])\s+"
    r"relationship=([YN])\s*$"
)


class HealthGuardianAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_user_patterns"]
    TRIGGERS         = ["cron.daily.21:00", "filewatch.health_journal"]
    CRITICAL_REASONS = {
        "health_3n_streak":
            "Three consecutive Ns in any single dimension over the rolling 7d window",
    }
    JOURNAL_PATH = "docs/personal/health-journal.md"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        trace_id = input["trace_id"]
        try:
            text = self._read_journal(trace_id)
            if text is None:
                return self._success(start, result={"status": "no_journal"})

            entries = _parse_journal(text)
            if not entries:
                return self._success(start, result={"status": "empty_journal"})

            # Sort newest-first defensively before slicing — _parse_journal
            # returns entries in file order, but _compute_streaks counts from
            # index 0 and treats it as the newest entry. If the user appends
            # to the journal (oldest-first in file), an unsorted slice would
            # look at the wrong end of history and could fire a stale streak.
            recent = sorted(entries, key=lambda e: e["date"], reverse=True)[:7]
            streaks = _compute_streaks(recent)

            # Persist current streaks (info-only — useful for dashboard).
            state = get_state_service()
            for dim in _DIMENSIONS:
                await state.set(self.name, f"streak:{dim}_n", streaks[dim])

            # Look at intervention history to pick a fresh intervention type.
            history: list[dict] = await state.get(
                self.name, _INTERVENTION_HISTORY_KEY,
            ) or []

            critical_dims = [d for d in _DIMENSIONS if streaks[d] >= _STREAK_THRESHOLD]
            week_iso = _iso_week(recent[0]["date"])

            if critical_dims:
                for dim in critical_dims:
                    intervention_type = _pick_intervention_type(
                        dim, history, _INTERVENTION_RECENT_DAYS,
                    )
                    message = await _draft_intervention(
                        dimension=dim,
                        streak_length=streaks[dim],
                        recent_entries=recent,
                        intervention_type=intervention_type,
                    )
                    dedup_key = f"streak:{dim}:{week_iso}"
                    await self.emit(
                        "critical",
                        "health_3n_streak",
                        dedup_key,
                        {
                            "text": message,
                            "trace_id": trace_id,
                            "dimension": dim,
                            "intervention_type": intervention_type,
                        },
                    )
                    history.append({
                        "at_ts": time.time(),
                        "type": intervention_type,
                        "dedup_key": dedup_key,
                        "dimension": dim,
                    })
                await state.set(
                    self.name, _INTERVENTION_HISTORY_KEY, history,
                )
            else:
                # All green — emit a low-key info so the user can see the trend.
                await self.emit(
                    "info",
                    None,
                    f"streaks-info:{week_iso}",
                    {
                        "text": _format_status(streaks),
                        "trace_id": trace_id,
                    },
                )

            return self._success(start, result={"streaks": streaks,
                                                 "critical": critical_dims})
        except Exception as exc:
            logger.exception("[%s] health_guardian failed: %s", trace_id, exc)
            return AgentOutput(
                success=False, result=None, agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0, error=str(exc),
                requires_approval=False, approval_prompt=None,
            )

    def _read_journal(self, trace_id: str) -> str | None:
        path = Path(self.JOURNAL_PATH)
        if not path.exists():
            logger.info("[%s] health journal not found at %s; skipping",
                        trace_id, path)
            return None
        try:
            return path.read_text()
        except Exception as exc:
            logger.warning("[%s] could not read journal %s: %s",
                           trace_id, path, exc)
            return None

    def _success(self, start: float, result: Any) -> AgentOutput:
        return AgentOutput(
            success=True, result=result, agent=self.name,
            duration_ms=int((time.monotonic() - start) * 1000),
            tokens_used=0, error=None,
            requires_approval=False, approval_prompt=None,
        )


# ── Module-level helpers (testable in isolation) ─────────────────────────

def _parse_journal(text: str) -> list[dict]:
    """Parse one-line-per-day journal text into a list of entries.

    Returns entries in **file order** — no sorting is performed. The
    caller is responsible for sorting if streak semantics depend on
    order (see ``HealthGuardianAgent.process``, which sorts newest-first
    before passing to ``_compute_streaks``). Lines that don't match the
    strict regex are skipped silently — the journal format is owner-
    controlled and we don't want to crash on a typo.
    """
    out: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _JOURNAL_LINE_RE.match(line)
        if not m:
            continue
        date, sleep, commitments, relationship = m.groups()
        out.append({
            "date": date,
            "sleep": sleep,
            "commitments": commitments,
            "relationship": relationship,
        })
    return out


def _compute_streaks(entries: list[dict]) -> dict[str, int]:
    """Count consecutive Ns from index 0 of ``entries`` for each dimension.

    The function treats ``entries[0]`` as the newest entry and walks
    forward, stopping at the first Y. The returned int is the count of
    Ns at the head of the list in that dimension. The caller (currently
    ``HealthGuardianAgent.process``) is responsible for guaranteeing
    newest-first ordering before invoking this — see the sort there.
    """
    streaks: dict[str, int] = {}
    for dim in _DIMENSIONS:
        n = 0
        for entry in entries:
            if entry.get(dim) == "N":
                n += 1
            else:
                break
        streaks[dim] = n
    return streaks


def _iso_week(date_str: str) -> str:
    """Return Wyyyy-ww for an ISO date string (e.g. '2026-04-26' → 'W2026-17').

    Format chosen so dedup keys of the form ``streak:{dim}:{week_iso}``
    contain the literal ``:W`` substring, which downstream consumers
    (and tests) use to recognise streak dedup keys.
    """
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        # Defensive — should never happen since _JOURNAL_LINE_RE validates.
        d = datetime.now(timezone.utc).date()
    iso_year, iso_week, _ = d.isocalendar()
    return f"W{iso_year}-{iso_week:02d}"


def _pick_intervention_type(
    dimension: str, history: list[dict], recent_days: int,
) -> str:
    """Pick an intervention type for `dimension` that hasn't been used in
    the last `recent_days` for that dimension.

    Available types: nudge, reframe, action. Rotate through them so the
    user doesn't see the same intervention shape week after week.
    """
    types = ["nudge", "reframe", "action"]
    cutoff = time.time() - recent_days * 86400
    used_recently = {
        h.get("type") for h in history
        if h.get("dimension") == dimension and h.get("at_ts", 0) >= cutoff
    }
    for t in types:
        if t not in used_recently:
            return t
    # All used recently — return the oldest by usage time.
    same_dim = [h for h in history if h.get("dimension") == dimension]
    if same_dim:
        oldest = min(same_dim, key=lambda h: h.get("at_ts", 0))
        return oldest.get("type", "nudge")
    return "nudge"


async def _draft_intervention(
    dimension: str,
    streak_length: int,
    recent_entries: list[dict],
    intervention_type: str,
) -> str:
    """LLM call (Claude Sonnet 4.6 — Charter Rule 2 override) that drafts
    a personalized intervention message for the user."""
    journal_excerpt = "\n".join(
        f"  {e['date']}: sleep={e['sleep']} commitments={e['commitments']} relationship={e['relationship']}"
        for e in recent_entries
    )
    style_hint = {
        "nudge": "Gentle, non-judgemental nudge.",
        "reframe": "Reframe the streak as data, not failure. Curious tone.",
        "action": "Suggest one concrete action for tomorrow. Direct.",
    }.get(intervention_type, "Gentle, non-judgemental nudge.")

    system_prompt = (
        "You are a private health-and-habits assistant for a single user. "
        "The user keeps a daily journal with three Y/N flags: sleep, "
        "commitments (kept what they promised themselves), relationship. "
        "When they hit 3+ Ns in a row in any dimension, you draft a short "
        "(<=4 sentence) message they will see on their phone. You never "
        "lecture. You never assume cause. You match the requested style."
    )
    user_prompt = (
        f"Dimension: {dimension}\n"
        f"Current streak length: {streak_length} consecutive Ns\n"
        f"Style: {style_hint}\n\n"
        "Recent journal (most recent first):\n"
        f"{journal_excerpt}\n\n"
        "Draft the message. <=4 sentences. Plain text. No emoji."
    )
    response = await llm_chat(
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=200,
        backend="anthropic",
        model=os.environ.get("AGENT_MODEL_HEALTH_GUARDIAN", _INTERVENTION_MODEL),
    )
    for block in response.content:
        if hasattr(block, "type") and block.type == "text":
            return block.text.strip()
    return ""


def _format_status(streaks: dict[str, int]) -> str:
    """One-line summary for the all-green info emit."""
    parts = [f"{dim}={streaks.get(dim, 0)}" for dim in _DIMENSIONS]
    return "Health streaks (Ns): " + ", ".join(parts)
