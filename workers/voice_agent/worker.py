"""
LiveKit Agent worker. Runs on the Mac Mini; listens to rooms named
cruz-<conversation_id>-<device_id>.

Per room:
  1. Subscribes to the participant's audio track
  2. Feeds frames to DeepgramSTT
  3. On each final transcript: calls CruzAgent.stream_response()
  4. Pipes sentence events to DeepgramTTS
  5. Publishes the synthesised audio back to the room
  6. Barge-in: when user speaks while CRUZ is speaking, cancel current TTS

Run locally (after env vars set):
    python -m workers.voice_agent.worker dev
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger("cruz.workers.voice_agent")


@dataclass
class VoiceAgentConfig:
    ws_url: str
    api_key: str
    api_secret: str

    @classmethod
    def from_env(cls) -> "VoiceAgentConfig":
        return cls(
            ws_url=os.environ["LIVEKIT_WS_URL"],
            api_key=os.environ["LIVEKIT_API_KEY"],
            api_secret=os.environ["LIVEKIT_API_SECRET"],
        )


def _is_speech(frame: Any) -> bool:
    """Heuristic barge-in detector: RMS > 600 over the frame's samples."""
    import struct

    data = bytes(frame.data)
    if not data:
        return False
    samples = struct.unpack(f"{len(data) // 2}h", data)
    if not samples:
        return False
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
    return rms > 600


async def _iter_remote_participants(room: Any) -> AsyncIterator[Any]:
    """Yield each remote participant as they join the room.

    Participants already in the room when the worker connects are emitted
    first, then new arrivals via the ``participant_connected`` event.
    """
    queue: asyncio.Queue = asyncio.Queue()

    # Drain participants already present at connect time.
    for p in room.remote_participants.values():
        queue.put_nowait(p)

    def _on_connected(p: Any) -> None:
        queue.put_nowait(p)

    room.on("participant_connected", _on_connected)
    while True:
        p = await queue.get()
        yield p


async def _iter_audio_frames(room: Any, participant: Any) -> AsyncIterator[Any]:
    """Yield AudioFrame objects for the participant's first audio track.

    Waits for the audio track to be subscribed if it isn't available yet,
    then opens an AudioStream and yields frames until the stream closes.
    """
    from livekit import rtc  # type: ignore

    async def _wait_for_audio_track() -> Any:
        fut: asyncio.Future = asyncio.get_running_loop().create_future()

        def _on_sub(track: Any, pub: Any, p: Any) -> None:
            if (
                p.identity == participant.identity
                and track.kind == rtc.TrackKind.KIND_AUDIO
            ):
                if not fut.done():
                    fut.set_result(track)

        room.on("track_subscribed", _on_sub)
        # Check publications already subscribed before the listener was added.
        for pub in participant.track_publications.values():
            if pub.kind == rtc.TrackKind.KIND_AUDIO and pub.track:
                return pub.track
        return await fut

    track = await _wait_for_audio_track()
    stream = rtc.AudioStream(track)
    async for event in stream:
        yield event.frame


async def _speak(
    text: str,
    tts: Any,
    source: Any,
    cancel_evt: asyncio.Event,
) -> None:
    """Stream TTS audio chunks into the LiveKit AudioSource."""
    from livekit import rtc  # type: ignore

    async for pcm_chunk in tts.synthesize(text):
        if cancel_evt.is_set():
            return
        frame = rtc.AudioFrame(
            data=pcm_chunk,
            sample_rate=tts.sample_rate,
            num_channels=1,
            samples_per_channel=len(pcm_chunk) // 2,
        )
        await source.capture_frame(frame)


async def _speak_with_fallback(
    text: str,
    tts: Any,
    source: Any,
    cancel: asyncio.Event,
) -> None:
    """
    Try DeepgramTTS; on failure, fall back to services.voice.VoicePipeline
    (Inworld → macOS say chain). Inworld returns MP3; we transcode to PCM
    via ffmpeg so LiveKit can consume it.
    """
    try:
        await _speak(text, tts, source, cancel)
        return
    except Exception as exc:
        logger.warning("DeepgramTTS failed, falling back to Inworld: %s", exc)

    import subprocess
    import tempfile

    from livekit import rtc  # type: ignore

    from services.voice import VoicePipeline

    audio = await VoicePipeline().speak(text)  # MP3 or AIFF bytes
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3:
        mp3.write(audio)
        mp3_path = mp3.name
    try:
        pcm = subprocess.check_output([
            "ffmpeg", "-i", mp3_path, "-f", "s16le",
            "-ar", str(tts.sample_rate), "-ac", "1",
            "-loglevel", "error", "pipe:1",
        ])
    finally:
        os.unlink(mp3_path)

    frame = rtc.AudioFrame(
        data=pcm,
        sample_rate=tts.sample_rate,
        num_channels=1,
        samples_per_channel=len(pcm) // 2,
    )
    await source.capture_frame(frame)


async def entrypoint(ctx: Any) -> None:
    """Called by the LiveKit agent harness for each new room."""
    from livekit import rtc  # type: ignore

    from agents.cruz.cruz_agent import CruzAgent
    from agents.cruz.stream_events import Done, Text, ToolStart
    from services.db import get_db_service
    from services.realtime_voice import DeepgramSTT, DeepgramTTS
    from services.voice_sessions import VoiceSessionService

    await ctx.connect()
    room = ctx.room
    logger.info("voice_agent joined room=%s", room.name)

    # room name format: cruz-<conversation_id>-<device_id>
    parts = room.name.split("-", 2)
    conversation_id: str = parts[1] if len(parts) > 1 else str(uuid.uuid4())
    device_id: str = parts[2] if len(parts) > 2 else "unknown"

    session_svc = VoiceSessionService(get_db_service())
    session_id: str = await session_svc.start(
        conversation_id=conversation_id,
        device_id=device_id,
        room=room.name,
    )

    stt = DeepgramSTT()
    tts = DeepgramTTS()
    await stt.connect()

    cruz = CruzAgent()
    tts_cancel: asyncio.Event = asyncio.Event()
    speaking: dict = {"active": False}
    audio_source = rtc.AudioSource(sample_rate=tts.sample_rate, num_channels=1)
    track = rtc.LocalAudioTrack.create_audio_track("cruz-voice", audio_source)
    await room.local_participant.publish_track(track)

    turns: int = 0
    barges: int = 0

    async def _pump_audio_into_stt() -> None:
        async for participant in _iter_remote_participants(room):
            async for frame in _iter_audio_frames(room, participant):
                if speaking["active"] and _is_speech(frame) and not tts_cancel.is_set():
                    tts_cancel.set()
                await stt.send(bytes(frame.data))

    async def _process_turns() -> None:
        nonlocal turns, barges
        async for t in stt.transcripts():
            if not t.is_final or not t.text.strip():
                continue
            turns += 1
            await session_svc.increment_turn(session_id)
            tts_cancel.clear()
            async for ev in cruz.stream_response(
                task=t.text,
                conversation_id=conversation_id,
                trace_id=str(uuid.uuid4()),
                device="mac_mini",
            ):
                if isinstance(ev, (Text, ToolStart)):
                    text = ev.content if isinstance(ev, Text) else ev.summary
                    speaking["active"] = True
                    try:
                        await _speak_with_fallback(text, tts, audio_source, tts_cancel)
                    finally:
                        speaking["active"] = False
                    if tts_cancel.is_set():
                        barges += 1
                        await session_svc.increment_barge(session_id)
                        break
                elif isinstance(ev, Done):
                    logger.info(
                        "turn done tokens=%d ms=%d",
                        ev.tokens_used,
                        ev.duration_ms,
                    )

    try:
        await asyncio.gather(_pump_audio_into_stt(), _process_turns())
    finally:
        await stt.close()
        await session_svc.end(session_id, turns=turns, barges=barges)


if __name__ == "__main__":
    # livekit-agents >= 1.x requires Python 3.10+ at import time.
    # This guard prevents the ImportError from crashing the module on 3.9.
    try:
        from livekit.agents import WorkerOptions, cli  # type: ignore
        cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            f"livekit-agents requires Python 3.10+. Got: {exc}"
        ) from exc
