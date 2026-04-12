"""
Tests for services/ollama.py — Ollama local LLM HTTP client.
RED phase — must fail before production code exists.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ollama import OllamaService


class TestOllamaServiceInterface:
    def test_ollama_service_class_exists(self):
        service = OllamaService()
        assert service is not None

    def test_ollama_service_has_generate_method(self):
        service = OllamaService()
        assert hasattr(service, "generate")
        assert callable(service.generate)

    def test_ollama_service_has_list_models_method(self):
        service = OllamaService()
        assert hasattr(service, "list_models")
        assert callable(service.list_models)

    def test_ollama_service_has_health_check_method(self):
        service = OllamaService()
        assert hasattr(service, "health_check")
        assert callable(service.health_check)

    def test_default_base_url_is_localhost(self):
        service = OllamaService()
        assert "localhost" in service.base_url or "127.0.0.1" in service.base_url
        assert "11434" in service.base_url

    def test_base_url_can_be_overridden_via_env(self):
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://192.168.1.10:11434"}):
            service = OllamaService()
            assert service.base_url == "http://192.168.1.10:11434"

    def test_base_url_can_be_passed_directly(self):
        service = OllamaService(base_url="http://custom-host:11434")
        assert service.base_url == "http://custom-host:11434"


class TestOllamaGenerate:
    async def test_generate_posts_to_api_generate(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "model": "qwen2.5-coder:14b",
            "response": "Hello world",
            "done": True,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        service = OllamaService()
        with patch("services.ollama.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await service.generate(
                model="qwen2.5-coder:14b",
                prompt="Write a hello world function",
            )

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/api/generate" in call_args[0][0]

    async def test_generate_returns_response_text(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "model": "qwen2.5-coder:14b",
            "response": "def hello(): return 'world'",
            "done": True,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        service = OllamaService()
        with patch("services.ollama.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await service.generate(
                model="qwen2.5-coder:14b",
                prompt="Write a hello world function",
            )

        assert result["response"] == "def hello(): return 'world'"

    async def test_generate_sends_stream_false_by_default(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "ok", "done": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        service = OllamaService()
        with patch("services.ollama.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await service.generate(model="llama3.1:8b", prompt="test")

        call_json = mock_client.post.call_args[1]["json"]
        assert call_json["stream"] is False

    async def test_generate_includes_model_in_request(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "ok", "done": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        service = OllamaService()
        with patch("services.ollama.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await service.generate(model="qwen2.5-coder:14b", prompt="test")

        call_json = mock_client.post.call_args[1]["json"]
        assert call_json["model"] == "qwen2.5-coder:14b"


class TestOllamaListModels:
    async def test_list_models_gets_api_tags(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "models": [
                {"name": "qwen2.5-coder:14b"},
                {"name": "llama3.1:8b"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        service = OllamaService()
        with patch("services.ollama.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            models = await service.list_models()

        mock_client.get.assert_called_once()
        assert "/api/tags" in mock_client.get.call_args[0][0]
        assert len(models) == 2


class TestOllamaHealthCheck:
    async def test_health_check_returns_true_when_reachable(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        service = OllamaService()
        with patch("services.ollama.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            ok = await service.health_check()

        assert ok is True

    async def test_health_check_returns_false_when_unreachable(self):
        import httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        service = OllamaService()
        with patch("services.ollama.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            ok = await service.health_check()

        assert ok is False
