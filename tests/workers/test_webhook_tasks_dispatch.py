"""Webhook engine extension — verify existing webhook tasks now also
dispatch to registered EventDrivenAgent classes via EVENT_REGISTRY."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.event_driven_agent import (
    EventDrivenAgent,
    register_event_agent,
    clear_event_registry,
)
from workers.tasks.webhook_tasks import (
    process_github_webhook,
    process_vercel_webhook,
    process_google_calendar_webhook,
)


@pytest.fixture(autouse=True)
def _isolated_registry():
    clear_event_registry()
    yield
    clear_event_registry()


class _GithubAgent(EventDrivenAgent):
    TRIGGERS = ["webhook.github"]
    async def process(self, input):
        return None


@pytest.mark.asyncio
async def test_github_webhook_dispatches_to_registered_agent():
    register_event_agent(_GithubAgent)
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("workers.tasks.webhook_tasks._get_arq_pool",
               return_value=fake_pool):
        await process_github_webhook(
            ctx={},
            event="pull_request",
            payload={"action": "opened", "repository": {"full_name": "x/y"},
                     "pull_request": {"number": 7}},
        )
    fake_pool.enqueue_job.assert_awaited_with(
        "dispatch_event_to_agent",
        # module_path, class_name
        "tests.workers.test_webhook_tasks_dispatch",
        "_GithubAgent",
        # event dict
        {
            "trigger": "webhook.github",
            "data": {"action": "opened",
                     "repository": {"full_name": "x/y"},
                     "pull_request": {"number": 7}},
            "github_event": "pull_request",
        },
    )


@pytest.mark.asyncio
async def test_no_registered_agent_means_no_dispatch_but_logging_still_runs():
    """v1 logging behavior is preserved when no agent is registered."""
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("workers.tasks.webhook_tasks._get_arq_pool",
               return_value=fake_pool):
        result = await process_github_webhook(
            ctx={},
            event="push",
            payload={"action": "push"},
        )
    fake_pool.enqueue_job.assert_not_called()
    # Original return value (logging summary) still produced
    assert result is not None
    assert result.get("event") == "push"


@pytest.mark.asyncio
async def test_calendar_webhook_dispatches_with_trigger_name():
    class _CalAgent(EventDrivenAgent):
        TRIGGERS = ["webhook.google-calendar"]
        async def process(self, input):
            return None

    register_event_agent(_CalAgent)
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("workers.tasks.webhook_tasks._get_arq_pool",
               return_value=fake_pool):
        await process_google_calendar_webhook(
            ctx={},
            headers={"X-Goog-Resource-State": "exists",
                     "X-Goog-Channel-ID": "ch1"},
        )
    args = fake_pool.enqueue_job.await_args.args
    assert args[0] == "dispatch_event_to_agent"
    assert args[1] == _CalAgent.__module__
    assert args[2] == "_CalAgent"
    assert args[3]["trigger"] == "webhook.google-calendar"
