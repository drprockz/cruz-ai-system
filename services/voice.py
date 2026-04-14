"""
VoicePipeline + WakeWordDetector — STT, TTS, wake word.

VoicePipeline:
  transcribe(audio_bytes) -> str
      Runs Whisper Large v3 via transformers.pipeline. Never raises.
  speak(text) -> bytes
      Inworld TTS REST API for voice-cloned JARVIS-style output.
      Falls back to macOS `say` when Inworld is missing/down.
      Raises RuntimeError only when BOTH paths fail.

WakeWordDetector:
  Thin wrapper around pvporcupine for "Hey CRUZ" detection. On-device,
  <1% CPU. Requires a trained .ppn keyword model + PICOVOICE_ACCESS_KEY.

Model loading: Whisper (~1.5GB) loads lazily on first transcribe().
pvporcupine is imported lazily so this module imports cleanly when
the package isn't installed (tests patch it in).
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import List, Optional, Sequence

import httpx
from transformers import pipeline

try:  # lazy — test suite patches services.voice.pvporcupine directly
    import pvporcupine  # type: ignore
except ImportError:  # pragma: no cover — real environment installs pvporcupine
    pvporcupine = None  # type: ignore

logger = logging.getLogger("cruz.services.voice")

_WHISPER_MODEL = "openai/whisper-large-v3"
_INWORLD_TTS_URL = "https://api.inworld.ai/tts/v1/voice"


class VoicePipeline:
    """Whisper STT + Inworld TTS (with macOS say fallback)."""

    _whisper_instance = None  # class-level singleton

    def _get_whisper(self):
        """Lazily load and cache the Whisper model."""
        if VoicePipeline._whisper_instance is None:
            logger.info("Loading Whisper model '%s' — first call only", _WHISPER_MODEL)
            VoicePipeline._whisper_instance = pipeline(
                "automatic-speech-recognition",
                model=_WHISPER_MODEL,
                device="cpu",
            )
        return VoicePipeline._whisper_instance

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Convert audio bytes to text via Whisper. Returns '' on failure."""
        if not audio_bytes:
            return ""

        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            whisper = self._get_whisper()
            result = whisper(tmp_path)
            text: str = result.get("text", "") if isinstance(result, dict) else ""
            return text.strip()

        except Exception as exc:
            logger.warning("Whisper transcription failed (non-fatal): %s", exc)
            return ""

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    async def speak(self, text: str) -> bytes:
        """
        Convert text to speech audio bytes.

        Strategy:
          1. If INWORLD_API_KEY is set, try Inworld TTS REST API.
          2. If Inworld fails (no key, network, non-2xx): fall back to
             the macOS `say` command piped to stdout (AIFF bytes).
          3. If both fail: raise RuntimeError with surfaced cause.

        Returns audio bytes (MP3 from Inworld, AIFF from macOS say).
        """
        inworld_error: Optional[str] = None
        api_key = os.environ.get("INWORLD_API_KEY", "").strip()

        if api_key:
            try:
                return await self._speak_inworld(text, api_key)
            except Exception as exc:
                inworld_error = str(exc)
                logger.warning(
                    "Inworld TTS failed (%s) — falling back to macOS say",
                    inworld_error,
                )

        # Fallback: macOS `say -o /dev/stdout`
        try:
            return await self._speak_say(text)
        except Exception as say_exc:
            parts = []
            if inworld_error:
                parts.append(f"Inworld: {inworld_error}")
            parts.append(f"say: {say_exc}")
            raise RuntimeError(
                "TTS failed on both backends — " + " | ".join(parts)
            ) from say_exc

    async def _speak_inworld(self, text: str, api_key: str) -> bytes:
        """POST to Inworld TTS REST API, return audio bytes."""
        voice_id = os.environ.get("INWORLD_VOICE_ID", "").strip() or "default"
        payload = {
            "text": text,
            "voice": {"id": voice_id},
            "format": "mp3",
        }
        async with httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        ) as client:
            resp = await client.post(_INWORLD_TTS_URL, json=payload)
        if resp.status_code >= 300:
            raise RuntimeError(
                f"Inworld TTS HTTP {resp.status_code} — {resp.text[:200]}"
            )
        return resp.content

    async def _speak_say(self, text: str) -> bytes:
        """Run macOS `say` and capture AIFF bytes from stdout."""
        proc = await asyncio.create_subprocess_exec(
            "say", "-o", "/dev/stdout", "--data-format=LEI16@22050", text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"macOS say exit={proc.returncode}: {stderr.decode(errors='replace')[:200]}"
            )
        return stdout


# ─────────────────────────────────────────────
# Wake word detection
# ─────────────────────────────────────────────


class WakeWordDetector:
    """
    Porcupine wake-word detector ("Hey CRUZ").

    On-device, ~1% CPU. Load a custom .ppn file trained on Picovoice
    Console. Feed 512-sample int16 frames at 16 kHz to `detect()`.

    Env:
        PICOVOICE_ACCESS_KEY — required (free tier at picovoice.ai)

    Usage:
        det = WakeWordDetector(keyword_path="Hey_CRUZ.ppn")
        while True:
            frame = read_mic_frame()    # 512 int16 samples
            if det.detect(frame):
                trigger_cruz()
        det.close()
    """

    def __init__(
        self,
        keyword_path: Optional[str] = None,
        keywords: Optional[Sequence[str]] = None,
    ) -> None:
        access_key = os.environ.get("PICOVOICE_ACCESS_KEY", "").strip()
        if not access_key:
            raise RuntimeError(
                "PICOVOICE_ACCESS_KEY is not set — cannot initialise wake word. "
                "Get a free key at https://console.picovoice.ai."
            )
        if pvporcupine is None:
            raise RuntimeError(
                "pvporcupine package not installed. Run `pip install pvporcupine`."
            )

        create_kwargs = {"access_key": access_key}
        if keyword_path:
            create_kwargs["keyword_paths"] = [keyword_path]
        if keywords:
            create_kwargs["keywords"] = list(keywords)
        self._handle = pvporcupine.create(**create_kwargs)

    def detect(self, frame: List[int]) -> bool:
        """
        Process one audio frame. Returns True iff the wake word triggered.

        `frame` must be 512 int16 samples at 16 kHz — Porcupine's contract.
        """
        idx = self._handle.process(frame)
        return isinstance(idx, int) and idx >= 0

    def close(self) -> None:
        """Release the Porcupine handle (call on shutdown)."""
        if self._handle is not None:
            try:
                self._handle.delete()
            except Exception:  # best-effort — never crash on cleanup
                pass
            self._handle = None
