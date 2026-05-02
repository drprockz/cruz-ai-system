# services/proactive_engine.py
"""
ProactiveEngine — the central gate for SP5 proactive notifications.

Every event-driven agent calls gate.allow(GateRequest) before emitting.
The gate enforces:
  1. Whitelist: criticals must declare a known reason_code per agent
  2. Dedup: same (agent, dedup_key) within DEDUP_WINDOW → SUPPRESS
  3. Per-agent cooldown: 1h between any pings, 24h between criticals
  4. Per-agent info cap: 20 info pings/agent/day
  5. Global daily rate limit: 8 non-info pings across all agents

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.2
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from services.agent_state import StateService, get_state_service
from services.db import get_db_service
from services.redis_client import get_redis_service

logger = logging.getLogger("cruz.services.proactive_engine")


class GateDecision(str, Enum):
    """Outcome of gate.allow() — see spec §3.2."""

    ALLOW          = "allow"
    SUPPRESS       = "suppress"
    DEMOTE_TO_WARN = "demote_warn"
    DEMOTE_TO_INFO = "demote_info"


@dataclass
class GateRequest:
    """One request to the gate — built by EventDrivenAgent.emit()."""

    agent: str
    severity: Literal["info", "warn", "critical"]
    reason_code: Optional[str]
    dedup_key: str
    payload: dict
    valid_critical_reasons: set[str] = field(default_factory=set)
