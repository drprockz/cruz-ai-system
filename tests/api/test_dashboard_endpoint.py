"""Tests for GET /dashboard aggregate endpoint."""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


def test_dashboard_returns_expected_shape(monkeypatch):
    """GET /dashboard returns top-level keys: today, metrics, system_health, upcoming."""
    monkeypatch.setenv("ENVIRONMENT", "test")

    # Fake DB that returns a metrics row
    class FakeDB:
        async def fetchrow(self, q, *a):
            return {"turns": 42, "tokens": 58342, "duration_total_ms": 73000}

    with patch("backend.api.main.get_db_service", return_value=FakeDB()):
        from backend.api.main import app
        client = TestClient(app)
        r = client.get("/dashboard")
        assert r.status_code == 200
        j = r.json()
        assert set(j.keys()) >= {"today", "metrics", "system_health", "upcoming"}
        assert "turns_today" in j["metrics"]
        assert "deepgram" in j["system_health"]


def test_dashboard_metrics_values(monkeypatch):
    """GET /dashboard reflects DB-returned metric values in metrics block."""
    monkeypatch.setenv("ENVIRONMENT", "test")

    class FakeDB:
        async def fetchrow(self, q, *a):
            return {"turns": 7, "tokens": 1_000_000, "duration_total_ms": 5000}

    with patch("backend.api.main.get_db_service", return_value=FakeDB()):
        from backend.api.main import app
        client = TestClient(app)
        r = client.get("/dashboard")
        assert r.status_code == 200
        j = r.json()
        assert j["metrics"]["turns_today"] == 7
        assert j["metrics"]["tokens_today"] == 1_000_000
        # estimated cost at 1M tokens * $9/M = $9.00
        assert j["metrics"]["estimated_cost_usd"] == pytest.approx(9.0, abs=0.01)
        # estimated_time_saved_hours = 7 * 0.1 = 0.7
        assert j["metrics"]["estimated_time_saved_hours"] == pytest.approx(0.7, abs=0.01)


def test_dashboard_system_health_contains_required_keys(monkeypatch):
    """system_health block contains deepgram, livekit, postgres, redis, qdrant, ollama, claude_api."""
    monkeypatch.setenv("ENVIRONMENT", "test")

    class FakeDB:
        async def fetchrow(self, q, *a):
            return {"turns": 0, "tokens": 0, "duration_total_ms": 0}

    expected_keys = {"deepgram", "livekit", "postgres", "redis", "qdrant", "ollama", "claude_api"}

    with patch("backend.api.main.get_db_service", return_value=FakeDB()):
        from backend.api.main import app
        client = TestClient(app)
        r = client.get("/dashboard")
        assert r.status_code == 200
        sh = r.json()["system_health"]
        assert expected_keys <= set(sh.keys())


def test_dashboard_today_block_has_required_keys(monkeypatch):
    """today block contains calendar_events, unread_emails, open_prs, deploys_today."""
    monkeypatch.setenv("ENVIRONMENT", "test")

    class FakeDB:
        async def fetchrow(self, q, *a):
            return {"turns": 0, "tokens": 0, "duration_total_ms": 0}

    with patch("backend.api.main.get_db_service", return_value=FakeDB()):
        from backend.api.main import app
        client = TestClient(app)
        r = client.get("/dashboard")
        assert r.status_code == 200
        today = r.json()["today"]
        assert set(today.keys()) >= {"calendar_events", "unread_emails", "open_prs", "deploys_today"}


def test_dashboard_upcoming_block_is_list(monkeypatch):
    """upcoming block is a non-empty list with agent and scheduled_at keys."""
    monkeypatch.setenv("ENVIRONMENT", "test")

    class FakeDB:
        async def fetchrow(self, q, *a):
            return {"turns": 0, "tokens": 0, "duration_total_ms": 0}

    with patch("backend.api.main.get_db_service", return_value=FakeDB()):
        from backend.api.main import app
        client = TestClient(app)
        r = client.get("/dashboard")
        assert r.status_code == 200
        upcoming = r.json()["upcoming"]
        assert isinstance(upcoming, list)
        assert len(upcoming) >= 1
        for item in upcoming:
            assert "agent" in item
            assert "scheduled_at" in item


def test_dashboard_still_200_when_db_fails(monkeypatch):
    """GET /dashboard returns 200 with zeroed metrics when DB raises an exception."""
    monkeypatch.setenv("ENVIRONMENT", "test")

    class BrokenDB:
        async def fetchrow(self, *a, **kw):
            raise RuntimeError("DB is down")

    with patch("backend.api.main.get_db_service", return_value=BrokenDB()):
        from backend.api.main import app
        client = TestClient(app)
        r = client.get("/dashboard")
        assert r.status_code == 200
        j = r.json()
        assert j["metrics"]["turns_today"] == 0
        assert j["metrics"]["tokens_today"] == 0
