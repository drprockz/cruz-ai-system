"""
Tests for missing API endpoints required by CLAUDE.md:
  - POST /conversations        — start a new conversation, return conversation_id
  - GET  /agents/status        — per-agent last run time + status from agent_logs
  - GET  /tasks                — list tasks with optional ?status= filter

RED phase — all must fail before the endpoints are implemented.
"""

from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend/api"))
from main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(rows=None, fetchrow_result=None):
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=rows or [])
    db.fetchrow = AsyncMock(return_value=fetchrow_result)
    db.execute = AsyncMock(return_value="INSERT 0 1")
    return db


# ---------------------------------------------------------------------------
# POST /conversations
# ---------------------------------------------------------------------------

class TestPostConversations:
    def test_post_conversations_returns_201(self):
        """POST /conversations must return 201 Created."""
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            resp = client.post("/conversations")
        assert resp.status_code == 201

    def test_post_conversations_returns_conversation_id(self):
        """Response must include a conversation_id UUID string."""
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            resp = client.post("/conversations")
        data = resp.json()
        assert "conversation_id" in data
        assert isinstance(data["conversation_id"], str)
        assert len(data["conversation_id"]) == 36  # UUID format

    def test_post_conversations_accepts_optional_device(self):
        """POST /conversations may include an optional device field."""
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            resp = client.post("/conversations", json={"device": "ipad"})
        assert resp.status_code == 201

    def test_post_conversations_inserts_into_db(self):
        """A new conversation row must be inserted into the database."""
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            client.post("/conversations")
        db.execute.assert_called_once()
        call_sql = db.execute.call_args[0][0]
        assert "conversations" in call_sql.lower()

    def test_post_conversations_conversation_id_is_uuid_format(self):
        """Returned conversation_id must be a valid UUID (8-4-4-4-12 format)."""
        import re
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            resp = client.post("/conversations")
        conv_id = resp.json()["conversation_id"]
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        assert uuid_pattern.match(conv_id)


# ---------------------------------------------------------------------------
# GET /agents/status
# ---------------------------------------------------------------------------

class TestGetAgentsStatus:
    def test_agents_status_returns_200(self):
        """GET /agents/status must return 200."""
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            resp = client.get("/agents/status")
        assert resp.status_code == 200

    def test_agents_status_returns_list(self):
        """Response must be a JSON list."""
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            resp = client.get("/agents/status")
        assert isinstance(resp.json(), list)

    def test_agents_status_each_entry_has_agent_field(self):
        """Each status entry must include the agent name."""
        rows = [
            {"agent": "FORGE", "status": "success", "last_run": "2026-04-13T10:00:00"},
            {"agent": "ECHO", "status": "success", "last_run": "2026-04-13T09:00:00"},
        ]
        db = _make_db(rows=rows)
        with patch("main.get_db_service", return_value=db):
            resp = client.get("/agents/status")
        data = resp.json()
        assert len(data) == 2
        assert data[0]["agent"] == "FORGE"

    def test_agents_status_each_entry_has_status_field(self):
        """Each entry must include last known status."""
        rows = [{"agent": "FORGE", "status": "success", "last_run": "2026-04-13T10:00:00"}]
        db = _make_db(rows=rows)
        with patch("main.get_db_service", return_value=db):
            resp = client.get("/agents/status")
        assert "status" in resp.json()[0]

    def test_agents_status_each_entry_has_last_run_field(self):
        """Each entry must include last_run timestamp."""
        rows = [{"agent": "FORGE", "status": "success", "last_run": "2026-04-13T10:00:00"}]
        db = _make_db(rows=rows)
        with patch("main.get_db_service", return_value=db):
            resp = client.get("/agents/status")
        assert "last_run" in resp.json()[0]

    def test_agents_status_empty_when_no_logs(self):
        """Empty list when no agent_logs exist."""
        db = _make_db(rows=[])
        with patch("main.get_db_service", return_value=db):
            resp = client.get("/agents/status")
        assert resp.json() == []

    def test_agents_status_queries_agent_logs(self):
        """Must query the agent_logs table."""
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            client.get("/agents/status")
        call_sql = db.fetch.call_args[0][0]
        assert "agent_logs" in call_sql.lower()


# ---------------------------------------------------------------------------
# GET /tasks
# ---------------------------------------------------------------------------

class TestGetTasks:
    def test_tasks_returns_200(self):
        """GET /tasks must return 200."""
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            resp = client.get("/tasks")
        assert resp.status_code == 200

    def test_tasks_returns_list(self):
        """Response must be a JSON list."""
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            resp = client.get("/tasks")
        assert isinstance(resp.json(), list)

    def test_tasks_returns_all_when_no_filter(self):
        """Without ?status= param, returns all tasks."""
        rows = [
            {"id": 1, "agent": "FORGE", "title": "Write tests", "status": "pending",
             "priority": 3, "created_at": "2026-04-13T10:00:00"},
            {"id": 2, "agent": "ECHO", "title": "Send email", "status": "done",
             "priority": 2, "created_at": "2026-04-13T11:00:00"},
        ]
        db = _make_db(rows=rows)
        with patch("main.get_db_service", return_value=db):
            resp = client.get("/tasks")
        assert len(resp.json()) == 2

    def test_tasks_filters_by_status(self):
        """GET /tasks?status=pending must filter results."""
        rows = [
            {"id": 1, "agent": "FORGE", "title": "Write tests", "status": "pending",
             "priority": 3, "created_at": "2026-04-13T10:00:00"},
        ]
        db = _make_db(rows=rows)
        with patch("main.get_db_service", return_value=db):
            resp = client.get("/tasks?status=pending")
        assert resp.status_code == 200
        db.fetch.assert_called_once()
        # Status filter must be passed as a query parameter to the DB
        call_args = db.fetch.call_args[0]
        assert "pending" in call_args[1:]  # 'pending' passed as bind param

    def test_tasks_each_entry_has_required_fields(self):
        """Each task must expose id, agent, title, status, priority."""
        rows = [
            {"id": 1, "agent": "FORGE", "title": "Write tests", "status": "pending",
             "priority": 3, "created_at": "2026-04-13T10:00:00"},
        ]
        db = _make_db(rows=rows)
        with patch("main.get_db_service", return_value=db):
            resp = client.get("/tasks")
        task = resp.json()[0]
        for field in ("id", "agent", "title", "status", "priority"):
            assert field in task

    def test_tasks_queries_tasks_table(self):
        """Must query the tasks table."""
        db = _make_db()
        with patch("main.get_db_service", return_value=db):
            client.get("/tasks")
        call_sql = db.fetch.call_args[0][0]
        assert "tasks" in call_sql.lower()
