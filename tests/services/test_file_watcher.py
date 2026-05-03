"""Tests for services.file_watcher."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from services.file_watcher import (
    WATCH_MAP,
    start_file_watcher,
    stop_file_watcher,
)


@pytest.mark.asyncio
async def test_modification_enqueues_dispatch(tmp_path, monkeypatch):
    """Touching the watched file enqueues dispatch_event_to_agent."""
    from agents.event_driven_agent import (
        EventDrivenAgent,
        clear_event_registry,
        register_event_agent,
    )

    f = tmp_path / "h.md"
    f.write_text("init\n")
    monkeypatch.setitem(WATCH_MAP, str(f), "filewatch.health_journal")

    # Register a fake agent for the trigger
    clear_event_registry()

    class _FW(EventDrivenAgent):
        TRIGGERS = ["filewatch.health_journal"]

        async def process(self, input):  # noqa: ANN001 — test stub
            return None

    register_event_agent(_FW)

    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch(
        "services.file_watcher._get_arq_pool",
        new=AsyncMock(return_value=fake_pool),
    ):
        loop = asyncio.get_event_loop()
        start_file_watcher(loop)
        try:
            f.write_text("changed\n")
            await asyncio.sleep(0.5)  # let watchdog fire
        finally:
            stop_file_watcher()
            clear_event_registry()

    fake_pool.enqueue_job.assert_awaited()


def test_watch_map_includes_health_journal():
    """WATCH_MAP wires health-journal.md → filewatch.health_journal."""
    assert "docs/personal/health-journal.md" in WATCH_MAP
    assert (
        WATCH_MAP["docs/personal/health-journal.md"]
        == "filewatch.health_journal"
    )


def test_start_is_idempotent(monkeypatch):
    """Calling start_file_watcher twice doesn't crash or double-observe."""
    monkeypatch.setattr("services.file_watcher.WATCH_MAP", {})
    loop = asyncio.new_event_loop()
    try:
        start_file_watcher(loop)
        start_file_watcher(loop)
    finally:
        stop_file_watcher()
        loop.close()
