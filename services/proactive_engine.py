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

from services.agent_state import get_state_service
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
    payload: dict[str, Any]
    valid_critical_reasons: set[str] = field(default_factory=set)


class ProactiveEngine:
    """Central gate. One instance per process."""

    # ── Gate parameters (spec §3.2) ─────────────────────────────────
    GLOBAL_DAILY_RATE_LIMIT  = 8           # non-info pings/day across all agents
    PER_AGENT_INFO_DAILY_CAP = 20          # info pings/day per agent
    PER_AGENT_COOLDOWN_ANY   = 3600        # 1h
    PER_AGENT_COOLDOWN_CRIT  = 86400       # 24h
    DEDUP_WINDOW             = 86400 * 7   # 7d

    GATE_AGENT = "_gate"
    GLOBAL_AGENT = "_global"

    def __init__(self, state: Any, db: Any) -> None:
        """Initialize with StateService and a DB execute-capable object."""
        self._state = state
        self._db = db

    async def allow(self, req: GateRequest) -> GateDecision:
        """Run the gate decision algorithm (spec §3.2)."""
        decision = await self._decide(req)
        await self._post_decision(req, decision)
        await self._log_decision(req, decision)
        return decision

    async def _decide(self, req: GateRequest) -> GateDecision:
        # Step 1: Whitelist (no state read)
        if req.severity == "critical":
            if (req.reason_code is None
                    or req.reason_code not in req.valid_critical_reasons):
                return GateDecision.DEMOTE_TO_WARN

        # Step 2: Dedup — CACHED
        dedup_key = f"dedup:{req.agent}:{req.dedup_key}"
        if await self._cached_get(self.GATE_AGENT, dedup_key) is not None:
            return GateDecision.SUPPRESS

        # Step 3: Critical cooldown — CACHED
        if req.severity == "critical":
            cool_crit = await self._cached_get(
                self.GATE_AGENT, f"cooldown:{req.agent}:critical")
            if cool_crit is not None and time.time() - cool_crit < self.PER_AGENT_COOLDOWN_CRIT:
                return GateDecision.SUPPRESS

        # Step 4: Per-agent cooldown — CACHED
        cool_any = await self._cached_get(
            self.GATE_AGENT, f"cooldown:{req.agent}:any")
        if cool_any is not None and time.time() - cool_any < self.PER_AGENT_COOLDOWN_ANY:
            if req.severity == "info":
                # Step 4a: per-agent info safety cap — UNCACHED counter
                today = self._today()
                cnt = await self._state.get(
                    self.GLOBAL_AGENT,
                    f"info_count_per_agent:{req.agent}:{today}",
                    default=0,
                )
                if cnt >= self.PER_AGENT_INFO_DAILY_CAP:
                    return GateDecision.SUPPRESS
                return GateDecision.ALLOW
            return GateDecision.DEMOTE_TO_INFO

        # Step 5: Global daily rate limit (non-info only) — UNCACHED counter
        if req.severity != "info":
            today = self._today()
            daily = await self._state.get(
                self.GLOBAL_AGENT, f"daily_count:{today}", default=0)
            if daily >= self.GLOBAL_DAILY_RATE_LIMIT:
                return GateDecision.SUPPRESS

        # Step 4a (info path that didn't hit cooldown) — UNCACHED counter.
        # Spec §3.2 step 5: info still routed up to the per-agent cap from 4a.
        if req.severity == "info":
            today = self._today()
            cnt = await self._state.get(
                self.GLOBAL_AGENT,
                f"info_count_per_agent:{req.agent}:{today}",
                default=0,
            )
            if cnt >= self.PER_AGENT_INFO_DAILY_CAP:
                return GateDecision.SUPPRESS

        return GateDecision.ALLOW

    async def _post_decision(self, req: GateRequest, decision: GateDecision) -> None:
        """Update counters/cooldowns after a non-suppressed decision.

        Counter reads stay on `self._state.get` (uncached) — see Task 2.4
        constraint. Cacheable writes (cooldown/dedup) invalidate the cache
        immediately after the set so the next dispatch sees fresh state.
        """
        if decision == GateDecision.SUPPRESS:
            return

        now_ts = time.time()
        today = self._today()

        # Per-agent any-cooldown
        await self._state.set(
            self.GATE_AGENT, f"cooldown:{req.agent}:any", now_ts,
            ttl_seconds=self.PER_AGENT_COOLDOWN_ANY,
        )
        await self._cache_invalidate(self.GATE_AGENT, f"cooldown:{req.agent}:any")

        # Critical cooldown only when this was actually a critical that ALLOWed
        if decision == GateDecision.ALLOW and req.severity == "critical":
            await self._state.set(
                self.GATE_AGENT, f"cooldown:{req.agent}:critical", now_ts,
                ttl_seconds=self.PER_AGENT_COOLDOWN_CRIT,
            )
            await self._cache_invalidate(
                self.GATE_AGENT, f"cooldown:{req.agent}:critical")

        # Dedup key
        await self._state.set(
            self.GATE_AGENT, f"dedup:{req.agent}:{req.dedup_key}", now_ts,
            ttl_seconds=self.DEDUP_WINDOW,
        )
        await self._cache_invalidate(
            self.GATE_AGENT, f"dedup:{req.agent}:{req.dedup_key}")

        # Counter increment — UNCACHED read + write to avoid stale-cache races.
        eff_severity = self._effective_severity(req.severity, decision)
        if eff_severity == "info":
            cnt_key = f"info_count_per_agent:{req.agent}:{today}"
            cnt = await self._state.get(self.GLOBAL_AGENT, cnt_key, default=0)
            await self._state.set(
                self.GLOBAL_AGENT, cnt_key, cnt + 1,
                ttl_seconds=86400 * 2,
            )
        else:
            cnt = await self._state.get(
                self.GLOBAL_AGENT, f"daily_count:{today}", default=0)
            await self._state.set(
                self.GLOBAL_AGENT, f"daily_count:{today}", cnt + 1,
                ttl_seconds=86400 * 2,
            )

    async def _log_decision(self, req: GateRequest, decision: GateDecision) -> None:
        """Write a row to agent_logs with action='gate_decision'."""
        try:
            await self._db.execute(
                """
                INSERT INTO agent_logs
                    (trace_id, agent, action, status, input_data, output_data,
                     tokens_used, duration_ms)
                VALUES ($1, $2, 'gate_decision', $3, $4::jsonb, $5::jsonb, 0, 0)
                """,
                req.payload.get("trace_id", "no-trace"),
                req.agent,
                decision.value,
                json.dumps({
                    "severity": req.severity,
                    "reason_code": req.reason_code,
                    "dedup_key": req.dedup_key,
                }),
                json.dumps({"decision": decision.value}),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("gate_decision log failed (non-fatal): %s", exc)

    # ── Hot cache wrapper (Redis read-through) ────────────────────
    #
    # Cacheable: cooldown:* and dedup:* keys (existence/timestamp probes).
    # NOT cacheable: counter keys (info_count_per_agent, daily_count) —
    # they participate in read-modify-write increments. A stale read
    # would silently lose counter increments. See spec §3.1, §3.2 step 5.

    CACHE_TTL_SECONDS = 60

    # Sentinel — `is`-comparable, distinct from any user value including 0/None.
    _MISSING = object()

    async def _cached_get(
        self, agent: str, key: str, default: Any = None,
    ) -> Any:
        """Read-through cache. Redis first, then StateService (Postgres)."""
        cache_key = f"cruz:gate:{agent}:{key}"
        try:
            redis = get_redis_service()
            if redis.client is not None:
                raw = await redis.client.get(cache_key)
                if raw is not None:
                    if raw in (b"__MISSING__", "__MISSING__"):
                        return default
                    try:
                        return json.loads(raw)
                    except Exception:
                        return default
        except Exception as exc:  # noqa: BLE001
            logger.debug("redis cache read failed (non-fatal): %s", exc)

        # Cache miss — read source of truth using the sentinel so we can
        # distinguish "absent" from "value happens to equal default".
        value = await self._state.get(agent, key, self._MISSING)
        was_missing = value is self._MISSING
        if was_missing:
            value = default

        try:
            redis = get_redis_service()
            if redis.client is not None:
                payload = "__MISSING__" if was_missing else json.dumps(value, default=str)
                await redis.client.set(cache_key, payload, ex=self.CACHE_TTL_SECONDS)
        except Exception as exc:
            logger.debug("redis cache write failed (non-fatal): %s", exc)
        return value

    async def _cache_invalidate(self, agent: str, key: str) -> None:
        """Delete the cached entry for this key so the next read sees fresh state."""
        try:
            redis = get_redis_service()
            if redis.client is not None:
                await redis.client.delete(f"cruz:gate:{agent}:{key}")
        except Exception:
            pass

    @staticmethod
    def _effective_severity(severity: str, decision: GateDecision) -> str:
        """Return the effective severity after demotion."""
        if decision == GateDecision.ALLOW:
            return severity
        if decision == GateDecision.DEMOTE_TO_WARN:
            return "warn"
        if decision == GateDecision.DEMOTE_TO_INFO:
            return "info"
        return severity  # SUPPRESS — caller skips

    @staticmethod
    def _today() -> str:
        """UTC date string for daily counters."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


_instance: Optional[ProactiveEngine] = None


def get_proactive_engine() -> ProactiveEngine:
    """Return the process-level ProactiveEngine singleton."""
    global _instance
    if _instance is None:
        _instance = ProactiveEngine(get_state_service(), get_db_service())
    return _instance
