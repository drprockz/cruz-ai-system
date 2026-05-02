# tests/agents/test_calendar_agent_live.py
"""Live-tier CalendarAgent tests — real Google Calendar API.

Run on the Mac Mini with a provisioned token:
    CRUZ_LIVE_MAC_TESTS=1 pytest tests/agents/test_calendar_agent_live.py -v

Skipped automatically when env var unset, on Linux, or when no token file exists.

Cleanup deletes ALL events with title prefix 'CRUZ TEST —' from the cleanup
window (now-1h to now+7d), even on failure (pytest finalizer).
"""

from __future__ import annotations

import asyncio
import os
import platform
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio

from agents.calendar.calendar_agent import CalendarAgent
from services.gcal import get_gcal_service

LIVE = os.environ.get("CRUZ_LIVE_MAC_TESTS") == "1"
IS_MAC = platform.system() == "Darwin"
TOKEN_PATH = Path(
    os.path.expanduser(os.environ.get("GCAL_TOKEN_PATH", "~/.config/cruz/gcal-token.json"))
)
HAS_TOKEN = TOKEN_PATH.exists()

pytestmark = pytest.mark.skipif(
    not (LIVE and IS_MAC and HAS_TOKEN),
    reason="Live calendar tests require CRUZ_LIVE_MAC_TESTS=1, macOS, and a provisioned gcal token",
)

PREFIX = "CRUZ TEST —"


def _input(**ctx):
    return {
        "task": "live calendar test",
        "context": ctx,
        "trace_id": "live-trace",
        "conversation_id": "live-conv",
    }


@pytest_asyncio.fixture
async def cleanup_test_events():
    """Delete all CRUZ TEST events created within the cleanup window, even on failure.

    Async fixture (not sync) — `asyncio.get_event_loop().run_until_complete()` from a
    sync fixture conflicts with pytest-asyncio's loop management. The yield-style
    finalizer still runs even if the wrapped test raises.
    """
    yield
    await _cleanup()


async def _cleanup():
    gcal = get_gcal_service()
    now = datetime.now(timezone.utc)
    # Window widened to +7d to catch any seeded events from future tests.
    events = await gcal.list_events(
        start_iso=(now - timedelta(hours=1)).isoformat(),
        end_iso=(now + timedelta(days=7)).isoformat(),
    )
    for ev in events:
        if (ev.get("summary", "")).startswith(PREFIX):
            try:
                await gcal.delete_event(ev["id"])
            except Exception as exc:
                print(f"cleanup failed for {ev.get('id')}: {exc}")


@pytest.mark.asyncio
async def test_live_create_self_only_event_round_trips_google_and_calendar_app(
    cleanup_test_events,
) -> None:
    agent = CalendarAgent()
    title = f"{PREFIX} self-only {uuid.uuid4().hex[:8]}"
    start = (datetime.now() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)

    out = await agent.process(_input(
        tool="calendar_create_event",
        title=title,
        start_iso=start.isoformat(timespec="seconds"),
        end_iso=end.isoformat(timespec="seconds"),
    ))

    assert out["success"] is True, f"create failed: {out.get('error')}"
    assert out["requires_approval"] is False
    event_id = out["result"]["id"]

    # Verify visible in Google API list
    gcal = get_gcal_service()
    events = await gcal.list_events(
        start.isoformat(timespec="seconds"),
        end.isoformat(timespec="seconds"),
    )
    assert any(e["id"] == event_id for e in events), "event not visible in Google list"

    # Verify visible in Calendar.app via osascript
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e",
        'tell application "Calendar" to return summary of (every event of every calendar '
        f'whose summary starts with "{PREFIX}")',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    # Calendar.app sync may take a few seconds; if mirror succeeded synchronously it should appear.
    out_text = stdout.decode("utf-8", errors="replace")
    if title not in out_text:
        # Mirror may have failed gracefully — verify warning surfaced.
        assert "mirror_warning" in out["result"], (
            f"event not in Calendar.app and no mirror_warning surfaced: {out_text}"
        )


@pytest.mark.asyncio
async def test_live_create_with_attendees_returns_approval_no_send(
    cleanup_test_events,
) -> None:
    agent = CalendarAgent()
    title = f"{PREFIX} attendees {uuid.uuid4().hex[:8]}"
    start = (datetime.now() + timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=30)

    out = await agent.process(_input(
        tool="calendar_create_event",
        title=title,
        start_iso=start.isoformat(timespec="seconds"),
        end_iso=end.isoformat(timespec="seconds"),
        attendees=["nonexistent-cruz-test@example.com"],
    ))

    assert out["requires_approval"] is True
    assert out["success"] is True
    assert "approval_prompt" in out and "nonexistent-cruz-test" in out["approval_prompt"]

    # Verify NO event was created in Google
    gcal = get_gcal_service()
    events = await gcal.list_events(
        start.isoformat(timespec="seconds"),
        end.isoformat(timespec="seconds"),
    )
    assert not any((e.get("summary", "")).startswith(title) for e in events), (
        "event was created despite send=False (approval gate failed)"
    )


@pytest.mark.asyncio
async def test_live_list_events_returns_real_events(cleanup_test_events) -> None:
    agent = CalendarAgent()
    title = f"{PREFIX} list {uuid.uuid4().hex[:8]}"
    start = (datetime.now() + timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=30)

    # Seed an event
    create_out = await agent.process(_input(
        tool="calendar_create_event",
        title=title,
        start_iso=start.isoformat(timespec="seconds"),
        end_iso=end.isoformat(timespec="seconds"),
    ))
    assert create_out["success"]

    # List
    list_out = await agent.process(_input(
        tool="calendar_list_events",
        start_iso=start.isoformat(timespec="seconds"),
        end_iso=end.isoformat(timespec="seconds"),
    ))
    assert list_out["success"]
    assert any((e.get("summary", "")).startswith(title) for e in list_out["result"])


@pytest.mark.asyncio
async def test_live_find_free_slot_against_real_calendar(cleanup_test_events) -> None:
    agent = CalendarAgent()
    # 24h window starting tomorrow
    base = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    out = await agent.process(_input(
        tool="calendar_find_free_slot",
        duration_minutes=30,
        earliest_iso=base.replace(hour=9).isoformat(timespec="seconds"),
        latest_iso=base.replace(hour=18).isoformat(timespec="seconds"),
    ))
    # Should find SOMETHING in a 9-hour window for a 30-min slot.
    assert out["success"] is True, f"failed to find free slot: {out.get('error')}"
    assert "start_iso" in out["result"]
    assert "end_iso" in out["result"]
