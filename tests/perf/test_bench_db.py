"""Tests for scripts/perf/bench_db.py — DB hot-query p95 benchmark."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_time_coro_returns_milliseconds():
    from scripts.perf.bench_db import time_coro

    async def fast():
        return "ok"

    ms = await time_coro(fast())
    assert ms >= 0
    assert ms < 1000  # trivial coro should be well under 1s


@pytest.mark.asyncio
async def test_bench_load_history_runs_n_times():
    from scripts.perf import bench_db

    mock_db = AsyncMock()
    mock_db.fetch = AsyncMock(return_value=[])
    samples = await bench_db.bench_load_history(mock_db, "conv-id", n=5)
    assert len(samples) == 5
    assert mock_db.fetch.await_count == 5


@pytest.mark.asyncio
async def test_bench_agent_log_insert_runs_n_times():
    from scripts.perf import bench_db

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=None)
    samples = await bench_db.bench_agent_log_insert(mock_db, n=5)
    assert len(samples) == 5
    assert mock_db.execute.await_count == 5


@pytest.mark.asyncio
async def test_bench_logs_by_trace_runs_n_times():
    from scripts.perf import bench_db

    mock_db = AsyncMock()
    mock_db.fetch = AsyncMock(return_value=[])
    samples = await bench_db.bench_logs_by_trace(mock_db, "trace-id", n=5)
    assert len(samples) == 5


@pytest.mark.asyncio
async def test_main_prints_friendly_message_when_db_unreachable(capsys):
    from scripts.perf import bench_db

    with patch.object(
        bench_db, "_connect", new=AsyncMock(side_effect=Exception("refused"))
    ):
        rc = await bench_db.main(n=1)
        assert rc != 0
        out = capsys.readouterr().out.lower()
        assert "postgres" in out or "database" in out or "not running" in out
