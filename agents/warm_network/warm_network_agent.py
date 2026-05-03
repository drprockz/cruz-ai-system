"""
WarmNetworkAgent — ranks LinkedIn contacts by recency-of-activity +
signal-of-openness + staleness-of-last-Gmail-contact, and emits a single
"warn" Telegram nudge per contact.

Trigger:
  - cron.weekly.monday.09:00 — once a week, Monday morning, surface a
    short list of warm contacts the user hasn't touched in a while.

Critical reasons (whitelist for the gate):
  - {} — relationship-nudge noise is never worth a critical interruption.
    All emits are at "warn".

Pre-SP4 stub mode
-----------------
The real ranking logic depends on SP4's headless-browser service to
scrape LinkedIn (no public API for the signals we need). Until SP4 ships
a `services.browser.get_browser_service()`, this agent runs in stub mode:
it logs one warning and returns a success+stub AgentOutput. No state
writes, no router calls, no external I/O.

When SP4 lands:
  1. Implement the real ranking flow per spec §4.5 — pull LinkedIn
     activity + openness signals via the browser service, cross-reference
     against Gmail thread recency, score, and emit the top N.
  2. Use dedup_key = f"last_nudge:{contact_id}" so a contact isn't
     nudged again the same week if the Monday job retries.
  3. Wire into cruz_activities + cruz_user_patterns rings.

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §4.5 + §1.2
"""

from __future__ import annotations

import logging

from agents.base_agent import AgentInput, AgentOutput
from agents.event_driven_agent import EventDrivenAgent

logger = logging.getLogger("cruz.agents.warm_network")


class WarmNetworkAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_activities", "cruz_user_patterns"]
    TRIGGERS         = ["cron.weekly.monday.09:00"]
    CRITICAL_REASONS = {}

    async def process(self, input: AgentInput) -> AgentOutput:
        if not _sp4_browser_available():
            logger.warning(
                "[%s] WarmNetworkAgent stub-mode: SP4 browser not ready",
                input["trace_id"],
            )
            return AgentOutput(
                success=True,
                result="stub",
                agent=self.name,
                duration_ms=0,
                tokens_used=0,
                error=None,
                requires_approval=False,
                approval_prompt=None,
            )
        # TODO(SP4): real implementation per spec §4.5 — rank LinkedIn
        # contacts by recency-of-activity + signal-of-openness +
        # staleness-of-last-Gmail-contact; emit "warn" with
        # dedup_key = f"last_nudge:{contact_id}".
        return AgentOutput(
            success=True,
            result="stub",
            agent=self.name,
            duration_ms=0,
            tokens_used=0,
            error=None,
            requires_approval=False,
            approval_prompt=None,
        )


def _sp4_browser_available() -> bool:
    """Probe whether SP4's services/browser.py exists and exposes get_browser_service()."""
    try:
        from services.browser import get_browser_service  # noqa: F401
        return True
    except ImportError:
        return False
