"""
Tests for RelayAgent — deterministic keyword classifier.

RELAY makes ZERO LLM calls. It pattern-matches the task string and
returns the name of the agent that should handle it.  All routing logic
is in pure Python; if no keyword matches, it falls back to GENERAL.

RED phase — must fail before production code exists.
"""

import pytest
from agents.base_agent import AgentInput, AgentOutput
from agents.relay.relay_agent import RelayAgent, AGENT_KEYWORDS


class TestRelayAgentIsBaseAgent:
    def test_relay_agent_subclasses_base_agent(self):
        from agents.base_agent import BaseAgent
        assert issubclass(RelayAgent, BaseAgent)

    def test_relay_agent_can_be_instantiated(self):
        agent = RelayAgent()
        assert agent is not None

    def test_relay_agent_name_is_relay(self):
        agent = RelayAgent()
        assert agent.name == "RELAY"


class TestAgentKeywordsMap:
    def test_agent_keywords_is_dict(self):
        assert isinstance(AGENT_KEYWORDS, dict)

    def test_agent_keywords_maps_to_agent_names(self):
        # Every value must be a non-empty string (agent name)
        for keyword, agent_name in AGENT_KEYWORDS.items():
            assert isinstance(agent_name, str), f"Value for '{keyword}' must be str"
            assert len(agent_name) > 0

    def test_forge_keywords_present(self):
        """FORGE handles code generation tasks."""
        forge_tasks = AGENT_KEYWORDS.values()
        assert "FORGE" in forge_tasks

    def test_echo_keywords_present(self):
        """ECHO handles email/communication tasks."""
        assert "ECHO" in AGENT_KEYWORDS.values()

    def test_reach_keywords_present(self):
        assert "REACH" in AGENT_KEYWORDS.values()

    def test_titan_keywords_present(self):
        assert "TITAN" in AGENT_KEYWORDS.values()


class TestRelayRouting:
    async def _route(self, task: str) -> AgentOutput:
        agent = RelayAgent()
        inp: AgentInput = {
            "task": task,
            "context": {},
            "trace_id": "trace-relay-test-001",
            "conversation_id": "conv-001",
        }
        return await agent.process(inp)

    async def test_routes_code_task_to_forge(self):
        result = await self._route("write a function to parse JSON")
        assert result["success"] is True
        assert result["result"]["agent"] == "FORGE"

    async def test_routes_create_function_to_forge(self):
        result = await self._route("create a React component for the navbar")
        assert result["result"]["agent"] == "FORGE"

    async def test_routes_email_task_to_echo(self):
        result = await self._route("send an email to the client about the delay")
        assert result["result"]["agent"] == "ECHO"

    async def test_routes_draft_email_to_echo(self):
        result = await self._route("draft a reply to John's message")
        assert result["result"]["agent"] == "ECHO"

    async def test_routes_deploy_task_to_titan(self):
        result = await self._route("deploy the app to production")
        assert result["result"]["agent"] == "TITAN"

    async def test_routes_leads_task_to_reach(self):
        result = await self._route("find leads for my SaaS product")
        assert result["result"]["agent"] == "REACH"

    async def test_unknown_task_falls_back_to_general(self):
        result = await self._route("what is the weather today")
        assert result["result"]["agent"] == "GENERAL"

    async def test_routing_is_case_insensitive(self):
        result = await self._route("WRITE A PYTHON SCRIPT")
        assert result["result"]["agent"] == "FORGE"

    async def test_result_contains_original_task(self):
        task = "write a unit test for auth module"
        result = await self._route(task)
        assert result["result"]["task"] == task

    async def test_result_contains_trace_id(self):
        agent = RelayAgent()
        inp: AgentInput = {
            "task": "write code",
            "context": {},
            "trace_id": "trace-xyz-999",
            "conversation_id": "conv-001",
        }
        result = await agent.process(inp)
        assert result["result"]["trace_id"] == "trace-xyz-999"

    async def test_relay_uses_zero_tokens(self):
        """RelayAgent makes no LLM calls — tokens_used must always be 0."""
        result = await self._route("write a function")
        assert result["tokens_used"] == 0

    async def test_relay_duration_is_fast(self):
        """Pure keyword matching should complete well under 100ms."""
        import time
        agent = RelayAgent()
        inp: AgentInput = {
            "task": "write a script",
            "context": {},
            "trace_id": "trace-perf-001",
            "conversation_id": "conv-001",
        }
        start = time.monotonic()
        await agent.process(inp)
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 100, f"RelayAgent took {elapsed_ms:.1f}ms — must be <100ms"


# ─────────────────────────────────────────────
# R17 — classify() module function used by CruzAgent pre-filter
# ─────────────────────────────────────────────

import time as _time


class TestRelayClassifyFunction:
    def test_classify_is_importable(self):
        from agents.relay.relay_agent import classify  # noqa: F401

    def test_returns_none_for_empty_string(self):
        from agents.relay.relay_agent import classify
        assert classify("") is None

    def test_returns_none_when_no_keyword_matches(self):
        from agents.relay.relay_agent import classify
        assert classify("hello, how are you today?") is None

    def test_matches_forge_keyword(self):
        from agents.relay.relay_agent import classify
        assert classify("Please write a function that parses CSV") == "forge"

    def test_matches_echo_keyword(self):
        from agents.relay.relay_agent import classify
        assert classify("Draft an email to ateet@ama.com") == "echo"

    def test_matches_titan_keyword(self):
        from agents.relay.relay_agent import classify
        assert classify("Deploy to production now") == "titan"

    def test_case_insensitive(self):
        from agents.relay.relay_agent import classify
        assert classify("DEPLOY TO PROD") == "titan"

    def test_returns_lowercase_agent_name(self):
        from agents.relay.relay_agent import classify
        result = classify("Please refactor this module")
        assert result == result.lower()

    def test_first_match_wins(self):
        from agents.relay.relay_agent import classify
        assert classify("Create a task for deployment prep") == "pm"

    def test_completes_under_100ms(self):
        from agents.relay.relay_agent import classify
        start = _time.monotonic()
        classify("write a function to parse CSV files efficiently")
        elapsed_ms = (_time.monotonic() - start) * 1000
        assert elapsed_ms < 100
