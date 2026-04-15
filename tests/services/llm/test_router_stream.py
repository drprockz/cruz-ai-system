import pytest
from unittest.mock import patch

from services.llm.router import chat_stream


@pytest.mark.asyncio
async def test_router_stream_dispatches_anthropic(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "anthropic")
    async def _fake(system, messages, **kw):
        yield {"delta": "x"}
    with patch("services.llm.router.anthropic_chat_stream", _fake):
        events = []
        async for ev in chat_stream(system="s", messages=[]):
            events.append(ev)
        assert events == [{"delta": "x"}]


@pytest.mark.asyncio
async def test_router_stream_rejects_non_anthropic(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    with pytest.raises(NotImplementedError):
        async for _ in chat_stream(system="s", messages=[]):
            pass
