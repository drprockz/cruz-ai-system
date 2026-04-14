"""
services.llm — unified LLM entry point.

Agents call `chat(...)` instead of instantiating anthropic / gemini /
ollama clients directly. Backend is chosen by the LLM_BACKEND env var
(default: anthropic) or via the `backend=` argument.
"""

from services.llm.router import chat, _resolve_backend  # noqa: F401
from services.llm.types import ChatResponse, ContentBlock, Usage  # noqa: F401

__all__ = [
    "chat",
    "ChatResponse",
    "ContentBlock",
    "Usage",
]
