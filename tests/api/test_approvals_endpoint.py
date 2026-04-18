"""Tests for /approvals list + approve/deny endpoints."""
from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


def test_list_approvals_returns_pending_rows():
    """GET /approvals?state=pending returns list of approval rows."""
    from backend.api.main import app

    row = {
        "id": "a-1",
        "trace_id": "t-1",
        "agent": "titan",
        "action": "deploy",
        "payload": {},
        "state": "pending",
        "requested_at": "2026-04-18T18:00:00Z",
        "responded_at": None,
        "expires_at": "2026-04-18T18:10:00Z",
    }

    class FakeDB:
        async def fetch(self, *a, **kw):
            return [row]

        async def fetchrow(self, *a, **kw):
            return row

        async def execute(self, *a, **kw):
            return "UPDATE 1"

    with patch("backend.api.main.get_db_service", return_value=FakeDB()):
        c = TestClient(app)
        r = c.get("/approvals?state=pending")
        assert r.status_code == 200
        j = r.json()
        assert len(j) == 1
        assert j[0]["id"] == "a-1"
        assert j[0]["agent"] == "titan"
        assert j[0]["action"] == "deploy"


def test_list_approvals_default_state_is_pending():
    """GET /approvals (no state param) defaults to pending."""
    from backend.api.main import app

    captured_queries = []

    class FakeDB:
        async def fetch(self, query, *args, **kw):
            captured_queries.append((query, args))
            return []

    with patch("backend.api.main.get_db_service", return_value=FakeDB()):
        c = TestClient(app)
        r = c.get("/approvals")
        assert r.status_code == 200
        assert r.json() == []
        # The query should have been called with 'pending' as first param
        assert len(captured_queries) == 1
        _, args = captured_queries[0]
        assert args[0] == "pending"


def test_list_approvals_returns_empty_list_when_none():
    """GET /approvals returns [] when no rows match."""
    from backend.api.main import app

    class FakeDB:
        async def fetch(self, *a, **kw):
            return []

    with patch("backend.api.main.get_db_service", return_value=FakeDB()):
        c = TestClient(app)
        r = c.get("/approvals?state=pending")
        assert r.status_code == 200
        assert r.json() == []


def test_approve_updates_state_and_returns_approved():
    """POST /approvals/:id/approve updates DB and returns {state: approved}."""
    from backend.api.main import app

    class FakeRedis:
        async def publish(self, *a, **kw):
            return 1

    class FakeDB:
        async def execute(self, *a, **kw):
            return "UPDATE 1"

    with patch("backend.api.main.get_db_service", return_value=FakeDB()), \
         patch("backend.api.main.get_redis_service", return_value=FakeRedis()):
        c = TestClient(app)
        aid = str(uuid.uuid4())
        r = c.post(f"/approvals/{aid}/approve")
        assert r.status_code == 200
        assert r.json()["state"] == "approved"


def test_deny_updates_state_and_returns_denied():
    """POST /approvals/:id/deny updates DB and returns {state: denied}."""
    from backend.api.main import app

    class FakeRedis:
        async def publish(self, *a, **kw):
            return 1

    class FakeDB:
        async def execute(self, *a, **kw):
            return "UPDATE 1"

    with patch("backend.api.main.get_db_service", return_value=FakeDB()), \
         patch("backend.api.main.get_redis_service", return_value=FakeRedis()):
        c = TestClient(app)
        aid = str(uuid.uuid4())
        r = c.post(f"/approvals/{aid}/deny")
        assert r.status_code == 200
        assert r.json()["state"] == "denied"


def test_approve_publishes_to_redis_channel():
    """POST /approvals/:id/approve publishes to cruz:approval:<id> channel."""
    from backend.api.main import app
    import json

    published_calls = []

    class FakeRedis:
        async def publish(self, channel, payload):
            published_calls.append((channel, payload))
            return 1

    class FakeDB:
        async def execute(self, *a, **kw):
            return "UPDATE 1"

    with patch("backend.api.main.get_db_service", return_value=FakeDB()), \
         patch("backend.api.main.get_redis_service", return_value=FakeRedis()):
        c = TestClient(app)
        aid = "test-approval-123"
        r = c.post(f"/approvals/{aid}/approve")
        assert r.status_code == 200
        assert len(published_calls) == 1
        channel, payload = published_calls[0]
        assert channel == f"cruz:approval:{aid}"
        parsed = json.loads(payload)
        assert parsed["state"] == "approved"


def test_deny_publishes_to_redis_channel():
    """POST /approvals/:id/deny publishes denied state to redis channel."""
    from backend.api.main import app
    import json

    published_calls = []

    class FakeRedis:
        async def publish(self, channel, payload):
            published_calls.append((channel, payload))
            return 1

    class FakeDB:
        async def execute(self, *a, **kw):
            return "UPDATE 1"

    with patch("backend.api.main.get_db_service", return_value=FakeDB()), \
         patch("backend.api.main.get_redis_service", return_value=FakeRedis()):
        c = TestClient(app)
        aid = "test-approval-456"
        r = c.post(f"/approvals/{aid}/deny")
        assert r.status_code == 200
        assert len(published_calls) == 1
        channel, payload = published_calls[0]
        assert channel == f"cruz:approval:{aid}"
        parsed = json.loads(payload)
        assert parsed["state"] == "denied"


def test_approve_still_returns_200_when_redis_fails():
    """POST /approvals/:id/approve returns 200 even if Redis publish raises."""
    from backend.api.main import app

    class BrokenRedis:
        async def publish(self, *a, **kw):
            raise ConnectionError("redis is down")

    class FakeDB:
        async def execute(self, *a, **kw):
            return "UPDATE 1"

    with patch("backend.api.main.get_db_service", return_value=FakeDB()), \
         patch("backend.api.main.get_redis_service", return_value=BrokenRedis()):
        c = TestClient(app)
        r = c.post(f"/approvals/{uuid.uuid4()}/approve")
        assert r.status_code == 200
        assert r.json()["state"] == "approved"


def test_list_approvals_respects_limit_param():
    """GET /approvals?limit=5 passes limit to DB query."""
    from backend.api.main import app

    captured = []

    class FakeDB:
        async def fetch(self, query, *args, **kw):
            captured.append(args)
            return []

    with patch("backend.api.main.get_db_service", return_value=FakeDB()):
        c = TestClient(app)
        r = c.get("/approvals?state=pending&limit=5")
        assert r.status_code == 200
        assert len(captured) == 1
        args = captured[0]
        # args: (state, limit) positional params
        assert args[1] == 5
