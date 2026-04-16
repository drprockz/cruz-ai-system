#!/usr/bin/env python3
"""
End-to-end voice pipeline smoke test (runs against a LIVE stack).

Requires:
  - Backend API running on localhost:3000
  - LiveKit Agent worker running (python -m workers.voice_agent.worker dev)
  - .env loaded with DEEPGRAM_API_KEY, ANTHROPIC_API_KEY, LIVEKIT_URL,
    LIVEKIT_API_KEY, LIVEKIT_API_SECRET

What it does:
  1. POST /voice/token → get a LiveKit room
  2. Join the room as a "test-client" participant
  3. Publish the tests/integration/fixtures/hello_cruz.wav clip as a mic
     audio track (streamed at real-time pace, 20ms chunks)
  4. Subscribe to any remote audio track (= the agent worker's voice reply)
  5. Collect received audio bytes for 30 seconds, print summary

Success = received audio bytes > 0 (i.e. CRUZ spoke back).
Failure with 0 bytes = pipeline is broken; read worker logs for why.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import pathlib
import sys
import wave

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import httpx  # noqa: E402
import numpy as np  # noqa: E402
from livekit import rtc  # type: ignore  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

logger = logging.getLogger("cruz.voice.e2e_smoke")


async def _fetch_token(host: str, device_id: str):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{host}/voice/token", json={"device_id": device_id}
        )
        r.raise_for_status()
        return r.json()


async def _publish_wav(source: rtc.AudioSource, wav_path: pathlib.Path):
    """Stream a mono 16kHz WAV into the LiveKit source at real-time pace."""
    with wave.open(str(wav_path), "rb") as w:
        assert w.getnchannels() == 1, "fixture must be mono"
        sr = w.getframerate()
        pcm = w.readframes(w.getnframes())
    logger.info("publishing %s: sr=%d bytes=%d", wav_path.name, sr, len(pcm))

    # 20ms chunks
    samples_per_20ms = sr // 50
    bytes_per_chunk = samples_per_20ms * 2  # int16
    offset = 0
    while offset < len(pcm):
        chunk = pcm[offset : offset + bytes_per_chunk]
        if len(chunk) < bytes_per_chunk:
            chunk = chunk + b"\x00" * (bytes_per_chunk - len(chunk))
        frame = rtc.AudioFrame(
            data=chunk,
            sample_rate=sr,
            num_channels=1,
            samples_per_channel=samples_per_20ms,
        )
        await source.capture_frame(frame)
        await asyncio.sleep(0.02)
        offset += bytes_per_chunk
    logger.info("wav publish finished; now sending silence to force flush")
    # Tail of silence so Deepgram's endpointing finalizes
    silent = b"\x00" * bytes_per_chunk
    for _ in range(25):  # 0.5s silence
        frame = rtc.AudioFrame(
            data=silent, sample_rate=sr, num_channels=1,
            samples_per_channel=samples_per_20ms,
        )
        await source.capture_frame(frame)
        await asyncio.sleep(0.02)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:3000")
    ap.add_argument(
        "--wav",
        default="tests/integration/fixtures/hello_cruz.wav",
        help="path to 16kHz mono WAV to play to CRUZ",
    )
    ap.add_argument(
        "--collect-seconds", type=float, default=25.0,
        help="how long to listen for CRUZ's reply audio",
    )
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    load_dotenv(os.path.join(_ROOT, ".env"), override=True)

    wav_path = pathlib.Path(args.wav).resolve()
    assert wav_path.exists(), f"wav fixture not found: {wav_path}"

    tok = await _fetch_token(args.host, device_id="test-client")
    logger.info("token room=%s", tok["room"])

    room = rtc.Room()
    await room.connect(tok["ws_url"], tok["token"])
    logger.info("joined room")

    # Publish mic
    mic_src = rtc.AudioSource(sample_rate=16000, num_channels=1)
    mic_track = rtc.LocalAudioTrack.create_audio_track("mic", mic_src)
    await room.local_participant.publish_track(mic_track)

    # Collect agent reply audio
    received = {"bytes": 0, "first_at": None, "sample_rate": None}

    def _on_track_sub(track, pub, participant):
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        # Ignore our own track echo — only collect audio FROM the worker agent.
        if participant.identity == "test-client":
            logger.info("ignoring self-track echo from %s", participant.identity)
            return
        logger.info("subscribed to remote audio track from %s", participant.identity)
        async def _collect():
            stream = rtc.AudioStream(track)
            async for ev in stream:
                if received["first_at"] is None:
                    received["first_at"] = asyncio.get_event_loop().time()
                    received["sample_rate"] = ev.frame.sample_rate
                    logger.info(
                        "FIRST reply audio frame: sr=%d ch=%d",
                        ev.frame.sample_rate, ev.frame.num_channels,
                    )
                received["bytes"] += len(bytes(ev.frame.data))
        asyncio.create_task(_collect())
    room.on("track_subscribed", _on_track_sub)

    # Wait for worker agent to join AND its AudioStream to warm up before
    # playing the wav. Too short = wav ends before worker starts reading frames.
    warmup_s = float(os.environ.get("E2E_WARMUP_SECONDS", "8"))
    logger.info("warmup %ss (waiting for worker audio pipeline)...", warmup_s)
    # Pre-fill a second of silence so the worker has SOMETHING to read early
    silent_sr = 16000
    spc = silent_sr // 50
    for _ in range(int(warmup_s * 50)):
        f = rtc.AudioFrame(
            data=b"\x00" * (spc * 2), sample_rate=silent_sr,
            num_channels=1, samples_per_channel=spc,
        )
        await mic_src.capture_frame(f)
        await asyncio.sleep(0.02)

    publish_start = asyncio.get_event_loop().time()
    await _publish_wav(mic_src, wav_path)

    logger.info("waiting %.0fs for CRUZ reply...", args.collect_seconds)
    await asyncio.sleep(args.collect_seconds)

    elapsed_first = (
        (received["first_at"] - publish_start) if received["first_at"] else None
    )

    await room.disconnect()

    print()
    print("=" * 60)
    print(f"test WAV: {wav_path.name}")
    print(f"reply bytes received: {received['bytes']}")
    print(f"reply sample_rate: {received['sample_rate']}")
    if elapsed_first is not None:
        print(f"first reply frame at: {elapsed_first:.2f}s after wav-start")
    print("=" * 60)

    if received["bytes"] > 0:
        print("PASS ✅ — CRUZ spoke back")
        sys.exit(0)
    else:
        print("FAIL ❌ — no reply audio; check worker logs")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
