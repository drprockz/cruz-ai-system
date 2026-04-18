# tests/api/test_events_endpoint.py
"""
Tests for GET /events SSE endpoint.

Verifies:
  - Returns text/event-stream media type
  - Emits `event: replay` on connect (even with empty DB)
  - Emits `event: ping` or `event: replay` in the SSE output
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


def _make_app():
    from backend.api.main import app
    return app


def test_events_returns_text_event_stream(monkeypatch):
    """GET /events responds with text/event-stream media type."""
    # Mock DB fetch for initial replay
    class FakePubSub:
        def __init__(self):
            self.subscribed = False

        async def subscribe(self, *channels):
            self.subscribed = True

        async def listen(self):
            # yield one fake subscribe-type message then return
            yield {"type": "subscribe", "data": 1}
            return

        async def unsubscribe(self, *c):
            pass

        async def close(self):
            pass

    fake_redis = MagicMock()
    fake_redis.pubsub = MagicMock(return_value=FakePubSub())

    class FakeDB:
        async def fetch(self, *a, **kw):
            return []

    fake_db = FakeDB()

    with patch("backend.api.main.get_redis_service", return_value=fake_redis), \
         patch("backend.api.main.get_db_service", return_value=fake_db):
        app = _make_app()
        client = TestClient(app)
        # Use stream=True so we don't block on the generator
        with client.stream("GET", "/events") as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]
            # Read a little to kick off the generator
            chunks = []
            for i, chunk in enumerate(r.iter_lines()):
                chunks.append(chunk)
                if i > 3:
                    break
            # Replay event or ping present
            payload = "\n".join(chunks)
            assert "event: replay" in payload or "event: ping" in payload


def test_events_replay_contains_empty_list_when_db_empty(monkeypatch):
    """When DB has no rows, replay event data should be an empty list."""
    class FakePubSub:
        async def subscribe(self, *c): pass
        async def listen(self):
            yield {"type": "subscribe", "data": 1}
            return
        async def unsubscribe(self, *c): pass
        async def close(self): pass

    fake_redis = MagicMock()
    fake_redis.pubsub = MagicMock(return_value=FakePubSub())

    class FakeDB:
        async def fetch(self, *a, **kw):
            return []

    with patch("backend.api.main.get_redis_service", return_value=fake_redis), \
         patch("backend.api.main.get_db_service", return_value=FakeDB()):
        from backend.api.main import app
        client = TestClient(app)
        with client.stream("GET", "/events") as r:
            assert r.status_code == 200
            lines = []
            for i, line in enumerate(r.iter_lines()):
                lines.append(line)
                if i > 5:
                    break
            full = "\n".join(lines)
            # Should have a replay event
            assert "event: replay" in full
            # Extract the data line after event: replay
            idx = lines.index("event: replay") if "event: replay" in lines else -1
            if idx >= 0 and idx + 1 < len(lines):
                data_line = lines[idx + 1]
                assert data_line.startswith("data:")
                parsed = json.loads(data_line[len("data:"):].strip())
                assert parsed == []


def test_events_emits_log_event_for_redis_message(monkeypatch):
    """When a redis message arrives on the pubsub, a `log` event is emitted."""
    log_row = {
        "trace_id": "t-123",
        "agent": "FORGE",
        "action": "log",
        "status": "success",
        "tokens_used": 50,
        "duration_ms": 100,
    }

    class FakePubSub:
        async def subscribe(self, *c): pass
        async def listen(self):
            yield {"type": "subscribe", "data": 1}
            yield {"type": "message", "data": json.dumps(log_row).encode()}
            return
        async def unsubscribe(self, *c): pass
        async def close(self): pass

    fake_redis = MagicMock()
    fake_redis.pubsub = MagicMock(return_value=FakePubSub())

    class FakeDB:
        async def fetch(self, *a, **kw):
            return []

    with patch("backend.api.main.get_redis_service", return_value=fake_redis), \
         patch("backend.api.main.get_db_service", return_value=FakeDB()):
        from backend.api.main import app
        client = TestClient(app)
        with client.stream("GET", "/events") as r:
            assert r.status_code == 200
            lines = []
            for i, line in enumerate(r.iter_lines()):
                lines.append(line)
                if i > 10:
                    break
            full = "\n".join(lines)
            assert "event: log" in full
