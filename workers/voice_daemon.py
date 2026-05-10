"""
workers/voice_daemon.py — always-on local voice daemon.

Uses the Mac Mini's physical microphone and speakers via the local
Whisper + Inworld stack. NOT LiveKit — see workers/voice_agent/ for
the web-client LiveKit bridge.

Loop:
  1. WakeWordDetector listens on mic (frame_length from detector)
  2. Wake word → play audio cue, start VAD-bounded capture (≤30 s)
  3. VoicePipeline.transcribe() → text
  4. POST /command to CRUZ API (stream=False, device="mac_mini")
  5. VoicePipeline.speak() → sounddevice playback
  6. Repeat

Conversation ID is stable for the daemon's lifetime (new UUID at
startup). SIGINT / SIGTERM trigger a clean shutdown.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import signal
import uuid
import wave
from typing import Optional

import httpx
import numpy as np

from services.alerts import get_alert_service
from services.mac_controller import get_mac_controller_service
from services.vad import SileroVAD
from services.voice import VoicePipeline, WakeWordDetector

logger = logging.getLogger("cruz.workers.voice_daemon")

# ── Config ────────────────────────────────────────────────────────────────
CRUZ_API_URL = os.environ.get("CRUZ_API_URL", "http://localhost:3000")
MAX_CAPTURE_SECONDS: float = 30.0
SILENCE_SECONDS: float = 1.5
SAMPLE_RATE: int = 16_000
CHANNELS: int = 1
SAMPLE_WIDTH: int = 2  # int16 = 2 bytes
REQUEST_TIMEOUT: float = 30.0

# ── Optional deps (guarded so the module imports cleanly in tests) ────────
try:
    import pyaudio  # type: ignore
except ImportError:  # pragma: no cover
    pyaudio = None  # type: ignore

try:
    import sounddevice as sd  # type: ignore
    import soundfile as sf  # type: ignore
except ImportError:  # pragma: no cover
    sd = None  # type: ignore
    sf = None  # type: ignore


# ── Helpers ───────────────────────────────────────────────────────────────


def _pcm_to_wav(pcm: bytes) -> bytes:
    """Wrap raw int16 PCM bytes in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


async def _play_audio(audio_bytes: bytes) -> None:
    """Decode audio bytes (MP3 or AIFF) and play via sounddevice.

    Falls back to a subprocess ``afplay`` call on macOS if soundfile
    cannot decode the format.
    """
    if sd is None or sf is None:
        logger.warning("sounddevice/soundfile not installed — skipping playback")
        return

    def _blocking_play() -> None:
        try:
            data, samplerate = sf.read(io.BytesIO(audio_bytes))
            sd.play(data, samplerate=samplerate)
            sd.wait()
        except Exception as exc:
            logger.warning("soundfile decode failed (%s) — trying afplay", exc)
            _afplay_fallback(audio_bytes)

    await asyncio.to_thread(_blocking_play)


def _afplay_fallback(audio_bytes: bytes) -> None:
    """Write audio to a temp file and play with macOS afplay."""
    import os
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
        f.write(audio_bytes)
        tmp = f.name
    try:
        subprocess.run(["afplay", tmp], check=False, timeout=60)  # noqa: S603
    except Exception as exc:
        logger.warning("afplay fallback failed: %s", exc)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


async def _post_to_cruz(
    text: str,
    conversation_id: str,
    trace_id: str,
) -> Optional[str]:
    """POST text to the CRUZ /command endpoint, return the text result."""
    payload = {
        "message": text,
        "conversation_id": conversation_id,
        "device": "mac_mini",
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(f"{CRUZ_API_URL}/command", json=payload)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", "")
        if isinstance(result, str):
            return result.strip() or None
        return None
    except httpx.ConnectError:
        logger.warning("[%s] CRUZ API unreachable — notifying via Telegram", trace_id)
        try:
            await get_alert_service().notify(
                "warning",
                "Voice daemon degraded",
                "Cannot reach CRUZ API at " + CRUZ_API_URL,
            )
        except Exception as alert_exc:
            logger.warning("alert send failed: %s", alert_exc)
        return None
    except Exception as exc:
        logger.warning("[%s] /command POST failed: %s", trace_id, exc)
        return None


# ── Capture loop helpers ──────────────────────────────────────────────────


def _sync_listen_for_wake(
    pa_stream: "pyaudio.Stream", detector: "WakeWordDetector"
) -> None:  # noqa: F821
    """Blocking read loop until wake word fires. Runs in a thread."""
    frame_len = detector.frame_length
    while True:
        raw = pa_stream.read(frame_len, exception_on_overflow=False)
        frame = np.frombuffer(raw, dtype=np.int16)
        if detector.detect(frame):
            return


def _sync_capture_speech(
    pa_stream: "pyaudio.Stream",  # noqa: F821
    vad: "SileroVAD",  # noqa: F821
    frame_len: int,
) -> bytes:
    """Capture PCM frames until 1.5 s silence or 30 s max. Runs in a thread."""
    max_frames = int(MAX_CAPTURE_SECONDS * SAMPLE_RATE / frame_len)
    silence_threshold = int(SILENCE_SECONDS * SAMPLE_RATE / frame_len)

    frames: list[bytes] = []
    consecutive_silent = 0

    for _ in range(max_frames):
        raw = pa_stream.read(frame_len, exception_on_overflow=False)
        frames.append(raw)
        arr = np.frombuffer(raw, dtype=np.int16)
        if vad.is_speech(arr):
            consecutive_silent = 0
        else:
            consecutive_silent += 1
            if consecutive_silent >= silence_threshold:
                break

    return b"".join(frames)


# ── Main loop ─────────────────────────────────────────────────────────────


async def run() -> None:
    """Entry point — run the daemon until SIGINT/SIGTERM."""
    if pyaudio is None:
        raise RuntimeError("pyaudio is not installed — cannot open microphone")

    conversation_id = str(uuid.uuid4())
    logger.info("voice-daemon starting — session %s", conversation_id)

    pipeline = VoicePipeline()
    detector = WakeWordDetector()
    vad = SileroVAD()
    mac = get_mac_controller_service()

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    pa = pyaudio.PyAudio()
    stream: Optional["pyaudio.Stream"] = None  # noqa: F821
    try:
        stream = pa.open(
            rate=SAMPLE_RATE,
            channels=CHANNELS,
            format=pa.get_format_from_width(SAMPLE_WIDTH),
            input=True,
            frames_per_buffer=detector.frame_length,
        )

        logger.info(
            "microphone open — frame_length=%d backend=%s",
            detector.frame_length,
            detector.backend,
        )

        while not shutdown.is_set():
            # ── Step 1: wait for wake word ────────────────────────────
            try:
                await asyncio.to_thread(_sync_listen_for_wake, stream, detector)
            except Exception as exc:
                logger.error("wake-word listener error: %s", exc)
                await asyncio.sleep(1)
                continue

            if shutdown.is_set():
                break

            logger.info("wake word detected")

            # ── Step 2: play audio cue ────────────────────────────────
            try:
                await mac.notify("CRUZ", "Listening…", sound=True)
            except Exception:
                pass  # non-fatal cue failure

            # ── Step 3: capture speech with VAD ───────────────────────
            trace_id = str(uuid.uuid4())
            try:
                pcm_bytes = await asyncio.to_thread(
                    _sync_capture_speech, stream, vad, detector.frame_length
                )
            except Exception as exc:
                logger.error("[%s] capture failed: %s", trace_id, exc)
                continue

            if not pcm_bytes:
                continue

            # ── Step 4: transcribe ────────────────────────────────────
            wav_bytes = _pcm_to_wav(pcm_bytes)
            text = await pipeline.transcribe(wav_bytes)
            text = (text or "").strip()
            if not text:
                logger.debug("[%s] empty transcription — skipping", trace_id)
                continue

            logger.info("[%s] heard: %.120s", trace_id, text)

            # ── Step 5: POST to CRUZ ──────────────────────────────────
            response_text = await _post_to_cruz(text, conversation_id, trace_id)
            if not response_text:
                logger.debug("[%s] empty CRUZ response", trace_id)
                continue

            logger.info("[%s] CRUZ: %.120s", trace_id, response_text)

            # ── Step 6: speak ─────────────────────────────────────────
            try:
                audio_bytes = await pipeline.speak(response_text)
                await _play_audio(audio_bytes)
            except Exception as exc:
                logger.warning("[%s] speak/play failed: %s", trace_id, exc)

    finally:
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        try:
            pa.terminate()
        except Exception:
            pass
        detector.close()
        logger.info("voice-daemon stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run())
