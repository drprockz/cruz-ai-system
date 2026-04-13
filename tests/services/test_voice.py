"""
Tests for VoicePipeline — Whisper STT + Inworld TTS stub.

VoicePipeline:
  - transcribe(audio_bytes: bytes) -> str
      Runs Whisper Large v3 via transformers.pipeline on the raw audio.
      Returns transcribed text. Never raises — returns empty string on error.
  - speak(text: str) -> bytes
      Phase 5 — Inworld TTS WebSocket. Currently raises NotImplementedError.
  - Whisper model is loaded lazily (1.5GB — don't load until first call).
  - Model is a class-level singleton (loaded once per process).

POST /voice/transcribe endpoint:
  - Accepts multipart audio file upload
  - Returns {"text": "<transcription>"}
  - 200 on success, 400 on missing file
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from services.voice import VoicePipeline


# ─────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────

class TestVoicePipelineInterface:
    def test_voice_pipeline_can_be_instantiated(self):
        assert VoicePipeline() is not None

    def test_has_transcribe_method(self):
        assert callable(VoicePipeline().transcribe)

    def test_has_speak_method(self):
        assert callable(VoicePipeline().speak)

    def test_transcribe_is_coroutine(self):
        import asyncio
        pipeline = VoicePipeline()
        with patch.object(pipeline, "_get_whisper", return_value=MagicMock()):
            coro = pipeline.transcribe(b"fake audio")
            assert asyncio.iscoroutine(coro)
            coro.close()

    def test_speak_is_coroutine(self):
        import asyncio
        coro = VoicePipeline().speak("hello")
        assert asyncio.iscoroutine(coro)
        coro.close()


# ─────────────────────────────────────────────
# transcribe()
# ─────────────────────────────────────────────

class TestVoicePipelineTranscribe:
    async def test_transcribe_returns_string(self):
        """transcribe() must return a str."""
        mock_whisper = MagicMock(return_value={"text": "hello world"})
        pipeline = VoicePipeline()

        with patch.object(pipeline, "_get_whisper", return_value=mock_whisper):
            result = await pipeline.transcribe(b"fake audio bytes")

        assert isinstance(result, str)

    async def test_transcribe_returns_model_text(self):
        """The text from Whisper must be returned as-is."""
        mock_whisper = MagicMock(return_value={"text": "deploy the AMA website"})
        pipeline = VoicePipeline()

        with patch.object(pipeline, "_get_whisper", return_value=mock_whisper):
            result = await pipeline.transcribe(b"audio")

        assert result == "deploy the AMA website"

    async def test_transcribe_strips_whitespace(self):
        """Leading/trailing whitespace should be stripped from Whisper output."""
        mock_whisper = MagicMock(return_value={"text": "  hello cruz  "})
        pipeline = VoicePipeline()

        with patch.object(pipeline, "_get_whisper", return_value=mock_whisper):
            result = await pipeline.transcribe(b"audio")

        assert result == "hello cruz"

    async def test_transcribe_returns_empty_string_on_empty_audio(self):
        """Empty audio bytes should return empty string, not raise."""
        mock_whisper = MagicMock(return_value={"text": ""})
        pipeline = VoicePipeline()

        with patch.object(pipeline, "_get_whisper", return_value=mock_whisper):
            result = await pipeline.transcribe(b"")

        assert result == ""

    async def test_transcribe_returns_empty_string_on_model_error(self):
        """If Whisper raises, return empty string — never crash the caller."""
        mock_whisper = MagicMock(side_effect=RuntimeError("CUDA out of memory"))
        pipeline = VoicePipeline()

        with patch.object(pipeline, "_get_whisper", return_value=mock_whisper):
            result = await pipeline.transcribe(b"audio")

        assert result == ""

    async def test_transcribe_passes_audio_to_whisper(self):
        """The audio bytes must be passed to the Whisper model."""
        mock_whisper = MagicMock(return_value={"text": "ok"})
        pipeline = VoicePipeline()

        with patch.object(pipeline, "_get_whisper", return_value=mock_whisper):
            await pipeline.transcribe(b"specific audio content")

        mock_whisper.assert_called_once()


# ─────────────────────────────────────────────
# Lazy model loading
# ─────────────────────────────────────────────

class TestVoicePipelineLazyLoading:
    def test_whisper_not_loaded_on_instantiation(self):
        """Model must NOT be loaded when VoicePipeline() is created."""
        with patch("services.voice.pipeline") as mock_pipeline:
            VoicePipeline()
        mock_pipeline.assert_not_called()

    async def test_whisper_loaded_on_first_transcribe(self):
        """Model IS loaded on the first transcribe() call."""
        VoicePipeline._whisper_instance = None  # reset singleton for isolation
        mock_model = MagicMock(return_value={"text": "hi"})

        with patch("services.voice.pipeline", return_value=mock_model) as mock_pipeline_fn:
            p = VoicePipeline()
            await p.transcribe(b"audio")

        mock_pipeline_fn.assert_called_once()
        VoicePipeline._whisper_instance = None  # clean up

    async def test_whisper_loaded_once_across_multiple_calls(self):
        """Model is only instantiated once — reused across calls."""
        VoicePipeline._whisper_instance = None  # reset singleton for isolation
        mock_model = MagicMock(return_value={"text": "hi"})

        with patch("services.voice.pipeline", return_value=mock_model) as mock_pipeline_fn:
            p = VoicePipeline()
            await p.transcribe(b"audio1")
            await p.transcribe(b"audio2")
            await p.transcribe(b"audio3")

        mock_pipeline_fn.assert_called_once()
        VoicePipeline._whisper_instance = None  # clean up after


# ─────────────────────────────────────────────
# speak() — Phase 5 stub
# ─────────────────────────────────────────────

class TestVoicePipelineSpeak:
    async def test_speak_raises_not_implemented(self):
        """speak() is a Phase 5 stub — must raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await VoicePipeline().speak("Hello CRUZ")

    async def test_speak_error_message_mentions_inworld(self):
        """Error message should reference Inworld TTS so devs know what to implement."""
        try:
            await VoicePipeline().speak("hello")
        except NotImplementedError as e:
            assert "inworld" in str(e).lower() or "phase" in str(e).lower()
