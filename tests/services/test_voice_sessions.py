"""Tests for VoiceSessionService — CRUD over voice_sessions table."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.voice_sessions import VoiceSessionService


def _make_db(fetchrow_result=None):
    db = AsyncMock()
    db.execute = AsyncMock(return_value="INSERT 0 1")
    db.fetchrow = AsyncMock(return_value=fetchrow_result)
    return db


@pytest.mark.asyncio
async def test_start_returns_uuid_and_inserts_row():
    db = _make_db()
    svc = VoiceSessionService(db)

    sid = await svc.start(
        conversation_id="conv-1", device_id="mac-mini", room="cruz-xyz"
    )
    assert sid and len(sid) == 36  # uuid4 string

    db.execute.assert_called_once()
    sql, *params = db.execute.call_args.args
    assert "INSERT INTO voice_sessions" in sql
    # params: id, conversation_id, device_id, livekit_room
    assert params == [sid, "conv-1", "mac-mini", "cruz-xyz"]


@pytest.mark.asyncio
async def test_end_updates_ended_at_turns_barges_ws_ms():
    db = _make_db()
    svc = VoiceSessionService(db)

    await svc.end("sess-1", turns=3, barges=1, deepgram_ws_ms=4200)

    db.execute.assert_called_once()
    sql, *params = db.execute.call_args.args
    assert "UPDATE voice_sessions" in sql
    assert "ended_at = NOW()" in sql
    assert params == [3, 1, 4200, "sess-1"]


@pytest.mark.asyncio
async def test_increment_turn_bumps_counter():
    db = _make_db()
    svc = VoiceSessionService(db)

    await svc.increment_turn("sess-1")

    db.execute.assert_called_once()
    sql, *params = db.execute.call_args.args
    assert "turns = turns + 1" in sql
    assert params == ["sess-1"]


@pytest.mark.asyncio
async def test_increment_barge_bumps_counter():
    db = _make_db()
    svc = VoiceSessionService(db)

    await svc.increment_barge("sess-1")

    db.execute.assert_called_once()
    sql, *params = db.execute.call_args.args
    assert "barges = barges + 1" in sql
    assert params == ["sess-1"]
