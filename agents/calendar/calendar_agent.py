"""
CalendarAgent — Google Calendar (primary) + Calendar.app (mirror).

Three CRUZ-callable operations dispatched by the `tool` field in
context (set by CRUZ's _dispatch_tool when forwarding):

  - calendar_create_event   — dual-write: Google → AppleScript mirror
  - calendar_list_events    — read-only, Google only
  - calendar_find_free_slot — deterministic gap finder, no LLM

Per charter Rule 3: declares KNOWLEDGE_RINGS, calls build_agent_context
at the top of process() and record_agent_activity in finally.

Per charter Rule 4 + Override #1: self-only events auto-create;
events with attendees require context['send'] = True.

Spec: docs/superpowers/specs/2026-04-26-sp3-mac-controller-design.md §4
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.gcal import GCalError, get_gcal_service
from services.knowledge_base import get_kb_service
from services.mac_controller import (  # noqa: F401 — used in Task 15 (_create_event)
    MacControllerError,
    get_mac_controller_service,
)

logger = logging.getLogger("cruz.agents.CALENDAR")


class CalendarAgent(BaseAgent):
    """Single-shot dispatcher — no internal agentic loop."""

    KNOWLEDGE_RINGS: List[str] = ["cruz_activities", "cruz_user_patterns"]

    def __init__(self) -> None:
        super().__init__()
        self.name = "CALENDAR"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        output: Optional[AgentOutput] = None

        # ── KB context (fire-and-forget; never raises) ───────────────────
        kb = get_kb_service()
        try:
            await kb.build_agent_context(
                input["task"],
                self.KNOWLEDGE_RINGS,
                input["trace_id"],
                project_id=input["context"].get("project_id"),
            )
        except Exception as exc:
            logger.warning("[%s] build_agent_context failed: %s", input["trace_id"], exc)

        try:
            tool = input["context"].get("tool", "calendar_find_free_slot")
            if tool == "calendar_find_free_slot":
                output = await self._find_free_slot(input, start)
            elif tool == "calendar_list_events":
                output = await self._list_events(input, start)
            elif tool == "calendar_create_event":
                output = await self._create_event(input, start)
            else:
                output = AgentOutput(
                    success=False,
                    result=None,
                    agent=self.name,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    tokens_used=0,
                    error=f"Unknown calendar tool: {tool!r}",
                    requires_approval=False,
                    approval_prompt=None,
                )
            return output

        except Exception as exc:
            output = self.handle_error(exc, input["trace_id"])
            return output

        finally:
            try:
                if output is not None:
                    await kb.record_agent_activity(
                        "calendar",
                        input["task"],
                        str(output.get("result", ""))[:200],
                        output["success"],
                        input["trace_id"],
                        project_id=input["context"].get("project_id"),
                        tokens_used=output.get("tokens_used"),
                    )
            except Exception:
                pass

    # ── find_free_slot ──────────────────────────────────────────────

    async def _find_free_slot(self, input: AgentInput, start: float) -> AgentOutput:
        ctx = input["context"]
        duration_minutes = int(ctx["duration_minutes"])
        earliest_iso = ctx["earliest_iso"]
        latest_iso = ctx["latest_iso"]

        gcal = get_gcal_service()
        try:
            events = await gcal.list_events(earliest_iso, latest_iso)
        except GCalError as exc:
            return _failure(self.name, start, f"Google list failed: {exc}")

        slot = _first_free_slot(
            earliest_iso, latest_iso, duration_minutes, events,
        )
        if slot is None:
            return _failure(
                self.name,
                start,
                f"No free slot of {duration_minutes}min in [{earliest_iso}, {latest_iso}].",
            )

        return AgentOutput(
            success=True,
            result={"start_iso": slot[0], "end_iso": slot[1]},
            agent=self.name,
            duration_ms=int((time.monotonic() - start) * 1000),
            tokens_used=0,
            error=None,
            requires_approval=False,
            approval_prompt=None,
        )

    # ── placeholders, filled by Tasks 14 + 15 ───────────────────────

    async def _list_events(self, input: AgentInput, start: float) -> AgentOutput:
        raise NotImplementedError("filled in Task 14")

    async def _create_event(self, input: AgentInput, start: float) -> AgentOutput:
        raise NotImplementedError("filled in Task 15")


# ─────────────────────────────────────────────────────────────────────
# Pure helpers (testable without mocks)
# ─────────────────────────────────────────────────────────────────────


def _failure(agent: str, start: float, msg: str) -> AgentOutput:
    return AgentOutput(
        success=False,
        result=None,
        agent=agent,
        duration_ms=int((time.monotonic() - start) * 1000),
        tokens_used=0,
        error=msg,
        requires_approval=False,
        approval_prompt=None,
    )


def _parse_iso(s: str) -> datetime:
    """Tolerate trailing Z or timezone offsets."""
    s = s.replace("Z", "")
    if "+" in s[10:]:
        s = s[: s.rindex("+")]
    return datetime.fromisoformat(s)


def _first_free_slot(
    earliest_iso: str,
    latest_iso: str,
    duration_minutes: int,
    busy_events: List[Dict[str, Any]],
) -> Optional[Tuple[str, str]]:
    """Return the first (start, end) gap of >= duration_minutes inside the window.

    Algorithm: build a sorted list of busy intervals, walk gaps, pick first fit.
    """
    window_start = _parse_iso(earliest_iso)
    window_end = _parse_iso(latest_iso)
    duration = timedelta(minutes=duration_minutes)

    busy: List[Tuple[datetime, datetime]] = []
    for ev in busy_events:
        s = ev.get("start", {}).get("dateTime")
        e = ev.get("end", {}).get("dateTime")
        if not s or not e:
            continue  # all-day events skipped
        bs = max(_parse_iso(s), window_start)
        be = min(_parse_iso(e), window_end)
        if be > bs:
            busy.append((bs, be))
    busy.sort()

    cursor = window_start
    for bs, be in busy:
        if bs - cursor >= duration:
            return (
                cursor.isoformat(timespec="seconds"),
                (cursor + duration).isoformat(timespec="seconds"),
            )
        cursor = max(cursor, be)

    if window_end - cursor >= duration:
        return (
            cursor.isoformat(timespec="seconds"),
            (cursor + duration).isoformat(timespec="seconds"),
        )
    return None
