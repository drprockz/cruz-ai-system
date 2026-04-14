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
# speak() — Inworld TTS + macOS say fallback (R16)
# ─────────────────────────────────────────────

import os


import base64


def _mock_inworld_response(status: int = 200, audio: bytes = b"MP3DATA"):
    """
    Mock Inworld TTS non-streaming response.

    Real API returns JSON: {"audioContent": "<base64-mp3>", "timestampInfo": {...}}
    """
    resp = MagicMock()
    resp.status_code = status
    resp.text = "" if status < 300 else "unauthorized"
    resp.json = MagicMock(return_value={
        "audioContent": base64.b64encode(audio).decode("ascii"),
    })
    return resp


def _patch_inworld_httpx(response):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)
    return patch("services.voice.httpx.AsyncClient", return_value=client), client


class TestVoicePipelineSpeak:
    @pytest.mark.asyncio
    async def test_speak_uses_inworld_when_key_set(self):
        resp = _mock_inworld_response(audio=b"IDKAUDIO123")
        pc, client = _patch_inworld_httpx(resp)
        env = {"INWORLD_API_KEY": "inworld_test", "INWORLD_VOICE_ID": "jarvis-v1"}
        with patch.dict(os.environ, env, clear=False), pc:
            audio = await VoicePipeline().speak("Hello Darshan")
        # Must be the decoded MP3 bytes, not the base64 string
        assert audio == b"IDKAUDIO123"
        client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_speak_posts_to_non_streaming_endpoint(self):
        """Endpoint: https://api.inworld.ai/tts/v1/voice (non-streaming)."""
        resp = _mock_inworld_response()
        pc, client = _patch_inworld_httpx(resp)
        with patch.dict(os.environ, {"INWORLD_API_KEY": "k"}, clear=False), pc:
            await VoicePipeline().speak("hi")
        url = client.post.call_args[0][0]
        assert url == "https://api.inworld.ai/tts/v1/voice"

    @pytest.mark.asyncio
    async def test_speak_uses_basic_auth_not_bearer(self):
        """Inworld uses Basic auth; the API key is already base64-encoded."""
        resp = _mock_inworld_response()
        with patch("services.voice.httpx.AsyncClient") as cls:
            inner = AsyncMock()
            inner.__aenter__ = AsyncMock(return_value=inner)
            inner.__aexit__ = AsyncMock(return_value=None)
            inner.post = AsyncMock(return_value=resp)
            cls.return_value = inner
            with patch.dict(os.environ, {"INWORLD_API_KEY": "SECRETKEY"},
                            clear=False):
                await VoicePipeline().speak("hi")
        headers = cls.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Basic SECRETKEY"

    @pytest.mark.asyncio
    async def test_speak_payload_uses_camelcase_fields(self):
        """Non-streaming payload: voiceId, modelId, audioConfig.speakingRate, temperature."""
        resp = _mock_inworld_response()
        pc, client = _patch_inworld_httpx(resp)
        env = {
            "INWORLD_API_KEY": "k",
            "INWORLD_VOICE_ID": "default--ypb7u4pb7ydy8zij82pta__jarvis_20",
        }
        with patch.dict(os.environ, env, clear=False), pc:
            await VoicePipeline().speak("Deploy complete")
        payload = client.post.call_args.kwargs["json"]
        assert payload["text"] == "Deploy complete"
        assert payload["voiceId"] == \
            "default--ypb7u4pb7ydy8zij82pta__jarvis_20"
        assert payload["modelId"] == "inworld-tts-1.5-max"
        assert payload["audioConfig"]["speakingRate"] == 1.05
        assert payload["temperature"] == 0.9

    @pytest.mark.asyncio
    async def test_speak_default_voice_is_jarvis_20(self):
        resp = _mock_inworld_response()
        pc, client = _patch_inworld_httpx(resp)
        with patch.dict(os.environ, {"INWORLD_API_KEY": "k", "INWORLD_VOICE_ID": ""},
                        clear=False), pc:
            await VoicePipeline().speak("hi")
        assert client.post.call_args.kwargs["json"]["voiceId"] == \
            "default--ypb7u4pb7ydy8zij82pta__jarvis_20"

    @pytest.mark.asyncio
    async def test_speak_falls_back_to_say_when_no_key(self):
        # _speak_say now writes AIFF to a temp file and reads bytes back,
        # so mocking subprocess alone isn't enough — patch the helper
        # directly to return the bytes we want to verify pass-through.
        pipeline = VoicePipeline()
        with patch.dict(os.environ, {"INWORLD_API_KEY": ""}, clear=True), \
             patch.object(pipeline, "_speak_say",
                          new=AsyncMock(return_value=b"AIFFDATA")):
            audio = await pipeline.speak("Hi")
        assert audio == b"AIFFDATA"

    @pytest.mark.asyncio
    async def test_speak_falls_back_to_say_on_inworld_failure(self):
        bad_resp = _mock_inworld_response(status=500)
        pc, _ = _patch_inworld_httpx(bad_resp)

        env = {"INWORLD_API_KEY": "inworld_test"}
        pipeline = VoicePipeline()
        with patch.dict(os.environ, env, clear=False), pc, \
             patch.object(pipeline, "_speak_say",
                          new=AsyncMock(return_value=b"FALLBACK")):
            audio = await pipeline.speak("Hello")
        assert audio == b"FALLBACK"

    @pytest.mark.asyncio
    async def test_speak_raises_runtime_error_when_both_paths_fail(self):
        bad_resp = _mock_inworld_response(status=500)
        pc, _ = _patch_inworld_httpx(bad_resp)

        env = {"INWORLD_API_KEY": "inworld_test"}
        pipeline = VoicePipeline()
        with patch.dict(os.environ, env, clear=False), pc, \
             patch.object(pipeline, "_speak_say",
                          new=AsyncMock(side_effect=RuntimeError("say not found"))):
            with pytest.raises(RuntimeError, match="TTS"):
                await pipeline.speak("Hello")


# ─────────────────────────────────────────────
# WakeWordDetector — two backends (picovoice + openwakeword)
# ─────────────────────────────────────────────

class TestWakeWordDetectorInterface:
    def test_can_be_imported(self):
        from services.voice import WakeWordDetector  # noqa: F401

    def test_default_backend_is_openwakeword(self):
        """No Picovoice approval needed for default usage — openWakeWord is free."""
        from services.voice import WakeWordDetector
        # Force picovoice env missing, so if the default was picovoice we'd crash
        fake_oww = MagicMock()
        fake_oww.Model = MagicMock()
        with patch.dict(os.environ, {"PICOVOICE_ACCESS_KEY": ""}, clear=True), \
             patch("services.voice.openwakeword", fake_oww):
            # Should not raise — openwakeword doesn't need a key
            WakeWordDetector(keyword="hey_jarvis")
        fake_oww.Model.assert_called_once()

    def test_explicit_backend_picovoice(self):
        from services.voice import WakeWordDetector
        fake_pv = MagicMock()
        fake_pv.create = MagicMock(return_value=MagicMock())
        with patch.dict(os.environ, {"PICOVOICE_ACCESS_KEY": "pv"}, clear=False), \
             patch("services.voice.pvporcupine", fake_pv):
            WakeWordDetector(backend="picovoice", keyword_path="/tmp/Hey_CRUZ.ppn")
        fake_pv.create.assert_called_once()

    def test_env_var_picks_backend(self):
        from services.voice import WakeWordDetector
        fake_pv = MagicMock()
        fake_pv.create = MagicMock(return_value=MagicMock())
        env = {"WAKE_WORD_BACKEND": "picovoice", "PICOVOICE_ACCESS_KEY": "pv"}
        with patch.dict(os.environ, env, clear=False), \
             patch("services.voice.pvporcupine", fake_pv):
            WakeWordDetector(keyword_path="/tmp/Hey_CRUZ.ppn")
        fake_pv.create.assert_called_once()

    def test_unknown_backend_raises(self):
        from services.voice import WakeWordDetector
        with pytest.raises(RuntimeError, match="unknown backend|WAKE_WORD_BACKEND"):
            WakeWordDetector(backend="skynet")


class TestPicovoiceBackend:
    def test_init_raises_without_access_key(self):
        from services.voice import WakeWordDetector
        with patch.dict(os.environ, {"PICOVOICE_ACCESS_KEY": ""}, clear=True):
            with pytest.raises(RuntimeError, match="PICOVOICE_ACCESS_KEY"):
                WakeWordDetector(backend="picovoice",
                                 keyword_path="/tmp/Hey_CRUZ.ppn")

    def test_init_calls_pvporcupine_create(self):
        from services.voice import WakeWordDetector
        fake_pv = MagicMock()
        fake_pv.create = MagicMock(return_value=MagicMock())
        with patch.dict(os.environ, {"PICOVOICE_ACCESS_KEY": "pv_test"}, clear=False), \
             patch("services.voice.pvporcupine", fake_pv):
            WakeWordDetector(backend="picovoice",
                             keyword_path="/tmp/Hey_CRUZ.ppn")
        fake_pv.create.assert_called_once()
        kwargs = fake_pv.create.call_args.kwargs
        assert kwargs["access_key"] == "pv_test"
        assert kwargs["keyword_paths"] == ["/tmp/Hey_CRUZ.ppn"]

    def test_detect_returns_true_when_keyword_matches(self):
        from services.voice import WakeWordDetector
        handle = MagicMock()
        handle.process = MagicMock(return_value=0)
        fake_pv = MagicMock()
        fake_pv.create = MagicMock(return_value=handle)
        with patch.dict(os.environ, {"PICOVOICE_ACCESS_KEY": "pv"}, clear=False), \
             patch("services.voice.pvporcupine", fake_pv):
            det = WakeWordDetector(backend="picovoice",
                                   keyword_path="/tmp/Hey_CRUZ.ppn")
            assert det.detect([0] * 512) is True

    def test_detect_returns_false_when_no_match(self):
        from services.voice import WakeWordDetector
        handle = MagicMock()
        handle.process = MagicMock(return_value=-1)
        fake_pv = MagicMock()
        fake_pv.create = MagicMock(return_value=handle)
        with patch.dict(os.environ, {"PICOVOICE_ACCESS_KEY": "pv"}, clear=False), \
             patch("services.voice.pvporcupine", fake_pv):
            det = WakeWordDetector(backend="picovoice",
                                   keyword_path="/tmp/Hey_CRUZ.ppn")
            assert det.detect([0] * 512) is False

    def test_close_releases_handle(self):
        from services.voice import WakeWordDetector
        handle = MagicMock()
        handle.delete = MagicMock()
        fake_pv = MagicMock()
        fake_pv.create = MagicMock(return_value=handle)
        with patch.dict(os.environ, {"PICOVOICE_ACCESS_KEY": "pv"}, clear=False), \
             patch("services.voice.pvporcupine", fake_pv):
            det = WakeWordDetector(backend="picovoice",
                                   keyword_path="/tmp/Hey_CRUZ.ppn")
            det.close()
        handle.delete.assert_called_once()


class TestOpenWakeWordBackend:
    def test_init_loads_builtin_keyword_model(self):
        from services.voice import WakeWordDetector
        fake_oww = MagicMock()
        fake_oww.Model = MagicMock()
        with patch.dict(os.environ, {}, clear=True), \
             patch("services.voice.openwakeword", fake_oww):
            WakeWordDetector(backend="openwakeword", keyword="hey_jarvis")
        fake_oww.Model.assert_called_once()
        kwargs = fake_oww.Model.call_args.kwargs
        # Model should be loaded with the hey_jarvis pretrained model
        blob = str(kwargs).lower()
        assert "hey_jarvis" in blob or "jarvis" in blob

    def test_detect_returns_true_when_score_above_threshold(self):
        """Score >= 0.5 → match."""
        from services.voice import WakeWordDetector
        model = MagicMock()
        model.predict = MagicMock(return_value={"hey_jarvis": 0.87})
        fake_oww = MagicMock()
        fake_oww.Model = MagicMock(return_value=model)
        with patch.dict(os.environ, {}, clear=True), \
             patch("services.voice.openwakeword", fake_oww):
            det = WakeWordDetector(backend="openwakeword", keyword="hey_jarvis")
            assert det.detect([0] * 1280) is True

    def test_detect_returns_false_when_score_below_threshold(self):
        from services.voice import WakeWordDetector
        model = MagicMock()
        model.predict = MagicMock(return_value={"hey_jarvis": 0.12})
        fake_oww = MagicMock()
        fake_oww.Model = MagicMock(return_value=model)
        with patch.dict(os.environ, {}, clear=True), \
             patch("services.voice.openwakeword", fake_oww):
            det = WakeWordDetector(backend="openwakeword", keyword="hey_jarvis")
            assert det.detect([0] * 1280) is False

    def test_custom_threshold_respected(self):
        """Operator can lower the threshold to reduce missed wakes."""
        from services.voice import WakeWordDetector
        model = MagicMock()
        model.predict = MagicMock(return_value={"hey_jarvis": 0.30})
        fake_oww = MagicMock()
        fake_oww.Model = MagicMock(return_value=model)
        with patch.dict(os.environ, {}, clear=True), \
             patch("services.voice.openwakeword", fake_oww):
            # With threshold=0.25, 0.30 should now count as match
            det = WakeWordDetector(
                backend="openwakeword", keyword="hey_jarvis", threshold=0.25,
            )
            assert det.detect([0] * 1280) is True

    def test_close_is_safe(self):
        """openWakeWord model has no explicit close — wrapper must no-op cleanly."""
        from services.voice import WakeWordDetector
        fake_oww = MagicMock()
        fake_oww.Model = MagicMock(return_value=MagicMock())
        with patch.dict(os.environ, {}, clear=True), \
             patch("services.voice.openwakeword", fake_oww):
            det = WakeWordDetector(backend="openwakeword", keyword="hey_jarvis")
            det.close()  # should not raise
