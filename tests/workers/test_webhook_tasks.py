"""
Webhook task handlers run from the ARQ worker. Each receives the parsed
payload as a dict and returns a summary dict. Failures go via the
after_job_end alert hook; the tasks themselves just log + return.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_github_webhook_task_returns_summary():
    from workers.tasks.webhook_tasks import process_github_webhook
    out = await process_github_webhook(
        {}, event="pull_request",
        payload={"action": "opened", "pull_request": {"number": 9}},
    )
    assert out["event"] == "pull_request"
    assert out["action"] == "opened"
    assert out["pr_number"] == 9


@pytest.mark.asyncio
async def test_vercel_webhook_task_returns_summary():
    from workers.tasks.webhook_tasks import process_vercel_webhook
    out = await process_vercel_webhook(
        {}, payload={"type": "deployment.ready", "payload": {"url": "u"}},
    )
    assert out["type"] == "deployment.ready"


@pytest.mark.asyncio
async def test_google_calendar_webhook_task_returns_summary():
    from workers.tasks.webhook_tasks import process_google_calendar_webhook
    out = await process_google_calendar_webhook(
        {}, headers={"X-Goog-Resource-State": "exists", "X-Goog-Channel-ID": "ch1"},
    )
    assert out["resource_state"] == "exists"
    assert out["channel_id"] == "ch1"


def test_webhook_tasks_registered_on_worker():
    from workers.arq_worker import WorkerSettings
    from workers.tasks.webhook_tasks import (
        process_github_webhook,
        process_vercel_webhook,
        process_google_calendar_webhook,
    )
    assert process_github_webhook in WorkerSettings.functions
    assert process_vercel_webhook in WorkerSettings.functions
    assert process_google_calendar_webhook in WorkerSettings.functions
