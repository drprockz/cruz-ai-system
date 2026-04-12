"""
Tests for services/redis_client.py — Redis connection management.
RED phase — must fail before production code exists.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.redis_client import RedisService, get_redis_service


class TestRedisServiceInterface:
    def test_redis_service_class_exists(self):
        service = RedisService()
        assert service is not None

    def test_redis_service_has_connect_method(self):
        service = RedisService()
        assert hasattr(service, "connect")

    def test_redis_service_has_disconnect_method(self):
        service = RedisService()
        assert hasattr(service, "disconnect")

    def test_redis_service_has_get_method(self):
        service = RedisService()
        assert hasattr(service, "get")

    def test_redis_service_has_set_method(self):
        service = RedisService()
        assert hasattr(service, "set")

    def test_redis_service_has_delete_method(self):
        service = RedisService()
        assert hasattr(service, "delete")

    def test_redis_service_has_publish_method(self):
        """publish() is needed for cross-device sync via Redis pub/sub."""
        service = RedisService()
        assert hasattr(service, "publish")

    def test_redis_service_uses_redis_url_from_env(self):
        url = "redis://localhost:6380"
        with patch.dict(os.environ, {"REDIS_URL": url}):
            service = RedisService()
            assert service.redis_url == url

    def test_redis_service_raises_if_redis_url_missing(self):
        env_without_url = {k: v for k, v in os.environ.items() if k != "REDIS_URL"}
        with patch.dict(os.environ, env_without_url, clear=True):
            with pytest.raises(ValueError, match="REDIS_URL"):
                RedisService()


class TestGetRedisService:
    def test_get_redis_service_returns_redis_service(self):
        service = get_redis_service()
        assert isinstance(service, RedisService)

    def test_get_redis_service_returns_same_instance(self):
        s1 = get_redis_service()
        s2 = get_redis_service()
        assert s1 is s2


class TestRedisServiceOperations:
    async def test_set_stores_value(self):
        mock_client = AsyncMock()
        service = RedisService()
        service.client = mock_client

        await service.set("mykey", "myvalue")
        mock_client.set.assert_called_once_with("mykey", "myvalue")

    async def test_set_with_ttl(self):
        mock_client = AsyncMock()
        service = RedisService()
        service.client = mock_client

        await service.set("mykey", "myvalue", ttl=300)
        mock_client.set.assert_called_once_with("mykey", "myvalue", ex=300)

    async def test_get_returns_value(self):
        mock_client = AsyncMock()
        mock_client.get.return_value = b"stored_value"
        service = RedisService()
        service.client = mock_client

        result = await service.get("mykey")
        assert result == b"stored_value"

    async def test_delete_removes_key(self):
        mock_client = AsyncMock()
        service = RedisService()
        service.client = mock_client

        await service.delete("mykey")
        mock_client.delete.assert_called_once_with("mykey")

    async def test_publish_sends_to_channel(self):
        mock_client = AsyncMock()
        service = RedisService()
        service.client = mock_client

        await service.publish("cruz:devices", '{"device":"ipad","event":"message"}')
        mock_client.publish.assert_called_once_with(
            "cruz:devices", '{"device":"ipad","event":"message"}'
        )

    async def test_operations_raise_if_not_connected(self):
        service = RedisService()
        service.client = None

        with pytest.raises(RuntimeError, match="not connected"):
            await service.get("key")
