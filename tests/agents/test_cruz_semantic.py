"""
Tests for CruzAgent semantic memory integration.

CruzAgent must:
  - Call SemanticMemoryService.search_similar(task) before each Claude call
  - Prepend semantic hits BEFORE session history in Claude's messages array
  - Call SemanticMemoryService.store() for user + assistant after success
  - NOT call store() on error

Message order in Claude's context:
  [semantic hits...] [session history...] [new user message]

RED phase — must fail before semantic memory is wired in.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput
from agents.cruz.cruz_agent import CruzAgent


def _make_text_response(text: str) -> MagicMock:
    msg = MagicMock()
    msg.stop_reason = "end_turn"
    msg.content = [MagicMock(type="text", text=text)]
    msg.usage = MagicMock(input_tokens=100, output_tokens=50)
    return msg


def _make_claude_client(response) -> MagicMock:
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


def _make_input(task: str = "what did we talk about?") -> AgentInput:
    return {
        "task": task,
        "context": {},
        "trace_id": "trace-sem-001",
        "conversation_id": "conv-sem-001",
    }


def _make_conv_service(history=None):
    svc = AsyncMock()
    svc.load_history = AsyncMock(return_value=history or [])
    svc.save_exchange = AsyncMock()
    svc.get_or_create_conversation = AsyncMock(return_value="conv-sem-001")
    return svc


def _make_semantic_service(hits=None):
    svc = AsyncMock()
    svc.search_similar = AsyncMock(return_value=hits or [])
    svc.store = AsyncMock()
    return svc


class TestCruzSearchesSemantic:
    async def test_search_similar_called_with_user_task(self):
        client = _make_claude_client(_make_text_response("answer"))
        conv_svc = _make_conv_service()
        sem_svc = _make_semantic_service()

        agent = CruzAgent()
        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=conv_svc), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=sem_svc), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"):
            await agent.process(_make_input("unique-search-query-text"))

        sem_svc.search_similar.assert_called_once_with("unique-search-query-text", limit=10)

    async def test_semantic_hits_prepended_before_session_history(self):
        """Order: [semantic hits] [session history] [new user message]."""
        semantic_hits = [
            {"role": "user", "content": "old question from another session"},
        ]
        session_history = [
            {"role": "user", "content": "current session first message"},
        ]

        client = _make_claude_client(_make_text_response("ok"))
        conv_svc = _make_conv_service(history=session_history)
        sem_svc = _make_semantic_service(hits=semantic_hits)

        agent = CruzAgent()
        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=conv_svc), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=sem_svc), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"):
            await agent.process(_make_input("new question"))

        messages = client.messages.create.call_args[1]["messages"]
        assert messages[0]["content"] == "old question from another session"
        assert messages[1]["content"] == "current session first message"
        assert messages[2]["content"] == "new question"

    async def test_empty_semantic_hits_still_works(self):
        client = _make_claude_client(_make_text_response("hello"))
        conv_svc = _make_conv_service()
        sem_svc = _make_semantic_service(hits=[])

        agent = CruzAgent()
        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=conv_svc), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=sem_svc), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"):
            result = await agent.process(_make_input("hello"))

        assert result["success"] is True


class TestCruzStoresSemantic:
    async def test_store_called_twice_after_success(self):
        """Both user message and assistant response must be stored."""
        client = _make_claude_client(_make_text_response("response text"))
        conv_svc = _make_conv_service()
        sem_svc = _make_semantic_service()

        agent = CruzAgent()
        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=conv_svc), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=sem_svc), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"):
            await agent.process(_make_input())

        assert sem_svc.store.call_count == 2

    async def test_store_includes_user_content(self):
        client = _make_claude_client(_make_text_response("reply"))
        conv_svc = _make_conv_service()
        sem_svc = _make_semantic_service()

        agent = CruzAgent()
        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=conv_svc), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=sem_svc), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"):
            await agent.process(_make_input("unique-user-task-text-for-store"))

        all_calls = str(sem_svc.store.call_args_list)
        assert "unique-user-task-text-for-store" in all_calls

    async def test_store_includes_assistant_response(self):
        client = _make_claude_client(_make_text_response("unique-assistant-response-for-store"))
        conv_svc = _make_conv_service()
        sem_svc = _make_semantic_service()

        agent = CruzAgent()
        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=conv_svc), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=sem_svc), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"):
            await agent.process(_make_input())

        all_calls = str(sem_svc.store.call_args_list)
        assert "unique-assistant-response-for-store" in all_calls

    async def test_store_not_called_on_error(self):
        import anthropic as ant

        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(
            side_effect=ant.APIConnectionError(request=MagicMock())
        )
        conv_svc = _make_conv_service()
        sem_svc = _make_semantic_service()

        agent = CruzAgent()
        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=conv_svc), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=sem_svc), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"):
            result = await agent.process(_make_input())

        assert result["success"] is False
        sem_svc.store.assert_not_called()
