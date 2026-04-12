"""
Tests for BaseAgent abstract class.
RED phase — these tests must fail before any production code is written.
"""

import pytest
import time
from typing import Any, Dict

# These imports will fail until we create agents/base_agent.py
from agents.base_agent import AgentInput, AgentOutput, BaseAgent


class TestAgentInputTypedDict:
    def test_agent_input_has_task_field(self):
        inp: AgentInput = {
            "task": "Do something",
            "context": {},
            "trace_id": "trace-001",
            "conversation_id": "conv-001",
        }
        assert inp["task"] == "Do something"

    def test_agent_input_has_context_field(self):
        inp: AgentInput = {
            "task": "Do something",
            "context": {"key": "value"},
            "trace_id": "trace-001",
            "conversation_id": "conv-001",
        }
        assert inp["context"] == {"key": "value"}

    def test_agent_input_has_trace_id_field(self):
        inp: AgentInput = {
            "task": "Do something",
            "context": {},
            "trace_id": "trace-abc-123",
            "conversation_id": "conv-001",
        }
        assert inp["trace_id"] == "trace-abc-123"

    def test_agent_input_has_conversation_id_field(self):
        inp: AgentInput = {
            "task": "Do something",
            "context": {},
            "trace_id": "trace-001",
            "conversation_id": "conv-xyz-456",
        }
        assert inp["conversation_id"] == "conv-xyz-456"


class TestAgentOutputTypedDict:
    def test_agent_output_has_success_field(self):
        out: AgentOutput = {
            "success": True,
            "result": "done",
            "agent": "TestAgent",
            "duration_ms": 42,
            "tokens_used": 100,
            "error": None,
            "requires_approval": False,
            "approval_prompt": None,
        }
        assert out["success"] is True

    def test_agent_output_has_result_field(self):
        out: AgentOutput = {
            "success": True,
            "result": {"output": "hello"},
            "agent": "TestAgent",
            "duration_ms": 10,
            "tokens_used": 50,
            "error": None,
            "requires_approval": False,
            "approval_prompt": None,
        }
        assert out["result"] == {"output": "hello"}

    def test_agent_output_has_agent_field(self):
        out: AgentOutput = {
            "success": True,
            "result": None,
            "agent": "FORGE",
            "duration_ms": 10,
            "tokens_used": 0,
            "error": None,
            "requires_approval": False,
            "approval_prompt": None,
        }
        assert out["agent"] == "FORGE"

    def test_agent_output_has_duration_ms_field(self):
        out: AgentOutput = {
            "success": True,
            "result": None,
            "agent": "TestAgent",
            "duration_ms": 1234,
            "tokens_used": 0,
            "error": None,
            "requires_approval": False,
            "approval_prompt": None,
        }
        assert out["duration_ms"] == 1234

    def test_agent_output_has_tokens_used_field(self):
        out: AgentOutput = {
            "success": True,
            "result": None,
            "agent": "TestAgent",
            "duration_ms": 10,
            "tokens_used": 999,
            "error": None,
            "requires_approval": False,
            "approval_prompt": None,
        }
        assert out["tokens_used"] == 999

    def test_agent_output_has_error_field(self):
        out: AgentOutput = {
            "success": False,
            "result": None,
            "agent": "TestAgent",
            "duration_ms": 5,
            "tokens_used": 0,
            "error": "Something went wrong",
            "requires_approval": False,
            "approval_prompt": None,
        }
        assert out["error"] == "Something went wrong"

    def test_agent_output_has_requires_approval_field(self):
        out: AgentOutput = {
            "success": True,
            "result": "draft email ready",
            "agent": "ECHO",
            "duration_ms": 200,
            "tokens_used": 300,
            "error": None,
            "requires_approval": True,
            "approval_prompt": "Send this email?",
        }
        assert out["requires_approval"] is True

    def test_agent_output_has_approval_prompt_field(self):
        out: AgentOutput = {
            "success": True,
            "result": "deploy script ready",
            "agent": "TITAN",
            "duration_ms": 500,
            "tokens_used": 400,
            "error": None,
            "requires_approval": True,
            "approval_prompt": "Deploy to production?",
        }
        assert out["approval_prompt"] == "Deploy to production?"


class TestBaseAgentIsAbstract:
    def test_cannot_instantiate_base_agent_directly(self):
        with pytest.raises(TypeError):
            BaseAgent()  # type: ignore

    def test_base_agent_process_is_abstract(self):
        """Subclass without process() must raise TypeError on instantiation."""

        class IncompleteAgent(BaseAgent):
            pass  # does not implement process()

        with pytest.raises(TypeError):
            IncompleteAgent()  # type: ignore


class ConcreteTestAgent(BaseAgent):
    """Minimal concrete subclass for testing BaseAgent behaviour."""

    async def process(self, input: AgentInput) -> AgentOutput:
        return {
            "success": True,
            "result": f"processed: {input['task']}",
            "agent": self.name,
            "duration_ms": 1,
            "tokens_used": 0,
            "error": None,
            "requires_approval": False,
            "approval_prompt": None,
        }


class TestConcreteAgentInstantiation:
    def test_concrete_agent_can_be_instantiated(self):
        agent = ConcreteTestAgent()
        assert agent is not None

    def test_agent_has_name_attribute(self):
        agent = ConcreteTestAgent()
        assert hasattr(agent, "name")
        assert isinstance(agent.name, str)
        assert len(agent.name) > 0

    async def test_process_returns_agent_output(self):
        agent = ConcreteTestAgent()
        inp: AgentInput = {
            "task": "hello",
            "context": {},
            "trace_id": "trace-001",
            "conversation_id": "conv-001",
        }
        result = await agent.process(inp)
        assert result["success"] is True
        assert "processed: hello" in result["result"]

    async def test_process_result_contains_agent_name(self):
        agent = ConcreteTestAgent()
        inp: AgentInput = {
            "task": "test task",
            "context": {},
            "trace_id": "trace-002",
            "conversation_id": "conv-002",
        }
        result = await agent.process(inp)
        assert result["agent"] == agent.name


class TestHandleError:
    def test_handle_error_returns_agent_output_with_success_false(self):
        agent = ConcreteTestAgent()
        error = ValueError("something broke")
        trace_id = "trace-err-001"
        result = agent.handle_error(error, trace_id)
        assert result["success"] is False

    def test_handle_error_includes_error_message(self):
        agent = ConcreteTestAgent()
        error = RuntimeError("database timeout")
        result = agent.handle_error(error, "trace-001")
        assert result["error"] is not None
        assert "database timeout" in result["error"]

    def test_handle_error_sets_agent_name(self):
        agent = ConcreteTestAgent()
        result = agent.handle_error(Exception("oops"), "trace-001")
        assert result["agent"] == agent.name

    def test_handle_error_sets_requires_approval_false(self):
        agent = ConcreteTestAgent()
        result = agent.handle_error(Exception("oops"), "trace-001")
        assert result["requires_approval"] is False

    def test_handle_error_sets_approval_prompt_none(self):
        agent = ConcreteTestAgent()
        result = agent.handle_error(Exception("oops"), "trace-001")
        assert result["approval_prompt"] is None

    def test_handle_error_result_is_none(self):
        agent = ConcreteTestAgent()
        result = agent.handle_error(Exception("oops"), "trace-001")
        assert result["result"] is None
