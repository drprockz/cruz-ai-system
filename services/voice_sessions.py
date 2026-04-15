"""VoiceSessionService — lightweight CRUD over the voice_sessions table.

Used by the LiveKit Agent worker to record session lifecycle events
(start, turn, barge, end) per voice-pipeline Phase 1 spec.
"""
from __future__ import annotations

import uuid
from typing import Any


class VoiceSessionService:
    """Manages voice session persistence for CRUZ voice pipeline."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def start(
        self,
        *,
        conversation_id: str,
        device_id: str,
        room: str,
    ) -> str:
        """Create a new voice_sessions row. Returns the session id (uuid4)."""
        sid = str(uuid.uuid4())
        await self._db.execute(
            "INSERT INTO voice_sessions (id, conversation_id, device_id, livekit_room) "
            "VALUES ($1, $2, $3, $4)",
            sid, conversation_id, device_id, room,
        )
        return sid

    async def end(
        self,
        session_id: str,
        *,
        turns: int = 0,
        barges: int = 0,
        deepgram_ws_ms: int = 0,
    ) -> None:
        """Mark the session ended and record final counters."""
        await self._db.execute(
            "UPDATE voice_sessions SET ended_at = NOW(), turns = $1, "
            "barges = $2, deepgram_ws_ms = $3 WHERE id = $4",
            turns, barges, deepgram_ws_ms, session_id,
        )

    async def increment_turn(self, session_id: str) -> None:
        """Increment the turn counter for an active session."""
        await self._db.execute(
            "UPDATE voice_sessions SET turns = turns + 1 WHERE id = $1",
            session_id,
        )

    async def increment_barge(self, session_id: str) -> None:
        """Increment the barge-in counter for an active session."""
        await self._db.execute(
            "UPDATE voice_sessions SET barges = barges + 1 WHERE id = $1",
            session_id,
        )
