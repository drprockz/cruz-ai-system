"""
Tests for CruzAgent's RELAY pre-filter integration (R17).

RELAY runs before the first Claude call. If classify(task) returns an
agent name that exists in CRUZ_TOOLS, the tool list sent to Claude is
narrowed to that single tool. Otherwise the full tool list is sent.

Rationale: deterministic keyword hits ("FORGE, refactor X", "deploy to
production") don't need Claude to pick the tool — RELAY already knows.
Narrowing the list saves tokens and makes the tool choice deterministic
while still letting Claude reason + execute. When no keyword matches,
behavior is unchanged.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput


def _make_input(task: str, device: str = None) -> AgentInput:
    ctx = {}
    if device:
        ctx["device"] = device
    return {
        "task": task,
        "context": ctx,
        "trace_id": "trace-prefilter",
        "conversation_id": "conv-prefilter",
    }


def _end_turn_response(text: str = "done"):
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [block]
    resp.usage = MagicMock(input_tokens=10, output_tokens=5)
    return resp


def _mock_claude(response):
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


def _mock_conv_service():
    svc = AsyncMock()
    svc.get_or_create_conversation = AsyncMock(return_value="conv-prefilter")
    svc.load_history = AsyncMock(return_value=[])
    svc.save_exchange = AsyncMock()
    return svc


def _mock_sem_service():
    svc = AsyncMock()
    svc.search_similar = AsyncMock(return_value=[])
    svc.store = AsyncMock()
    return svc


def _cruz_patches():
    return (
        patch("agents.cruz.cruz_agent.ConversationService",
              return_value=_mock_conv_service()),
        patch("agents.cruz.cruz_agent.SemanticMemoryService",
              return_value=_mock_sem_service()),
        patch("agents.cruz.cruz_agent.get_db_service"),
        patch("agents.cruz.cruz_agent.get_qdrant_service"),
        patch("agents.cruz.cruz_agent.get_embedding_service"),
    )


@pytest.mark.asyncio
class TestCruzRelayPrefilter:
    async def test_no_keyword_match_passes_full_tool_list(self):
        from agents.cruz.cruz_agent import CruzAgent, CRUZ_TOOLS
        claude = _mock_claude(_end_turn_response())
        conv, sem, db, qd, emb = _cruz_patches()
        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic",
                   return_value=claude), conv, sem, db, qd, emb:
            await CruzAgent().process(_make_input("Just chatting, hi!"))

        sent_tools = claude.messages.create.call_args.kwargs["tools"]
        assert len(sent_tools) == len(CRUZ_TOOLS)

    async def test_forge_keyword_narrows_tools_to_forge_only(self):
        from agents.cruz.cruz_agent import CruzAgent
        claude = _mock_claude(_end_turn_response())
        conv, sem, db, qd, emb = _cruz_patches()
        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic",
                   return_value=claude), conv, sem, db, qd, emb:
            await CruzAgent().process(_make_input(
                "FORGE, write a function that parses CSV"
            ))

        sent_tools = claude.messages.create.call_args.kwargs["tools"]
        assert len(sent_tools) == 1
        assert sent_tools[0]["name"] == "forge"

    async def test_deploy_keyword_narrows_to_titan(self):
        from agents.cruz.cruz_agent import CruzAgent
        claude = _mock_claude(_end_turn_response())
        conv, sem, db, qd, emb = _cruz_patches()
        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic",
                   return_value=claude), conv, sem, db, qd, emb:
            await CruzAgent().process(_make_input("Deploy ama to production"))
        sent_tools = claude.messages.create.call_args.kwargs["tools"]
        assert len(sent_tools) == 1
        assert sent_tools[0]["name"] == "titan"

    async def test_unknown_agent_hint_falls_back_to_full_list(self):
        """classify returning a name not in CRUZ_TOOLS must NOT narrow to empty."""
        from agents.cruz.cruz_agent import CruzAgent, CRUZ_TOOLS
        claude = _mock_claude(_end_turn_response())
        conv, sem, db, qd, emb = _cruz_patches()
        # Force classify() to return a name that is NOT advertised in
        # CRUZ_TOOLS. 'nonexistent-agent' isn't a real tool, so the
        # pre-filter should fall back to the full tool list.
        with patch("agents.cruz.cruz_agent.classify",
                   return_value="nonexistent-agent"), \
             patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic",
                   return_value=claude), conv, sem, db, qd, emb:
            await CruzAgent().process(_make_input("Run some tests"))
        sent_tools = claude.messages.create.call_args.kwargs["tools"]
        # Unknown tool hint — must not narrow to empty
        assert len(sent_tools) == len(CRUZ_TOOLS)

    async def test_prefilter_does_not_short_circuit_claude_call(self):
        """Even with a narrow tool list, Claude is still invoked to handle the request."""
        from agents.cruz.cruz_agent import CruzAgent
        claude = _mock_claude(_end_turn_response("Wrote the function."))
        conv, sem, db, qd, emb = _cruz_patches()
        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic",
                   return_value=claude), conv, sem, db, qd, emb:
            result = await CruzAgent().process(_make_input("write a function"))
        claude.messages.create.assert_called_once()
        assert result["success"] is True
