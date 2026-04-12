"""
Tests for services/db.py — asyncpg connection pool management.
RED phase — must fail before production code exists.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.db import DatabaseService, get_db_service


class TestDatabaseServiceInterface:
    def test_database_service_class_exists(self):
        service = DatabaseService()
        assert service is not None

    def test_database_service_has_connect_method(self):
        service = DatabaseService()
        assert hasattr(service, "connect")
        assert callable(service.connect)

    def test_database_service_has_disconnect_method(self):
        service = DatabaseService()
        assert hasattr(service, "disconnect")
        assert callable(service.disconnect)

    def test_database_service_has_execute_method(self):
        service = DatabaseService()
        assert hasattr(service, "execute")
        assert callable(service.execute)

    def test_database_service_has_fetch_method(self):
        service = DatabaseService()
        assert hasattr(service, "fetch")
        assert callable(service.fetch)

    def test_database_service_has_fetchrow_method(self):
        service = DatabaseService()
        assert hasattr(service, "fetchrow")
        assert callable(service.fetchrow)

    def test_database_service_uses_database_url_from_env(self):
        url = "postgresql://user:pass@host:5432/db"
        with patch.dict(os.environ, {"DATABASE_URL": url}):
            service = DatabaseService()
            assert service.database_url == url

    def test_database_service_raises_if_database_url_missing(self):
        env_without_url = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        with patch.dict(os.environ, env_without_url, clear=True):
            with pytest.raises(ValueError, match="DATABASE_URL"):
                DatabaseService()


class TestGetDbService:
    def test_get_db_service_returns_database_service(self):
        service = get_db_service()
        assert isinstance(service, DatabaseService)

    def test_get_db_service_returns_same_instance(self):
        """Module-level singleton — two calls return the same object."""
        s1 = get_db_service()
        s2 = get_db_service()
        assert s1 is s2


class TestDatabaseServiceConnect:
    async def test_connect_creates_pool(self):
        mock_pool = MagicMock()
        service = DatabaseService()

        with patch("services.db.asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            await service.connect()
            assert service.pool is mock_pool

    async def test_connect_uses_database_url(self):
        mock_pool = MagicMock()
        service = DatabaseService()

        with patch("services.db.asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)) as mock_create:
            await service.connect()
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args
            # DATABASE_URL must be passed (as first positional or dsn keyword)
            assert service.database_url in str(call_kwargs)

    async def test_disconnect_closes_pool(self):
        mock_pool = AsyncMock()
        service = DatabaseService()
        service.pool = mock_pool

        await service.disconnect()
        mock_pool.close.assert_called_once()


def _make_pool_mock(mock_conn: AsyncMock) -> MagicMock:
    """
    Build a MagicMock that mimics asyncpg.Pool.acquire() behaviour.

    asyncpg's pool.acquire() is NOT a coroutine — it returns a
    PoolConnectionContext (async context manager) directly without being
    awaited.  Using AsyncMock for the pool would make acquire() return a
    coroutine, which breaks `async with pool.acquire() as conn:`.
    """
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


class TestDatabaseServiceQueries:
    async def test_execute_calls_pool_execute(self):
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="INSERT 0 1")
        mock_pool = _make_pool_mock(mock_conn)

        service = DatabaseService()
        service.pool = mock_pool

        result = await service.execute("INSERT INTO test VALUES ($1)", "value")
        mock_conn.execute.assert_called_once_with("INSERT INTO test VALUES ($1)", "value")

    async def test_fetch_returns_list_of_rows(self):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
        mock_pool = _make_pool_mock(mock_conn)

        service = DatabaseService()
        service.pool = mock_pool

        rows = await service.fetch("SELECT * FROM test")
        assert rows == [{"id": 1}, {"id": 2}]

    async def test_fetchrow_returns_single_row(self):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"id": 1, "name": "test"})
        mock_pool = _make_pool_mock(mock_conn)

        service = DatabaseService()
        service.pool = mock_pool

        row = await service.fetchrow("SELECT * FROM test WHERE id = $1", 1)
        assert row == {"id": 1, "name": "test"}

    async def test_execute_raises_if_pool_not_connected(self):
        service = DatabaseService()
        service.pool = None

        with pytest.raises(RuntimeError, match="not connected"):
            await service.execute("SELECT 1")
