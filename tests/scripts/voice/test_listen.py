"""
Tests for scripts/voice/listen.py — the "Hey CRUZ" always-listening daemon.

The script pieces together:
  WakeWordDetector  → capture audio  → POST /voice/transcribe
                   → POST /command   → POST /voice/speak → speaker playback

We test each function in isolation with everything outside mocked (no
microphone, no speakers, no HTTP). The `run_one()` orchestrator is the
integration seam that a human runs interactively.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SCRIPT_DIR = os.path.join(os.path.dirname(__file__), "../../../scripts/voice")
sys.path.insert(0, os.path.abspath(_SCRIPT_DIR))


def _mock_httpx_client_with_responses(*responses):
    """Build a mock httpx.AsyncClient whose .post returns given responses in order."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(side_effect=list(responses))
    return client


def _json_response(payload: dict, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.json = MagicMock(return_value=payload)
    resp.content = b""
    return resp


def _bytes_response(content: bytes, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.content = content
    resp.json = MagicMock(return_value={})
    return resp


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class TestListenInterface:
    def test_module_importable(self):
        import listen  # noqa: F401

    def test_key_functions_exist(self):
        import listen
        assert callable(listen.transcribe)
        assert callable(listen.command)
        assert callable(listen.synthesize_and_play)
        assert callable(listen.run_one)


# ---------------------------------------------------------------------------
# transcribe() → POST /voice/transcribe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTranscribe:
    async def test_posts_audio_to_transcribe_endpoint(self):
        import listen
        resp = _json_response({"text": "hello cruz"})
        client = _mock_httpx_client_with_responses(resp)
        with patch("listen.httpx.AsyncClient", return_value=client):
            text = await listen.transcribe("http://localhost:3000", b"WAVDATA")
        assert text == "hello cruz"
        url = client.post.call_args[0][0]
        assert "/voice/transcribe" in url

    async def test_returns_empty_string_on_non_2xx(self):
        import listen
        resp = _json_response({"text": ""}, status=500)
        client = _mock_httpx_client_with_responses(resp)
        with patch("listen.httpx.AsyncClient", return_value=client):
            text = await listen.transcribe("http://localhost:3000", b"")
        assert text == ""


# ---------------------------------------------------------------------------
# command() → POST /command
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCommand:
    async def test_posts_command_with_text_and_device(self):
        import listen
        resp = _json_response({"success": True, "result": "CRUZ online",
                               "agent": "CRUZ"})
        client = _mock_httpx_client_with_responses(resp)
        with patch("listen.httpx.AsyncClient", return_value=client):
            reply = await listen.command(
                host="http://localhost:3000",
                text="what's up",
                conversation_id="conv-1",
                device="mac_mini",
            )
        body = client.post.call_args.kwargs["json"]
        assert body["command"] == "what's up"
        assert body["device"] == "mac_mini"
        assert body["conversation_id"] == "conv-1"
        assert reply == "CRUZ online"

    async def test_handles_approval_required_status_202(self):
        """ECHO-style draft responses come back as 202 with approval_prompt."""
        import listen
        resp = _json_response({
            "success": True,
            "result": {"subject": "Hi", "body": "..."},
            "approval_prompt": "Send this email?",
            "agent": "CRUZ",
        }, status=202)
        client = _mock_httpx_client_with_responses(resp)
        with patch("listen.httpx.AsyncClient", return_value=client):
            reply = await listen.command(
                host="http://localhost:3000", text="draft email",
            )
        # Daemon should surface the approval prompt as the spoken reply
        assert "Send this email" in reply or "approval" in reply.lower()


# ---------------------------------------------------------------------------
# synthesize_and_play() → POST /voice/speak + sounddevice.play
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSynthesizeAndPlay:
    async def test_posts_to_speak_and_plays_bytes(self):
        import listen
        resp = _bytes_response(b"\x00\x01\x02")
        client = _mock_httpx_client_with_responses(resp)
        with patch("listen.httpx.AsyncClient", return_value=client), \
             patch("listen._play_audio_bytes") as play_mock:
            await listen.synthesize_and_play(
                host="http://localhost:3000", text="hello",
            )
        client.post.assert_called_once()
        url = client.post.call_args[0][0]
        assert "/voice/speak" in url
        play_mock.assert_called_once()
        played_bytes = play_mock.call_args[0][0]
        assert played_bytes == b"\x00\x01\x02"

    async def test_skips_playback_when_tts_fails(self):
        import listen
        resp = _bytes_response(b"", status=500)
        client = _mock_httpx_client_with_responses(resp)
        with patch("listen.httpx.AsyncClient", return_value=client), \
             patch("listen._play_audio_bytes") as play_mock:
            await listen.synthesize_and_play(
                host="http://localhost:3000", text="hello",
            )
        play_mock.assert_not_called()


# ---------------------------------------------------------------------------
# run_one() — full wake → capture → transcribe → command → speak loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRunOneOrchestration:
    async def test_full_flow_push_to_talk(self):
        """push-to-talk mode skips wake detection, just captures + processes."""
        import listen
        with patch("builtins.input", return_value=""), \
             patch("listen._record_ptt", return_value=b"WAV"), \
             patch("listen.transcribe", new_callable=AsyncMock) as mock_trans, \
             patch("listen.command", new_callable=AsyncMock) as mock_cmd, \
             patch("listen.synthesize_and_play", new_callable=AsyncMock) as mock_speak:
            mock_trans.return_value = "hello cruz"
            mock_cmd.return_value = "How can I help?"
            await listen.run_one(
                host="http://localhost:3000",
                mode="push-to-talk",
                conversation_id="c-1",
            )
        mock_trans.assert_awaited_once()
        assert mock_trans.call_args.args[1] == b"WAV"
        mock_cmd.assert_awaited_once()
        assert mock_cmd.call_args.kwargs["text"] == "hello cruz"
        mock_speak.assert_awaited_once()
        assert mock_speak.call_args.kwargs["text"] == "How can I help?"

    async def test_empty_transcription_skips_command(self):
        """If Whisper returns empty text, don't waste a /command call."""
        import listen
        with patch("builtins.input", return_value=""), \
             patch("listen._record_ptt", return_value=b"WAV"), \
             patch("listen.transcribe", new_callable=AsyncMock) as mock_trans, \
             patch("listen.command", new_callable=AsyncMock) as mock_cmd, \
             patch("listen.synthesize_and_play", new_callable=AsyncMock) as mock_speak:
            mock_trans.return_value = ""
            await listen.run_one(host="http://localhost:3000", mode="push-to-talk")
        mock_cmd.assert_not_called()
        mock_speak.assert_not_called()

    async def test_wake_mode_uses_detector_and_vad_capture(self):
        """Wake-word mode must use VAD capture, not a fixed 6s window."""
        import listen
        fake_detector = MagicMock()
        with patch("listen._wait_for_wake", new_callable=AsyncMock) as mock_wake, \
             patch("listen._record_with_vad", return_value=b"WAV") as mock_vad, \
             patch("listen.transcribe", new_callable=AsyncMock) as mock_trans, \
             patch("listen.command", new_callable=AsyncMock) as mock_cmd, \
             patch("listen.synthesize_and_play", new_callable=AsyncMock) as mock_speak:
            mock_trans.return_value = "what time is it"
            mock_cmd.return_value = "It's 3pm."
            await listen.run_one(
                host="http://localhost:3000",
                mode="wake-word",
                detector=fake_detector,
                conversation_id="c-1",
            )
        mock_wake.assert_awaited_once()
        mock_vad.assert_called_once()  # VAD, NOT fixed-duration
        mock_trans.assert_awaited_once()
        mock_cmd.assert_awaited_once()
        mock_speak.assert_awaited_once()
