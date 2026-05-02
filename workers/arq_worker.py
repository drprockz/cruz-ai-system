"""
ARQ worker entrypoint for CRUZ background tasks.

Cron schedule:
  02:00  REACH  — nightly lead discovery + outreach drafting
  03:00  RAW    — tech research + dependency update scan (Phase 5 stub)
  04:00  BACKUP — pg_dump + Redis RDB + Qdrant tar → Google Drive
  06:00  PULSE  — morning briefing (Phase 5 stub)

Run with:
  arq workers.arq_worker.WorkerSettings
"""

from __future__ import annotations

import os

from arq import cron
from arq.connections import RedisSettings

from services.alerts import get_alert_service
from workers.tasks.backup_tasks import run_backup
from workers.tasks.pulse_tasks import run_pulse
from workers.tasks.raw_tasks import run_raw
from workers.tasks.reach_tasks import run_reach
from workers.tasks.dispatch import dispatch_event_to_agent, dispatch_event_to_handler
from workers.tasks.gmail_webhook_tasks import process_gmail_webhook
from workers.tasks.webhook_tasks import (
    process_github_webhook,
    process_google_calendar_webhook,
    process_vercel_webhook,
)


async def on_job_end(ctx: dict) -> None:
    """
    ARQ after_job hook — alert on failed scheduled jobs.

    Fires a critical alert whenever ``ctx['success']`` is False. Alert
    failures are swallowed inside AlertService so this hook never raises.
    """
    if ctx.get("success", True):
        return
    fn = ctx.get("function", "unknown")
    job_id = ctx.get("job_id", "?")
    exc = ctx.get("exception")
    try:
        await get_alert_service().notify(
            "critical",
            f"ARQ job failed: {fn}",
            f"job_id={job_id} function={fn} error={exc}",
        )
    except Exception:
        pass


class WorkerSettings:
    """ARQ WorkerSettings — defines scheduled cron jobs and Redis connection."""

    functions = [
        run_pulse, run_raw, run_reach, run_backup,
        process_github_webhook,
        process_vercel_webhook,
        process_google_calendar_webhook,
        process_gmail_webhook,
        dispatch_event_to_agent,
        dispatch_event_to_handler,
    ]
    after_job_end = on_job_end

    cron_jobs = [
        cron(run_reach, hour=2, minute=0),
        cron(run_raw, hour=3, minute=0),
        cron(run_backup, hour=4, minute=0),
        cron(run_pulse, hour=6, minute=0),
    ]

    redis_settings = RedisSettings.from_dsn(
        os.environ.get("REDIS_URL", "redis://localhost:6379")
    )
