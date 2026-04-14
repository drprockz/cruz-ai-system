"""Tests for workers/tasks/backup_tasks.py and cron registration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_backup_calls_all_three_snapshots_and_uploads():
    from workers.tasks import backup_tasks

    with patch.object(
        backup_tasks, "BackupService"
    ) as MockSvc:
        inst = MockSvc.return_value
        inst.snapshot_postgres = AsyncMock(return_value="/tmp/pg.dump")
        inst.snapshot_redis = AsyncMock(return_value="/tmp/redis.rdb")
        inst.snapshot_qdrant = AsyncMock(return_value="/tmp/qdrant.tar.gz")
        inst.upload_to_drive = AsyncMock(return_value="https://drive/x")

        result = await backup_tasks.run_backup({})

        inst.snapshot_postgres.assert_awaited_once()
        inst.snapshot_redis.assert_awaited_once()
        inst.snapshot_qdrant.assert_awaited_once()
        assert inst.upload_to_drive.await_count == 3
        assert len(result["uploaded"]) == 3


@pytest.mark.asyncio
async def test_run_backup_continues_when_one_snapshot_fails():
    from workers.tasks import backup_tasks

    with patch.object(backup_tasks, "BackupService") as MockSvc:
        inst = MockSvc.return_value
        inst.snapshot_postgres = AsyncMock(return_value="/tmp/pg.dump")
        inst.snapshot_redis = AsyncMock(side_effect=RuntimeError("redis down"))
        inst.snapshot_qdrant = AsyncMock(return_value="/tmp/q.tar.gz")
        inst.upload_to_drive = AsyncMock(return_value="https://drive/x")

        result = await backup_tasks.run_backup({})
        assert "redis" in result["errors"]
        assert len(result["uploaded"]) == 2


def test_backup_cron_registered_in_worker():
    from workers.arq_worker import WorkerSettings
    from workers.tasks.backup_tasks import run_backup

    assert run_backup in WorkerSettings.functions
    # find a cron entry whose coroutine is run_backup at 04:00
    found = False
    for job in WorkerSettings.cron_jobs:
        if getattr(job, "coroutine", None) is run_backup or getattr(
            job, "_coroutine", None
        ) is run_backup:
            found = True
            break
    assert found, "run_backup cron not registered"
