"""
Tests for agent logging to the agent_logs table.

BaseAgent.log() must:
  - Insert one row into agent_logs
  - Include: trace_id, agent name, action, status, tokens_used, duration_ms
  - Accept input_data and output_data as dicts (stored as JSON)
  - Swallow DB errors gracefully — logging must never crash an agent

CruzAgent integration:
  - Calls self.log() after every successful process() call (status="success")
  - Calls self.log() after every failed process() call (status="error")
  - Log includes the correct trace_id from AgentInput

RED phase — must fail before log() is implemented.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from agents.cruz.cruz_agent import CruzAgent


# ---------------------------------------------------------------------------
# Minimal concrete agent for BaseAgent tests
# ---------------------------------------------------------------------------

class _SimpleAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.name = "SIMPLE"

    async def process(self, input: AgentInput) -> AgentOutput:
        return AgentOutput(
            success=True, result="ok", agent=self.name,
            duration_ms=10, tokens_used=5, error=None,
            requires_approval=False, approval_prompt=None,
        )


def _make_db():
    db = AsyncMock()
    db.execute = AsyncMock(return_value="INSERT 0 1")
    return db


# ---------------------------------------------------------------------------
# BaseAgent.log() — interface
# ---------------------------------------------------------------------------

class TestBaseAgentLogInterface:
    def test_base_agent_has_log_method(self):
        assert hasattr(_SimpleAgent(), "log")

    def test_log_is_coroutine(self):
        import asyncio
        agent = _SimpleAgent()
        db = _make_db()
        coro = agent.log(
            db=db,
            trace_id="t1",
            status="success",
            input_data={},
            output_data={},
            tokens_used=0,
            duration_ms=0,
        )
        assert asyncio.iscoroutine(coro)
        # clean up unawaited coroutine
        coro.close()


# ---------------------------------------------------------------------------
# BaseAgent.log() — DB writes
# ---------------------------------------------------------------------------

class TestBaseAgentLogWrites:
    async def test_log_calls_db_execute(self):
        agent = _SimpleAgent()
        db = _make_db()

        await agent.log(
            db=db, trace_id="t1", status="success",
            input_data={}, output_data={}, tokens_used=10, duration_ms=50,
        )

        db.execute.assert_called_once()

    async def test_log_inserts_into_agent_logs(self):
        agent = _SimpleAgent()
        db = _make_db()

        await agent.log(
            db=db, trace_id="t1", status="success",
            input_data={}, output_data={}, tokens_used=10, duration_ms=50,
        )

        query = db.execute.call_args[0][0]
        assert "agent_logs" in query.lower()

    async def test_log_includes_trace_id(self):
        agent = _SimpleAgent()
        db = _make_db()

        await agent.log(
            db=db, trace_id="unique-trace-id-abc", status="success",
            input_data={}, output_data={}, tokens_used=0, duration_ms=0,
        )

        all_args = str(db.execute.call_args)
        assert "unique-trace-id-abc" in all_args

    async def test_log_includes_agent_name(self):
        agent = _SimpleAgent()
        db = _make_db()

        await agent.log(
            db=db, trace_id="t1", status="success",
            input_data={}, output_data={}, tokens_used=0, duration_ms=0,
        )

        all_args = str(db.execute.call_args)
        assert "SIMPLE" in all_args

    async def test_log_includes_status(self):
        agent = _SimpleAgent()
        db = _make_db()

        await agent.log(
            db=db, trace_id="t1", status="error",
            input_data={}, output_data={}, tokens_used=0, duration_ms=0,
        )

        all_args = str(db.execute.call_args)
        assert "error" in all_args

    async def test_log_includes_tokens_used(self):
        agent = _SimpleAgent()
        db = _make_db()

        await agent.log(
            db=db, trace_id="t1", status="success",
            input_data={}, output_data={}, tokens_used=999, duration_ms=0,
        )

        all_args = str(db.execute.call_args)
        assert "999" in all_args

    async def test_log_includes_duration_ms(self):
        agent = _SimpleAgent()
        db = _make_db()

        await agent.log(
            db=db, trace_id="t1", status="success",
            input_data={}, output_data={}, tokens_used=0, duration_ms=1234,
        )

        all_args = str(db.execute.call_args)
        assert "1234" in all_args

    async def test_log_never_raises_on_db_error(self):
        """DB failures must be swallowed — logging must not crash agents."""
        agent = _SimpleAgent()
        db = _make_db()
        db.execute = AsyncMock(side_effect=Exception("DB connection lost"))

        # Should not raise
        await agent.log(
            db=db, trace_id="t1", status="success",
            input_data={}, output_data={}, tokens_used=0, duration_ms=0,
        )


# ---------------------------------------------------------------------------
# CruzAgent integration — log() called on success and error paths
# ---------------------------------------------------------------------------

def _make_text_response(text: str) -> MagicMock:
    msg = MagicMock()
    msg.stop_reason = "end_turn"
    msg.content = [MagicMock(type="text", text=text)]
    msg.usage = MagicMock(input_tokens=100, output_tokens=50)
    return msg


def _make_input(trace_id: str = "trace-log-001") -> AgentInput:
    return {
        "task": "test task",
        "context": {},
        "trace_id": trace_id,
        "conversation_id": "conv-log-001",
    }


def _make_conv_service():
    svc = AsyncMock()
    svc.load_history = AsyncMock(return_value=[])
    svc.save_exchange = AsyncMock()
    svc.get_or_create_conversation = AsyncMock(return_value="conv-log-001")
    return svc


def _make_sem_service():
    svc = AsyncMock()
    svc.search_similar = AsyncMock(return_value=[])
    svc.store = AsyncMock()
    return svc


class TestCruzAgentLogging:
    async def test_log_called_after_successful_process(self):
        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(return_value=_make_text_response("answer"))

        mock_db = _make_db()
        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=client), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=_make_conv_service()), \
             patch("agents.cruz.cruz_agent.get_db_service", return_value=mock_db), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_make_sem_service()), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"), \
             patch.object(agent, "log", new=AsyncMock()) as mock_log:
            await agent.process(_make_input())

        mock_log.assert_called()

    async def test_log_called_with_success_status(self):
        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(return_value=_make_text_response("answer"))

        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=client), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=_make_conv_service()), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_make_sem_service()), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"), \
             patch.object(agent, "log", new=AsyncMock()) as mock_log:
            await agent.process(_make_input())

        call_kwargs = str(mock_log.call_args)
        assert "success" in call_kwargs

    async def test_log_called_on_error_path(self):
        import anthropic as ant

        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(
            side_effect=ant.APIConnectionError(request=MagicMock())
        )

        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=client), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=_make_conv_service()), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_make_sem_service()), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"), \
             patch.object(agent, "log", new=AsyncMock()) as mock_log:
            result = await agent.process(_make_input())

        assert result["success"] is False
        mock_log.assert_called()

    async def test_log_called_with_error_status_on_failure(self):
        import anthropic as ant

        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(
            side_effect=ant.APIConnectionError(request=MagicMock())
        )

        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=client), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=_make_conv_service()), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_make_sem_service()), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"), \
             patch.object(agent, "log", new=AsyncMock()) as mock_log:
            await agent.process(_make_input())

        call_kwargs = str(mock_log.call_args)
        assert "error" in call_kwargs

    async def test_log_receives_trace_id(self):
        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(return_value=_make_text_response("ok"))

        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=client), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=_make_conv_service()), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_make_sem_service()), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"), \
             patch.object(agent, "log", new=AsyncMock()) as mock_log:
            await agent.process(_make_input("unique-trace-for-log-test"))

        call_kwargs = str(mock_log.call_args)
        assert "unique-trace-for-log-test" in call_kwargs
