"""
Tests for POST /voice/speak (R16) — text-to-speech endpoint.

Contract:
  POST /voice/speak
  Body: {"text": "..."}
  Response: 200 + audio bytes (Content-Type: audio/mpeg or audio/aiff)
  500 when TTS fails
"""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend/api"))
from main import app

client = TestClient(app)


class TestVoiceSpeakEndpoint:
    def test_exists(self):
        """POST /voice/speak must not 405."""
        fake_pipeline = AsyncMock()
        fake_pipeline.speak = AsyncMock(return_value=b"audio")
        with patch("main.VoicePipeline", return_value=fake_pipeline):
            resp = client.post("/voice/speak", json={"text": "hi"})
        assert resp.status_code != 405

    def test_returns_200_on_success(self):
        fake_pipeline = AsyncMock()
        fake_pipeline.speak = AsyncMock(return_value=b"audiobytes")
        with patch("main.VoicePipeline", return_value=fake_pipeline):
            resp = client.post("/voice/speak", json={"text": "hello"})
        assert resp.status_code == 200

    def test_returns_audio_bytes(self):
        fake_pipeline = AsyncMock()
        fake_pipeline.speak = AsyncMock(return_value=b"MP3DATA")
        with patch("main.VoicePipeline", return_value=fake_pipeline):
            resp = client.post("/voice/speak", json={"text": "hello"})
        assert resp.content == b"MP3DATA"

    def test_passes_text_to_pipeline(self):
        fake_pipeline = AsyncMock()
        fake_pipeline.speak = AsyncMock(return_value=b"x")
        with patch("main.VoicePipeline", return_value=fake_pipeline):
            client.post("/voice/speak", json={"text": "Deploy complete"})
        fake_pipeline.speak.assert_called_once_with("Deploy complete")

    def test_returns_500_on_tts_failure(self):
        fake_pipeline = AsyncMock()
        fake_pipeline.speak = AsyncMock(side_effect=RuntimeError("TTS down"))
        with patch("main.VoicePipeline", return_value=fake_pipeline):
            resp = client.post("/voice/speak", json={"text": "hi"})
        assert resp.status_code == 500

    def test_empty_text_returns_400(self):
        resp = client.post("/voice/speak", json={"text": ""})
        assert resp.status_code in (400, 422)
