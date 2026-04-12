"""
Tests for SSE streaming on POST /command.

When the request body includes stream=True, the endpoint must:
  - Return Content-Type: text/event-stream
  - Emit one or more `data: {...}` lines in SSE format
  - Always include a final `done` event with conversation_id + trace_id
  - Emit `text` events carrying the agent's reply
  - Emit `approval_required` events when the agent sets requires_approval=True
  - Emit `error` events when the agent returns success=False
  - Never crash on empty / short responses

When stream=False (or omitted), the endpoint returns plain JSON as before
(regression guard — existing behaviour must not break).

RED phase — must fail before streaming is wired in.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from agents.base_agent import AgentOutput

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend/api"))
from main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_output(
    success: bool = True,
    result: str = "The answer is 42.",
    requires_approval: bool = False,
    approval_prompt: str | None = None,
) -> AgentOutput:
    return AgentOutput(
        success=success,
        result=result,
        agent="CRUZ",
        duration_ms=100,
        tokens_used=150,
        error=None if success else "Something went wrong",
        requires_approval=requires_approval,
        approval_prompt=approval_prompt,
    )


def _patch_cruz(output: AgentOutput):
    """Context manager: replace CruzAgent with a mock returning `output`."""
    mock_instance = AsyncMock()
    mock_instance.process = AsyncMock(return_value=output)

    patcher_cruz = patch("main.CruzAgent", return_value=mock_instance)
    return patcher_cruz


def _parse_sse(raw: str) -> list[dict]:
    """Parse raw SSE text into a list of decoded JSON event payloads."""
    events = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                events.append(json.loads(payload))
    return events


# ---------------------------------------------------------------------------
# Content-Type
# ---------------------------------------------------------------------------

class TestSSEContentType:
    def test_stream_true_returns_event_stream_content_type(self):
        """stream=True → Content-Type must be text/event-stream."""
        with _patch_cruz(_make_output()):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "hello", "stream": True})

        assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_stream_false_returns_json_content_type(self):
        """stream=False (default) must still return application/json."""
        with _patch_cruz(_make_output()):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "hello", "stream": False})

        assert "application/json" in resp.headers.get("content-type", "")

    def test_stream_omitted_returns_json_content_type(self):
        """Omitting stream field must default to JSON (backwards compat)."""
        with _patch_cruz(_make_output()):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "hello"})

        assert "application/json" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# SSE event format
# ---------------------------------------------------------------------------

class TestSSEEventFormat:
    def test_each_event_is_valid_json(self):
        """Every `data:` line in the SSE stream must be parseable JSON."""
        with _patch_cruz(_make_output(result="All good.")):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "hello", "stream": True})

        events = _parse_sse(resp.text)
        assert len(events) > 0, "Expected at least one SSE event"

    def test_each_event_has_type_field(self):
        """Every event payload must include a 'type' field."""
        with _patch_cruz(_make_output(result="test")):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "hello", "stream": True})

        for event in _parse_sse(resp.text):
            assert "type" in event, f"Event missing 'type': {event}"

    def test_sse_lines_start_with_data_colon(self):
        """Raw SSE lines carrying events must start with 'data:'."""
        with _patch_cruz(_make_output(result="answer")):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "hello", "stream": True})

        non_empty = [l for l in resp.text.splitlines() if l.strip()]
        data_lines = [l for l in non_empty if l.startswith("data:")]
        assert len(data_lines) > 0


# ---------------------------------------------------------------------------
# Text event
# ---------------------------------------------------------------------------

class TestSSETextEvent:
    def test_successful_response_emits_text_event(self):
        """A successful CruzAgent response must produce at least one 'text' event."""
        with _patch_cruz(_make_output(result="The answer is 42.")):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "what is 6*7?", "stream": True})

        types = [e["type"] for e in _parse_sse(resp.text)]
        assert "text" in types

    def test_text_event_contains_result(self):
        """The 'text' event's content field must carry the agent result."""
        with _patch_cruz(_make_output(result="unique-result-string-xyz")):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "anything", "stream": True})

        text_events = [e for e in _parse_sse(resp.text) if e.get("type") == "text"]
        combined = " ".join(e.get("content", "") for e in text_events)
        assert "unique-result-string-xyz" in combined


# ---------------------------------------------------------------------------
# Done event
# ---------------------------------------------------------------------------

class TestSSEDoneEvent:
    def test_stream_always_ends_with_done_event(self):
        """The last event in any SSE stream must have type='done'."""
        with _patch_cruz(_make_output()):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "hello", "stream": True})

        events = _parse_sse(resp.text)
        assert events, "No events received"
        assert events[-1]["type"] == "done"

    def test_done_event_includes_trace_id(self):
        """The done event must include trace_id for client-side logging."""
        with _patch_cruz(_make_output()):
            client = TestClient(app)
            resp = client.post(
                "/command",
                json={"command": "hello", "stream": True, "trace_id": "trace-sse-001"},
            )

        done = _parse_sse(resp.text)[-1]
        assert done["type"] == "done"
        assert "trace_id" in done

    def test_done_event_includes_conversation_id(self):
        """The done event must include conversation_id for cross-device pickup."""
        with _patch_cruz(_make_output()):
            client = TestClient(app)
            resp = client.post(
                "/command",
                json={"command": "hello", "stream": True, "conversation_id": "conv-sse-001"},
            )

        done = _parse_sse(resp.text)[-1]
        assert "conversation_id" in done


# ---------------------------------------------------------------------------
# Approval gate event
# ---------------------------------------------------------------------------

class TestSSEApprovalEvent:
    def test_approval_required_emits_approval_required_event(self):
        """When agent returns requires_approval=True, stream emits approval_required."""
        output = _make_output(
            requires_approval=True,
            approval_prompt="Send this email to client@x.com?",
            result="Draft ready.",
        )
        with _patch_cruz(output):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "send email", "stream": True})

        types = [e["type"] for e in _parse_sse(resp.text)]
        assert "approval_required" in types

    def test_approval_event_contains_prompt(self):
        """The approval_required event must include the approval_prompt text."""
        output = _make_output(
            requires_approval=True,
            approval_prompt="Deploy to production? (unique-approval-prompt-text)",
            result="Deploy ready.",
        )
        with _patch_cruz(output):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "deploy", "stream": True})

        approval_events = [
            e for e in _parse_sse(resp.text) if e.get("type") == "approval_required"
        ]
        assert approval_events, "No approval_required event found"
        combined = json.dumps(approval_events)
        assert "unique-approval-prompt-text" in combined


# ---------------------------------------------------------------------------
# Error event
# ---------------------------------------------------------------------------

class TestSSEErrorEvent:
    def test_agent_error_emits_error_event(self):
        """When agent returns success=False, stream emits an 'error' event."""
        output = _make_output(success=False, result=None)
        with _patch_cruz(output):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "bad task", "stream": True})

        types = [e["type"] for e in _parse_sse(resp.text)]
        assert "error" in types

    def test_error_event_followed_by_done(self):
        """Even on error the stream must end with a done event."""
        output = _make_output(success=False, result=None)
        with _patch_cruz(output):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "bad task", "stream": True})

        events = _parse_sse(resp.text)
        assert events[-1]["type"] == "done"


# ---------------------------------------------------------------------------
# Regression — non-streaming path unchanged
# ---------------------------------------------------------------------------

class TestNonStreamingRegression:
    def test_json_path_still_returns_200_on_success(self):
        with _patch_cruz(_make_output()):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "hello"})
        assert resp.status_code == 200

    def test_json_path_still_returns_500_on_error(self):
        with _patch_cruz(_make_output(success=False, result=None)):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "bad"})
        assert resp.status_code == 500

    def test_json_path_still_returns_202_on_approval(self):
        with _patch_cruz(_make_output(requires_approval=True, approval_prompt="ok?")):
            client = TestClient(app)
            resp = client.post("/command", json={"command": "send email"})
        assert resp.status_code == 202
