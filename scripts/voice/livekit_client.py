#!/usr/bin/env python3
"""
CRUZ Mac voice daemon (Phase 1).

- openWakeWord listens on a local mic stream (services.voice.WakeWordDetector)
- On wake, POST /voice/token → LiveKit room JWT
- Join room, unmute mic track, publish audio
- Subscribe to agent's audio track, play to speakers
- After N seconds of silence, mute mic (gated STT — agent closes Deepgram WS)

Run:
    python scripts/voice/livekit_client.py --host http://localhost:3000
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from typing import Dict, Optional

import httpx

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from services.voice import WakeWordDetector  # existing
from livekit import rtc  # type: ignore
import sounddevice as sd  # type: ignore
import numpy as np  # type: ignore

logger = logging.getLogger("cruz.voice.daemon")

SAMPLE_RATE = 16000
SILENCE_SECONDS_TO_MUTE = 15
WAKE_WORD_FRAME = 1280  # openWakeWord default (80ms @ 16 kHz)


async def _fetch_token(host: str, device_id: str, conversation_id: Optional[str]):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{host}/voice/token",
            json={"device_id": device_id, "conversation_id": conversation_id},
        )
        r.raise_for_status()
        return r.json()


async def _join_and_run(tok_info: dict, conversation_id: str):
    room = rtc.Room()
    await room.connect(tok_info["ws_url"], tok_info["token"])
    logger.info("joined %s", room.name)

    mic_source = rtc.AudioSource(sample_rate=SAMPLE_RATE, num_channels=1)
    mic_track = rtc.LocalAudioTrack.create_audio_track("mic", mic_source)
    await room.local_participant.publish_track(mic_track)
    mic_track.mute()  # start muted; wake-word loop unmutes on detection

    loop = asyncio.get_running_loop()

    # RawOutputStream is non-blocking; sd.play() is not safe from async.
    playback: Dict[str, Optional[sd.RawOutputStream]] = {"stream": None}

    def on_track_sub(track, pub, participant):
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return

        async def _play():
            stream = rtc.AudioStream(track)
            async for ev in stream:
                sr = ev.frame.sample_rate
                if playback["stream"] is None:
                    playback["stream"] = sd.RawOutputStream(
                        samplerate=sr, channels=1, dtype="int16", blocksize=0,
                    )
                    playback["stream"].start()
                playback["stream"].write(bytes(ev.frame.data))

        asyncio.create_task(_play())

    room.on("track_subscribed", on_track_sub)

    detector = WakeWordDetector(keyword="hey_jarvis")
    last_unmute = 0.0

    # Diagnostics — every ~2s report mic activity + current wake score so the
    # user can tell whether the mic is even firing.
    debug: dict = {"frames": 0, "max_rms": 0, "max_score": 0.0, "last_log": 0.0}
    # Debug threshold: log every detection attempt (score) with DEBUG_VOICE=1
    debug_voice = os.environ.get("DEBUG_VOICE") == "1"

    def _audio_cb(indata, frames, time_, status):
        nonlocal last_unmute
        # RMS over this frame — 0 means silent, >500 means speech-ish
        import numpy as _np
        samples = indata[:, 0]
        rms = float(_np.sqrt(_np.mean(samples.astype(_np.float32) ** 2)))
        debug["frames"] += 1
        if rms > debug["max_rms"]:
            debug["max_rms"] = rms

        if mic_track.muted:
            # Run wake detector on every frame (must be 1280 int16 for openWakeWord)
            try:
                scores = detector._oww_model.predict(samples)  # raw dict
                if isinstance(scores, dict):
                    top_score = max(scores.values(), default=0.0)
                    if top_score > debug["max_score"]:
                        debug["max_score"] = top_score
                    detected = top_score >= detector._threshold
                else:
                    detected = bool(scores)
            except Exception:
                detected = detector.detect(samples)

            if detected:
                mic_track.unmute()
                last_unmute = loop.time()
                logger.info("wake word detected — mic unmuted (score=%.2f)", debug["max_score"])
                debug["max_score"] = 0.0
        frame = rtc.AudioFrame(
            data=indata.tobytes(), sample_rate=SAMPLE_RATE,
            num_channels=1, samples_per_channel=frames,
        )
        loop.call_soon_threadsafe(
            asyncio.create_task, mic_source.capture_frame(frame)
        )

    with sd.InputStream(
        channels=1, samplerate=SAMPLE_RATE, dtype="int16",
        blocksize=WAKE_WORD_FRAME, callback=_audio_cb,
    ):
        while True:
            await asyncio.sleep(2)
            # Periodic heartbeat so silence isn't mistaken for a dead daemon
            logger.info(
                "listening: frames=%d max_rms=%.0f max_wake_score=%.3f (threshold=0.5) muted=%s",
                debug["frames"], debug["max_rms"], debug["max_score"], mic_track.muted,
            )
            debug["frames"] = 0
            debug["max_rms"] = 0
            debug["max_score"] = 0.0
            if (
                not mic_track.muted
                and loop.time() - last_unmute > SILENCE_SECONDS_TO_MUTE
            ):
                mic_track.mute()
                logger.info("silence timeout — mic muted")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:3000")
    ap.add_argument("--conversation-id", default=None)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)
    conv_id = args.conversation_id or str(uuid.uuid4())
    tok = await _fetch_token(
        args.host, device_id="mac-mini", conversation_id=conv_id,
    )
    await _join_and_run(tok, conv_id)


if __name__ == "__main__":
    asyncio.run(main())
