"""
Tests for device field on POST /command.

The /command endpoint must:
  - Accept an optional "device" field in the request body
  - Pass the device value into the agent context
  - Work normally when device is omitted
"""

from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend/api"))
from main import app

client = TestClient(app)


def _mock_agent_output(text: str = "CRUZ online") -> dict:
    return {
        "success": True,
        "result": text,
        "agent": "CRUZ",
        "duration_ms": 50,
        "tokens_used": 10,
        "error": None,
        "requires_approval": False,
        "approval_prompt": None,
    }


def _mock_cruz_agent(output=None):
    agent = MagicMock()
    agent.process = AsyncMock(return_value=output or _mock_agent_output())
    return agent


class TestCommandDeviceField:
    def test_command_accepts_device_field(self):
        """POST /command with device=ipad must return 200."""
        with patch("main.CruzAgent", return_value=_mock_cruz_agent()):
            resp = client.post("/command", json={
                "command": "hello",
                "device": "ipad",
            })
        assert resp.status_code == 200

    def test_command_works_without_device(self):
        """device is optional — omitting it must still return 200."""
        with patch("main.CruzAgent", return_value=_mock_cruz_agent()):
            resp = client.post("/command", json={"command": "hello"})
        assert resp.status_code == 200

    def test_device_passed_in_agent_context(self):
        """device value must appear in the AgentInput context passed to CruzAgent."""
        mock_agent = _mock_cruz_agent()
        with patch("main.CruzAgent", return_value=mock_agent):
            client.post("/command", json={"command": "hello", "device": "phone"})
        call_input = mock_agent.process.call_args[0][0]
        assert call_input["context"].get("device") == "phone"

    def test_device_none_in_context_when_not_provided(self):
        """When device omitted, context["device"] should be None or absent."""
        mock_agent = _mock_cruz_agent()
        with patch("main.CruzAgent", return_value=mock_agent):
            client.post("/command", json={"command": "hello"})
        call_input = mock_agent.process.call_args[0][0]
        # device should be None or not present when not sent
        assert call_input["context"].get("device") is None

    def test_device_values_accepted(self):
        """All expected device strings are accepted without validation error."""
        for device in ("phone", "ipad", "thinkpad", "mac_mini", "web"):
            with patch("main.CruzAgent", return_value=_mock_cruz_agent()):
                resp = client.post("/command", json={"command": "hi", "device": device})
            assert resp.status_code == 200, f"Rejected device: {device}"
