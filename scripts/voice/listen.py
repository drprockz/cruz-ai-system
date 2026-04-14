#!/usr/bin/env python3
"""
CRUZ voice daemon — "Hey CRUZ" always-listening loop + push-to-talk.

Flow (wake-word mode, the default):
  1. Open mic stream at 16 kHz, mono, int16
  2. Feed frames to WakeWordDetector (openWakeWord by default)
  3. On wake: record until silence (~1.5s RMS below threshold) or timeout
  4. POST audio to /voice/transcribe → text
  5. POST text to /command → reply text
  6. POST reply to /voice/speak → audio bytes → speaker

Push-to-talk mode: skip wake detection. Press Enter → record fixed
duration → same downstream pipeline. Useful when no wake word is trained.

Usage:
    python scripts/voice/listen.py                     # wake-word mode (hey_jarvis)
    python scripts/voice/listen.py --push-to-talk      # Enter-to-talk
    python scripts/voice/listen.py --once              # one interaction, then exit
    python scripts/voice/listen.py --host http://localhost:3000

Env:
    WAKE_WORD_BACKEND  openwakeword (default) | picovoice
    CRUZ_VOICE_KEYWORD defaults to 'hey_jarvis' (for openwakeword)
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import os
import sys
import uuid
import wave
from typing import Optional

# Make project root importable when this file is run as a script
# (so `from services.voice import WakeWordDetector` resolves).
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import httpx

logger = logging.getLogger("cruz.voice.daemon")

# Audio constants (both backends operate at 16kHz mono int16)
_SAMPLE_RATE = 16000
_CHANNELS = 1
_SAMPLE_WIDTH = 2  # int16 = 2 bytes

# Silence detection heuristic — a very low RMS for this many consecutive ms
# means the speaker is done. Tune if you clip the end of utterances.
_SILENCE_RMS_THRESHOLD = 400
_SILENCE_DURATION_MS = 1500
_MAX_UTTERANCE_MS = 10_000
_PTT_DURATION_MS = 8_000


# ─────────────────────────────────────────────
# HTTP — small wrappers around the three endpoints
# ─────────────────────────────────────────────

async def transcribe(host: str, wav_bytes: bytes) -> str:
    """POST audio to /voice/transcribe, return recognised text."""
    files = {"file": ("utterance.wav", wav_bytes, "audio/wav")}
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{host}/voice/transcribe", files=files)
    if resp.status_code >= 300:
        logger.warning("transcribe HTTP %s — %s", resp.status_code, resp.text[:200])
        return ""
    data = resp.json()
    return (data.get("text") or "").strip()


async def command(
    host: str,
    text: str,
    conversation_id: Optional[str] = None,
    device: str = "mac_mini",
) -> str:
    """POST text to /command, return the reply we should speak back."""
    body: dict = {"command": text, "device": device, "stream": False}
    if conversation_id:
        body["conversation_id"] = conversation_id
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{host}/command", json=body)
    data = resp.json()
    result = data.get("result")
    # Approval gates (HTTP 202) — speak the approval prompt so the
    # operator hears what needs confirmation.
    if resp.status_code == 202 or data.get("approval_prompt"):
        prompt = data.get("approval_prompt") or "I need your approval before continuing."
        return prompt
    # Happy path — result may be a string or a dict (e.g. ECHO draft)
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return result.get("summary") or result.get("body") or str(result)[:300]
    return str(result or "")


async def synthesize_and_play(host: str, text: str) -> None:
    """POST text to /voice/speak and play the returned audio locally."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{host}/voice/speak", json={"text": text},
        )
    if resp.status_code >= 300:
        logger.warning("TTS HTTP %s — %s", resp.status_code, resp.text[:200])
        return
    _play_audio_bytes(resp.content)


def _play_audio_bytes(audio: bytes) -> None:
    """Play raw audio bytes through the default output device.

    Tries `sounddevice` + `soundfile` (handles MP3/AIFF/WAV). Falls back
    to `afplay` on macOS if those aren't importable.
    """
    try:
        import numpy as np  # noqa: F401
        import sounddevice as sd  # type: ignore
        import soundfile as sf  # type: ignore
    except ImportError:
        # Fallback — write to a temp file and let macOS play it
        import subprocess
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
            tmp.write(audio)
            path = tmp.name
        try:
            subprocess.run(["afplay", path], check=False)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        return

    bio = io.BytesIO(audio)
    try:
        data, rate = sf.read(bio, dtype="int16")
        sd.play(data, rate)
        sd.wait()
    except Exception as exc:
        logger.warning("playback failed (%s) — falling back to afplay", exc)
        import subprocess
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio)
            path = tmp.name
        try:
            subprocess.run(["afplay", path], check=False)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


# ─────────────────────────────────────────────
# Audio capture (real microphone — untestable without hardware)
# ─────────────────────────────────────────────

def _record_ptt(duration_ms: int = _PTT_DURATION_MS) -> bytes:
    """Record fixed-duration mono int16 audio, return WAV bytes."""
    try:
        import numpy as np
        import sounddevice as sd  # type: ignore
    except ImportError:
        raise RuntimeError(
            "sounddevice + numpy not installed. "
            "Run: pip install sounddevice numpy soundfile"
        )
    frames = int(_SAMPLE_RATE * duration_ms / 1000)
    audio = sd.rec(frames, samplerate=_SAMPLE_RATE,
                   channels=_CHANNELS, dtype="int16")
    sd.wait()
    return _pcm_to_wav_bytes(audio.tobytes())


def _record_until_silence(
    duration_ms: int = _MAX_UTTERANCE_MS,
    silence_ms: int = _SILENCE_DURATION_MS,
) -> bytes:
    """Record from the mic until silence or hard timeout. Returns WAV bytes."""
    try:
        import numpy as np
        import sounddevice as sd  # type: ignore
    except ImportError:
        raise RuntimeError(
            "sounddevice + numpy not installed. "
            "Run: pip install sounddevice numpy soundfile"
        )
    chunk_ms = 100
    chunk_frames = int(_SAMPLE_RATE * chunk_ms / 1000)
    silence_chunks_needed = silence_ms // chunk_ms
    max_chunks = duration_ms // chunk_ms

    collected: list = []
    silent = 0
    stream = sd.InputStream(
        samplerate=_SAMPLE_RATE, channels=_CHANNELS, dtype="int16",
    )
    stream.start()
    try:
        for _ in range(max_chunks):
            audio, _ = stream.read(chunk_frames)
            collected.append(audio)
            rms = float(np.sqrt(np.mean(audio.astype("int32") ** 2)))
            if rms < _SILENCE_RMS_THRESHOLD:
                silent += 1
                if silent >= silence_chunks_needed:
                    break
            else:
                silent = 0
    finally:
        stream.stop()
        stream.close()

    import numpy as np
    audio = np.concatenate(collected) if collected else np.zeros(0, dtype="int16")
    return _pcm_to_wav_bytes(audio.tobytes())


async def _wait_for_wake(detector) -> None:
    """
    Block until the wake detector fires.

    Reads from the mic in the detector's native frame size, calls
    detector.detect() on each frame, returns as soon as it returns True.
    """
    try:
        import numpy as np
        import sounddevice as sd  # type: ignore
    except ImportError:
        raise RuntimeError(
            "sounddevice + numpy not installed. "
            "Run: pip install sounddevice numpy soundfile"
        )
    frame_length = detector.frame_length
    stream = sd.InputStream(
        samplerate=detector.sample_rate, channels=_CHANNELS, dtype="int16",
    )
    stream.start()
    try:
        while True:
            audio, _ = stream.read(frame_length)
            # Keep as a 1-D numpy int16 array — WakeWordDetector handles
            # both numpy (openwakeword) and list (picovoice) internally.
            frame = audio.flatten()
            if detector.detect(frame):
                return
            # Yield to the event loop so Ctrl-C works and other tasks run
            await asyncio.sleep(0)
    finally:
        stream.stop()
        stream.close()


def _pcm_to_wav_bytes(pcm: bytes) -> bytes:
    """Wrap raw int16 PCM bytes into a WAV container."""
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(_CHANNELS)
        w.setsampwidth(_SAMPLE_WIDTH)
        w.setframerate(_SAMPLE_RATE)
        w.writeframes(pcm)
    return bio.getvalue()


# ─────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────

async def run_one(
    host: str,
    mode: str = "wake-word",
    conversation_id: Optional[str] = None,
    device: str = "mac_mini",
    detector=None,
) -> None:
    """Run exactly one interaction (wake → capture → reply → speak)."""
    if mode == "wake-word":
        if detector is None:
            raise RuntimeError("wake-word mode requires a detector instance")
        print("🎧 Listening for wake word…")
        await _wait_for_wake(detector)
        print("👂 Heard you — go ahead.")
        wav_bytes = _record_until_silence()
    elif mode == "push-to-talk":
        input("🎙️  Press Enter to talk… ")
        wav_bytes = _record_ptt()
    else:
        raise ValueError(f"unknown mode '{mode}'")

    text = await transcribe(host, wav_bytes)
    if not text:
        print("(silent — skipping)")
        return
    print(f"📝 Heard: {text}")

    reply = await command(
        host=host, text=text,
        conversation_id=conversation_id, device=device,
    )
    if not reply:
        print("(CRUZ had no reply)")
        return
    print(f"🤖 CRUZ: {reply}")

    await synthesize_and_play(host=host, text=reply)


async def run_loop(
    host: str,
    mode: str,
    conversation_id: Optional[str],
    device: str,
    detector,
) -> None:
    """Forever loop — one interaction at a time."""
    while True:
        try:
            await run_one(
                host=host, mode=mode,
                conversation_id=conversation_id, device=device,
                detector=detector,
            )
        except KeyboardInterrupt:
            print("\n👋 shutting down voice daemon")
            break
        except Exception as exc:
            logger.exception("interaction failed (continuing): %s", exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("CRUZ_HOST", "http://localhost:3000"))
    parser.add_argument("--push-to-talk", action="store_true",
                        help="Press Enter instead of using wake word")
    parser.add_argument("--once", action="store_true",
                        help="Process one interaction then exit")
    parser.add_argument("--device", default="mac_mini")
    parser.add_argument("--conversation-id", default=None)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.push_to_talk:
        mode = "push-to-talk"
        detector = None
    else:
        # Import here so push-to-talk mode works without openwakeword installed
        from services.voice import WakeWordDetector
        detector = WakeWordDetector(
            keyword=os.environ.get("CRUZ_VOICE_KEYWORD", "hey_jarvis"),
        )
        mode = "wake-word"
        print(f"🎤 Voice daemon starting — backend={detector.backend}, "
              f"keyword={os.environ.get('CRUZ_VOICE_KEYWORD', 'hey_jarvis')}")

    conversation_id = args.conversation_id or str(uuid.uuid4())
    print(f"Conversation id: {conversation_id}")
    print(f"CRUZ host: {args.host}")

    try:
        if args.once:
            asyncio.run(run_one(
                host=args.host, mode=mode,
                conversation_id=conversation_id, device=args.device,
                detector=detector,
            ))
        else:
            asyncio.run(run_loop(
                host=args.host, mode=mode,
                conversation_id=conversation_id, device=args.device,
                detector=detector,
            ))
    except KeyboardInterrupt:
        print("\n👋 bye")
    finally:
        if detector is not None:
            try:
                detector.close()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
