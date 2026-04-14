"""
Tests for CruzAgent — main orchestrator.

CruzAgent is what the user always talks to. It:
  1. Loads conversation history from PostgreSQL (session memory)
  2. Calls Claude with tool_use enabled so Claude can invoke specialist agents
  3. Executes any tool_use calls Claude returns (dispatching to FORGE, ECHO, etc.)
  4. Returns a final text response

Tests here cover the contract, routing behaviour, and error handling.
They mock all I/O (Claude API, DB, agent calls) to stay fast and deterministic.

RED phase — must fail before production code exists.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import anthropic

from agents.base_agent import AgentInput, AgentOutput
from agents.cruz.cruz_agent import CruzAgent, CRUZ_TOOLS


@pytest.fixture(autouse=True)
def _mock_external_services():
    """Silence DB, ConversationService, and SemanticMemoryService for all tests."""
    mock_conv = AsyncMock()
    mock_conv.load_history = AsyncMock(return_value=[])
    mock_conv.save_exchange = AsyncMock()
    mock_conv.get_or_create_conversation = AsyncMock(return_value="conv-001")

    mock_sem = AsyncMock()
    mock_sem.search_similar = AsyncMock(return_value=[])
    mock_sem.store = AsyncMock()

    with patch("agents.cruz.cruz_agent.get_db_service"), \
         patch("agents.cruz.cruz_agent.ConversationService", return_value=mock_conv), \
         patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=mock_sem), \
         patch("agents.cruz.cruz_agent.get_qdrant_service"), \
         patch("agents.cruz.cruz_agent.get_embedding_service"):
        yield


class TestCruzAgentIsBaseAgent:
    def test_cruz_agent_subclasses_base_agent(self):
        from agents.base_agent import BaseAgent
        assert issubclass(CruzAgent, BaseAgent)

    def test_cruz_agent_can_be_instantiated(self):
        agent = CruzAgent()
        assert agent is not None

    def test_cruz_agent_name_is_cruz(self):
        agent = CruzAgent()
        assert agent.name == "CRUZ"


class TestCruzTools:
    def test_cruz_tools_is_list(self):
        assert isinstance(CRUZ_TOOLS, list)

    def test_cruz_tools_not_empty(self):
        assert len(CRUZ_TOOLS) > 0

    def test_each_tool_has_name(self):
        for tool in CRUZ_TOOLS:
            assert "name" in tool, f"Tool missing 'name': {tool}"

    def test_each_tool_has_description(self):
        for tool in CRUZ_TOOLS:
            assert "description" in tool, f"Tool missing 'description': {tool}"

    def test_each_tool_has_input_schema(self):
        for tool in CRUZ_TOOLS:
            assert "input_schema" in tool, f"Tool missing 'input_schema': {tool}"

    def test_forge_tool_present(self):
        names = [t["name"] for t in CRUZ_TOOLS]
        assert "forge" in names, f"Expected 'forge' tool in {names}"

    def test_echo_tool_present(self):
        names = [t["name"] for t in CRUZ_TOOLS]
        assert "echo" in names, f"Expected 'echo' tool in {names}"


class TestCruzAgentProcessSimpleResponse:
    """Claude returns a plain text message (no tool_use)."""

    def _make_text_response(self, text: str) -> MagicMock:
        mock_msg = MagicMock()
        mock_msg.stop_reason = "end_turn"
        mock_msg.content = [MagicMock(type="text", text=text)]
        mock_msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        return mock_msg

    def _make_claude_client(self, response: MagicMock) -> MagicMock:
        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(return_value=response)
        return client

    async def test_returns_success_true_for_text_response(self):
        resp = self._make_text_response("Hello! How can I help?")
        client = self._make_claude_client(resp)
        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            inp: AgentInput = {
                "task": "hi there",
                "context": {},
                "trace_id": "trace-cruz-001",
                "conversation_id": "conv-001",
            }
            result = await agent.process(inp)

        assert result["success"] is True

    async def test_returns_text_in_result(self):
        resp = self._make_text_response("I am CRUZ, your AI assistant.")
        client = self._make_claude_client(resp)
        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            inp: AgentInput = {
                "task": "who are you?",
                "context": {},
                "trace_id": "trace-cruz-002",
                "conversation_id": "conv-001",
            }
            result = await agent.process(inp)

        assert result["result"] == "I am CRUZ, your AI assistant."

    async def test_sets_agent_name_to_cruz(self):
        resp = self._make_text_response("answer")
        client = self._make_claude_client(resp)
        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            inp: AgentInput = {
                "task": "anything",
                "context": {},
                "trace_id": "trace-cruz-003",
                "conversation_id": "conv-001",
            }
            result = await agent.process(inp)

        assert result["agent"] == "CRUZ"

    async def test_tracks_tokens_used(self):
        resp = self._make_text_response("answer")
        client = self._make_claude_client(resp)
        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            inp: AgentInput = {
                "task": "anything",
                "context": {},
                "trace_id": "trace-cruz-004",
                "conversation_id": "conv-001",
            }
            result = await agent.process(inp)

        assert result["tokens_used"] == 150  # 100 input + 50 output

    async def test_does_not_require_approval_for_text(self):
        resp = self._make_text_response("answer")
        client = self._make_claude_client(resp)
        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            inp: AgentInput = {
                "task": "anything",
                "context": {},
                "trace_id": "trace-cruz-005",
                "conversation_id": "conv-001",
            }
            result = await agent.process(inp)

        assert result["requires_approval"] is False

    async def test_passes_tools_to_claude(self):
        resp = self._make_text_response("answer")
        client = self._make_claude_client(resp)
        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            inp: AgentInput = {
                "task": "write me a function",
                "context": {},
                "trace_id": "trace-cruz-006",
                "conversation_id": "conv-001",
            }
            await agent.process(inp)

        call_kwargs = client.messages.create.call_args[1]
        assert "tools" in call_kwargs
        assert len(call_kwargs["tools"]) > 0


class TestCruzAgentToolUse:
    """Claude returns a tool_use block; CRUZ dispatches and returns final text."""

    def _make_tool_use_response(self, tool_name: str, tool_input: dict) -> MagicMock:
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "toolu_test_001"
        tool_block.name = tool_name
        tool_block.input = tool_input

        msg = MagicMock()
        msg.stop_reason = "tool_use"
        msg.content = [tool_block]
        msg.usage = MagicMock(input_tokens=200, output_tokens=30)
        return msg

    def _make_final_text_response(self, text: str) -> MagicMock:
        msg = MagicMock()
        msg.stop_reason = "end_turn"
        msg.content = [MagicMock(type="text", text=text)]
        msg.usage = MagicMock(input_tokens=50, output_tokens=80)
        return msg

    async def test_tool_use_dispatches_to_agent(self):
        """When Claude returns tool_use for 'forge', CruzAgent calls ForgeAgent."""
        tool_resp = self._make_tool_use_response("forge", {"task": "write hello world"})
        final_resp = self._make_final_text_response("Here is the code: ...")

        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(side_effect=[tool_resp, final_resp])

        mock_forge_result = AgentOutput(
            success=True,
            result="def hello(): return 'world'",
            agent="FORGE",
            duration_ms=100,
            tokens_used=500,
            error=None,
            requires_approval=False,
            approval_prompt=None,
        )

        agent = CruzAgent()
        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            with patch.object(agent, "_dispatch_tool", new=AsyncMock(return_value=mock_forge_result)):
                inp: AgentInput = {
                    "task": "write a hello world function",
                    "context": {},
                    "trace_id": "trace-tool-001",
                    "conversation_id": "conv-001",
                }
                result = await agent.process(inp)

        assert result["success"] is True

    async def test_requires_approval_propagates_from_tool(self):
        """When a tool returns requires_approval=True, CruzAgent surfaces it."""
        tool_resp = self._make_tool_use_response("echo", {"task": "send email to client"})
        # No second Claude call needed — approval gates halt processing

        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(return_value=tool_resp)

        mock_echo_result = AgentOutput(
            success=True,
            result="Draft email: Dear Client...",
            agent="ECHO",
            duration_ms=200,
            tokens_used=300,
            error=None,
            requires_approval=True,
            approval_prompt="Send this email to the client?",
        )

        agent = CruzAgent()
        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            with patch.object(agent, "_dispatch_tool", new=AsyncMock(return_value=mock_echo_result)):
                inp: AgentInput = {
                    "task": "send the email to the client",
                    "context": {},
                    "trace_id": "trace-approval-001",
                    "conversation_id": "conv-001",
                }
                result = await agent.process(inp)

        assert result["requires_approval"] is True
        assert result["approval_prompt"] == "Send this email to the client?"


class TestCruzAgentErrorHandling:
    async def test_returns_failure_on_claude_error(self):
        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(
            side_effect=anthropic.APIConnectionError(request=MagicMock())
        )

        agent = CruzAgent()
        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            inp: AgentInput = {
                "task": "anything",
                "context": {},
                "trace_id": "trace-err-001",
                "conversation_id": "conv-001",
            }
            result = await agent.process(inp)

        assert result["success"] is False
        assert result["error"] is not None


class TestCruzDispatchTool:
    """Unit-tests for the internal _dispatch_tool() method."""

    async def test_dispatch_forge_tool_returns_agent_output(self):
        """_dispatch_tool('forge', ...) must call ForgeAgent and return its output."""
        import agents.cruz.cruz_agent as cruz_module

        agent = CruzAgent()

        mock_forge_output = AgentOutput(
            success=True,
            result="code result",
            agent="FORGE",
            duration_ms=50,
            tokens_used=100,
            error=None,
            requires_approval=False,
            approval_prompt=None,
        )

        mock_instance = AsyncMock()
        mock_instance.process = AsyncMock(return_value=mock_forge_output)
        MockForge = MagicMock(return_value=mock_instance)

        # Patch the tool map dict entry so _dispatch_tool picks up the mock
        with patch.dict(cruz_module._TOOL_AGENT_MAP, {"forge": MockForge}):
            result = await agent._dispatch_tool(
                tool_name="forge",
                tool_input={"task": "write hello world"},
                trace_id="trace-dispatch-001",
                conversation_id="conv-001",
            )

        assert result["agent"] == "FORGE"
        assert result["success"] is True

    async def test_dispatch_unknown_tool_returns_error(self):
        """_dispatch_tool with an unknown tool name must return success=False."""
        agent = CruzAgent()

        result = await agent._dispatch_tool(
            tool_name="nonexistent_agent",
            tool_input={"task": "do something"},
            trace_id="trace-dispatch-err",
            conversation_id="conv-001",
        )

        assert result["success"] is False
        assert result["error"] is not None
