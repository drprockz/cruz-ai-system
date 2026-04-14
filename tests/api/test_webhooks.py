"""
Tests for Cloudflare Tunnel webhook endpoints.

  POST /webhooks/github          — x-hub-signature-256 HMAC-SHA256
  POST /webhooks/vercel          — x-vercel-signature HMAC-SHA1
  POST /webhooks/google-calendar — X-Goog-Channel-Token static match

Each endpoint:
  • Verifies signature/token against its env secret.
  • Enqueues an ARQ job with the raw JSON body.
  • Returns 200 immediately on success, 401 on bad signature.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "gh-secret")
    monkeypatch.setenv("VERCEL_WEBHOOK_SECRET", "vc-secret")
    monkeypatch.setenv("GOOGLE_WEBHOOK_TOKEN", "gc-token")


@pytest.fixture
def client():
    from backend.api.main import app
    return TestClient(app)


def _sign(secret: str, body: bytes, algo: str = "sha256") -> str:
    h = hmac.new(secret.encode(), body, getattr(hashlib, algo))
    return h.hexdigest()


class TestGitHubWebhook:
    def test_valid_signature_enqueues_and_returns_200(self, client):
        payload = {"action": "opened", "pull_request": {"number": 7}}
        body = json.dumps(payload).encode()
        sig = "sha256=" + _sign("gh-secret", body)
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock()
        with patch("backend.api.main.get_arq_pool", new=AsyncMock(return_value=mock_pool)):
            r = client.post(
                "/webhooks/github",
                data=body,
                headers={
                    "x-hub-signature-256": sig,
                    "x-github-event": "pull_request",
                    "content-type": "application/json",
                },
            )
        assert r.status_code == 200
        mock_pool.enqueue_job.assert_awaited_once()
        name, _payload = mock_pool.enqueue_job.await_args.args[:2]
        assert name == "process_github_webhook"

    def test_bad_signature_returns_401(self, client):
        body = b'{"a":1}'
        r = client.post(
            "/webhooks/github",
            data=body,
            headers={"x-hub-signature-256": "sha256=deadbeef",
                     "content-type": "application/json"},
        )
        assert r.status_code == 401

    def test_missing_signature_returns_401(self, client):
        r = client.post(
            "/webhooks/github",
            data=b'{"a":1}',
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 401


class TestVercelWebhook:
    def test_valid_signature_returns_200(self, client):
        body = json.dumps({"type": "deployment.ready"}).encode()
        sig = _sign("vc-secret", body, "sha1")
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock()
        with patch("backend.api.main.get_arq_pool", new=AsyncMock(return_value=mock_pool)):
            r = client.post(
                "/webhooks/vercel",
                data=body,
                headers={"x-vercel-signature": sig,
                         "content-type": "application/json"},
            )
        assert r.status_code == 200
        mock_pool.enqueue_job.assert_awaited_once()
        assert mock_pool.enqueue_job.await_args.args[0] == "process_vercel_webhook"

    def test_bad_signature_returns_401(self, client):
        r = client.post(
            "/webhooks/vercel",
            data=b'{}',
            headers={"x-vercel-signature": "bad",
                     "content-type": "application/json"},
        )
        assert r.status_code == 401


class TestGoogleCalendarWebhook:
    def test_valid_token_returns_200(self, client):
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock()
        with patch("backend.api.main.get_arq_pool", new=AsyncMock(return_value=mock_pool)):
            r = client.post(
                "/webhooks/google-calendar",
                data=b"",
                headers={
                    "X-Goog-Channel-Token": "gc-token",
                    "X-Goog-Resource-State": "exists",
                    "X-Goog-Channel-ID": "ch1",
                },
            )
        assert r.status_code == 200
        mock_pool.enqueue_job.assert_awaited_once()
        assert mock_pool.enqueue_job.await_args.args[0] == "process_google_calendar_webhook"

    def test_bad_token_returns_401(self, client):
        r = client.post(
            "/webhooks/google-calendar",
            data=b"",
            headers={"X-Goog-Channel-Token": "wrong"},
        )
        assert r.status_code == 401
