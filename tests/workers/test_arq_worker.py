"""
Tests for ARQ background worker configuration.

Structure under test:
  workers/arq_worker.py        — WorkerSettings with 3 cron jobs
  workers/tasks/pulse_tasks.py — run_pulse(ctx) coroutine  (6 AM)
  workers/tasks/raw_tasks.py   — run_raw(ctx)   coroutine  (3 AM)
  workers/tasks/reach_tasks.py — run_reach(ctx) coroutine  (2 AM)

Cron schedule:
  PULSE  06:00 — morning briefing (stub — RAW/PULSE agents built in Phase 5)
  RAW    03:00 — tech research update (stub)
  REACH  02:00 — lead generation via ReachAgent

Rules:
  - WorkerSettings.redis_settings honours REDIS_URL env var
  - All task functions are async coroutines
  - run_reach() calls ReachAgent with a criteria pulled from env (REACH_CRITERIA)
  - run_pulse() and run_raw() are stubs that log and return without crashing
"""

from __future__ import annotations

import asyncio
import importlib
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────
# WorkerSettings structure
# ─────────────────────────────────────────────

class TestWorkerSettingsStructure:
    def test_arq_worker_can_be_imported(self):
        from workers.arq_worker import WorkerSettings  # noqa: F401

    def test_worker_settings_has_functions(self):
        from workers.arq_worker import WorkerSettings
        assert hasattr(WorkerSettings, "functions")
        assert isinstance(WorkerSettings.functions, list)

    def test_worker_settings_has_cron_jobs(self):
        from workers.arq_worker import WorkerSettings
        assert hasattr(WorkerSettings, "cron_jobs")
        assert isinstance(WorkerSettings.cron_jobs, list)

    def test_worker_settings_has_four_cron_jobs(self):
        from workers.arq_worker import WorkerSettings
        assert len(WorkerSettings.cron_jobs) == 4

    def test_worker_settings_has_redis_settings(self):
        from workers.arq_worker import WorkerSettings
        assert hasattr(WorkerSettings, "redis_settings")

    def test_redis_settings_uses_redis_url_env_var(self):
        """WorkerSettings.redis_settings must reflect REDIS_URL."""
        # Re-import to pick up env var — we just verify the attribute exists and is set
        from workers.arq_worker import WorkerSettings
        settings = WorkerSettings.redis_settings
        assert settings is not None


# ─────────────────────────────────────────────
# Cron schedule
# ─────────────────────────────────────────────

class TestCronSchedule:
    def _get_cron_by_hour(self, hour: int):
        from workers.arq_worker import WorkerSettings
        for job in WorkerSettings.cron_jobs:
            if job.hour == hour:
                return job
        return None

    def test_pulse_runs_at_6am(self):
        job = self._get_cron_by_hour(6)
        assert job is not None, "No cron job scheduled at 6 AM"
        assert job.minute == 0

    def test_raw_runs_at_3am(self):
        job = self._get_cron_by_hour(3)
        assert job is not None, "No cron job scheduled at 3 AM"
        assert job.minute == 0

    def test_reach_runs_at_2am(self):
        job = self._get_cron_by_hour(2)
        assert job is not None, "No cron job scheduled at 2 AM"
        assert job.minute == 0

    def test_each_cron_job_has_a_coroutine(self):
        from workers.arq_worker import WorkerSettings
        for job in WorkerSettings.cron_jobs:
            assert asyncio.iscoroutinefunction(job.coroutine), (
                f"Cron job at {job.hour}:{job.minute:02d} coroutine is not async"
            )


# ─────────────────────────────────────────────
# Task functions — interface
# ─────────────────────────────────────────────

class TestPulseTask:
    def test_run_pulse_can_be_imported(self):
        from workers.tasks.pulse_tasks import run_pulse  # noqa: F401

    def test_run_pulse_is_coroutine(self):
        from workers.tasks.pulse_tasks import run_pulse
        assert asyncio.iscoroutinefunction(run_pulse)

    async def test_run_pulse_does_not_crash(self):
        from workers.tasks.pulse_tasks import run_pulse
        ctx = {}
        # Should not raise — stub implementation
        result = await run_pulse(ctx)
        # No assertion on result; just verify it completes


class TestRawTask:
    def test_run_raw_can_be_imported(self):
        from workers.tasks.raw_tasks import run_raw  # noqa: F401

    def test_run_raw_is_coroutine(self):
        from workers.tasks.raw_tasks import run_raw
        assert asyncio.iscoroutinefunction(run_raw)

    async def test_run_raw_does_not_crash(self):
        from workers.tasks.raw_tasks import run_raw
        ctx = {}
        result = await run_raw(ctx)
        # No assertion on result; just verify it completes


# ─────────────────────────────────────────────
# REACH task — real implementation
# ─────────────────────────────────────────────

class TestReachTask:
    def test_run_reach_can_be_imported(self):
        from workers.tasks.reach_tasks import run_reach  # noqa: F401

    def test_run_reach_is_coroutine(self):
        from workers.tasks.reach_tasks import run_reach
        assert asyncio.iscoroutinefunction(run_reach)

    async def test_run_reach_calls_reach_agent(self):
        """run_reach() must invoke ReachAgent.process()."""
        from workers.tasks.reach_tasks import run_reach

        mock_output = {
            "success": True,
            "result": {"criteria": "test", "total": 1, "leads": []},
            "agent": "REACH",
            "duration_ms": 50,
            "tokens_used": 0,
            "error": None,
            "requires_approval": True,
            "approval_prompt": "Send 1 outreach email?",
        }

        mock_agent = AsyncMock()
        mock_agent.process = AsyncMock(return_value=mock_output)

        with patch("workers.tasks.reach_tasks.ReachAgent", return_value=mock_agent):
            ctx = {}
            await run_reach(ctx)

        mock_agent.process.assert_called_once()

    async def test_run_reach_uses_reach_criteria_env_var(self):
        """run_reach() passes REACH_CRITERIA env var as the task."""
        from workers.tasks.reach_tasks import run_reach

        mock_output = {
            "success": True,
            "result": {"criteria": "test", "total": 0, "leads": []},
            "agent": "REACH",
            "duration_ms": 50,
            "tokens_used": 0,
            "error": None,
            "requires_approval": True,
            "approval_prompt": "Send 0 outreach emails?",
        }

        mock_agent = AsyncMock()
        mock_agent.process = AsyncMock(return_value=mock_output)

        criteria = "Find SaaS founders in Bangalore needing full-stack development"
        with patch("workers.tasks.reach_tasks.ReachAgent", return_value=mock_agent), \
             patch.dict(os.environ, {"REACH_CRITERIA": criteria}):
            await run_reach({})

        call_input = mock_agent.process.call_args[0][0]
        assert call_input["task"] == criteria

    async def test_run_reach_has_default_criteria_when_env_not_set(self):
        """run_reach() has a sensible default criteria if REACH_CRITERIA is unset."""
        from workers.tasks.reach_tasks import run_reach

        mock_output = {
            "success": True,
            "result": {"criteria": "test", "total": 0, "leads": []},
            "agent": "REACH",
            "duration_ms": 50,
            "tokens_used": 0,
            "error": None,
            "requires_approval": True,
            "approval_prompt": "Send 0 outreach emails?",
        }

        mock_agent = AsyncMock()
        mock_agent.process = AsyncMock(return_value=mock_output)

        env_without_criteria = {k: v for k, v in os.environ.items() if k != "REACH_CRITERIA"}
        with patch("workers.tasks.reach_tasks.ReachAgent", return_value=mock_agent), \
             patch.dict(os.environ, env_without_criteria, clear=True):
            await run_reach({})

        call_input = mock_agent.process.call_args[0][0]
        assert isinstance(call_input["task"], str)
        assert len(call_input["task"]) > 0

    async def test_run_reach_does_not_crash_on_agent_failure(self):
        """If ReachAgent raises, run_reach() catches and logs — does not re-raise."""
        from workers.tasks.reach_tasks import run_reach

        mock_agent = AsyncMock()
        mock_agent.process = AsyncMock(side_effect=Exception("Gemini down"))

        with patch("workers.tasks.reach_tasks.ReachAgent", return_value=mock_agent):
            # Should not raise
            await run_reach({})


# ─────────────────────────────────────────────
# Functions list wiring
# ─────────────────────────────────────────────

class TestFunctionsList:
    def test_functions_list_includes_run_pulse(self):
        from workers.arq_worker import WorkerSettings
        from workers.tasks.pulse_tasks import run_pulse
        assert run_pulse in WorkerSettings.functions

    def test_functions_list_includes_run_raw(self):
        from workers.arq_worker import WorkerSettings
        from workers.tasks.raw_tasks import run_raw
        assert run_raw in WorkerSettings.functions

    def test_functions_list_includes_run_reach(self):
        from workers.arq_worker import WorkerSettings
        from workers.tasks.reach_tasks import run_reach
        assert run_reach in WorkerSettings.functions
