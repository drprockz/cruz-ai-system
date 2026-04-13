"""
Tests for POST /voice/transcribe endpoint.

Contract:
  - Accepts multipart audio file upload (field name: "file")
  - Calls VoicePipeline.transcribe(audio_bytes) -> str
  - Returns 200 + {"text": "<transcription>"} on success
  - Returns 400 if no file uploaded
  - Returns 200 + {"text": ""} if transcription is empty
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend/api"))
from main import app


def _make_audio_upload(content: bytes = b"fake wav audio", filename: str = "audio.wav"):
    return ("file", (filename, io.BytesIO(content), "audio/wav"))


class TestVoiceTranscribeEndpointExists:
    def test_post_voice_transcribe_does_not_return_404(self):
        client = TestClient(app)
        resp = client.post("/voice/transcribe", files=[_make_audio_upload()])
        assert resp.status_code != 404

    def test_post_voice_transcribe_does_not_return_405(self):
        client = TestClient(app)
        resp = client.post("/voice/transcribe", files=[_make_audio_upload()])
        assert resp.status_code != 405


class TestVoiceTranscribeEndpointSuccess:
    def test_returns_200_with_audio_file(self):
        with patch("main.VoicePipeline") as MockPipeline:
            mock_instance = MockPipeline.return_value
            mock_instance.transcribe = AsyncMock(return_value="deploy the AMA website")
            client = TestClient(app)
            resp = client.post("/voice/transcribe", files=[_make_audio_upload()])
        assert resp.status_code == 200

    def test_returns_text_field_in_response(self):
        with patch("main.VoicePipeline") as MockPipeline:
            mock_instance = MockPipeline.return_value
            mock_instance.transcribe = AsyncMock(return_value="hello cruz")
            client = TestClient(app)
            resp = client.post("/voice/transcribe", files=[_make_audio_upload()])
        assert "text" in resp.json()

    def test_returns_transcribed_text(self):
        with patch("main.VoicePipeline") as MockPipeline:
            mock_instance = MockPipeline.return_value
            mock_instance.transcribe = AsyncMock(return_value="forge build a contact form")
            client = TestClient(app)
            resp = client.post("/voice/transcribe", files=[_make_audio_upload()])
        assert resp.json()["text"] == "forge build a contact form"

    def test_returns_empty_text_when_transcription_empty(self):
        with patch("main.VoicePipeline") as MockPipeline:
            mock_instance = MockPipeline.return_value
            mock_instance.transcribe = AsyncMock(return_value="")
            client = TestClient(app)
            resp = client.post("/voice/transcribe", files=[_make_audio_upload()])
        assert resp.status_code == 200
        assert resp.json()["text"] == ""

    def test_audio_bytes_passed_to_pipeline(self):
        """The exact audio bytes from the upload must be passed to transcribe()."""
        audio_content = b"specific audio content bytes"
        captured = {}

        async def capture_transcribe(audio_bytes):
            captured["audio"] = audio_bytes
            return "captured"

        with patch("main.VoicePipeline") as MockPipeline:
            mock_instance = MockPipeline.return_value
            mock_instance.transcribe = capture_transcribe
            client = TestClient(app)
            client.post("/voice/transcribe", files=[_make_audio_upload(content=audio_content)])

        assert captured.get("audio") == audio_content


class TestVoiceTranscribeEndpointValidation:
    def test_returns_400_when_no_file_provided(self):
        client = TestClient(app)
        resp = client.post("/voice/transcribe")
        assert resp.status_code == 422  # FastAPI validation error for missing required field
