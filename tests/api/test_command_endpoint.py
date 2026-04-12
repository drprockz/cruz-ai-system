"""
Tests for POST /command endpoint.

The endpoint receives a user command, runs it through CruzAgent,
and returns either:
  - A plain JSON response   (when requires_approval is False)
  - An SSE stream           (when the client sends Accept: text/event-stream)
  - A 200 with approval payload (when the agent requires human approval)

RED phase — must fail until the endpoint is wired in main.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from agents.base_agent import AgentOutput


# Import the app — conftest.py sets up env vars before this
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend/api"))
from main import app


def _make_agent_output(
    success: bool = True,
    result: str = "Here is the answer.",
    requires_approval: bool = False,
    approval_prompt: str | None = None,
    tokens_used: int = 150,
) -> AgentOutput:
    return AgentOutput(
        success=success,
        result=result,
        agent="CRUZ",
        duration_ms=200,
        tokens_used=tokens_used,
        error=None if success else "Something went wrong",
        requires_approval=requires_approval,
        approval_prompt=approval_prompt,
    )


class TestCommandEndpointExists:
    def test_post_command_returns_not_405(self):
        """POST /command must exist — 405 would mean GET-only."""
        client = TestClient(app)
        resp = client.post("/command", json={"command": "hello"})
        assert resp.status_code != 405

    def test_post_command_rejects_missing_body(self):
        """Missing command field → 422 Unprocessable Entity."""
        client = TestClient(app)
        resp = client.post("/command", json={})
        assert resp.status_code == 422

    def test_post_command_rejects_empty_command(self):
        """Empty string command → 422."""
        client = TestClient(app)
        resp = client.post("/command", json={"command": ""})
        assert resp.status_code == 422


class TestCommandEndpointResponse:
    def test_successful_response_has_result(self):
        mock_output = _make_agent_output(result="The answer is 42.")
        client = TestClient(app)

        with patch("main.CruzAgent") as MockCruz:
            mock_instance = AsyncMock()
            mock_instance.process = AsyncMock(return_value=mock_output)
            MockCruz.return_value = mock_instance

            resp = client.post("/command", json={"command": "what is 6 * 7?"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] == "The answer is 42."

    def test_successful_response_has_success_true(self):
        mock_output = _make_agent_output()
        client = TestClient(app)

        with patch("main.CruzAgent") as MockCruz:
            mock_instance = AsyncMock()
            mock_instance.process = AsyncMock(return_value=mock_output)
            MockCruz.return_value = mock_instance

            resp = client.post("/command", json={"command": "hello"})

        assert resp.json()["success"] is True

    def test_response_includes_tokens_used(self):
        mock_output = _make_agent_output(tokens_used=300)
        client = TestClient(app)

        with patch("main.CruzAgent") as MockCruz:
            mock_instance = AsyncMock()
            mock_instance.process = AsyncMock(return_value=mock_output)
            MockCruz.return_value = mock_instance

            resp = client.post("/command", json={"command": "hello"})

        assert resp.json()["tokens_used"] == 300

    def test_response_includes_agent_name(self):
        mock_output = _make_agent_output()
        client = TestClient(app)

        with patch("main.CruzAgent") as MockCruz:
            mock_instance = AsyncMock()
            mock_instance.process = AsyncMock(return_value=mock_output)
            MockCruz.return_value = mock_instance

            resp = client.post("/command", json={"command": "hello"})

        assert resp.json()["agent"] == "CRUZ"

    def test_agent_error_returns_500(self):
        mock_output = _make_agent_output(success=False, result=None)
        client = TestClient(app)

        with patch("main.CruzAgent") as MockCruz:
            mock_instance = AsyncMock()
            mock_instance.process = AsyncMock(return_value=mock_output)
            MockCruz.return_value = mock_instance

            resp = client.post("/command", json={"command": "do something"})

        assert resp.status_code == 500


class TestCommandEndpointApprovalGate:
    def test_approval_required_returns_202(self):
        mock_output = _make_agent_output(
            requires_approval=True,
            approval_prompt="Send this email to the client?",
            result="Draft: Dear Client...",
        )
        client = TestClient(app)

        with patch("main.CruzAgent") as MockCruz:
            mock_instance = AsyncMock()
            mock_instance.process = AsyncMock(return_value=mock_output)
            MockCruz.return_value = mock_instance

            resp = client.post("/command", json={"command": "send email to client"})

        assert resp.status_code == 202

    def test_approval_response_has_approval_prompt(self):
        mock_output = _make_agent_output(
            requires_approval=True,
            approval_prompt="Deploy to production?",
            result="Deploy script ready.",
        )
        client = TestClient(app)

        with patch("main.CruzAgent") as MockCruz:
            mock_instance = AsyncMock()
            mock_instance.process = AsyncMock(return_value=mock_output)
            MockCruz.return_value = mock_instance

            resp = client.post("/command", json={"command": "deploy"})

        data = resp.json()
        assert data["approval_prompt"] == "Deploy to production?"
        assert data["requires_approval"] is True


class TestCommandEndpointTracing:
    def test_request_accepts_optional_trace_id(self):
        mock_output = _make_agent_output()
        client = TestClient(app)

        with patch("main.CruzAgent") as MockCruz:
            mock_instance = AsyncMock()
            mock_instance.process = AsyncMock(return_value=mock_output)
            MockCruz.return_value = mock_instance

            resp = client.post(
                "/command",
                json={"command": "hello", "trace_id": "my-trace-001"},
            )

        assert resp.status_code == 200

    def test_trace_id_auto_generated_if_missing(self):
        mock_output = _make_agent_output()
        client = TestClient(app)

        captured_input = {}

        async def capture(inp):
            captured_input.update(inp)
            return mock_output

        with patch("main.CruzAgent") as MockCruz:
            mock_instance = AsyncMock()
            mock_instance.process = capture
            MockCruz.return_value = mock_instance

            resp = client.post("/command", json={"command": "hello"})

        assert resp.status_code == 200
        assert "trace_id" in captured_input
        assert len(captured_input["trace_id"]) > 0

    def test_response_includes_trace_id(self):
        mock_output = _make_agent_output()
        client = TestClient(app)

        with patch("main.CruzAgent") as MockCruz:
            mock_instance = AsyncMock()
            mock_instance.process = AsyncMock(return_value=mock_output)
            MockCruz.return_value = mock_instance

            resp = client.post("/command", json={"command": "hello"})

        assert "trace_id" in resp.json()
