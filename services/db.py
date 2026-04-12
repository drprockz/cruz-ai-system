"""
DatabaseService — asyncpg connection pool for CRUZ AI System.

Usage:
    from services.db import get_db_service

    db = get_db_service()
    await db.connect()
    row = await db.fetchrow("SELECT * FROM conversations WHERE id = $1", conv_id)
    await db.disconnect()

All methods raise RuntimeError if called before connect().
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional

import asyncpg

logger = logging.getLogger("cruz.services.db")

# Module-level singleton, initialised on first call to get_db_service()
_db_service: Optional["DatabaseService"] = None


class DatabaseService:
    """
    Wraps an asyncpg connection pool with a simple query interface.

    Lifecycle:
        connect()    — create the pool (call once at startup)
        disconnect() — close the pool (call once at shutdown)
    """

    def __init__(self) -> None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise ValueError(
                "DATABASE_URL environment variable is required but not set."
            )
        self.database_url: str = url
        self.pool: Optional[asyncpg.Pool] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Create the asyncpg connection pool."""
        logger.info("Creating asyncpg pool for %s", self.database_url)
        self.pool = await asyncpg.create_pool(self.database_url)
        logger.info("Database pool ready")

    async def disconnect(self) -> None:
        """Close the asyncpg connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Database pool closed")

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def _require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError(
                "DatabaseService is not connected. Call await db.connect() first."
            )
        return self.pool

    async def execute(self, query: str, *args: Any) -> str:
        """Execute a DML statement (INSERT / UPDATE / DELETE). Returns status string."""
        pool = self._require_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> List[asyncpg.Record]:
        """Execute a SELECT and return all matching rows."""
        pool = self._require_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        """Execute a SELECT and return the first row, or None."""
        pool = self._require_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)


def get_db_service() -> DatabaseService:
    """Return the module-level DatabaseService singleton."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service
