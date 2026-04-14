"""
Tests for GeneralAgent — Claude-backed catch-all for tasks no specialist handles.

GeneralAgent calls Claude Sonnet 4 with the user's task and returns
a plain-text response.  It is always the fallback from RELAY.

RED phase — must fail before production code exists.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents.base_agent import AgentInput, AgentOutput
from agents.general.general_agent import GeneralAgent


class TestGeneralAgentIsBaseAgent:
    def test_general_agent_subclasses_base_agent(self):
        from agents.base_agent import BaseAgent
        assert issubclass(GeneralAgent, BaseAgent)

    def test_general_agent_can_be_instantiated(self):
        agent = GeneralAgent()
        assert agent is not None

    def test_general_agent_name_is_general(self):
        agent = GeneralAgent()
        assert agent.name == "GENERAL"


class TestGeneralAgentProcess:
    def _make_mock_client(self, response_text: str) -> MagicMock:
        """Build a mock anthropic.AsyncAnthropic that returns response_text."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=response_text)]
        mock_message.usage = MagicMock(input_tokens=50, output_tokens=100)

        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_message)

        mock_client = MagicMock()
        mock_client.messages = mock_messages
        return mock_client

    async def test_process_returns_success_true(self):
        mock_client = self._make_mock_client("The weather is sunny.")
        agent = GeneralAgent()

        with patch("agents.general.general_agent.llm_chat", new=mock_client.messages.create):
            inp: AgentInput = {
                "task": "What is the weather like?",
                "context": {},
                "trace_id": "trace-gen-001",
                "conversation_id": "conv-001",
            }
            result = await agent.process(inp)

        assert result["success"] is True

    async def test_process_returns_claude_response_in_result(self):
        mock_client = self._make_mock_client("Paris is the capital of France.")
        agent = GeneralAgent()

        with patch("agents.general.general_agent.llm_chat", new=mock_client.messages.create):
            inp: AgentInput = {
                "task": "What is the capital of France?",
                "context": {},
                "trace_id": "trace-gen-002",
                "conversation_id": "conv-001",
            }
            result = await agent.process(inp)

        assert result["result"] == "Paris is the capital of France."

    async def test_process_sets_agent_name(self):
        mock_client = self._make_mock_client("answer")
        agent = GeneralAgent()

        with patch("agents.general.general_agent.llm_chat", new=mock_client.messages.create):
            inp: AgentInput = {
                "task": "anything",
                "context": {},
                "trace_id": "trace-gen-003",
                "conversation_id": "conv-001",
            }
            result = await agent.process(inp)

        assert result["agent"] == "GENERAL"

    async def test_process_tracks_tokens_used(self):
        mock_client = self._make_mock_client("answer")
        agent = GeneralAgent()

        with patch("agents.general.general_agent.llm_chat", new=mock_client.messages.create):
            inp: AgentInput = {
                "task": "anything",
                "context": {},
                "trace_id": "trace-gen-004",
                "conversation_id": "conv-001",
            }
            result = await agent.process(inp)

        # input_tokens=50 + output_tokens=100
        assert result["tokens_used"] == 150

    async def test_process_does_not_require_approval(self):
        mock_client = self._make_mock_client("answer")
        agent = GeneralAgent()

        with patch("agents.general.general_agent.llm_chat", new=mock_client.messages.create):
            inp: AgentInput = {
                "task": "anything",
                "context": {},
                "trace_id": "trace-gen-005",
                "conversation_id": "conv-001",
            }
            result = await agent.process(inp)

        assert result["requires_approval"] is False

    async def test_process_calls_claude_with_task(self):
        mock_client = self._make_mock_client("answer")
        agent = GeneralAgent()

        with patch("agents.general.general_agent.llm_chat", new=mock_client.messages.create):
            inp: AgentInput = {
                "task": "Explain quantum computing",
                "context": {},
                "trace_id": "trace-gen-006",
                "conversation_id": "conv-001",
            }
            await agent.process(inp)

        create_call = mock_client.messages.create.call_args
        # The task must appear somewhere in the messages passed to Claude
        messages_arg = create_call[1].get("messages") or create_call[0][0]
        assert any("Explain quantum computing" in str(m) for m in messages_arg)

    async def test_handle_error_on_api_failure(self):
        import anthropic

        mock_client = MagicMock()
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APIConnectionError(request=MagicMock())
        )

        agent = GeneralAgent()
        with patch("agents.general.general_agent.llm_chat", new=mock_client.messages.create), \
             patch("agents.general.general_agent.get_db_service"):
            inp: AgentInput = {
                "task": "anything",
                "context": {},
                "trace_id": "trace-gen-err",
                "conversation_id": "conv-001",
            }
            result = await agent.process(inp)

        assert result["success"] is False
        assert result["error"] is not None


class TestGeneralAgentLogging:
    def _make_mock_client(self, response_text: str = "answer") -> MagicMock:
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=response_text)]
        mock_message.usage = MagicMock(input_tokens=10, output_tokens=20)
        mock_client = MagicMock()
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)
        return mock_client

    async def test_log_called_on_success(self):
        agent = GeneralAgent()
        with patch("agents.general.general_agent.anthropic.AsyncAnthropic", return_value=self._make_mock_client()), \
             patch("agents.general.general_agent.get_db_service"):
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process({
                    "task": "hello",
                    "context": {},
                    "trace_id": "trace-log-ok",
                    "conversation_id": "conv-log-001",
                })
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "success"

    async def test_log_called_on_error(self):
        import anthropic as _anthropic
        mock_client = MagicMock()
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=_anthropic.APIConnectionError(request=MagicMock())
        )
        agent = GeneralAgent()
        with patch("agents.general.general_agent.llm_chat", new=mock_client.messages.create), \
             patch("agents.general.general_agent.get_db_service"):
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process({
                    "task": "anything",
                    "context": {},
                    "trace_id": "trace-log-err",
                    "conversation_id": "conv-log-002",
                })
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "error"

    async def test_log_failure_does_not_crash_agent(self):
        agent = GeneralAgent()
        with patch("agents.general.general_agent.anthropic.AsyncAnthropic", return_value=self._make_mock_client()), \
             patch("agents.general.general_agent.get_db_service"):
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                mock_log.side_effect = Exception("DB dead")
                result = await agent.process({
                    "task": "hello",
                    "context": {},
                    "trace_id": "trace-log-fail",
                    "conversation_id": "conv-log-003",
                })
        assert result["success"] is True
