"""StateService unit tests — verifies Postgres-backed per-agent state."""

from __future__ import annotations

import uuid

import pytest

from services.agent_state import StateService, get_state_service
from services.db import get_db_service


@pytest.fixture
async def db():
    svc = get_db_service()
    await svc.connect()
    # Clean slate
    await svc.execute("DELETE FROM agent_state WHERE agent_name LIKE 'test_%'")
    yield svc
    await svc.execute("DELETE FROM agent_state WHERE agent_name LIKE 'test_%'")


@pytest.fixture
async def state(db):
    """Async fixture so pytest-asyncio resolves the `db` async generator first.
    Provides a (StateService, unique_agent_name) tuple so each test gets an
    isolated agent_name namespace — safe for `pytest -n auto` parallel runs."""
    return StateService(db), f"test_{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_set_and_get_returns_value(state):
    svc, agent = state
    await svc.set(agent, "key1", {"foo": "bar"})
    result = await svc.get(agent, "key1")
    assert result == {"foo": "bar"}


@pytest.mark.asyncio
async def test_get_missing_returns_default(state):
    svc, agent = state
    result = await svc.get(agent, "missing", default={"d": 1})
    assert result == {"d": 1}


@pytest.mark.asyncio
async def test_set_overwrites_existing(state):
    svc, agent = state
    await svc.set(agent, "key1", {"v": 1})
    await svc.set(agent, "key1", {"v": 2})
    result = await svc.get(agent, "key1")
    assert result == {"v": 2}


@pytest.mark.asyncio
async def test_set_with_ttl_populates_expires_at(state, db):
    svc, agent = state
    await svc.set(agent, "k_ttl", {"x": 1}, ttl_seconds=60)
    # immediately readable
    assert await svc.get(agent, "k_ttl") == {"x": 1}
    # row has expires_at populated (~60s in future)
    row = await db.fetchrow(
        "SELECT expires_at FROM agent_state WHERE agent_name=$1 AND key=$2",
        agent, "k_ttl",
    )
    assert row["expires_at"] is not None


@pytest.mark.asyncio
async def test_get_skips_expired_row_without_cleanup(state, db):
    """Verify the WHERE clause `expires_at > NOW()` works on its own."""
    svc, agent = state
    await svc.set(agent, "k_exp_read", {"x": 1}, ttl_seconds=60)
    # Force expiry without running cleanup_expired — get() must still skip it.
    await db.execute(
        "UPDATE agent_state SET expires_at = NOW() - INTERVAL '1 minute' "
        "WHERE agent_name=$1 AND key=$2",
        agent, "k_exp_read",
    )
    assert await svc.get(agent, "k_exp_read", default="MISS") == "MISS"


@pytest.mark.asyncio
async def test_delete_removes_row(state):
    svc, agent = state
    await svc.set(agent, "k_del", {"y": 1})
    await svc.delete(agent, "k_del")
    assert await svc.get(agent, "k_del") is None


@pytest.mark.asyncio
async def test_cleanup_expired_removes_only_expired(state, db):
    svc, agent = state
    # one expired, one not
    await svc.set(agent, "k_exp", {"a": 1}, ttl_seconds=1)
    await svc.set(agent, "k_keep", {"b": 1})
    # force expiry by direct UPDATE in past
    await db.execute(
        "UPDATE agent_state SET expires_at = NOW() - INTERVAL '1 hour' "
        "WHERE agent_name=$1 AND key=$2",
        agent, "k_exp",
    )
    deleted = await svc.cleanup_expired()
    assert deleted >= 1
    assert await svc.get(agent, "k_exp") is None
    assert await svc.get(agent, "k_keep") == {"b": 1}


@pytest.mark.asyncio
async def test_set_rejects_non_serialisable_value(state):
    """Use a self-referencing dict — survives `default=str` fallback,
    triggers ValueError("Circular reference detected")."""
    svc, agent = state
    circular: dict = {}
    circular["self"] = circular
    with pytest.raises(ValueError, match="not JSON-serialisable"):
        await svc.set(agent, "k_bad", circular)


@pytest.mark.asyncio
async def test_get_state_service_returns_singleton():
    # Reset module-level singleton so this test is order-independent.
    import services.agent_state as mod
    mod._instance = None
    svc1 = get_state_service()
    svc2 = get_state_service()
    assert svc1 is svc2
