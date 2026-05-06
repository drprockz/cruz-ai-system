"""
HandlerContext — info-only emission surface for SP5 handlers.

Per spec §5 (charter Rule 7), handlers cannot emit warn or critical.
This type structurally enforces that constraint by exposing only
emit_info(). A handler that needs warn/critical semantics is, by
definition, not a handler — it should be promoted to an
EventDrivenAgent and re-checked against Rule 1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from services.notification_router import get_notification_router
from services.proactive_engine import (
    GateDecision,
    GateRequest,
    get_proactive_engine,
)

logger = logging.getLogger("cruz.workers.handlers")


@dataclass
class HandlerResult:
    """Standard return shape for a handler invocation."""
    handler_name: str
    success: bool
    summary: str = ""
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class HandlerContext:
    """Per-invocation context object passed to every handler.

    Provides:
      - kb         : KnowledgeBaseService singleton (read-only path: build_agent_context)
      - db         : DatabaseService singleton accessor (lazy)
      - trace_id   : ID for log correlation
      - now        : current UTC time (frozen at HandlerContext construction)
      - emit_info  : the ONLY way for a handler to surface a notification
    """

    def __init__(
        self,
        trace_id: str,
        now: datetime,
    ) -> None:
        self.trace_id = trace_id
        self.now = now
        self._kb = None
        self._db = None

    @property
    def kb(self):
        if self._kb is None:
            from services.knowledge_base import get_kb_service
            self._kb = get_kb_service()
        return self._kb

    @property
    def db(self):
        if self._db is None:
            from services.db import get_db_service
            self._db = get_db_service()
        return self._db

    async def emit_info(
        self,
        handler_name: str,
        reason: str,
        dedup_key: str,
        payload: dict,
    ) -> GateDecision:
        """Route an info-tier notification through the gate.

        Note: handlers are NOT permitted to emit warn or critical. This
        method does not accept a `severity` argument by design.
        """
        payload = {**payload, "agent": handler_name, "dedup_key": dedup_key}
        req = GateRequest(
            agent=handler_name,
            severity="info",
            reason_code=reason,
            dedup_key=dedup_key,
            payload=payload,
            valid_critical_reasons=set(),  # info severity ignores whitelist
        )
        decision = await get_proactive_engine().allow(req)
        if decision == GateDecision.ALLOW:
            await get_notification_router().route("info", payload)
        # Demotions: emit_info already at info, so DEMOTE_TO_INFO is a no-op
        # (still ALLOWed by the gate); SUPPRESS = silent.
        return decision
