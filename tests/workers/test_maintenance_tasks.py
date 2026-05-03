"""Tests for SP5 maintenance crons."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from workers.tasks.maintenance_tasks import (
    agent_state_cleanup,
    gmail_poll_fallback,
    gmail_watch_resubscribe,
)


@pytest.mark.asyncio
async def test_state_cleanup_returns_deleted_count():
    fake_state = AsyncMock()
    fake_state.cleanup_expired = AsyncMock(return_value=42)
    with patch(
        "workers.tasks.maintenance_tasks.get_state_service",
        return_value=fake_state,
    ):
        result = await agent_state_cleanup({})
    assert result == {"success": True, "deleted": 42}


@pytest.mark.asyncio
async def test_gmail_resubscribe_skips_when_topic_unset(monkeypatch):
    monkeypatch.delenv("GMAIL_PUBSUB_TOPIC", raising=False)
    result = await gmail_watch_resubscribe({})
    assert result["success"] is False
    assert result["reason"] == "no_topic"


@pytest.mark.asyncio
async def test_gmail_poll_dispatches_only_new_ids():
    from agents.event_driven_agent import (
        EventDrivenAgent,
        clear_event_registry,
        register_event_agent,
    )

    clear_event_registry()

    class _RT(EventDrivenAgent):
        TRIGGERS = ["webhook.gmail.new_message"]

        async def process(self, input):  # noqa: A002
            return None

    register_event_agent(_RT)

    fake_state = AsyncMock()
    fake_state.get = AsyncMock(return_value=["seen-1", "seen-2"])
    fake_state.set = AsyncMock()
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch(
        "workers.tasks.maintenance_tasks.get_state_service",
        return_value=fake_state,
    ), patch(
        "workers.tasks.maintenance_tasks.list_recent_inbound",
        AsyncMock(return_value=["seen-1", "new-3", "new-4"]),
    ), patch(
        "workers.tasks.maintenance_tasks._get_arq_pool",
        new=AsyncMock(return_value=fake_pool),
    ):
        result = await gmail_poll_fallback({})
    clear_event_registry()
    assert result["new"] == 2
    # Should enqueue exactly twice (new-3, new-4)
    assert fake_pool.enqueue_job.await_count == 2


@pytest.mark.asyncio
async def test_gmail_poll_no_new_returns_zero():
    fake_state = AsyncMock()
    fake_state.get = AsyncMock(return_value=["a", "b"])
    fake_state.set = AsyncMock()
    with patch(
        "workers.tasks.maintenance_tasks.get_state_service",
        return_value=fake_state,
    ), patch(
        "workers.tasks.maintenance_tasks.list_recent_inbound",
        AsyncMock(return_value=["a", "b"]),
    ):
        result = await gmail_poll_fallback({})
    assert result == {"success": True, "new": 0}
