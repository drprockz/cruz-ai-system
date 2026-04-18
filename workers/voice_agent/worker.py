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
            ws_url=os.environ.get("LIVEKIT_URL") or os.environ["LIVEKIT_WS_URL"],
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
    # Force 16kHz mono — Deepgram STT is configured for this rate.
    # Without this, LiveKit may deliver 48kHz opus-decoded frames and
    # Deepgram will hear garbled speech (running at ~3x speed).
    stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1)
    logged_first = False
    async for event in stream:
        if not logged_first:
            f = event.frame
            logger.info(
                "first audio frame: sample_rate=%d channels=%d samples=%d bytes=%d",
                f.sample_rate, f.num_channels,
                f.samples_per_channel, len(bytes(f.data)),
            )
            logged_first = True
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
    from services.qdrant import get_qdrant_service
    from services.realtime_voice import DeepgramSTT, DeepgramTTS
    from services.voice_sessions import VoiceSessionService

    # livekit-agents runs each job in a fresh subprocess, so shared service
    # singletons (DB, Qdrant) start unconnected. Connect them here.
    db = get_db_service()
    await db.connect()
    qdrant = get_qdrant_service()
    try:
        await qdrant.connect()
    except Exception as exc:
        # Semantic memory is non-fatal — degrade gracefully.
        logger.warning("Qdrant connect failed (continuing without semantic memory): %s", exc)

    await ctx.connect()
    room = ctx.room
    logger.info("voice_agent joined room=%s", room.name)

    # room name format: cruz__<conversation_id>__<device_id>
    # `__` delimiter — dash-containing UUIDs aren't ambiguous.
    parts = room.name.split("__")
    if len(parts) >= 3 and parts[0] == "cruz":
        conversation_id: str = parts[1]
        device_id: str = parts[2]
    else:
        # Legacy single-dash format / unexpected room — synthesize fallbacks.
        conversation_id = str(uuid.uuid4())
        device_id = "unknown"

    # voice_sessions.conversation_id FKs to conversations(id), so the
    # conversation row must exist before we can insert the session.
    from services.conversation import ConversationService
    conv_svc = ConversationService(db)
    await conv_svc.get_or_create_conversation(conversation_id)

    session_svc = VoiceSessionService(db)
    session_id: str = await session_svc.start(
        conversation_id=conversation_id,
        device_id=device_id,
        room=room.name,
    )

    stt = DeepgramSTT()
    tts = DeepgramTTS()
    # LAZY connect — Deepgram closes an idle WS after ~10s. Only connect
    # when we have real audio to send (i.e. after the client unmutes the
    # mic post-wake-word), and keep-alive every 5s while connected.

    cruz = CruzAgent()
    tts_cancel: asyncio.Event = asyncio.Event()
    speaking: dict = {"active": False}
    stt_state: dict = {"connected": False, "keepalive_task": None}
    audio_source = rtc.AudioSource(sample_rate=tts.sample_rate, num_channels=1)
    track = rtc.LocalAudioTrack.create_audio_track("cruz-voice", audio_source)
    await room.local_participant.publish_track(track)

    turns: int = 0
    barges: int = 0

    async def _stt_keepalive() -> None:
        # Deepgram recommends keepalive every 3-10s when idle. 5s is safe.
        while stt_state["connected"]:
            try:
                await asyncio.sleep(5)
                if stt_state["connected"] and stt._conn is not None:
                    await stt._conn.keep_alive()  # type: ignore[union-attr]
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("stt keepalive failed")

    async def _ensure_stt_connected() -> None:
        if stt_state["connected"]:
            return
        await stt.connect()
        stt_state["connected"] = True
        stt_state["keepalive_task"] = asyncio.create_task(_stt_keepalive())
        logger.info("deepgram STT WS opened lazily")

    last_audio_at: dict = {"ts": asyncio.get_event_loop().time()}

    # If DEBUG_SAVE_AUDIO=1, persist all received PCM to disk so we can
    # replay it and confirm audio quality end-to-end.
    debug_dump_path = None
    if os.environ.get("DEBUG_SAVE_AUDIO") == "1":
        debug_dump_path = f"/tmp/cruz_worker_in_{session_id[:8]}.raw"
        logger.info("DEBUG_SAVE_AUDIO=1 — dumping received PCM to %s", debug_dump_path)
    debug_dump_handle = open(debug_dump_path, "wb") if debug_dump_path else None
    frame_count: dict = {"n": 0, "total_bytes": 0}

    # Direct track-subscription — simpler and more reliable than the previous
    # _iter_remote_participants / _iter_audio_frames generator chain.
    _pump_tasks: list = []

    async def _consume_track(track: Any, participant_identity: str) -> None:
        logger.info("consuming audio track from %s", participant_identity)
        stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1)
        first = True
        async for event in stream:
            f = event.frame
            if first:
                logger.info(
                    "first audio frame: sr=%d ch=%d samples=%d bytes=%d",
                    f.sample_rate, f.num_channels,
                    f.samples_per_channel, len(bytes(f.data)),
                )
                first = False
            last_audio_at["ts"] = asyncio.get_event_loop().time()
            await _ensure_stt_connected()
            if speaking["active"] and _is_speech(f) and not tts_cancel.is_set():
                tts_cancel.set()
            data = bytes(f.data)
            frame_count["n"] += 1
            frame_count["total_bytes"] += len(data)
            if debug_dump_handle is not None:
                debug_dump_handle.write(data)
                debug_dump_handle.flush()
            await stt.send(data)

    def _on_track_subscribed(track: Any, pub: Any, participant: Any) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        logger.info("track_subscribed: audio from %s", participant.identity)
        task = asyncio.create_task(
            _consume_track(track, participant.identity)
        )
        _pump_tasks.append(task)

    room.on("track_subscribed", _on_track_subscribed)

    # Handle pre-existing participants (race: they may have already published
    # a track before our listener wired up).
    for p in room.remote_participants.values():
        for pub in p.track_publications.values():
            if pub.kind == rtc.TrackKind.KIND_AUDIO and pub.track is not None:
                logger.info("pre-subscribed track from %s", p.identity)
                _pump_tasks.append(asyncio.create_task(
                    _consume_track(pub.track, p.identity)
                ))

    async def _pump_audio_into_stt() -> None:
        # The actual consumption happens in _consume_track tasks above.
        # This coroutine stays alive for asyncio.wait() semantics.
        while True:
            await asyncio.sleep(5)

    async def _idle_watchdog() -> None:
        """Exit gracefully if no audio arrives within AUDIO_IDLE_TIMEOUT seconds.

        Stale rooms (Ctrl+C'd daemons) dispatch jobs to the worker that will
        never see audio. Without this, the worker hangs until livekit-agents
        force-cancels the entrypoint.
        """
        timeout = float(os.environ.get("AUDIO_IDLE_TIMEOUT", "90"))
        while True:
            await asyncio.sleep(10)
            idle = asyncio.get_event_loop().time() - last_audio_at["ts"]
            if idle > timeout:
                logger.info(
                    "no audio for %.0fs — exiting job (likely stale room)",
                    idle,
                )
                return

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
        # wait returns when the FIRST of these completes — idle_watchdog
        # completing means "stale room, exit cleanly".
        pump = asyncio.create_task(_pump_audio_into_stt())
        turns_task = asyncio.create_task(_process_turns())
        watchdog = asyncio.create_task(_idle_watchdog())
        done, pending = await asyncio.wait(
            {pump, turns_task, watchdog},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
        for t in done:
            if t is watchdog:
                continue
            exc = t.exception()
            if exc:
                logger.exception("voice task failed", exc_info=exc)
    finally:
        ka_task = stt_state.get("keepalive_task")
        if ka_task is not None:
            stt_state["connected"] = False
            ka_task.cancel()
        await stt.close()
        try:
            await session_svc.end(session_id, turns=turns, barges=barges)
        except Exception:
            logger.exception("voice_session end failed (non-fatal)")
        try:
            await db.disconnect()
        except Exception:
            pass
        try:
            await qdrant.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    # livekit-agents >= 1.x requires Python 3.10+ at import time.
    # This guard prevents the ImportError from crashing the module on 3.9.
    try:
        from livekit.agents import WorkerOptions, cli  # type: ignore
        # agent_name is REQUIRED for explicit dispatch on livekit-agents >=1.x.
        # The /voice/token endpoint references this name via RoomConfiguration.
        cli.run_app(
            WorkerOptions(
                agent_name="cruz-voice",
                entrypoint_fnc=entrypoint,
            )
        )
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            f"livekit-agents requires Python 3.10+. Got: {exc}"
        ) from exc
