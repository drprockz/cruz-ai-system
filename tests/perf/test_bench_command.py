"""Tests for scripts/perf/bench_command.py — latency benchmark harness."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_percentiles_computes_p50_p95_p99():
    from scripts.perf.bench_command import percentiles

    samples = list(range(1, 101))  # 1..100 ms
    p = percentiles(samples)
    assert p["p50"] == 50
    assert p["p95"] == 95
    assert p["p99"] == 99


def test_percentiles_handles_empty_list():
    from scripts.perf.bench_command import percentiles

    assert percentiles([]) == {"p50": 0.0, "p95": 0.0, "p99": 0.0}


@pytest.mark.asyncio
async def test_run_one_returns_elapsed_ms_on_success():
    from scripts.perf import bench_command

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"ok": True})
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    elapsed = await bench_command.run_one(
        mock_client, "http://x", {"message": "hi", "stream": False}
    )
    assert elapsed is not None
    assert elapsed >= 0
    mock_client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_one_returns_none_on_error():
    from scripts.perf import bench_command

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("boom"))
    result = await bench_command.run_one(
        mock_client, "http://x", {"message": "hi"}
    )
    assert result is None


@pytest.mark.asyncio
async def test_bench_path_runs_n_iterations():
    from scripts.perf import bench_command

    with patch.object(bench_command, "run_one", new=AsyncMock(return_value=5.0)):
        mock_client = AsyncMock()
        results = await bench_command.bench_path(
            mock_client, "http://x", {"message": "hi"}, n=10
        )
        assert len(results) == 10
        assert all(r == 5.0 for r in results)


@pytest.mark.asyncio
async def test_main_prints_server_not_running_when_unreachable(capsys):
    from scripts.perf import bench_command

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        rc = await bench_command.main(n=1)
        assert rc != 0
        out = capsys.readouterr().out
        assert "start CRUZ" in out.lower() or "not running" in out.lower()
