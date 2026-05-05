"""
ARQ worker entrypoint for CRUZ background tasks.

v1 cron schedule:
  02:00  REACH  — nightly lead discovery + outreach drafting
  03:00  RAW    — tech research + dependency update scan (Phase 5 stub)
  04:00  BACKUP — pg_dump + Redis RDB + Qdrant tar → Google Drive
  06:00  PULSE  — morning briefing (Phase 5 stub)

SP5 cron schedule (per spec §6 trigger inventory):
  06:00  gmail_watch_resubscribe — refresh Gmail Pub/Sub watch
  04:30  agent_state_cleanup     — prune stale dedup keys / agent state
  */5    gmail_poll_fallback     — every 5 min when push isn't healthy
  07:00  daily_briefing           — handler
  08:00  funded_watcher           — agent
  10:00  followup                 — agent
  17:00 fri  portfolio_watcher    — handler
  18:00 sun  relationship_maint.  — handler
  21:00  health_guardian          — agent
  09:00 mon  warm_network         — agent
  09:00 1st  expense_auditor      — handler (monthly)
  10:00 1st {Jan, Apr, Jul, Oct}  tax_helper — handler (quarterly)

Run with:
  arq workers.arq_worker.WorkerSettings
"""

from __future__ import annotations

import asyncio
import os

from arq import cron
from arq.connections import RedisSettings

from services.alerts import get_alert_service
from workers.tasks.backup_tasks import run_backup
from workers.tasks.browser_health import browser_health_probe
from workers.tasks.pulse_tasks import run_pulse
from workers.tasks.raw_tasks import run_raw
from workers.tasks.reach_tasks import run_reach
from workers.tasks.webhook_tasks import (
    process_github_webhook,
    process_google_calendar_webhook,
    process_vercel_webhook,
)

# ─── SP5 imports ────────────────────────────────────────────────
from workers.tasks.dispatch import (
    dispatch_event_to_agent,
    dispatch_event_to_handler,
    register_event_handler,
)
from workers.tasks.gmail_webhook_tasks import process_gmail_webhook
from workers.tasks.maintenance_tasks import (
    agent_state_cleanup,
    gmail_poll_fallback,
    gmail_watch_resubscribe,
)

# Importing handler modules; cron-triggered ones are explicitly registered
# below. travel_planner self-registers at module bottom for its webhook
# trigger.
import workers.handlers.daily_briefing  # noqa: F401
import workers.handlers.expense_auditor  # noqa: F401
import workers.handlers.portfolio_watcher  # noqa: F401
import workers.handlers.relationship_maintenance  # noqa: F401
import workers.handlers.tax_helper  # noqa: F401
import workers.handlers.travel_planner  # noqa: F401

# SP5 agent classes are explicitly registered below for clarity (no
# module-level side effects in agent files — keeps them framework-agnostic).
from agents.event_driven_agent import register_event_agent
from agents.followup.followup_agent import FollowupAgent
from agents.funded_watcher.funded_watcher_agent import FundedWatcherAgent
from agents.health_guardian.health_guardian_agent import HealthGuardianAgent
from agents.meeting_prep.meeting_prep_agent import MeetingPrepAgent
from agents.reply_triage.reply_triage_agent import ReplyTriageAgent
from agents.warm_network.warm_network_agent import WarmNetworkAgent

register_event_agent(ReplyTriageAgent)
register_event_agent(FollowupAgent)
register_event_agent(MeetingPrepAgent)
register_event_agent(FundedWatcherAgent)
register_event_agent(WarmNetworkAgent)
register_event_agent(HealthGuardianAgent)

# Cron-triggered handlers register here (webhook-triggered ones
# self-register at their module bottom).
register_event_handler("workers.handlers.daily_briefing", ["cron.daily.07:00"])
register_event_handler("workers.handlers.expense_auditor", ["cron.monthly.1st.09:00"])
register_event_handler("workers.handlers.portfolio_watcher", ["cron.weekly.friday.17:00"])
register_event_handler("workers.handlers.tax_helper", ["cron.quarterly.1st.10:00"])
register_event_handler(
    "workers.handlers.relationship_maintenance", ["cron.weekly.sunday.18:00"]
)


# ─── ARQ task wrappers for cron-triggered handlers ──────────────
# ARQ cron jobs need a callable, not a string trigger. Wrap each
# handler dispatch in a tiny coroutine that arq can invoke directly.

async def fire_daily_briefing(ctx):
    return await dispatch_event_to_handler(
        ctx,
        "workers.handlers.daily_briefing",
        {"trigger": "cron.daily.07:00", "data": {}},
    )


async def fire_expense_auditor(ctx):
    return await dispatch_event_to_handler(
        ctx,
        "workers.handlers.expense_auditor",
        {"trigger": "cron.monthly.1st.09:00", "data": {}},
    )


async def fire_portfolio_watcher(ctx):
    return await dispatch_event_to_handler(
        ctx,
        "workers.handlers.portfolio_watcher",
        {"trigger": "cron.weekly.friday.17:00", "data": {}},
    )


async def fire_tax_helper(ctx):
    return await dispatch_event_to_handler(
        ctx,
        "workers.handlers.tax_helper",
        {"trigger": "cron.quarterly.1st.10:00", "data": {}},
    )


async def fire_relationship_maintenance(ctx):
    return await dispatch_event_to_handler(
        ctx,
        "workers.handlers.relationship_maintenance",
        {"trigger": "cron.weekly.sunday.18:00", "data": {}},
    )


# ─── ARQ task wrappers for cron-triggered AGENTS ────────────────
# Same pattern — use dispatch_event_to_agent. Agent classes already
# imported above for register_event_agent calls.

async def fire_followup_cron(ctx):
    return await dispatch_event_to_agent(
        ctx,
        FollowupAgent.__module__,
        FollowupAgent.__name__,
        {"trigger": "cron.daily.10:00", "data": {}},
    )


async def fire_funded_watcher_cron(ctx):
    return await dispatch_event_to_agent(
        ctx,
        FundedWatcherAgent.__module__,
        FundedWatcherAgent.__name__,
        {"trigger": "cron.daily.08:00", "data": {}},
    )


async def fire_warm_network_cron(ctx):
    return await dispatch_event_to_agent(
        ctx,
        WarmNetworkAgent.__module__,
        WarmNetworkAgent.__name__,
        {"trigger": "cron.weekly.monday.09:00", "data": {}},
    )


async def fire_health_guardian_cron(ctx):
    return await dispatch_event_to_agent(
        ctx,
        HealthGuardianAgent.__module__,
        HealthGuardianAgent.__name__,
        {"trigger": "cron.daily.21:00", "data": {}},
    )


async def on_startup(ctx):
    """ARQ startup hook — start the file watcher on the running loop."""
    from services.file_watcher import start_file_watcher

    start_file_watcher(asyncio.get_running_loop())


async def on_shutdown(ctx):
    """ARQ shutdown hook — stop the file watcher."""
    from services.file_watcher import stop_file_watcher

    stop_file_watcher()


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
        # v1
        run_pulse,
        run_raw,
        run_reach,
        run_backup,
        # SP4
        browser_health_probe,
        process_github_webhook,
        process_vercel_webhook,
        process_google_calendar_webhook,
        # SP5 — dispatch
        dispatch_event_to_agent,
        dispatch_event_to_handler,
        process_gmail_webhook,
        # SP5 — maintenance
        gmail_watch_resubscribe,
        agent_state_cleanup,
        gmail_poll_fallback,
        # SP5 — cron fire wrappers (handlers)
        fire_daily_briefing,
        fire_expense_auditor,
        fire_portfolio_watcher,
        fire_tax_helper,
        fire_relationship_maintenance,
        # SP5 — cron fire wrappers (agents)
        fire_followup_cron,
        fire_funded_watcher_cron,
        fire_warm_network_cron,
        fire_health_guardian_cron,
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    after_job_end = on_job_end

    cron_jobs = [
        # v1
        cron(run_reach, hour=2, minute=0),
        cron(run_raw, hour=3, minute=0),
        cron(run_backup, hour=4, minute=0),
        cron(run_pulse, hour=6, minute=0),
        # SP4
        cron(browser_health_probe, hour=9, minute=0),
        # SP5 — agent crons
        cron(fire_funded_watcher_cron, hour=8, minute=0),  # daily
        cron(fire_followup_cron, hour=10, minute=0),  # daily
        cron(fire_health_guardian_cron, hour=21, minute=0),  # daily
        cron(fire_warm_network_cron, weekday="mon", hour=9, minute=0),
        # SP5 — handler crons
        cron(fire_daily_briefing, hour=7, minute=0),  # daily
        cron(fire_portfolio_watcher, weekday="fri", hour=17, minute=0),
        cron(fire_relationship_maintenance, weekday="sun", hour=18, minute=0),
        cron(fire_expense_auditor, day=1, hour=9, minute=0),  # monthly
        cron(
            fire_tax_helper,
            month={1, 4, 7, 10},
            day=1,
            hour=10,
            minute=0,
        ),
        # SP5 — maintenance
        cron(gmail_watch_resubscribe, hour=6, minute=0),
        cron(agent_state_cleanup, hour=4, minute=30),
        cron(
            gmail_poll_fallback,
            minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
        ),
    ]

    redis_settings = RedisSettings.from_dsn(
        os.environ.get("REDIS_URL", "redis://localhost:6379")
    )
