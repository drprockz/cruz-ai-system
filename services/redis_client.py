"""
RedisService — async Redis client for CRUZ AI System.

Responsibilities:
- Session data caching
- Cross-device sync via pub/sub (Tailscale + Redis pub/sub, <2s latency)
- Agent result caching

Usage:
    from services.redis_client import get_redis_service

    redis = get_redis_service()
    await redis.connect()
    await redis.set("session:123", json.dumps(data), ttl=3600)
    data = await redis.get("session:123")
    await redis.publish("cruz:devices", json.dumps(event))
    await redis.disconnect()
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger("cruz.services.redis")

_redis_service: Optional["RedisService"] = None


class RedisService:
    """
    Wraps a redis.asyncio client with a minimal interface used by CRUZ.

    Lifecycle:
        connect()    — open the connection
        disconnect() — close the connection
    """

    def __init__(self) -> None:
        url = os.environ.get("REDIS_URL")
        if not url:
            raise ValueError(
                "REDIS_URL environment variable is required but not set."
            )
        self.redis_url: str = url
        self.client: Optional[aioredis.Redis] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the Redis connection from REDIS_URL."""
        logger.info("Connecting to Redis at %s", self.redis_url)
        self.client = await aioredis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=False,
        )
        logger.info("Redis connection ready")

    async def disconnect(self) -> None:
        """Close the Redis connection."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Redis connection closed")

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def _require_client(self) -> aioredis.Redis:
        if self.client is None:
            raise RuntimeError(
                "RedisService is not connected. Call await redis.connect() first."
            )
        return self.client

    async def get(self, key: str) -> Optional[bytes]:
        """Get the value stored at key, or None if missing."""
        client = self._require_client()
        return await client.get(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set key to value. Pass ttl (seconds) to set an expiry."""
        client = self._require_client()
        if ttl is not None:
            await client.set(key, value, ex=ttl)
        else:
            await client.set(key, value)

    async def delete(self, key: str) -> None:
        """Delete a key."""
        client = self._require_client()
        await client.delete(key)

    async def publish(self, channel: str, message: str) -> None:
        """Publish a message to a Redis pub/sub channel."""
        client = self._require_client()
        await client.publish(channel, message)


def get_redis_service() -> RedisService:
    """Return the module-level RedisService singleton."""
    global _redis_service
    if _redis_service is None:
        _redis_service = RedisService()
    return _redis_service
