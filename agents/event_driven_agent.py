"""
EventDrivenAgent — base class for SP5 proactive agents.

Layer on top of BaseAgent. Adds class-level declarations that the
event registry and gate need to know about:

  KNOWLEDGE_RINGS  : list[str]            — Rule 3 (KB participation)
  TRIGGERS         : list[str]            — event types this agent subscribes to
  CRITICAL_REASONS : dict[str, str]       — whitelist for gate criticals (Rule B)

Provides emit() — the canonical way for an event-driven agent to surface
a notification through the gate + router pipeline.

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.4
"""

from __future__ import annotations

import logging
from typing import Literal

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.notification_router import get_notification_router
from services.proactive_engine import (
    GateDecision,
    GateRequest,
    get_proactive_engine,
)

logger = logging.getLogger("cruz.agents.event_driven_agent")


class EventDrivenAgent(BaseAgent):
    """Subclass to make a v2 proactive agent. Implement `process()`
    as usual. Inside it, call `await self.emit(...)` to ship notifications.
    """

    # ── Class-level declarations (override in each subclass) ──────────
    KNOWLEDGE_RINGS: list[str] = []
    TRIGGERS: list[str] = []
    CRITICAL_REASONS: dict[str, str] = {}

    DEFAULT_DEDUP_TTL_SECONDS: int = 7 * 86400

    async def emit(
        self,
        severity: Literal["info", "warn", "critical"],
        reason_code: str | None,
        dedup_key: str,
        payload: dict,
    ) -> GateDecision:
        """Build a GateRequest from class declarations, run the gate,
        route notification via NotificationRouter according to decision.

        Returns the GateDecision so callers can branch on it (e.g.,
        log "we tried to fire but were rate-limited").
        """
        # Inject metadata the TelegramChannel uses for the False-alarm button.
        # Idempotent — caller may have already set these.
        payload = {**payload, "agent": self.name, "dedup_key": dedup_key}

        req = GateRequest(
            agent=self.name,
            severity=severity,
            reason_code=reason_code,
            dedup_key=dedup_key,
            payload=payload,
            valid_critical_reasons=set(self.CRITICAL_REASONS.keys()),
        )

        decision = await get_proactive_engine().allow(req)
        router = get_notification_router()

        if decision == GateDecision.ALLOW:
            await router.route(severity, payload)
        elif decision == GateDecision.DEMOTE_TO_WARN:
            await router.route("warn", payload)
        elif decision == GateDecision.DEMOTE_TO_INFO:
            await router.route("info", payload)
        # GateDecision.SUPPRESS: silent — gate already logged the decision

        return decision
