from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.cruz.cruz_agent import CruzAgent
from agents.cruz.stream_events import Text, Done
from services.llm.stream_events import TextDeltaEvent, DoneEvent, UsageInfo


@pytest.mark.asyncio
async def test_stream_response_yields_sentences_then_done(monkeypatch):
    async def _fake_stream(**kw):
        yield TextDeltaEvent(delta="Deployment ")
        yield TextDeltaEvent(delta="complete. ")
        yield TextDeltaEvent(delta="All good. ")
        yield DoneEvent(stop_reason="end_turn", usage=UsageInfo(5, 3))

    with patch("agents.cruz.cruz_agent.llm_chat_stream", _fake_stream), \
         patch("agents.cruz.cruz_agent.ConversationService") as conv_cls, \
         patch("agents.cruz.cruz_agent.SemanticMemoryService") as sem_cls, \
         patch("agents.cruz.cruz_agent.get_db_service"), \
         patch("agents.cruz.cruz_agent.get_qdrant_service"), \
         patch("agents.cruz.cruz_agent.get_embedding_service"), \
         patch("agents.cruz.cruz_agent.classify", return_value=None):
        conv_cls.return_value.get_or_create_conversation = AsyncMock()
        conv_cls.return_value.load_history = AsyncMock(return_value=[])
        conv_cls.return_value.save_exchange = AsyncMock()
        sem_cls.return_value.search_similar = AsyncMock(return_value=[])
        sem_cls.return_value.store = AsyncMock()

        agent = CruzAgent()
        events = []
        async for ev in agent.stream_response(
            task="deploy ama",
            conversation_id="conv-1",
            trace_id="t-1",
            device="mac_mini",
        ):
            events.append(ev)

    texts = [e.content for e in events if isinstance(e, Text)]
    assert texts == ["Deployment complete.", "All good."]
    assert isinstance(events[-1], Done)
    assert events[-1].tokens_used == 8


@pytest.mark.asyncio
async def test_stream_response_web_search(monkeypatch):
    """Streaming path also dispatches web_search to BrowserService."""
    from agents.cruz.stream_events import ToolStart, ToolFinish
    from services.llm.stream_events import (
        TextDeltaEvent, ToolUseEvent, DoneEvent, UsageInfo,
    )
    import services.browser.service as browser_mod

    fake_browser = MagicMock()
    fake_browser.search = AsyncMock(return_value=[
        {"title": "X", "url": "https://x", "snippet": "s", "rank": 1},
    ])
    monkeypatch.setattr(browser_mod, "_instance", fake_browser)

    # Two fake LLM streaming calls: first emits a tool_use, second emits final text.
    async def fake_stream_first(**kw):
        yield ToolUseEvent(
            tool_use_id="tu1", name="web_search",
            input={"query": "anthropic", "limit": 5},
        )
        yield DoneEvent(stop_reason="tool_use", usage=UsageInfo(10, 5))

    async def fake_stream_second(**kw):
        yield TextDeltaEvent(delta="Anthropic released ")
        yield TextDeltaEvent(delta="Claude 5.")
        yield DoneEvent(stop_reason="end_turn", usage=UsageInfo(20, 5))

    streams = [fake_stream_first, fake_stream_second]
    def stream_side_effect(**kw):
        return streams.pop(0)(**kw)

    with patch("agents.cruz.cruz_agent.llm_chat_stream", stream_side_effect), \
         patch("agents.cruz.cruz_agent.ConversationService") as conv_cls, \
         patch("agents.cruz.cruz_agent.SemanticMemoryService") as sem_cls, \
         patch("agents.cruz.cruz_agent.get_db_service"), \
         patch("agents.cruz.cruz_agent.get_qdrant_service"), \
         patch("agents.cruz.cruz_agent.get_embedding_service"), \
         patch("agents.cruz.cruz_agent.classify", return_value=None):
        conv_cls.return_value.get_or_create_conversation = AsyncMock()
        conv_cls.return_value.load_history = AsyncMock(return_value=[])
        conv_cls.return_value.save_exchange = AsyncMock()
        sem_cls.return_value.search_similar = AsyncMock(return_value=[])
        sem_cls.return_value.store = AsyncMock()

        agent = CruzAgent()
        events = []
        async for ev in agent.stream_response(
            task="what's new",
            conversation_id="c-1",
            trace_id="t-1",
            device="phone",
        ):
            events.append(ev)

    assert any(isinstance(e, ToolStart) and e.agent == "web_search" for e in events)
    assert any(isinstance(e, ToolFinish) and e.agent == "web_search" for e in events)
    fake_browser.search.assert_awaited()
