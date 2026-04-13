"""
Tests for PMAgent — sprint planning specialist.

PMAgent:
  - Uses Qwen 2.5 Coder 14B via Ollama (local, zero cloud cost)
  - Falls back to Claude Haiku when Ollama is unavailable
  - Returns a structured sprint plan: {sprint_name, goal, tasks[]}
  - ALWAYS requires human approval before creating Linear tickets
  - Calls self.log() on success AND error paths

Sprint plan structure:
  {
    "sprint_name": "<name>",
    "goal": "<one-line goal>",
    "tasks": [
      {
        "title": "<task title>",
        "description": "<detail>",
        "estimate_hours": <int>,
        "priority": "high" | "medium" | "low",
        "labels": ["<label>", ...]
      }
    ]
  }
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput, BaseAgent


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_input(task: str = "Plan a 2-week sprint for the AMA website redesign") -> AgentInput:
    return {
        "task": task,
        "context": {},
        "trace_id": "trace-pm-001",
        "conversation_id": "conv-pm-001",
    }


def _sprint_plan_json(
    sprint_name: str = "Sprint 12",
    goal: str = "Redesign AMA website homepage",
    tasks: list | None = None,
) -> str:
    if tasks is None:
        tasks = [
            {
                "title": "Redesign hero section",
                "description": "Update hero section with new branding",
                "estimate_hours": 4,
                "priority": "high",
                "labels": ["frontend"],
            },
            {
                "title": "Update contact form",
                "description": "Add new fields and validation",
                "estimate_hours": 3,
                "priority": "medium",
                "labels": ["frontend", "backend"],
            },
        ]
    return json.dumps({"sprint_name": sprint_name, "goal": goal, "tasks": tasks})


def _mock_ollama_response(raw_text: str) -> MagicMock:
    return {"response": raw_text}


# ─────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────

class TestPMAgentInterface:
    def test_pm_agent_can_be_imported(self):
        from agents.pm.pm_agent import PMAgent  # noqa: F401

    def test_pm_agent_extends_base_agent(self):
        from agents.pm.pm_agent import PMAgent
        assert issubclass(PMAgent, BaseAgent)

    def test_pm_agent_name_is_PM(self):
        from agents.pm.pm_agent import PMAgent
        assert PMAgent().name == "PM"

    def test_process_is_coroutine(self):
        import asyncio
        from agents.pm.pm_agent import PMAgent
        agent = PMAgent()
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama
            coro = agent.process(_make_input())
            assert asyncio.iscoroutine(coro)
            coro.close()


# ─────────────────────────────────────────────
# AgentOutput structure
# ─────────────────────────────────────────────

class TestPMAgentOutput:
    async def test_returns_agent_output_on_success(self):
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())
        assert isinstance(result, dict)
        assert result["success"] is True

    async def test_agent_name_is_PM_in_output(self):
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())
        assert result["agent"] == "PM"

    async def test_result_contains_sprint_name(self):
        from agents.pm.pm_agent import PMAgent
        plan_json = _sprint_plan_json(sprint_name="Sprint 12")
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(plan_json))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())
        assert result["result"]["sprint_name"] == "Sprint 12"

    async def test_result_contains_goal(self):
        from agents.pm.pm_agent import PMAgent
        plan_json = _sprint_plan_json(goal="Ship AMA redesign by April 30")
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(plan_json))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())
        assert result["result"]["goal"] == "Ship AMA redesign by April 30"

    async def test_result_contains_tasks_list(self):
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())
        assert isinstance(result["result"]["tasks"], list)
        assert len(result["result"]["tasks"]) > 0

    async def test_each_task_has_required_fields(self):
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())
        for task in result["result"]["tasks"]:
            assert "title" in task
            assert "description" in task
            assert "estimate_hours" in task
            assert "priority" in task

    async def test_duration_ms_is_positive_integer(self):
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())
        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] >= 0


# ─────────────────────────────────────────────
# Approval gate — ALWAYS requires approval
# ─────────────────────────────────────────────

class TestPMAgentApprovalGate:
    async def test_requires_approval_is_true_on_success(self):
        """Creating Linear tickets is irreversible — always gate."""
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())
        assert result["requires_approval"] is True

    async def test_approval_prompt_is_set(self):
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())
        assert result["approval_prompt"] is not None
        assert len(result["approval_prompt"]) > 0

    async def test_approval_prompt_mentions_task_count(self):
        """User must see how many tickets will be created before confirming."""
        from agents.pm.pm_agent import PMAgent
        tasks = [
            {"title": f"Task {i}", "description": "desc", "estimate_hours": 2,
             "priority": "medium", "labels": []}
            for i in range(3)
        ]
        plan_json = _sprint_plan_json(tasks=tasks)
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(plan_json))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())
        assert "3" in result["approval_prompt"]

    async def test_approval_prompt_mentions_linear(self):
        """User must know where the tickets will be created."""
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())
        prompt_lower = result["approval_prompt"].lower()
        assert "linear" in prompt_lower


# ─────────────────────────────────────────────
# Ollama primary path
# ─────────────────────────────────────────────

class TestPMAgentOllamaPrimary:
    async def test_calls_qwen_model(self):
        """PM must use qwen2.5-coder:14b — not any other model."""
        from agents.pm.pm_agent import PMAgent, _MODEL
        assert "qwen" in _MODEL.lower()

    async def test_ollama_called_on_happy_path(self):
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama
            await PMAgent().process(_make_input())
        mock_ollama.generate.assert_called_once()

    async def test_ollama_receives_task_in_prompt(self):
        """The user's task must appear in the prompt sent to Ollama."""
        from agents.pm.pm_agent import PMAgent
        task = "Plan sprint for Shooterista API v2"
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama
            await PMAgent().process(_make_input(task=task))
        call_kwargs = mock_ollama.generate.call_args
        prompt = call_kwargs[1].get("prompt") or call_kwargs[0][1]
        assert task in prompt

    async def test_tokens_used_is_zero_for_local_model(self):
        """Local Ollama calls have no cloud token cost."""
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())
        assert result["tokens_used"] == 0


# ─────────────────────────────────────────────
# Claude fallback path
# ─────────────────────────────────────────────

class TestPMAgentClaudeFallback:
    async def test_falls_back_to_claude_when_ollama_raises(self):
        """When Ollama is down, PM must still produce a sprint plan via Claude."""
        from agents.pm.pm_agent import PMAgent

        mock_claude_client = MagicMock()
        mock_claude_client.messages = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=_sprint_plan_json())]
        mock_response.usage = MagicMock(input_tokens=200, output_tokens=100)
        mock_claude_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.anthropic.AsyncAnthropic", return_value=mock_claude_client), \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=ConnectionError("Ollama is down"))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())

        assert result["success"] is True
        assert result["result"]["sprint_name"] is not None

    async def test_claude_fallback_counts_tokens(self):
        """Cloud fallback tokens must be tracked — they cost money."""
        from agents.pm.pm_agent import PMAgent

        mock_claude_client = MagicMock()
        mock_claude_client.messages = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=_sprint_plan_json())]
        mock_response.usage = MagicMock(input_tokens=200, output_tokens=100)
        mock_claude_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.anthropic.AsyncAnthropic", return_value=mock_claude_client), \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=ConnectionError("Ollama is down"))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())

        assert result["tokens_used"] == 300  # 200 in + 100 out

    async def test_returns_error_when_both_ollama_and_claude_fail(self):
        """If both backends fail, return success=False — never crash."""
        from agents.pm.pm_agent import PMAgent

        mock_claude_client = MagicMock()
        mock_claude_client.messages = MagicMock()
        mock_claude_client.messages.create = AsyncMock(
            side_effect=Exception("Claude also down")
        )

        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.anthropic.AsyncAnthropic", return_value=mock_claude_client), \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=ConnectionError("Ollama is down"))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())

        assert result["success"] is False
        assert result["error"] is not None

    async def test_requires_approval_false_on_error(self):
        """Don't show an approval gate when there's nothing to approve."""
        from agents.pm.pm_agent import PMAgent

        mock_claude_client = MagicMock()
        mock_claude_client.messages = MagicMock()
        mock_claude_client.messages.create = AsyncMock(
            side_effect=Exception("Claude also down")
        )

        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.anthropic.AsyncAnthropic", return_value=mock_claude_client), \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=ConnectionError("Ollama is down"))
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())

        assert result["requires_approval"] is False


# ─────────────────────────────────────────────
# Sprint plan parsing
# ─────────────────────────────────────────────

class TestSprintPlanParsing:
    def test_parses_clean_json(self):
        from agents.pm.pm_agent import _parse_plan
        plan = _parse_plan(_sprint_plan_json())
        assert plan["sprint_name"] == "Sprint 12"
        assert plan["goal"] == "Redesign AMA website homepage"
        assert len(plan["tasks"]) == 2

    def test_parses_json_in_code_fence(self):
        from agents.pm.pm_agent import _parse_plan
        fenced = f"```json\n{_sprint_plan_json()}\n```"
        plan = _parse_plan(fenced)
        assert plan is not None
        assert plan["sprint_name"] == "Sprint 12"

    def test_parses_json_embedded_in_prose(self):
        from agents.pm.pm_agent import _parse_plan
        prose = f"Here is your sprint plan:\n{_sprint_plan_json()}\nLet me know if you need changes."
        plan = _parse_plan(prose)
        assert plan is not None
        assert "tasks" in plan

    def test_returns_none_on_invalid_json(self):
        from agents.pm.pm_agent import _parse_plan
        result = _parse_plan("not json at all")
        assert result is None

    def test_returns_none_when_tasks_field_missing(self):
        from agents.pm.pm_agent import _parse_plan
        incomplete = json.dumps({"sprint_name": "S1", "goal": "g"})
        result = _parse_plan(incomplete)
        assert result is None

    def test_returns_none_when_goal_missing(self):
        from agents.pm.pm_agent import _parse_plan
        incomplete = json.dumps({"sprint_name": "S1", "tasks": []})
        result = _parse_plan(incomplete)
        assert result is None

    def test_returns_none_on_empty_string(self):
        from agents.pm.pm_agent import _parse_plan
        assert _parse_plan("") is None


# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

class TestPMAgentLogging:
    async def test_log_called_on_success(self):
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service") as mock_db_svc:
            mock_db = AsyncMock()
            mock_db_svc.return_value = mock_db
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama

            agent = PMAgent()
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input())

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args[1]
        assert call_kwargs["status"] == "success"

    async def test_log_called_on_total_failure(self):
        from agents.pm.pm_agent import PMAgent

        mock_claude_client = MagicMock()
        mock_claude_client.messages = MagicMock()
        mock_claude_client.messages.create = AsyncMock(side_effect=Exception("all down"))

        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.anthropic.AsyncAnthropic", return_value=mock_claude_client), \
             patch("agents.pm.pm_agent.get_db_service") as mock_db_svc:
            mock_db = AsyncMock()
            mock_db_svc.return_value = mock_db
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=ConnectionError("down"))
            mock_ollama_cls.return_value = mock_ollama

            agent = PMAgent()
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input())

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args[1]
        assert call_kwargs["status"] == "error"

    async def test_log_failure_does_not_crash_agent(self):
        """DB log failure must be swallowed — never propagate."""
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(return_value=_mock_ollama_response(_sprint_plan_json()))
            mock_ollama_cls.return_value = mock_ollama

            agent = PMAgent()
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                mock_log.side_effect = Exception("DB is dead")
                result = await agent.process(_make_input())

        assert result["success"] is True  # agent succeeds even when log fails


# ─────────────────────────────────────────────
# Parse failure path
# ─────────────────────────────────────────────

class TestPMAgentParseFailure:
    async def test_returns_error_when_model_returns_garbage(self):
        """If neither Ollama nor Claude can produce parseable JSON, return failure."""
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response("I cannot help with that.")
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())

        assert result["success"] is False

    async def test_requires_approval_false_on_parse_failure(self):
        from agents.pm.pm_agent import PMAgent
        with patch("agents.pm.pm_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.pm.pm_agent.get_db_service"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response("Sorry, I don't understand.")
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await PMAgent().process(_make_input())

        assert result["requires_approval"] is False
