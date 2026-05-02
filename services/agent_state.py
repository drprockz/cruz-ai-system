"""
StateService — Postgres-backed per-agent persistent state for SP5.

Used by:
  - ProactiveEngine cooldown / dedup / global-rate-limit reads & writes
  - EventDrivenAgent subclasses for streak counters, queues, dedup sets

Schema: see migrations/versions/0005_agent_state.py
Spec:   docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.1

Charter override (Rule 5): see spec §11. agent_state is mutable state,
not a log; storing in agent_logs would corrupt log semantics.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from services.db import get_db_service

logger = logging.getLogger("cruz.services.agent_state")

_instance: Optional["StateService"] = None


def get_state_service() -> "StateService":
    """Return the module-level StateService singleton."""
    global _instance
    if _instance is None:
        _instance = StateService(get_db_service())
    return _instance


class StateService:
    """Read/write per-agent state with optional TTL."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def get(
        self,
        agent: str,
        key: str,
        default: Any = None,
    ) -> Any:
        """Return the value at (agent, key), or default if absent or expired."""
        row = await self._db.fetchrow(
            """
            SELECT value
            FROM agent_state
            WHERE agent_name = $1
              AND key = $2
              AND (expires_at IS NULL OR expires_at > NOW())
            """,
            agent, key,
        )
        if row is None:
            return default
        # JSONB columns: asyncpg returns dict/list directly. Belt-and-braces
        # str fallback in case a future driver upgrade changes that.
        v = row["value"]
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v

    async def set(
        self,
        agent: str,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """Upsert (agent, key) → value with optional TTL.

        Raises:
            ValueError: if value cannot be JSON-serialised.
        """
        try:
            value_json = json.dumps(value, default=str)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"agent_state value for ({agent}, {key}) is not JSON-serialisable: {exc}"
            ) from exc

        if ttl_seconds is not None:
            await self._db.execute(
                """
                INSERT INTO agent_state (agent_name, key, value, expires_at, updated_at)
                VALUES ($1, $2, $3::jsonb, NOW() + ($4::int * INTERVAL '1 second'), NOW())
                ON CONFLICT (agent_name, key) DO UPDATE
                  SET value      = EXCLUDED.value,
                      expires_at = EXCLUDED.expires_at,
                      updated_at = NOW()
                """,
                agent, key, value_json, ttl_seconds,
            )
        else:
            await self._db.execute(
                """
                INSERT INTO agent_state (agent_name, key, value, expires_at, updated_at)
                VALUES ($1, $2, $3::jsonb, NULL, NOW())
                ON CONFLICT (agent_name, key) DO UPDATE
                  SET value      = EXCLUDED.value,
                      expires_at = NULL,
                      updated_at = NOW()
                """,
                agent, key, value_json,
            )

    async def delete(self, agent: str, key: str) -> None:
        """Remove a single (agent, key) row."""
        await self._db.execute(
            "DELETE FROM agent_state WHERE agent_name = $1 AND key = $2",
            agent, key,
        )

    async def cleanup_expired(self) -> int:
        """Delete all rows where expires_at <= NOW(). Returns count deleted."""
        result = await self._db.execute(
            "DELETE FROM agent_state WHERE expires_at IS NOT NULL AND expires_at <= NOW()"
        )
        # asyncpg returns "DELETE <n>" — best-effort parse
        try:
            return int(result.split()[-1]) if result else 0
        except Exception:
            return 0
