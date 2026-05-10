"""
Tests for workers/voice_daemon.py.

All external I/O mocked:
  - pyaudio (mic stream)
  - WakeWordDetector (force wake on first detect() call)
  - SileroVAD (immediate silence so capture finishes in minimum frames)
  - VoicePipeline.transcribe / speak
  - httpx.AsyncClient (CRUZ API)
  - sounddevice / soundfile (playback)
  - AlertService (degraded-mode notification)
"""

from __future__ import annotations

import asyncio
import io
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ── _pcm_to_wav ────────────────────────────────────────────────────────────


def test_pcm_to_wav_produces_valid_riff_header():
    from workers.voice_daemon import CHANNELS, SAMPLE_RATE, SAMPLE_WIDTH, _pcm_to_wav

    pcm = b"\x00\x00" * 512
    wav = _pcm_to_wav(pcm)

    with wave.open(io.BytesIO(wav), "rb") as wf:
        assert wf.getnchannels() == CHANNELS
        assert wf.getsampwidth() == SAMPLE_WIDTH
        assert wf.getframerate() == SAMPLE_RATE
        assert wf.getnframes() == 512


def test_pcm_to_wav_empty_input():
    from workers.voice_daemon import _pcm_to_wav

    wav = _pcm_to_wav(b"")
    # Should still produce a valid (zero-frame) WAV
    with wave.open(io.BytesIO(wav), "rb") as wf:
        assert wf.getnframes() == 0


# ── _post_to_cruz ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_to_cruz_success():
    from workers.voice_daemon import _post_to_cruz

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"success": True, "result": "Done."}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("workers.voice_daemon.httpx.AsyncClient", return_value=mock_client):
        result = await _post_to_cruz("deploy AMA", "conv-1", "trace-1")

    assert result == "Done."


@pytest.mark.asyncio
async def test_post_to_cruz_whitespace_result_returns_none():
    from workers.voice_daemon import _post_to_cruz

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"success": True, "result": "   "}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("workers.voice_daemon.httpx.AsyncClient", return_value=mock_client):
        result = await _post_to_cruz("hi", "conv-1", "trace-1")

    assert result is None


@pytest.mark.asyncio
async def test_post_to_cruz_non_string_result_returns_none():
    from workers.voice_daemon import _post_to_cruz

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"success": True, "result": {"nested": "dict"}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("workers.voice_daemon.httpx.AsyncClient", return_value=mock_client):
        result = await _post_to_cruz("hi", "conv-1", "trace-1")

    assert result is None


@pytest.mark.asyncio
async def test_post_to_cruz_connect_error_triggers_alert_and_returns_none():
    import httpx

    from workers.voice_daemon import _post_to_cruz

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_alert = MagicMock()
    mock_alert.notify = AsyncMock()

    with (
        patch("workers.voice_daemon.httpx.AsyncClient", return_value=mock_client),
        patch("workers.voice_daemon.get_alert_service", return_value=mock_alert),
    ):
        result = await _post_to_cruz("hello", "conv-1", "trace-1")

    assert result is None
    mock_alert.notify.assert_awaited_once()
    call_args = mock_alert.notify.call_args.args
    assert call_args[0] == "warning"


@pytest.mark.asyncio
async def test_post_to_cruz_generic_error_returns_none_no_alert():
    from workers.voice_daemon import _post_to_cruz

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=RuntimeError("unexpected"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_alert = MagicMock()
    mock_alert.notify = AsyncMock()

    with (
        patch("workers.voice_daemon.httpx.AsyncClient", return_value=mock_client),
        patch("workers.voice_daemon.get_alert_service", return_value=mock_alert),
    ):
        result = await _post_to_cruz("hello", "conv-1", "trace-1")

    assert result is None
    mock_alert.notify.assert_not_awaited()


# ── _play_audio ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_play_audio_sounddevice_missing_is_nonfatal():
    from workers.voice_daemon import _play_audio

    with (
        patch("workers.voice_daemon.sd", None),
        patch("workers.voice_daemon.sf", None),
    ):
        await _play_audio(b"fake-audio")  # must not raise


@pytest.mark.asyncio
async def test_play_audio_calls_sounddevice_play():
    from workers.voice_daemon import _play_audio

    mock_sf = MagicMock()
    mock_sf.read.return_value = (np.zeros(100, dtype=np.float32), 22050)
    mock_sd = MagicMock()

    with (
        patch("workers.voice_daemon.sf", mock_sf),
        patch("workers.voice_daemon.sd", mock_sd),
    ):
        await _play_audio(b"audio-bytes")

    mock_sf.read.assert_called_once()
    mock_sd.play.assert_called_once()
    mock_sd.wait.assert_called_once()


# ── _sync_listen_for_wake ──────────────────────────────────────────────────


def test_sync_listen_returns_after_first_detect():
    from workers.voice_daemon import _sync_listen_for_wake

    mock_stream = MagicMock()
    mock_stream.read.return_value = np.zeros(1280, dtype=np.int16).tobytes()

    mock_detector = MagicMock()
    mock_detector.frame_length = 1280
    mock_detector.detect.side_effect = [False, False, True]

    _sync_listen_for_wake(mock_stream, mock_detector)

    assert mock_stream.read.call_count == 3
    assert mock_detector.detect.call_count == 3


def test_sync_listen_calls_read_with_correct_frame_len():
    from workers.voice_daemon import _sync_listen_for_wake

    mock_stream = MagicMock()
    mock_stream.read.return_value = np.zeros(512, dtype=np.int16).tobytes()

    mock_detector = MagicMock()
    mock_detector.frame_length = 512
    mock_detector.detect.return_value = True

    _sync_listen_for_wake(mock_stream, mock_detector)

    mock_stream.read.assert_called_with(512, exception_on_overflow=False)


# ── _sync_capture_speech ───────────────────────────────────────────────────


def test_sync_capture_stops_on_silence_threshold():
    from workers.voice_daemon import SAMPLE_RATE, SILENCE_SECONDS, _sync_capture_speech

    frame_len = 512
    silence_threshold = int(SILENCE_SECONDS * SAMPLE_RATE / frame_len)

    mock_stream = MagicMock()
    mock_stream.read.return_value = np.zeros(frame_len, dtype=np.int16).tobytes()

    mock_vad = MagicMock()
    mock_vad.is_speech.return_value = False  # all silence

    result = _sync_capture_speech(mock_stream, mock_vad, frame_len)

    assert mock_stream.read.call_count == silence_threshold
    assert len(result) == silence_threshold * frame_len * 2  # int16 = 2 bytes


def test_sync_capture_resets_silence_counter_on_speech():
    from workers.voice_daemon import SAMPLE_RATE, SILENCE_SECONDS, _sync_capture_speech

    frame_len = 512
    silence_threshold = int(SILENCE_SECONDS * SAMPLE_RATE / frame_len)

    mock_stream = MagicMock()
    mock_stream.read.return_value = np.zeros(frame_len, dtype=np.int16).tobytes()

    mock_vad = MagicMock()
    # silence * (threshold-1), then speech, then silence * threshold → stops
    mock_vad.is_speech.side_effect = (
        [False] * (silence_threshold - 1) + [True] + [False] * silence_threshold
    )

    result = _sync_capture_speech(mock_stream, mock_vad, frame_len)

    total_expected = (silence_threshold - 1) + 1 + silence_threshold
    assert mock_stream.read.call_count == total_expected
    assert len(result) == total_expected * frame_len * 2


def test_sync_capture_max_duration_bounds():
    from workers.voice_daemon import (
        MAX_CAPTURE_SECONDS,
        SAMPLE_RATE,
        _sync_capture_speech,
    )

    frame_len = 512
    max_frames = int(MAX_CAPTURE_SECONDS * SAMPLE_RATE / frame_len)

    mock_stream = MagicMock()
    mock_stream.read.return_value = np.zeros(frame_len, dtype=np.int16).tobytes()

    mock_vad = MagicMock()
    mock_vad.is_speech.return_value = True  # continuous speech → hits max

    _sync_capture_speech(mock_stream, mock_vad, frame_len)

    assert mock_stream.read.call_count == max_frames


# ── run() integration ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_full_loop_one_turn():
    """Wake word → transcribe → POST → speak, then stop on 2nd wake-listen."""
    from workers.voice_daemon import run

    frame_len = 1280
    silence_bytes = np.zeros(frame_len, dtype=np.int16).tobytes()

    # ── PyAudio mock ──────────────────────────────────────────────────────
    mock_stream = MagicMock()
    mock_stream.read.return_value = silence_bytes

    mock_pa = MagicMock()
    mock_pa.open.return_value = mock_stream
    mock_pa.get_format_from_width.return_value = 8

    mock_pa_mod = MagicMock()
    mock_pa_mod.PyAudio.return_value = mock_pa

    # ── Detector: fires on very first detect() call ───────────────────────
    mock_detector = MagicMock()
    mock_detector.frame_length = frame_len
    mock_detector.backend = "openwakeword"
    mock_detector.detect.return_value = True  # always wake

    # ── VAD: immediate silence → fast capture ─────────────────────────────
    mock_vad = MagicMock()
    mock_vad.is_speech.return_value = False

    # ── Pipeline ──────────────────────────────────────────────────────────
    mock_pipeline = MagicMock()
    mock_pipeline.transcribe = AsyncMock(return_value="deploy AMA site")
    mock_pipeline.speak = AsyncMock(return_value=b"mp3-audio")

    # ── Mac controller (cue notification) ────────────────────────────────
    mock_mac = MagicMock()
    mock_mac.notify = AsyncMock()

    # ── CRUZ API ──────────────────────────────────────────────────────────
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"success": True, "result": "Deploying now."}

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    # ── soundfile / sounddevice ───────────────────────────────────────────
    mock_sf = MagicMock()
    mock_sf.read.return_value = (np.zeros(100, dtype=np.float32), 22050)
    mock_sd = MagicMock()

    # ── Stop after one turn: raise CancelledError on 3rd to_thread call ──
    _call_count = 0
    _original_to_thread = asyncio.to_thread

    async def _bounded_to_thread(fn, *args, **kwargs):
        nonlocal _call_count
        _call_count += 1
        if _call_count > 2:
            raise asyncio.CancelledError("test stop after one turn")
        return fn(*args, **kwargs)

    with (
        patch("workers.voice_daemon.pyaudio", mock_pa_mod),
        patch("workers.voice_daemon.WakeWordDetector", return_value=mock_detector),
        patch("workers.voice_daemon.VoicePipeline", return_value=mock_pipeline),
        patch("workers.voice_daemon.SileroVAD", return_value=mock_vad),
        patch("workers.voice_daemon.get_mac_controller_service", return_value=mock_mac),
        patch("workers.voice_daemon.get_alert_service"),
        patch("workers.voice_daemon.httpx.AsyncClient", return_value=mock_http),
        patch("workers.voice_daemon.sf", mock_sf),
        patch("workers.voice_daemon.sd", mock_sd),
        patch("asyncio.to_thread", side_effect=_bounded_to_thread),
    ):
        try:
            await run()
        except asyncio.CancelledError:
            pass

    mock_pipeline.transcribe.assert_awaited_once()
    mock_http.post.assert_awaited_once()
    mock_pipeline.speak.assert_awaited_once()
    mock_mac.notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_skips_post_when_transcription_empty():
    """Empty transcription → no /command POST, no speak."""
    from workers.voice_daemon import run

    frame_len = 1280
    silence_bytes = np.zeros(frame_len, dtype=np.int16).tobytes()

    mock_stream = MagicMock()
    mock_stream.read.return_value = silence_bytes

    mock_pa = MagicMock()
    mock_pa.open.return_value = mock_stream
    mock_pa.get_format_from_width.return_value = 8
    mock_pa_mod = MagicMock()
    mock_pa_mod.PyAudio.return_value = mock_pa

    mock_detector = MagicMock()
    mock_detector.frame_length = frame_len
    mock_detector.backend = "openwakeword"
    mock_detector.detect.return_value = True

    mock_vad = MagicMock()
    mock_vad.is_speech.return_value = False

    mock_pipeline = MagicMock()
    mock_pipeline.transcribe = AsyncMock(return_value="")  # empty → skip
    mock_pipeline.speak = AsyncMock(return_value=b"audio")

    mock_mac = MagicMock()
    mock_mac.notify = AsyncMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    _call_count = 0

    async def _bounded_to_thread(fn, *args, **kwargs):
        nonlocal _call_count
        _call_count += 1
        if _call_count > 2:
            raise asyncio.CancelledError
        return fn(*args, **kwargs)

    with (
        patch("workers.voice_daemon.pyaudio", mock_pa_mod),
        patch("workers.voice_daemon.WakeWordDetector", return_value=mock_detector),
        patch("workers.voice_daemon.VoicePipeline", return_value=mock_pipeline),
        patch("workers.voice_daemon.SileroVAD", return_value=mock_vad),
        patch("workers.voice_daemon.get_mac_controller_service", return_value=mock_mac),
        patch("workers.voice_daemon.get_alert_service"),
        patch("workers.voice_daemon.httpx.AsyncClient", return_value=mock_http),
        patch("workers.voice_daemon.sf", MagicMock()),
        patch("workers.voice_daemon.sd", MagicMock()),
        patch("asyncio.to_thread", side_effect=_bounded_to_thread),
    ):
        try:
            await run()
        except asyncio.CancelledError:
            pass

    mock_pipeline.transcribe.assert_awaited_once()
    mock_http.post.assert_not_awaited()
    mock_pipeline.speak.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_missing_pyaudio_raises():
    from workers.voice_daemon import run

    with (
        patch("workers.voice_daemon.pyaudio", None),
        patch("workers.voice_daemon.WakeWordDetector"),
        patch("workers.voice_daemon.VoicePipeline"),
        patch("workers.voice_daemon.SileroVAD"),
        patch("workers.voice_daemon.get_mac_controller_service"),
        patch("workers.voice_daemon.get_alert_service"),
    ):
        with pytest.raises(RuntimeError, match="pyaudio"):
            await run()
