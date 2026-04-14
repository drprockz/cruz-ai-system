"""
Tests for GET /health — full dependency health check.

The endpoint must:
  - Always return HTTP 200 (never 500 — health checks must always respond)
  - Return a JSON object with a top-level `status` field
  - status == "healthy"  when all critical services are up
  - status == "degraded" when one or more services are down
  - Include per-service keys: postgresql, redis, ollama, claude_api
  - Each service value is a status string: "connected" | "reachable" |
    "loaded" | "error: <msg>" — so the operator knows what's wrong
  - Report individual Ollama models under ollama.models
  - Never let an unhandled exception escape (defensive — always returns JSON)

RED phase — must fail before the full health check is wired in.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend/api"))
from main import app


# ---------------------------------------------------------------------------
# Helpers — mock each dependency
# ---------------------------------------------------------------------------

def _healthy_db():
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"result": 1})
    return db


def _unhealthy_db():
    db = AsyncMock()
    db.fetchrow = AsyncMock(side_effect=Exception("connection refused"))
    return db


def _healthy_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    return r


def _unhealthy_redis():
    r = AsyncMock()
    r.ping = AsyncMock(side_effect=Exception("redis not available"))
    return r


def _healthy_ollama():
    svc = AsyncMock()
    svc.health_check = AsyncMock(return_value=True)
    svc.list_models = AsyncMock(return_value=["qwen2.5-coder:14b", "llama3.1:8b"])
    return svc


def _unhealthy_ollama():
    svc = AsyncMock()
    svc.health_check = AsyncMock(return_value=False)
    svc.list_models = AsyncMock(return_value=[])
    return svc


def _healthy_claude():
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text="ok")]
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=msg)
    return client


def _unhealthy_claude():
    import anthropic
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(
        side_effect=anthropic.APIConnectionError(request=MagicMock())
    )
    return client


# ---------------------------------------------------------------------------
# Always HTTP 200
# ---------------------------------------------------------------------------

class TestHealthAlways200:
    def test_returns_200_when_all_healthy(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            client = TestClient(app)
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_returns_200_even_when_db_is_down(self):
        with patch("main.get_db_service", return_value=_unhealthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            client = TestClient(app)
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_returns_200_even_when_all_services_down(self):
        with patch("main.get_db_service", return_value=_unhealthy_db()), \
             patch("main.aioredis.from_url", return_value=_unhealthy_redis()), \
             patch("main.OllamaService", return_value=_unhealthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_unhealthy_claude()):
            client = TestClient(app)
            resp = client.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Top-level structure
# ---------------------------------------------------------------------------

class TestHealthStructure:
    def test_response_is_json_object(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert isinstance(resp.json(), dict)

    def test_has_status_field(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert "status" in resp.json()

    def test_has_postgresql_field(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert "postgresql" in resp.json()

    def test_has_redis_field(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert "redis" in resp.json()

    def test_has_ollama_field(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert "ollama" in resp.json()

    def test_has_claude_api_field(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert "claude_api" in resp.json()


# ---------------------------------------------------------------------------
# Overall status field
# ---------------------------------------------------------------------------

class TestHealthOverallStatus:
    def test_status_is_healthy_when_all_up(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["status"] == "healthy"

    def test_status_is_degraded_when_db_is_down(self):
        with patch("main.get_db_service", return_value=_unhealthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["status"] == "degraded"

    def test_status_is_degraded_when_redis_is_down(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_unhealthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["status"] == "degraded"

    def test_status_is_degraded_when_claude_is_down(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_unhealthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["status"] == "degraded"


# ---------------------------------------------------------------------------
# Per-service values
# ---------------------------------------------------------------------------

class TestHealthServiceValues:
    def test_postgresql_connected_when_healthy(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["postgresql"] == "connected"

    def test_postgresql_error_when_unhealthy(self):
        with patch("main.get_db_service", return_value=_unhealthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["postgresql"].startswith("error:")

    def test_redis_connected_when_healthy(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["redis"] == "connected"

    def test_redis_error_when_unhealthy(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_unhealthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["redis"].startswith("error:")

    def test_ollama_reachable_when_healthy(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["ollama"]["status"] == "reachable"

    def test_ollama_lists_models_when_healthy(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert "models" in resp.json()["ollama"]
        assert "qwen2.5-coder:14b" in resp.json()["ollama"]["models"]

    def test_ollama_unreachable_when_unhealthy(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_unhealthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["ollama"]["status"] == "unreachable"

    def test_claude_api_reachable_when_healthy(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["claude_api"] == "reachable"

    def test_claude_api_error_when_unhealthy(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_unhealthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["claude_api"].startswith("error:")

    def test_has_qdrant_field(self):
        qdrant_svc = AsyncMock()
        qdrant_svc.health_check = AsyncMock(return_value=True)
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()), \
             patch("main.get_qdrant_service", return_value=qdrant_svc):
            resp = TestClient(app).get("/health")
        assert "qdrant" in resp.json()

    def test_qdrant_connected_when_healthy(self):
        qdrant_svc = AsyncMock()
        qdrant_svc.health_check = AsyncMock(return_value=True)
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()), \
             patch("main.get_qdrant_service", return_value=qdrant_svc):
            resp = TestClient(app).get("/health")
        assert resp.json()["qdrant"] == "connected"

    def test_qdrant_unreachable_when_unhealthy(self):
        qdrant_svc = AsyncMock()
        qdrant_svc.health_check = AsyncMock(return_value=False)
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()), \
             patch("main.get_qdrant_service", return_value=qdrant_svc):
            resp = TestClient(app).get("/health")
        assert resp.json()["qdrant"] == "unreachable"


# ---------------------------------------------------------------------------
# R4 — required Ollama model availability
# ---------------------------------------------------------------------------

def _ollama_with_models(models: list[str]):
    svc = AsyncMock()
    svc.health_check = AsyncMock(return_value=True)
    svc.list_models = AsyncMock(return_value=models)
    return svc


class TestHealthOllamaRequiredModels:
    """
    /health must expose which Ollama models are required by CRUZ agents and
    which are actually loaded. Status degrades to 'degraded' when required
    models are missing because agents will hang or fall back to Claude.
    """

    def test_ollama_response_has_required_models_list(self):
        """Response must expose ollama.required so operators know what to pull."""
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        ollama = resp.json()["ollama"]
        assert "required" in ollama
        assert "qwen2.5-coder:14b" in ollama["required"]
        assert "llama3.1:8b" in ollama["required"]

    def test_ollama_response_has_missing_models_list(self):
        """Response must expose ollama.missing so operators can fix."""
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert "missing" in resp.json()["ollama"]

    def test_missing_empty_when_all_required_loaded(self):
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["ollama"]["missing"] == []

    def test_missing_lists_qwen_when_only_llama_loaded(self):
        ollama = _ollama_with_models(["llama3.1:8b"])
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=ollama), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["ollama"]["missing"] == ["qwen2.5-coder:14b"]

    def test_missing_lists_both_when_no_models_loaded(self):
        ollama = _ollama_with_models([])
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=ollama), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        missing = resp.json()["ollama"]["missing"]
        assert "qwen2.5-coder:14b" in missing
        assert "llama3.1:8b" in missing

    def test_status_degraded_when_required_model_missing(self):
        """Even if every service is 'reachable', missing models degrade status."""
        ollama = _ollama_with_models([])  # no models pulled
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=ollama), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["status"] == "degraded"
