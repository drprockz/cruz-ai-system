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

try:  # faster-whisper — our Whisper runtime (CTranslate2, ~4x faster than transformers)
    from faster_whisper import WhisperModel  # type: ignore
except ImportError:  # pragma: no cover
    WhisperModel = None  # type: ignore

# Legacy transformers pipeline kept as a fallback when faster-whisper isn't
# available (e.g. in a minimal test env). New runs default to faster-whisper.
try:
    from transformers import pipeline as _hf_pipeline  # type: ignore
except ImportError:  # pragma: no cover
    _hf_pipeline = None  # type: ignore

try:  # lazy — test suite patches services.voice.pvporcupine directly
    import pvporcupine  # type: ignore
except ImportError:  # pragma: no cover — only needed when backend=picovoice
    pvporcupine = None  # type: ignore

try:  # lazy — test suite patches services.voice.openwakeword directly
    import openwakeword  # type: ignore
except ImportError:  # pragma: no cover — only needed when backend=openwakeword
    openwakeword = None  # type: ignore

logger = logging.getLogger("cruz.services.voice")

# Whisper model — configurable via WHISPER_MODEL env var.
#
# faster-whisper accepts short names ("tiny.en" / "small.en" / "medium"
# / "large-v3") or the full HuggingFace id ("openai/whisper-small").
# Default `small.en` + int8 quantisation gives ~400-700ms transcribes
# on Mac Mini M4 CPU with excellent English accuracy (~4x faster than
# transformers). Override with `WHISPER_MODEL=large-v3` when you need
# non-English or nuanced dictation.
_WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small.en")
_WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
_INWORLD_TTS_URL = "https://api.inworld.ai/tts/v1/voice"
_INWORLD_MODEL = "inworld-tts-1.5-max"
_INWORLD_DEFAULT_VOICE = "default--ypb7u4pb7ydy8zij82pta__jarvis_20"  # JARVIS preset


class VoicePipeline:
    """Whisper STT + Inworld TTS (with macOS say fallback)."""

    _whisper_instance = None  # class-level singleton (faster-whisper or HF)
    _whisper_runtime = None   # "faster-whisper" or "transformers"

    def _get_whisper(self):
        """Lazily load and cache the Whisper model (faster-whisper preferred)."""
        if VoicePipeline._whisper_instance is not None:
            return VoicePipeline._whisper_instance

        # Preferred: faster-whisper (CTranslate2, ~4x faster than transformers)
        if WhisperModel is not None:
            logger.info(
                "Loading faster-whisper model '%s' (compute_type=%s) — first call only",
                _WHISPER_MODEL, _WHISPER_COMPUTE_TYPE,
            )
            VoicePipeline._whisper_instance = WhisperModel(
                _WHISPER_MODEL,
                device="cpu",
                compute_type=_WHISPER_COMPUTE_TYPE,
            )
            VoicePipeline._whisper_runtime = "faster-whisper"
            return VoicePipeline._whisper_instance

        # Fallback: transformers pipeline (kept for test/CI envs)
        if _hf_pipeline is not None:
            logger.info(
                "faster-whisper unavailable — falling back to transformers "
                "pipeline for model '%s'", _WHISPER_MODEL,
            )
            model_id = (
                _WHISPER_MODEL
                if "/" in _WHISPER_MODEL
                else f"openai/whisper-{_WHISPER_MODEL.split('.')[0]}"
            )
            VoicePipeline._whisper_instance = _hf_pipeline(
                "automatic-speech-recognition",
                model=model_id,
                device="cpu",
            )
            VoicePipeline._whisper_runtime = "transformers"
            return VoicePipeline._whisper_instance

        raise RuntimeError(
            "Neither faster-whisper nor transformers is installed. "
            "Run `pip install faster-whisper`."
        )

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
            runtime = VoicePipeline._whisper_runtime

            if runtime == "faster-whisper":
                # Returns (segments, info); segments is an iterator of Segment
                # objects with a .text attribute. vad_filter=True drops silence
                # padding automatically — noticeable win on longer clips.
                segments, _info = whisper.transcribe(
                    tmp_path, vad_filter=True, beam_size=1,
                )
                text = " ".join(seg.text.strip() for seg in segments)
                return text.strip()

            # transformers fallback
            result = whisper(tmp_path)
            text = result.get("text", "") if isinstance(result, dict) else ""
            return text.strip()

        except Exception as exc:
            logger.warning(
                "Whisper transcription failed (non-fatal): %s", exc,
                exc_info=True,
            )
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
        """
        Run macOS `say`, write AIFF to a temp file, read+return bytes.

        `say -o /dev/stdout` does NOT work reliably on macOS — the tool
        refuses to write audio to a non-seekable stream. Must use a real
        file path.
        """
        path = tempfile.mktemp(suffix=".aiff")
        try:
            proc = await asyncio.create_subprocess_exec(
                "say", "-o", path, text,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(
                    f"macOS say exit={proc.returncode}: "
                    f"{stderr.decode(errors='replace')[:200]}"
                )
            with open(path, "rb") as f:
                return f.read()
        finally:
            if os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


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
          - openwakeword: 1280 int16 samples @ 16kHz (80ms chunks) — numpy array
          - picovoice:    512  int16 samples @ 16kHz — list[int]

        Callers can pass either a numpy array or a list; we coerce to
        whatever the underlying backend expects.
        """
        if self._backend == "openwakeword":
            # openwakeword rejects Python lists; needs numpy
            try:
                import numpy as np
            except ImportError:  # pragma: no cover
                raise RuntimeError(
                    "numpy is required for the openwakeword backend. "
                    "Run `pip install numpy`."
                )
            arr = frame if hasattr(frame, "dtype") else np.asarray(frame, dtype=np.int16)
            scores = self._oww_model.predict(arr)
            if not isinstance(scores, dict):
                return False
            best = max(scores.values(), default=0.0)
            return best >= self._threshold
        # picovoice wants a list of Python ints
        if hasattr(frame, "tolist"):
            frame = frame.tolist()
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
