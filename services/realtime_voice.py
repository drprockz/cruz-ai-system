"""
Realtime voice primitives for Phase 1.

DeepgramSTT — WebSocket streaming STT wrapping deepgram-sdk's LiveClient.
DeepgramTTS (added in Task 4.1) — HTTP-streaming TTS for Aura-2.

Both are designed to plug into a LiveKit Agent worker. They deliberately do
NOT touch LiveKit types so they're unit-testable without a live-kit server.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import AsyncIterator, Optional

logger = logging.getLogger("cruz.services.realtime_voice")


@dataclass
class STTTranscript:
    text: str
    is_final: bool


def _deepgram_live_connection():
    """
    Indirection so tests can monkeypatch. Imports lazily so this module
    loads cleanly in environments where deepgram-sdk isn't installed
    (tests patch the SDK out before it's needed).
    """
    from deepgram import DeepgramClient, LiveTranscriptionEvents  # type: ignore
    key = os.environ["DEEPGRAM_API_KEY"]
    client = DeepgramClient(key)
    conn = client.listen.asyncwebsocket.v("1")
    # Pin the SDK 3.7+ event enum; we register on LiveTranscriptionEvents.Transcript.
    conn._TRANSCRIPT_EVENT = LiveTranscriptionEvents.Transcript  # type: ignore[attr-defined]
    return conn


class DeepgramSTT:
    """
    Streaming STT. Connect, push audio frames, iterate transcripts.
    Caller is responsible for audio format: linear16, 16kHz, mono.
    """

    def __init__(
        self,
        *,
        model: str = "nova-3",
        endpointing_ms: int = 300,
    ) -> None:
        self._model = model
        self._endpointing_ms = endpointing_ms
        self._conn: Optional[object] = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._closed = False

    async def connect(self) -> None:
        self._conn = _deepgram_live_connection()

        async def _on_transcript(_self: object, result: object) -> None:
            try:
                alt = result.channel.alternatives[0]  # type: ignore[union-attr]
                text = (alt.transcript or "").strip()
                if not text:
                    return
                await self._queue.put(
                    STTTranscript(text=text, is_final=bool(result.is_final))  # type: ignore[union-attr]
                )
            except Exception:
                logger.exception("DeepgramSTT transcript parse failed")

        self._conn.on(self._conn._TRANSCRIPT_EVENT, _on_transcript)  # type: ignore[union-attr]

        opts = {
            "model": self._model,
            "encoding": "linear16",
            "sample_rate": 16000,
            "channels": 1,
            "interim_results": True,
            "punctuate": True,
            "endpointing": self._endpointing_ms,
        }
        started = await self._conn.start(opts)  # type: ignore[union-attr]
        if not started:
            raise RuntimeError("DeepgramSTT: failed to start WS")

    async def send(self, audio_bytes: bytes) -> None:
        if self._conn is None or self._closed:
            raise RuntimeError("STT not connected")
        await self._conn.send(audio_bytes)  # type: ignore[union-attr]

    async def transcripts(self) -> AsyncIterator[STTTranscript]:
        while not self._closed:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                yield item
            except asyncio.TimeoutError:
                continue

    async def close(self) -> None:
        self._closed = True
        if self._conn is not None:
            try:
                await self._conn.finish()  # type: ignore[union-attr]
            except Exception:
                pass
            self._conn = None
