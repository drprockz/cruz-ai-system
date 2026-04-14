"""Tests for scripts/perf/bench_concurrent.py — 10 concurrent POST /command."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_concurrent_returns_result_per_request():
    from scripts.perf import bench_concurrent

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await bench_concurrent.run_concurrent(
            "http://x", {"message": "hi"}, concurrency=10
        )
    assert len(results) == 10
    assert all(r["status"] == 200 for r in results)


@pytest.mark.asyncio
async def test_run_concurrent_captures_errors():
    from scripts.perf import bench_concurrent

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("network"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await bench_concurrent.run_concurrent(
            "http://x", {"message": "hi"}, concurrency=3
        )
    assert len(results) == 3
    assert all(r["status"] == "error" for r in results)


@pytest.mark.asyncio
async def test_main_prints_clear_message_when_server_down(capsys):
    from scripts.perf import bench_concurrent

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        rc = await bench_concurrent.main()
    assert rc != 0
    out = capsys.readouterr().out.lower()
    assert "start cruz" in out or "not running" in out
