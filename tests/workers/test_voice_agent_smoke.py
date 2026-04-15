"""Smoke tests for the LiveKit voice agent worker.

These tests do NOT import livekit.rtc or livekit.agents; they only verify
the pure-Python config loading and helper logic that has no external deps.
"""
from __future__ import annotations

from workers.voice_agent.worker import VoiceAgentConfig


def test_config_defaults_from_env(monkeypatch):
    monkeypatch.setenv("LIVEKIT_WS_URL", "wss://x")
    monkeypatch.setenv("LIVEKIT_API_KEY", "k")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "s" * 32)
    cfg = VoiceAgentConfig.from_env()
    assert cfg.ws_url == "wss://x"
    assert cfg.api_key == "k"
    assert cfg.api_secret == "s" * 32
