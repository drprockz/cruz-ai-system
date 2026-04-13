"""
VoicePipeline — STT via Whisper Large v3, TTS stub for Phase 5.

transcribe(audio_bytes) -> str
    Runs Whisper Large v3 via transformers.pipeline on raw audio bytes.
    Writes bytes to a temp file, runs the model, returns cleaned text.
    Never raises — returns empty string on any error.

speak(text) -> bytes
    Phase 5: Inworld TTS WebSocket streaming.
    Raises NotImplementedError until Phase 5 is implemented.

Model loading:
    Whisper (~1.5GB) is loaded lazily on the first transcribe() call
    and reused for the lifetime of the process.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

from transformers import pipeline

logger = logging.getLogger("cruz.services.voice")

_WHISPER_MODEL = "openai/whisper-large-v3"


class VoicePipeline:
    """
    Whisper STT + Inworld TTS pipeline.

    Instantiate once per request (or use a singleton) — the underlying
    Whisper model is a class-level cache so it loads only once.
    """

    _whisper_instance = None  # class-level singleton

    def _get_whisper(self):
        """Lazily load and cache the Whisper model."""
        if VoicePipeline._whisper_instance is None:
            logger.info("Loading Whisper model '%s' — first call only", _WHISPER_MODEL)
            VoicePipeline._whisper_instance = pipeline(
                "automatic-speech-recognition",
                model=_WHISPER_MODEL,
                device="cpu",  # Mac Mini M4 — use CPU; MPS optional in future
            )
        return VoicePipeline._whisper_instance

    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Convert raw audio bytes to text using Whisper Large v3.

        Args:
            audio_bytes: Raw audio data (WAV, MP3, OGG, etc.)

        Returns:
            Transcribed text, stripped of leading/trailing whitespace.
            Returns empty string on any error — never raises.
        """
        if not audio_bytes:
            return ""

        tmp_path: Optional[str] = None
        try:
            # Write to a temp file — Whisper pipeline accepts file paths
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False
            ) as tmp:
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
        Convert text to speech via Inworld TTS 1.5 Max.

        Phase 5 — not yet implemented. Requires:
          - Inworld API key (INWORLD_API_KEY)
          - WebSocket streaming connection
          - Cloned voice ID (INWORLD_VOICE_ID)

        Raises:
            NotImplementedError: Always, until Phase 5 is built.
        """
        raise NotImplementedError(
            "Inworld TTS not yet implemented. "
            "Phase 5 will add WebSocket streaming via INWORLD_API_KEY."
        )
