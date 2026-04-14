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

from workers.tasks.backup_tasks import run_backup
from workers.tasks.pulse_tasks import run_pulse
from workers.tasks.raw_tasks import run_raw
from workers.tasks.reach_tasks import run_reach


class WorkerSettings:
    """ARQ WorkerSettings — defines scheduled cron jobs and Redis connection."""

    functions = [run_pulse, run_raw, run_reach, run_backup]

    cron_jobs = [
        cron(run_reach, hour=2, minute=0),
        cron(run_raw, hour=3, minute=0),
        cron(run_backup, hour=4, minute=0),
        cron(run_pulse, hour=6, minute=0),
    ]

    redis_settings = RedisSettings.from_dsn(
        os.environ.get("REDIS_URL", "redis://localhost:6379")
    )
