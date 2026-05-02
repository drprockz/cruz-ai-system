"""process_gmail_webhook — decode Pub/Sub envelope, resolve historyId
to new messages, dispatch webhook.gmail.new_message per message."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, patch

import pytest

from agents.event_driven_agent import (
    EventDrivenAgent,
    register_event_agent,
    clear_event_registry,
)
from workers.tasks.gmail_webhook_tasks import process_gmail_webhook


@pytest.fixture(autouse=True)
def _isolated_registry():
    clear_event_registry()
    yield
    clear_event_registry()


class _GAgent(EventDrivenAgent):
    TRIGGERS = ["webhook.gmail.new_message"]
    async def process(self, input):
        return None


def _b64(d: dict) -> str:
    return base64.b64encode(json.dumps(d).encode()).decode()


@pytest.mark.asyncio
async def test_dispatches_per_message_id():
    """Pub/Sub envelope contains historyId; we resolve to message IDs
    via Gmail History API and dispatch one trigger per message."""
    register_event_agent(_GAgent)
    fake_history = AsyncMock(return_value=["msg-1", "msg-2"])
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("workers.tasks.gmail_webhook_tasks._fetch_new_message_ids",
               fake_history), \
         patch("workers.tasks.gmail_webhook_tasks._get_arq_pool",
               return_value=fake_pool):
        await process_gmail_webhook(
            ctx={},
            pubsub_message={"data": _b64({"emailAddress": "u@e.com",
                                          "historyId": "12345"})},
        )
    # Two enqueues — one per message
    assert fake_pool.enqueue_job.await_count == 2
    args = [c.args for c in fake_pool.enqueue_job.await_args_list]
    triggers = [a[3]["data"]["message_id"] for a in args]
    assert "msg-1" in triggers and "msg-2" in triggers


@pytest.mark.asyncio
async def test_handles_missing_history_id_gracefully():
    """Malformed Pub/Sub message — log and return without enqueue."""
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("workers.tasks.gmail_webhook_tasks._get_arq_pool",
               return_value=fake_pool):
        result = await process_gmail_webhook(
            ctx={},
            pubsub_message={"data": _b64({})},
        )
    fake_pool.enqueue_job.assert_not_called()
    assert result.get("queued", 0) == 0


@pytest.mark.asyncio
async def test_no_registered_agent_skips_dispatch():
    """Unknown trigger lookup → no enqueue but no error."""
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("workers.tasks.gmail_webhook_tasks._fetch_new_message_ids",
               AsyncMock(return_value=["m1"])), \
         patch("workers.tasks.gmail_webhook_tasks._get_arq_pool",
               return_value=fake_pool):
        await process_gmail_webhook(
            ctx={},
            pubsub_message={"data": _b64({"historyId": "1"})},
        )
    fake_pool.enqueue_job.assert_not_called()
