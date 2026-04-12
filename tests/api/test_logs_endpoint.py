"""
Tests for GET /logs/{trace_id} — execution trace query.

The endpoint queries agent_logs for all rows matching a trace_id and returns
them ordered by created_at ASC so operators can see every agent in a call chain.

Contract:
  - 200 + list of log entries for any trace_id (including unknown → empty list)
  - Each entry has: agent, action, status, tokens_used, duration_ms, created_at
  - No DB internals (id column) leaked to the caller
  - Entries are in chronological order (oldest first)
  - trace_id from the URL path is passed to the DB query
  - Always HTTP 200 (no 404 for unknown trace_ids — empty list is fine)

RED phase — must fail before the endpoint exists.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend/api"))
from main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(rows=None):
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=rows or [])
    return db


def _make_log_row(
    agent="CRUZ",
    action="process",
    status="success",
    tokens_used=150,
    duration_ms=200,
    created_at="2026-04-13T12:00:00",
    trace_id="trace-001",
    id=1,
):
    """Simulate a dict-like asyncpg row."""
    return {
        "id": id,
        "trace_id": trace_id,
        "agent": agent,
        "action": action,
        "status": status,
        "tokens_used": tokens_used,
        "duration_ms": duration_ms,
        "input_data": None,
        "output_data": None,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Route exists
# ---------------------------------------------------------------------------

class TestLogsEndpointExists:
    def test_get_logs_does_not_return_405(self):
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            client = TestClient(app)
            resp = client.get("/logs/some-trace-id")
        assert resp.status_code != 405

    def test_get_logs_returns_200(self):
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            client = TestClient(app)
            resp = client.get("/logs/some-trace-id")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------

class TestLogsEndpointShape:
    def test_returns_list(self):
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            resp = TestClient(app).get("/logs/trace-001")
        assert isinstance(resp.json(), list)

    def test_empty_list_for_unknown_trace_id(self):
        db = _make_db(rows=[])
        with patch("main.get_db_service", return_value=db):
            resp = TestClient(app).get("/logs/nonexistent-trace")
        assert resp.json() == []

    def test_entry_has_agent_field(self):
        db = _make_db(rows=[_make_log_row(agent="FORGE")])
        with patch("main.get_db_service", return_value=db):
            resp = TestClient(app).get("/logs/trace-001")
        assert "agent" in resp.json()[0]

    def test_entry_has_action_field(self):
        db = _make_db(rows=[_make_log_row()])
        with patch("main.get_db_service", return_value=db):
            resp = TestClient(app).get("/logs/trace-001")
        assert "action" in resp.json()[0]

    def test_entry_has_status_field(self):
        db = _make_db(rows=[_make_log_row(status="success")])
        with patch("main.get_db_service", return_value=db):
            resp = TestClient(app).get("/logs/trace-001")
        assert "status" in resp.json()[0]

    def test_entry_has_tokens_used_field(self):
        db = _make_db(rows=[_make_log_row(tokens_used=99)])
        with patch("main.get_db_service", return_value=db):
            resp = TestClient(app).get("/logs/trace-001")
        assert "tokens_used" in resp.json()[0]

    def test_entry_has_duration_ms_field(self):
        db = _make_db(rows=[_make_log_row(duration_ms=42)])
        with patch("main.get_db_service", return_value=db):
            resp = TestClient(app).get("/logs/trace-001")
        assert "duration_ms" in resp.json()[0]

    def test_entry_has_created_at_field(self):
        db = _make_db(rows=[_make_log_row()])
        with patch("main.get_db_service", return_value=db):
            resp = TestClient(app).get("/logs/trace-001")
        assert "created_at" in resp.json()[0]

    def test_entry_does_not_expose_id(self):
        """Internal DB primary key must not leak to callers."""
        db = _make_db(rows=[_make_log_row(id=42)])
        with patch("main.get_db_service", return_value=db):
            resp = TestClient(app).get("/logs/trace-001")
        assert "id" not in resp.json()[0]


# ---------------------------------------------------------------------------
# Correct values
# ---------------------------------------------------------------------------

class TestLogsEndpointValues:
    def test_agent_name_correct(self):
        db = _make_db(rows=[_make_log_row(agent="FORGE")])
        with patch("main.get_db_service", return_value=db):
            resp = TestClient(app).get("/logs/trace-001")
        assert resp.json()[0]["agent"] == "FORGE"

    def test_status_correct(self):
        db = _make_db(rows=[_make_log_row(status="error")])
        with patch("main.get_db_service", return_value=db):
            resp = TestClient(app).get("/logs/trace-001")
        assert resp.json()[0]["status"] == "error"

    def test_tokens_used_correct(self):
        db = _make_db(rows=[_make_log_row(tokens_used=777)])
        with patch("main.get_db_service", return_value=db):
            resp = TestClient(app).get("/logs/trace-001")
        assert resp.json()[0]["tokens_used"] == 777

    def test_multiple_entries_returned(self):
        rows = [
            _make_log_row(agent="CRUZ", id=1),
            _make_log_row(agent="FORGE", id=2),
        ]
        db = _make_db(rows=rows)
        with patch("main.get_db_service", return_value=db):
            resp = TestClient(app).get("/logs/trace-001")
        assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# DB query correctness
# ---------------------------------------------------------------------------

class TestLogsEndpointQuery:
    def test_trace_id_from_path_passed_to_db(self):
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            TestClient(app).get("/logs/specific-trace-id-xyz")

        call_args = str(db.fetch.call_args)
        assert "specific-trace-id-xyz" in call_args

    def test_query_orders_by_created_at(self):
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            TestClient(app).get("/logs/trace-001")

        query = db.fetch.call_args[0][0]
        assert "ORDER BY" in query.upper()
        assert "created_at" in query.lower()
