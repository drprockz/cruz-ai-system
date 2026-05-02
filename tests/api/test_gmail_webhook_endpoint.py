"""POST /webhooks/gmail — Pub/Sub push receiver with OIDC JWT verification."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app


def test_gmail_webhook_rejects_missing_auth():
    with TestClient(app) as client:
        resp = client.post("/webhooks/gmail", json={"message": {"data": "abc"}})
    assert resp.status_code == 401


def test_gmail_webhook_rejects_invalid_jwt():
    with TestClient(app) as client:
        resp = client.post(
            "/webhooks/gmail",
            json={"message": {"data": "abc"}},
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )
    assert resp.status_code == 401


def test_gmail_webhook_accepts_valid_jwt_and_enqueues():
    """Valid JWT → 200, enqueues process_gmail_webhook."""
    from unittest.mock import AsyncMock
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock()
    # AsyncMock(return_value=pool) — awaiting get_arq_pool() resolves to pool.
    fake_verify = patch(
        "backend.api.main._verify_pubsub_jwt",
        return_value={"email": "ok"},
    )
    fake_pool = patch(
        "backend.api.main.get_arq_pool",
        new=AsyncMock(return_value=pool),
    )
    with fake_verify, fake_pool, TestClient(app) as client:
        resp = client.post(
            "/webhooks/gmail",
            json={"message": {"data": "eyJoaXN0b3J5SWQiOiAiOTk5In0="}},
            headers={"Authorization": "Bearer x.y.z"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("queued") is True
    pool.enqueue_job.assert_awaited_once()
