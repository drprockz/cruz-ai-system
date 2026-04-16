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

import httpx

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

        async def _on_transcript(_self: object, result: object, **kwargs) -> None:
            # deepgram-sdk 3.11 calls callbacks with (client, result, **kwargs)
            try:
                alt = result.channel.alternatives[0]  # type: ignore[union-attr]
                text = (alt.transcript or "").strip()
                is_final = bool(result.is_final)  # type: ignore[union-attr]
                if not text:
                    return
                logger.info(
                    "deepgram transcript: final=%s text=%r", is_final, text,
                )
                await self._queue.put(STTTranscript(text=text, is_final=is_final))
            except Exception:
                logger.exception("DeepgramSTT transcript parse failed")

        async def _on_open(_self: object, data: object = None, **kwargs) -> None:
            logger.info("deepgram STT WS opened")

        async def _on_close(_self: object, data: object = None, **kwargs) -> None:
            logger.info("deepgram STT WS closed: %s", data)

        async def _on_error(_self: object, error: object = None, **kwargs) -> None:
            logger.error("deepgram STT error: %s", error)

        self._conn.on(self._conn._TRANSCRIPT_EVENT, _on_transcript)  # type: ignore[union-attr]
        try:
            from deepgram import LiveTranscriptionEvents  # type: ignore
            self._conn.on(LiveTranscriptionEvents.Open, _on_open)  # type: ignore[union-attr]
            self._conn.on(LiveTranscriptionEvents.Close, _on_close)  # type: ignore[union-attr]
            self._conn.on(LiveTranscriptionEvents.Error, _on_error)  # type: ignore[union-attr]
        except Exception:
            pass  # tests use a fake SDK

        try:
            from deepgram import LiveOptions  # type: ignore
            opts = LiveOptions(
                model=self._model,
                language="en-US",
                encoding="linear16",
                sample_rate=16000,
                channels=1,
                interim_results=True,
                punctuate=True,
                endpointing=self._endpointing_ms,
            )
        except ImportError:
            # Test-only path — the fake SDK passes a dict through.
            opts = {  # type: ignore[assignment]
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

    async def finalize(self) -> None:
        """Force Deepgram to emit a final transcript for all audio sent so far.

        Use after you've sent the last audio chunk for a turn but want the
        final transcript without closing the WS.
        """
        if self._conn is None or self._closed:
            return
        try:
            await self._conn.finalize()  # type: ignore[union-attr]
        except Exception:
            logger.exception("DeepgramSTT finalize failed")

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


# ── Aura-2 Orion streaming TTS ──────────────────────────────────


class DeepgramTTS:
    """
    HTTP-streaming TTS (Aura-2 Orion by default). Deepgram's /v1/speak
    endpoint returns audio progressively — we yield chunks as they
    arrive so the caller can start playback before the whole sentence
    synthesises (~100ms TTFB in practice).

    Deepgram also offers a WebSocket TTS variant. HTTP streaming is
    sufficient for Phase 1 and simpler to wrap. If observed TTFB
    exceeds SLO in Phase 3 benchmarks, swap to WS.
    """

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        encoding: str = "linear16",
        sample_rate: int = 24000,
    ) -> None:
        self._model = model or os.environ.get(
            "DEEPGRAM_TTS_MODEL", "aura-2-orion-en"
        )
        self._encoding = encoding
        self._sample_rate = sample_rate

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        api_key = os.environ["DEEPGRAM_API_KEY"]
        params = {
            "model": self._model,
            "encoding": self._encoding,
            "sample_rate": str(self._sample_rate),
            "container": "none",
        }
        headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        }
        payload = {"text": text}

        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                "https://api.deepgram.com/v1/speak",
                params=params, headers=headers, json=payload,
            ) as resp:
                if resp.status_code >= 300:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"DeepgramTTS HTTP {resp.status_code}: {body[:200]!r}"
                    )
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk

    @property
    def sample_rate(self) -> int:
        return self._sample_rate
