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
import base64
import logging
import os
import tempfile
from typing import List, Optional, Sequence

import httpx
from transformers import pipeline

try:  # lazy — test suite patches services.voice.pvporcupine directly
    import pvporcupine  # type: ignore
except ImportError:  # pragma: no cover — only needed when backend=picovoice
    pvporcupine = None  # type: ignore

try:  # lazy — test suite patches services.voice.openwakeword directly
    import openwakeword  # type: ignore
except ImportError:  # pragma: no cover — only needed when backend=openwakeword
    openwakeword = None  # type: ignore

logger = logging.getLogger("cruz.services.voice")

_WHISPER_MODEL = "openai/whisper-large-v3"
_INWORLD_TTS_URL = "https://api.inworld.ai/tts/v1/voice"
_INWORLD_MODEL = "inworld-tts-1.5-max"
_INWORLD_DEFAULT_VOICE = "default--ypb7u4pb7ydy8zij82pta__jarvis_20"  # JARVIS preset


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
        """
        POST to Inworld TTS non-streaming endpoint, return raw MP3 bytes.

        Real API contract (per docs.inworld.ai):
          - Auth:    "Authorization: Basic <api_key>"  (key already base64-encoded)
          - Payload: {text, voiceId, modelId, timestampType, audioConfig.speakingRate, temperature}
          - Response: {"audioContent": "<base64-mp3>", "timestampInfo": {...}}
        """
        voice_id = (
            os.environ.get("INWORLD_VOICE_ID", "").strip()
            or _INWORLD_DEFAULT_VOICE
        )
        payload = {
            "text": text,
            "voiceId": voice_id,
            "modelId": _INWORLD_MODEL,
            "timestampType": "WORD",
            "audioConfig": {"speakingRate": 1.05},
            "temperature": 0.9,
        }
        async with httpx.AsyncClient(
            headers={
                "Authorization": f"Basic {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        ) as client:
            resp = await client.post(_INWORLD_TTS_URL, json=payload)
        if resp.status_code >= 300:
            raise RuntimeError(
                f"Inworld TTS HTTP {resp.status_code} — {resp.text[:200]}"
            )
        data = resp.json()
        encoded = data.get("audioContent") or ""
        if not encoded:
            raise RuntimeError("Inworld TTS response missing audioContent")
        return base64.b64decode(encoded)

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


_VALID_BACKENDS = ("openwakeword", "picovoice")


class WakeWordDetector:
    """
    On-device wake-word detector with two pluggable backends.

    Backends:
      - **openwakeword** (default) — fully open source, no API key required.
        Pre-trained models include 'hey_jarvis', 'alexa', 'hey_mycroft'.
        Feed 1280-sample int16 frames at 16 kHz (80ms).
      - **picovoice** — Porcupine. Needs PICOVOICE_ACCESS_KEY. Supports
        custom .ppn models (e.g. a trained "Hey CRUZ" keyword).
        Feed 512-sample int16 frames at 16 kHz.

    Backend selected by `backend=` arg (wins), then WAKE_WORD_BACKEND env
    var, then default 'openwakeword'.

    Usage (openWakeWord — no signup):
        det = WakeWordDetector(keyword="hey_jarvis")
        while True:
            frame = read_mic_frame()
            if det.detect(frame):
                trigger_cruz()
        det.close()

    Usage (Picovoice custom model):
        det = WakeWordDetector(backend="picovoice", keyword_path="Hey_CRUZ.ppn")
    """

    def __init__(
        self,
        backend: Optional[str] = None,
        keyword: Optional[str] = None,
        keyword_path: Optional[str] = None,
        keywords: Optional[Sequence[str]] = None,
        threshold: float = 0.5,
    ) -> None:
        resolved = (
            backend
            or os.environ.get("WAKE_WORD_BACKEND", "").strip().lower()
            or "openwakeword"
        )
        if resolved not in _VALID_BACKENDS:
            raise RuntimeError(
                f"unknown backend '{resolved}' — WAKE_WORD_BACKEND must be "
                f"one of {_VALID_BACKENDS}"
            )
        self._backend = resolved
        self._threshold = threshold
        self._oww_model = None
        self._pv_handle = None
        self._keyword = keyword or "hey_jarvis"

        if resolved == "openwakeword":
            self._init_openwakeword()
        else:
            self._init_picovoice(keyword_path, keywords)

    # ── backend init ──────────────────────────────────────────────────

    def _init_openwakeword(self) -> None:
        if openwakeword is None:
            raise RuntimeError(
                "openwakeword package not installed. "
                "Run `pip install openwakeword`."
            )
        # The pretrained models aren't shipped inside the pip package;
        # openwakeword provides a helper that fetches them on demand.
        # Download-if-missing is cheap (local check) so always call it.
        try:
            from openwakeword.utils import download_models  # type: ignore
            download_models()
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "openwakeword model download failed (continuing — "
                "will fail loudly on Model() if truly missing): %s", exc,
            )
        self._oww_model = openwakeword.Model(
            wakeword_models=[self._keyword],
            inference_framework="onnx",
        )

    def _init_picovoice(
        self,
        keyword_path: Optional[str],
        keywords: Optional[Sequence[str]],
    ) -> None:
        access_key = os.environ.get("PICOVOICE_ACCESS_KEY", "").strip()
        if not access_key:
            raise RuntimeError(
                "PICOVOICE_ACCESS_KEY is not set — cannot initialise "
                "picovoice wake-word backend. Either get a free consumer "
                "key at console.picovoice.ai or use the default "
                "openwakeword backend (no signup)."
            )
        if pvporcupine is None:
            raise RuntimeError(
                "pvporcupine package not installed. Run `pip install pvporcupine`."
            )
        create_kwargs: dict = {"access_key": access_key}
        if keyword_path:
            create_kwargs["keyword_paths"] = [keyword_path]
        if keywords:
            create_kwargs["keywords"] = list(keywords)
        self._pv_handle = pvporcupine.create(**create_kwargs)

    # ── detect / close ────────────────────────────────────────────────

    def detect(self, frame) -> bool:
        """
        Process one audio frame. Returns True iff the wake word triggered.

        Frame size depends on backend:
          - openwakeword: 1280 int16 samples @ 16kHz (80ms chunks)
          - picovoice:    512  int16 samples @ 16kHz
        """
        if self._backend == "openwakeword":
            scores = self._oww_model.predict(frame)
            if not isinstance(scores, dict):
                return False
            best = max(scores.values(), default=0.0)
            return best >= self._threshold
        # picovoice
        idx = self._pv_handle.process(frame)
        return isinstance(idx, int) and idx >= 0

    def close(self) -> None:
        """Release backend resources (safe to call twice)."""
        if self._backend == "picovoice" and self._pv_handle is not None:
            try:
                self._pv_handle.delete()
            except Exception:
                pass
            self._pv_handle = None
        # openwakeword.Model has no explicit close — drop the reference
        self._oww_model = None

    # ── Backend introspection ─────────────────────────────────────────

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def frame_length(self) -> int:
        """Expected frame size in int16 samples."""
        return 1280 if self._backend == "openwakeword" else 512

    @property
    def sample_rate(self) -> int:
        return 16000  # both backends operate at 16kHz
