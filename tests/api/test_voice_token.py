"""Tests for POST /voice/token — LiveKit JWT minting endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_voice_token_returns_jwt(monkeypatch):
    monkeypatch.setenv("LIVEKIT_API_KEY", "key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "s" * 32)
    monkeypatch.setenv("LIVEKIT_WS_URL", "wss://x.livekit.cloud")

    from backend.api.main import app
    client = TestClient(app)
    r = client.post("/voice/token", json={"device_id": "mac-mini"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["room"].startswith("cruz-")
    assert j["ws_url"] == "wss://x.livekit.cloud"
    assert len(j["token"].split(".")) == 3  # JWT
    assert "conversation_id" in j


def test_voice_token_accepts_existing_conversation_id(monkeypatch):
    monkeypatch.setenv("LIVEKIT_API_KEY", "key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "s" * 32)
    monkeypatch.setenv("LIVEKIT_WS_URL", "wss://x.livekit.cloud")
    from backend.api.main import app
    client = TestClient(app)
    r = client.post(
        "/voice/token",
        json={"device_id": "phone", "conversation_id": "abc-123"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["conversation_id"] == "abc-123"
    assert "abc-123" in j["room"]
    assert j["room"] == "cruz-abc-123-phone"


def test_voice_token_500s_when_livekit_not_configured(monkeypatch):
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    from backend.api.main import app
    client = TestClient(app)
    r = client.post("/voice/token", json={"device_id": "mac-mini"})
    assert r.status_code == 500
