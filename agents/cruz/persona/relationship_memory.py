"""
RelationshipMemory — builds a lightweight user profile from signals we
already collect.  Cached for 5 minutes; rebuilds asynchronously.

Signals used (no new tables):
  - agent_logs: total turns, most-used agents, typical latency, error rate
  - messages: typical work hours (from created_at distribution)
  - voice_sessions: voice vs text preference
  - approval_requests: approval vs denial rate per agent

What the profile is USED for:
  - Short summary line in the system prompt ("User typically works 09-21;
    most-used agent: forge; voice preferred; approval rate 92%.")
  - NOT for decisions this turn — we're not smart enough to do that safely
    yet.  Surfaces context; Claude decides.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional


@dataclass
class UserPersonaProfile:
    user_id: str = "darshan"
    total_turns: int = 0
    top_agents: List[str] = field(default_factory=list)
    typical_work_hours: str = "09-21"  # "HH-HH" local
    voice_fraction: float = 0.0  # 0..1
    approval_rate: float = 0.0  # 0..1
    error_rate_7d: float = 0.0  # 0..1
    last_built: Optional[datetime] = None

    def summary_line(self) -> str:
        top = ", ".join(self.top_agents[:3]) or "none yet"
        return (
            f"{self.total_turns} total turns; "
            f"top agents: {top}; "
            f"typical hours: {self.typical_work_hours}; "
            f"voice_frac={self.voice_fraction:.0%}; "
            f"approval_rate={self.approval_rate:.0%}; "
            f"7d_error={self.error_rate_7d:.0%}"
        )


class RelationshipMemory:
    """Singleton profile builder with a 5-minute memo cache."""

    _instance: Optional["RelationshipMemory"] = None
    _ttl = timedelta(minutes=5)

    def __init__(self) -> None:
        self._cache: Dict[str, UserPersonaProfile] = {}

    @classmethod
    def get(cls) -> "RelationshipMemory":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def build_user_profile(
        self,
        db,
        user_id: str = "darshan",
        *,
        force: bool = False,
    ) -> UserPersonaProfile:
        """
        Build (or fetch cached) profile. `db` is a DatabaseService instance
        with .fetch() + .fetchrow().
        """
        now = datetime.now()
        cached = self._cache.get(user_id)
        if cached and not force and cached.last_built:
            if now - cached.last_built < self._ttl:
                return cached

        profile = UserPersonaProfile(user_id=user_id, last_built=now)

        try:
            # Total turns (last 30 days)
            row = await db.fetchrow(
                "SELECT COUNT(*)::int AS n "
                "FROM agent_logs WHERE created_at > NOW() - INTERVAL '30 days'"
            )
            profile.total_turns = (row or {}).get("n", 0)

            # Top 3 agents by call count
            top = await db.fetch(
                "SELECT agent, COUNT(*)::int AS n FROM agent_logs "
                "WHERE created_at > NOW() - INTERVAL '30 days' "
                "GROUP BY agent ORDER BY n DESC LIMIT 3"
            )
            profile.top_agents = [r["agent"] for r in (top or [])]

            # Typical work hours — bucket by hour, find where 80% of calls fall
            hist = await db.fetch(
                "SELECT EXTRACT(hour FROM created_at)::int AS h, COUNT(*)::int AS n "
                "FROM agent_logs "
                "WHERE created_at > NOW() - INTERVAL '30 days' "
                "GROUP BY h ORDER BY h"
            )
            if hist:
                total = sum(r["n"] for r in hist)
                if total:
                    cum, lo, hi = 0, 0, 23
                    lo_set = False
                    for r in hist:
                        cum += r["n"]
                        if not lo_set and cum >= total * 0.1:
                            lo = r["h"]
                            lo_set = True
                        if cum >= total * 0.9:
                            hi = r["h"]
                            break
                    profile.typical_work_hours = f"{lo:02d}-{hi:02d}"

            # Error rate last 7 days
            err = await db.fetchrow(
                "SELECT COUNT(*)::int AS total, "
                "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END)::int AS errs "
                "FROM agent_logs WHERE created_at > NOW() - INTERVAL '7 days'"
            )
            if err and err.get("total"):
                profile.error_rate_7d = (err.get("errs") or 0) / err["total"]

            # Voice fraction — turns with a voice_session vs without
            vrow = await db.fetchrow(
                "SELECT COUNT(*)::int AS total, "
                "SUM(CASE WHEN voice_session_id IS NOT NULL THEN 1 ELSE 0 END)::int AS voice "
                "FROM messages WHERE created_at > NOW() - INTERVAL '30 days'"
            )
            if vrow and vrow.get("total"):
                profile.voice_fraction = (vrow.get("voice") or 0) / vrow["total"]

            # Approval rate
            arow = await db.fetchrow(
                "SELECT "
                "  SUM(CASE WHEN state='approved' THEN 1 ELSE 0 END)::int AS a, "
                "  SUM(CASE WHEN state IN ('approved','denied') THEN 1 ELSE 0 END)::int AS decided "
                "FROM approval_requests WHERE requested_at > NOW() - INTERVAL '30 days'"
            )
            if arow and arow.get("decided"):
                profile.approval_rate = (arow.get("a") or 0) / arow["decided"]

        except Exception:
            # DB hiccup — return whatever we have.  Never throw; profile is optional.
            pass

        self._cache[user_id] = profile
        return profile


async def quick_profile(db, user_id: str = "darshan") -> UserPersonaProfile:
    """Convenience — just get a profile without fiddling with the singleton."""
    return await RelationshipMemory.get().build_user_profile(db, user_id)
