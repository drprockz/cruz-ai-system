# tests/api/test_false_alarm_endpoint.py
"""POST /notifications/false-alarm — Telegram inline-button callback.

Uses fastapi.testclient.TestClient because the endpoint depends on
the FastAPI lifespan (DB pool, Redis pool) being initialised. AsyncClient
+ ASGITransport does NOT run lifespan; existing tests in this dir
(test_health_endpoint.py, test_voice_token.py, test_approvals_endpoint.py)
all use TestClient for the same reason.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.main import app


def test_false_alarm_records_state_for_agent_and_dedup_key():
    """Test that false-alarm endpoint records the state and returns 200."""
    with TestClient(app) as client:
        resp = client.post(
            "/notifications/false-alarm",
            json={"agent": "reply_triage", "dedup_key": "email:abc-123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["recorded"] is True


def test_false_alarm_rejects_missing_fields():
    """Test that omitting required fields returns 422 Unprocessable Entity."""
    with TestClient(app) as client:
        resp = client.post("/notifications/false-alarm", json={"agent": "x"})
    assert resp.status_code in (400, 422)
