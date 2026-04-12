"""
OllamaService — HTTP client for the local Ollama LLM server.

Ollama runs locally on the Mac Mini M4 at http://localhost:11434.
Models used by CRUZ agents:
  - qwen2.5-coder:14b  (FORGE, REACH, PM, TITAN, MARK, QT)
  - llama3.1:8b        (RAW, PULSE — lighter research tasks)

Override the default base URL with OLLAMA_BASE_URL env var for
cross-device or containerised setups.

Usage:
    from services.ollama import OllamaService

    ollama = OllamaService()
    result = await ollama.generate(
        model="qwen2.5-coder:14b",
        prompt="Write a Python function that ...",
    )
    print(result["response"])
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import httpx

logger = logging.getLogger("cruz.services.ollama")

_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaService:
    """
    Thin async HTTP wrapper around the Ollama REST API.

    All methods open a fresh httpx.AsyncClient per call so the service
    is stateless and safe to share across concurrent agent tasks.
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        if base_url is not None:
            self.base_url = base_url
        else:
            self.base_url = os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def generate(
        self,
        model: str,
        prompt: str,
        stream: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Call POST /api/generate and return the full response dict.

        Args:
            model:   Ollama model tag (e.g. "qwen2.5-coder:14b").
            prompt:  Prompt string.
            stream:  If True, returns a streaming response (not yet supported).
            **kwargs: Extra fields merged into the request body.

        Returns:
            Ollama response dict with at minimum {"response": str, "done": bool}.
        """
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            **kwargs,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def list_models(self) -> List[Dict[str, Any]]:
        """
        Call GET /api/tags and return the list of available local models.

        Returns:
            List of model dicts, each containing at least {"name": str}.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])

    async def health_check(self) -> bool:
        """
        Return True if the Ollama server is reachable, False otherwise.

        Used by the /health endpoint to surface Ollama status without
        crashing the whole health check on a transient connection failure.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
            return True
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            logger.warning("Ollama health check failed — server may be offline")
            return False


# Fix missing Optional import used in __init__ signature
from typing import Optional  # noqa: E402 — must come after class body
