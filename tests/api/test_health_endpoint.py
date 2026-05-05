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
        """Claude API down → degraded, but only when LLM_BACKEND=anthropic."""
        with patch.dict(os.environ, {"LLM_BACKEND": "anthropic"}, clear=False), \
             patch("main.get_db_service", return_value=_healthy_db()), \
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

    def test_accepts_real_ollama_dict_shape(self):
        """
        Real Ollama /api/tags returns list[dict] with a `name` key, not
        list[str]. Production bug 2026-04-14: health reported both models
        as missing even when loaded because we compared dicts directly
        against the required string names.
        """
        ollama = _ollama_with_models([
            {"name": "qwen2.5-coder:14b", "size": 8988124298,
             "details": {"parameter_size": "14.8B"}},
            {"name": "llama3.1:8b", "size": 4920753328,
             "details": {"parameter_size": "8.0B"}},
        ])
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=ollama), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        body = resp.json()
        assert body["ollama"]["missing"] == [], (
            f"required models were detected as missing despite being loaded: "
            f"{body['ollama']}"
        )

    def test_dict_shape_with_one_model_missing(self):
        """Partial match under the real dict shape — only llama loaded."""
        ollama = _ollama_with_models([
            {"name": "llama3.1:8b", "size": 4920753328},
        ])
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=ollama), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["ollama"]["missing"] == ["qwen2.5-coder:14b"]

    def test_claude_down_does_not_degrade_when_backend_is_ollama(self):
        """
        Regression: /health used to report 'degraded' whenever Claude API
        was unreachable, even if the operator had switched LLM_BACKEND to
        ollama. The claude_api probe is now only gated when backend=anthropic.
        """
        with patch.dict(os.environ, {"LLM_BACKEND": "ollama"}, clear=False), \
             patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_unhealthy_claude()):
            resp = TestClient(app).get("/health")
        body = resp.json()
        assert body["llm_backend"] == "ollama"
        assert body["status"] == "healthy", (
            f"Backend=ollama + dead Claude API should stay healthy. "
            f"Got: {body}"
        )

    def test_claude_down_still_degrades_when_backend_is_anthropic(self):
        """Opposite direction: when backend=anthropic, Claude API being
        down must still degrade status."""
        with patch.dict(os.environ, {"LLM_BACKEND": "anthropic"}, clear=False), \
             patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_unhealthy_claude()):
            resp = TestClient(app).get("/health")
        assert resp.json()["status"] == "degraded"


# ---------------------------------------------------------------------------
# Browser service (SP4)
# ---------------------------------------------------------------------------

def _healthy_browser():
    svc = AsyncMock()
    svc.health = AsyncMock(return_value={"status": "alive", "contexts": []})
    return svc


def _not_started_browser():
    svc = AsyncMock()
    svc.health = AsyncMock(return_value={"status": "not_started"})
    return svc


def _degraded_browser():
    svc = AsyncMock()
    svc.health = AsyncMock(return_value={"status": "degraded", "reason": "page evaluation timeout"})
    return svc


class TestHealthBrowserBlock:
    """Browser service health is exposed on /health (SP4)."""

    def test_has_browser_field(self):
        """Response must include a `browser` key."""
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()), \
             patch("main.get_browser_service", return_value=_healthy_browser()):
            resp = TestClient(app).get("/health")
        assert "browser" in resp.json()

    def test_browser_status_alive(self):
        """Browser reports 'alive' when healthy."""
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()), \
             patch("main.get_browser_service", return_value=_healthy_browser()):
            resp = TestClient(app).get("/health")
        assert resp.json()["browser"]["status"] == "alive"

    def test_browser_status_not_started(self):
        """Browser reports 'not_started' before init."""
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()), \
             patch("main.get_browser_service", return_value=_not_started_browser()):
            resp = TestClient(app).get("/health")
        assert resp.json()["browser"]["status"] == "not_started"

    def test_browser_status_degraded(self):
        """Browser reports 'degraded' on partial failure."""
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()), \
             patch("main.get_browser_service", return_value=_degraded_browser()):
            resp = TestClient(app).get("/health")
        assert resp.json()["browser"]["status"] == "degraded"

    def test_browser_error_handling(self):
        """Browser health check errors are caught and reported."""
        browser_svc = AsyncMock()
        browser_svc.health = AsyncMock(side_effect=Exception("playwright crash"))
        with patch("main.get_db_service", return_value=_healthy_db()), \
             patch("main.aioredis.from_url", return_value=_healthy_redis()), \
             patch("main.OllamaService", return_value=_healthy_ollama()), \
             patch("main.anthropic.AsyncAnthropic", return_value=_healthy_claude()), \
             patch("main.get_browser_service", return_value=browser_svc):
            resp = TestClient(app).get("/health")
        body = resp.json()
        assert "browser" in body
        assert body["browser"]["status"] == "error"
        assert "playwright crash" in body["browser"].get("reason", "")
