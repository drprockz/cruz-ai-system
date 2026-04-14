"""
Tests for CruzAgent conversation persistence integration.

Verifies that CruzAgent:
  - Loads history from ConversationService before calling Claude
  - Includes history in the messages array sent to Claude
  - Saves the new exchange after a successful response
  - Passes conversation_id through to ConversationService

RED phase — must fail before wiring is done.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput
from agents.cruz.cruz_agent import CruzAgent


@pytest.fixture(autouse=True)
def _mock_semantic_service():
    """Silence SemanticMemoryService for all tests in this module."""
    mock_sem = AsyncMock()
    mock_sem.search_similar = AsyncMock(return_value=[])
    mock_sem.store = AsyncMock()
    with patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=mock_sem), \
         patch("agents.cruz.cruz_agent.get_qdrant_service"), \
         patch("agents.cruz.cruz_agent.get_embedding_service"):
        yield


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


def _make_input(conversation_id: str = "conv-persist-001") -> AgentInput:
    return {
        "task": "what did we discuss before?",
        "context": {},
        "trace_id": "trace-persist-001",
        "conversation_id": conversation_id,
    }


class TestCruzLoadsHistory:
    async def test_load_history_called_with_conversation_id(self):
        client = _make_claude_client(_make_text_response("I remember now."))
        agent = CruzAgent()

        mock_conv_service = AsyncMock()
        mock_conv_service.load_history = AsyncMock(return_value=[])
        mock_conv_service.save_exchange = AsyncMock()
        mock_conv_service.get_or_create_conversation = AsyncMock(return_value="conv-persist-001")

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            with patch("agents.cruz.cruz_agent.ConversationService", return_value=mock_conv_service):
                with patch("agents.cruz.cruz_agent.get_db_service"):
                    await agent.process(_make_input("conv-persist-001"))

        mock_conv_service.load_history.assert_called_once_with("conv-persist-001")

    async def test_history_prepended_to_claude_messages(self):
        """Prior turns from DB must appear before the new user message in Claude's input."""
        history = [
            {"role": "user", "content": "My name is Darshan"},
            {"role": "assistant", "content": "Nice to meet you, Darshan!"},
        ]
        client = _make_claude_client(_make_text_response("You told me your name earlier."))
        agent = CruzAgent()

        mock_conv_service = AsyncMock()
        mock_conv_service.load_history = AsyncMock(return_value=history)
        mock_conv_service.save_exchange = AsyncMock()
        mock_conv_service.get_or_create_conversation = AsyncMock(return_value="conv-persist-001")

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            with patch("agents.cruz.cruz_agent.ConversationService", return_value=mock_conv_service):
                with patch("agents.cruz.cruz_agent.get_db_service"):
                    await agent.process(_make_input())

        messages_sent = client.messages.create.call_args[1]["messages"]
        assert messages_sent[0]["content"] == "My name is Darshan"
        assert messages_sent[1]["content"] == "Nice to meet you, Darshan!"
        assert messages_sent[2]["content"] == "what did we discuss before?"

    async def test_empty_history_still_works(self):
        """New conversation with no history — should not crash."""
        client = _make_claude_client(_make_text_response("Hello!"))
        agent = CruzAgent()

        mock_conv_service = AsyncMock()
        mock_conv_service.load_history = AsyncMock(return_value=[])
        mock_conv_service.save_exchange = AsyncMock()
        mock_conv_service.get_or_create_conversation = AsyncMock(return_value="new-conv")

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            with patch("agents.cruz.cruz_agent.ConversationService", return_value=mock_conv_service):
                with patch("agents.cruz.cruz_agent.get_db_service"):
                    result = await agent.process(_make_input("new-conv"))

        assert result["success"] is True
        messages_sent = client.messages.create.call_args[1]["messages"]
        assert len(messages_sent) == 1
        assert messages_sent[0]["role"] == "user"


class TestCruzSavesExchange:
    async def test_save_exchange_called_after_success(self):
        client = _make_claude_client(_make_text_response("The answer is 42."))
        agent = CruzAgent()

        mock_conv_service = AsyncMock()
        mock_conv_service.load_history = AsyncMock(return_value=[])
        mock_conv_service.save_exchange = AsyncMock()
        mock_conv_service.get_or_create_conversation = AsyncMock(return_value="conv-persist-001")

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            with patch("agents.cruz.cruz_agent.ConversationService", return_value=mock_conv_service):
                with patch("agents.cruz.cruz_agent.get_db_service"):
                    await agent.process(_make_input())

        mock_conv_service.save_exchange.assert_called_once()

    async def test_save_exchange_receives_conversation_id(self):
        client = _make_claude_client(_make_text_response("Done."))
        agent = CruzAgent()

        mock_conv_service = AsyncMock()
        mock_conv_service.load_history = AsyncMock(return_value=[])
        mock_conv_service.save_exchange = AsyncMock()
        mock_conv_service.get_or_create_conversation = AsyncMock(return_value="conv-save-test")

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            with patch("agents.cruz.cruz_agent.ConversationService", return_value=mock_conv_service):
                with patch("agents.cruz.cruz_agent.get_db_service"):
                    await agent.process(_make_input("conv-save-test"))

        save_args = mock_conv_service.save_exchange.call_args
        assert "conv-save-test" in str(save_args)

    async def test_save_exchange_receives_user_task(self):
        client = _make_claude_client(_make_text_response("Done."))
        agent = CruzAgent()

        mock_conv_service = AsyncMock()
        mock_conv_service.load_history = AsyncMock(return_value=[])
        mock_conv_service.save_exchange = AsyncMock()
        mock_conv_service.get_or_create_conversation = AsyncMock(return_value="conv-1")

        inp = {
            "task": "unique-task-string-xyz",
            "context": {},
            "trace_id": "t1",
            "conversation_id": "conv-1",
        }

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            with patch("agents.cruz.cruz_agent.ConversationService", return_value=mock_conv_service):
                with patch("agents.cruz.cruz_agent.get_db_service"):
                    await agent.process(inp)

        save_args = str(mock_conv_service.save_exchange.call_args)
        assert "unique-task-string-xyz" in save_args

    async def test_save_exchange_receives_assistant_response(self):
        client = _make_claude_client(_make_text_response("unique-response-string-abc"))
        agent = CruzAgent()

        mock_conv_service = AsyncMock()
        mock_conv_service.load_history = AsyncMock(return_value=[])
        mock_conv_service.save_exchange = AsyncMock()
        mock_conv_service.get_or_create_conversation = AsyncMock(return_value="conv-1")

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            with patch("agents.cruz.cruz_agent.ConversationService", return_value=mock_conv_service):
                with patch("agents.cruz.cruz_agent.get_db_service"):
                    await agent.process(_make_input())

        save_args = str(mock_conv_service.save_exchange.call_args)
        assert "unique-response-string-abc" in save_args

    async def test_save_not_called_on_agent_error(self):
        """If Claude errors, we do not save a broken exchange."""
        import anthropic as ant

        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(
            side_effect=ant.APIConnectionError(request=MagicMock())
        )
        agent = CruzAgent()

        mock_conv_service = AsyncMock()
        mock_conv_service.load_history = AsyncMock(return_value=[])
        mock_conv_service.save_exchange = AsyncMock()
        mock_conv_service.get_or_create_conversation = AsyncMock(return_value="conv-1")

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            with patch("agents.cruz.cruz_agent.ConversationService", return_value=mock_conv_service):
                with patch("agents.cruz.cruz_agent.get_db_service"):
                    result = await agent.process(_make_input())

        assert result["success"] is False
        mock_conv_service.save_exchange.assert_not_called()
