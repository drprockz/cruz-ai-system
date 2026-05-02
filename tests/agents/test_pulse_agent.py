"""
Tests for PulseAgent — 6 AM daily morning briefing.

Data sources (all optional — briefing degrades gracefully if any fail):
  1. Google Calendar API  — today's events via httpx REST
  2. Qdrant semantic memory — RAW's overnight research findings
  3. agent_logs            — what agents ran overnight
  4. tasks table           — pending/in-progress tasks

Primary model: Llama 3.1 8B via Ollama (local, zero cost)
Fallback: Claude Haiku when Ollama unavailable

Output (AgentOutput.result):
  {
    "date":               "<YYYY-MM-DD>",
    "calendar_events":    [{title, start, end}, ...],
    "overnight_research": "<RAW findings summary from Qdrant>",
    "overnight_agents":   [{agent, status, last_run}, ...],
    "pending_tasks":      [{title, agent, priority}, ...],
    "summary":            "<Llama-generated morning briefing>",
  }

requires_approval=False — briefing is read-only.
self.log() on both success and error paths.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput, BaseAgent


# ---------------------------------------------------------------------------
# KB service mock — autouse, applies to every test in this module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_kb_service():
    """Mock KnowledgeBaseService for all PULSE tests."""
    mock_kb = MagicMock()
    mock_kb.build_agent_context = AsyncMock(return_value="")
    mock_kb.record_agent_activity = AsyncMock()
    with patch("agents.pulse.pulse_agent.get_kb_service", return_value=mock_kb):
        yield mock_kb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_input(mode: str = "briefing") -> AgentInput:
    return {
        "task": "Generate morning briefing",
        "context": {"mode": mode},
        "trace_id": "trace-pulse-001",
        "conversation_id": "conv-pulse-001",
    }


def _mock_ollama(response_text: str = "Good morning! Here is your briefing..."):
    svc = MagicMock()
    svc.generate = AsyncMock(return_value={"response": response_text})
    return svc


def _mock_claude(
    response_text: str = "Claude briefing.",
    input_tokens: int = 200,
    output_tokens: int = 100,
):
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]
    msg.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=msg)
    return client


def _mock_db(agent_log_rows=None, task_rows=None):
    db = AsyncMock()

    def _fetch_side_effect(query, *args):
        if "agent_logs" in query.lower():
            return agent_log_rows or []
        if "tasks" in query.lower():
            return task_rows or []
        return []

    db.fetch = AsyncMock(side_effect=_fetch_side_effect)
    db.execute = AsyncMock(return_value=None)
    return db


def _mock_google_calendar_response(events=None):
    """Return a mock httpx response for Google Calendar API."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={
        "items": events or [
            {
                "summary": "Client call — AMA Solutions",
                "start": {"dateTime": "2026-04-13T10:00:00+05:30"},
                "end": {"dateTime": "2026-04-13T11:00:00+05:30"},
            }
        ]
    })
    return resp


def _mock_semantic_memory(search_result=None):
    svc = AsyncMock()
    svc.search_similar = AsyncMock(return_value=search_result or [
        {"role": "assistant", "content": "[RAW:research] Python frameworks\n\nKey findings: ..."}
    ])
    return svc


# ---------------------------------------------------------------------------
# Interface tests
# ---------------------------------------------------------------------------

class TestPulseAgentInterface:
    def test_pulse_agent_can_be_imported(self):
        from agents.pulse.pulse_agent import PulseAgent
        assert PulseAgent is not None

    def test_pulse_agent_extends_base_agent(self):
        from agents.pulse.pulse_agent import PulseAgent
        assert issubclass(PulseAgent, BaseAgent)

    def test_pulse_agent_name_is_PULSE(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        assert agent.name == "PULSE"

    def test_process_is_coroutine(self):
        import asyncio
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        assert asyncio.iscoroutinefunction(agent.process)

    def test_uses_llama_model(self):
        from agents.pulse import pulse_agent
        assert "llama" in pulse_agent._MODEL.lower()


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------

class TestPulseAgentOutput:
    @pytest.mark.asyncio
    async def test_returns_agent_output_typeddict(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        for key in ("success", "result", "agent", "duration_ms", "tokens_used"):
            assert key in out

    @pytest.mark.asyncio
    async def test_success_true_on_happy_path(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        assert out["success"] is True

    @pytest.mark.asyncio
    async def test_result_has_all_required_keys(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        result = out["result"]
        for key in ("date", "calendar_events", "overnight_research",
                    "overnight_agents", "pending_tasks", "summary"):
            assert key in result, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_requires_approval_false(self):
        """Briefing is read-only — no approval needed."""
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        assert out["requires_approval"] is False

    @pytest.mark.asyncio
    async def test_tokens_zero_when_ollama_used(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        assert out["tokens_used"] == 0

    @pytest.mark.asyncio
    async def test_result_date_is_today(self):
        """Result date must be today's date in YYYY-MM-DD format."""
        import datetime
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        today = datetime.date.today().isoformat()
        assert out["result"]["date"] == today


# ---------------------------------------------------------------------------
# Calendar events
# ---------------------------------------------------------------------------

class TestPulseCalendarEvents:
    @pytest.mark.asyncio
    async def test_calendar_events_included_in_result(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        events = [{"title": "Client call", "start": "10:00", "end": "11:00"}]
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=events),
        ):
            out = await agent.process(_make_input())
        assert out["result"]["calendar_events"] == events

    @pytest.mark.asyncio
    async def test_calendar_failure_is_non_fatal(self):
        """If calendar fetch fails, briefing still succeeds with empty events."""
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events",
                  side_effect=Exception("Calendar API down")),
        ):
            out = await agent.process(_make_input())
        assert out["success"] is True
        assert out["result"]["calendar_events"] == []

    @pytest.mark.asyncio
    async def test_fetch_calendar_events_calls_google_api(self):
        """_fetch_calendar_events() must call Google Calendar API via httpx."""
        from agents.pulse import pulse_agent
        mock_resp = _mock_google_calendar_response()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch("agents.pulse.pulse_agent.httpx.AsyncClient", return_value=mock_client),
            patch.dict("os.environ", {"GOOGLE_CALENDAR_ACCESS_TOKEN": "token123",
                                       "GOOGLE_CALENDAR_ID": "primary"}),
        ):
            events = await pulse_agent._fetch_calendar_events()
        mock_client.get.assert_called_once()
        assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_fetch_calendar_returns_empty_without_token(self):
        """If GOOGLE_CALENDAR_ACCESS_TOKEN not set, return [] without raising."""
        from agents.pulse import pulse_agent
        with patch.dict("os.environ", {}, clear=True):
            events = await pulse_agent._fetch_calendar_events()
        assert events == []


# ---------------------------------------------------------------------------
# Overnight research from Qdrant
# ---------------------------------------------------------------------------

class TestPulseOvernightResearch:
    @pytest.mark.asyncio
    async def test_overnight_research_pulled_from_qdrant(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        sem = _mock_semantic_memory(search_result=[
            {"role": "assistant", "content": "[RAW:research] FastAPI\n\nKey findings: use lifespan"}
        ])
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=sem),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        assert "[RAW:research]" in out["result"]["overnight_research"] or \
               out["result"]["overnight_research"] != ""

    @pytest.mark.asyncio
    async def test_qdrant_failure_is_non_fatal(self):
        """Qdrant failure → overnight_research is empty string, briefing still succeeds."""
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        bad_sem = AsyncMock()
        bad_sem.search_similar = AsyncMock(side_effect=Exception("Qdrant down"))
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=bad_sem),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        assert out["success"] is True
        assert out["result"]["overnight_research"] == ""


# ---------------------------------------------------------------------------
# Overnight agents + pending tasks from DB
# ---------------------------------------------------------------------------

class TestPulseDbData:
    @pytest.mark.asyncio
    async def test_overnight_agents_from_agent_logs(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        agent_rows = [
            {"agent": "RAW", "status": "success", "created_at": "2026-04-13T03:00:00"},
            {"agent": "REACH", "status": "success", "created_at": "2026-04-13T02:00:00"},
        ]
        db = _mock_db(agent_log_rows=agent_rows)
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=db),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        assert len(out["result"]["overnight_agents"]) == 2

    @pytest.mark.asyncio
    async def test_pending_tasks_from_tasks_table(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        task_rows = [
            {"title": "Write AMA tests", "agent": "QT", "priority": 2},
            {"title": "Deploy Shooterista", "agent": "TITAN", "priority": 1},
        ]
        db = _mock_db(task_rows=task_rows)
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=db),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        assert len(out["result"]["pending_tasks"]) == 2

    @pytest.mark.asyncio
    async def test_db_failure_is_non_fatal(self):
        """DB failure → empty lists, briefing still succeeds."""
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        bad_db = AsyncMock()
        bad_db.fetch = AsyncMock(side_effect=Exception("DB down"))
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=bad_db),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        assert out["success"] is True
        assert out["result"]["overnight_agents"] == []
        assert out["result"]["pending_tasks"] == []


# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------

class TestPulseSummaryGeneration:
    @pytest.mark.asyncio
    async def test_summary_content_from_ollama(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService",
                  return_value=_mock_ollama("Good morning Darshan! Here's your brief.")),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        assert out["result"]["summary"] == "Good morning Darshan! Here's your brief."

    @pytest.mark.asyncio
    async def test_summary_prompt_includes_calendar_events(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        events = [{"title": "Client call", "start": "10:00", "end": "11:00"}]
        ollama = _mock_ollama("Brief")
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=ollama),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=events),
        ):
            await agent.process(_make_input())
        prompt_used = ollama.generate.call_args[1]["prompt"] if \
            ollama.generate.call_args[1] else ollama.generate.call_args[0][1]
        assert "Client call" in prompt_used or "calendar" in prompt_used.lower()


# ---------------------------------------------------------------------------
# Claude Haiku fallback
# ---------------------------------------------------------------------------

class TestPulseClaudeFallback:
    @pytest.mark.asyncio
    async def test_falls_back_to_claude_when_ollama_fails(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        bad_ollama = MagicMock()
        bad_ollama.generate = AsyncMock(side_effect=Exception("Ollama down"))
        claude = _mock_claude("Claude briefing text", 300, 150)
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=bad_ollama),
            patch("agents.pulse.pulse_agent.anthropic.AsyncAnthropic", return_value=claude),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        assert out["success"] is True
        assert out["result"]["summary"] == "Claude briefing text"

    @pytest.mark.asyncio
    async def test_claude_fallback_tracks_tokens(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        bad_ollama = MagicMock()
        bad_ollama.generate = AsyncMock(side_effect=Exception("Ollama down"))
        claude = _mock_claude("Brief", input_tokens=300, output_tokens=150)
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=bad_ollama),
            patch("agents.pulse.pulse_agent.anthropic.AsyncAnthropic", return_value=claude),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        assert out["tokens_used"] == 450

    @pytest.mark.asyncio
    async def test_returns_error_when_both_fail(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        bad_ollama = MagicMock()
        bad_ollama.generate = AsyncMock(side_effect=Exception("Ollama down"))
        bad_claude = MagicMock()
        bad_claude.messages = MagicMock()
        bad_claude.messages.create = AsyncMock(side_effect=Exception("Claude down"))
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=bad_ollama),
            patch("agents.pulse.pulse_agent.anthropic.AsyncAnthropic", return_value=bad_claude),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        assert out["success"] is False
        assert out["error"] is not None


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class TestPulseLogging:
    @pytest.mark.asyncio
    async def test_log_called_on_success(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        agent.log = AsyncMock()
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            await agent.process(_make_input())
        agent.log.assert_called_once()
        assert agent.log.call_args.kwargs["status"] == "success"

    @pytest.mark.asyncio
    async def test_log_called_on_error(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        agent.log = AsyncMock()
        bad_ollama = MagicMock()
        bad_ollama.generate = AsyncMock(side_effect=Exception("fail"))
        bad_claude = MagicMock()
        bad_claude.messages = MagicMock()
        bad_claude.messages.create = AsyncMock(side_effect=Exception("fail"))
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=bad_ollama),
            patch("agents.pulse.pulse_agent.anthropic.AsyncAnthropic", return_value=bad_claude),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            await agent.process(_make_input())
        agent.log.assert_called_once()
        assert agent.log.call_args.kwargs["status"] == "error"

    @pytest.mark.asyncio
    async def test_log_failure_does_not_crash_agent(self):
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        agent.log = AsyncMock(side_effect=Exception("DB down"))
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            out = await agent.process(_make_input())
        assert out["success"] is True


# ---------------------------------------------------------------------------
# Knowledge Base integration
# ---------------------------------------------------------------------------


class TestPulseKnowledgeBase:
    @pytest.mark.asyncio
    async def test_pulse_calls_kb_build_context(self, mock_kb_service):
        """build_agent_context and record_agent_activity must each fire once per process()."""
        from agents.pulse.pulse_agent import PulseAgent
        agent = PulseAgent()
        with (
            patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
            patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
            patch("agents.pulse.pulse_agent.get_qdrant_service"),
            patch("agents.pulse.pulse_agent.get_embedding_service"),
            patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
        ):
            await agent.process(_make_input())

        mock_kb_service.build_agent_context.assert_awaited_once()
        mock_kb_service.record_agent_activity.assert_awaited_once()

    def test_pulse_declares_knowledge_rings(self):
        """KNOWLEDGE_RINGS must be declared on the class."""
        from agents.pulse.pulse_agent import PulseAgent
        assert PulseAgent.KNOWLEDGE_RINGS == ["cruz_activities", "cruz_domain_knowledge"]


# ---------------------------------------------------------------------------
# Web roundup (browser-sourced) — Task 5.2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pulse_web_roundup_includes_browser_sourced_content(monkeypatch, tmp_path):
    """When sources.yml has pages, the Web roundup section is populated."""
    from agents.pulse.pulse_agent import PulseAgent
    import services.browser.service as browser_mod

    fake_browser = MagicMock()
    fake_browser.fetch = AsyncMock(return_value={
        "url": "https://techcrunch.com/", "final_url": "https://techcrunch.com/",
        "status": 200, "title": "TechCrunch", "html": "<html></html>",
        "text": "Big AI news today.", "byte_size": 100,
    })
    monkeypatch.setattr(browser_mod, "_instance", fake_browser)

    sources_yml = tmp_path / "sources.yml"
    sources_yml.write_text(
        "pages:\n  - url: https://techcrunch.com/\n    selector: main\n"
    )
    monkeypatch.setattr("agents.pulse.pulse_agent._SOURCES_PATH", str(sources_yml))

    agent = PulseAgent()
    with (
        patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
        patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
        patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
        patch("agents.pulse.pulse_agent.get_qdrant_service"),
        patch("agents.pulse.pulse_agent.get_embedding_service"),
        patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
    ):
        out = await agent.process(_make_input())

    assert out["success"]
    assert "web_roundup" in out["result"]
    roundup = out["result"]["web_roundup"]
    assert len(roundup) == 1
    assert roundup[0]["url"] == "https://techcrunch.com/"
    assert "Big AI news today." in roundup[0]["excerpt"]
    fake_browser.fetch.assert_awaited_with(
        "https://techcrunch.com/", trace_id="trace-pulse-001",
    )


@pytest.mark.asyncio
async def test_pulse_web_roundup_omitted_on_failure(monkeypatch, tmp_path):
    """One source raising BrowserRateLimited must not fail the briefing.
    The roundup section ends up empty (or just missing the failed entry)."""
    from agents.pulse.pulse_agent import PulseAgent
    from services.browser import BrowserRateLimited
    import services.browser.service as browser_mod

    fake_browser = MagicMock()
    fake_browser.fetch = AsyncMock(
        side_effect=BrowserRateLimited(domain="techcrunch.com", retry_after_ms=1000)
    )
    monkeypatch.setattr(browser_mod, "_instance", fake_browser)

    sources_yml = tmp_path / "sources.yml"
    sources_yml.write_text(
        "pages:\n  - url: https://techcrunch.com/\n    selector: main\n"
    )
    monkeypatch.setattr("agents.pulse.pulse_agent._SOURCES_PATH", str(sources_yml))

    agent = PulseAgent()
    with (
        patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
        patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
        patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
        patch("agents.pulse.pulse_agent.get_qdrant_service"),
        patch("agents.pulse.pulse_agent.get_embedding_service"),
        patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
    ):
        out = await agent.process(_make_input())

    assert out["success"]
    assert out["result"].get("web_roundup", []) == []


@pytest.mark.asyncio
async def test_pulse_load_pages_handles_missing_file(tmp_path, monkeypatch):
    """If sources.yml is missing, _load_pages returns empty list, no crash."""
    monkeypatch.setattr(
        "agents.pulse.pulse_agent._SOURCES_PATH", str(tmp_path / "missing.yml"),
    )
    from agents.pulse.pulse_agent import _load_pages
    assert _load_pages() == []


# ---------------------------------------------------------------------------
# Latency regression checks (SP4 smoke tests)
# ---------------------------------------------------------------------------

import time as _time


@pytest.mark.asyncio
async def test_pulse_full_run_completes_quickly(monkeypatch, tmp_path):
    """Sanity tripwire: full PULSE briefing run with mocked I/O stays under 5s."""
    from agents.pulse.pulse_agent import PulseAgent
    import services.browser.service as browser_mod

    fake_browser = MagicMock()
    fake_browser.fetch = AsyncMock(return_value={
        "url": "https://techcrunch.com/", "final_url": "https://techcrunch.com/",
        "status": 200, "title": "TechCrunch", "html": "<html></html>",
        "text": "Big AI news today.", "byte_size": 100,
    })
    monkeypatch.setattr(browser_mod, "_instance", fake_browser)

    sources_yml = tmp_path / "sources.yml"
    sources_yml.write_text(
        "pages:\n  - url: https://techcrunch.com/\n    selector: main\n"
    )
    monkeypatch.setattr("agents.pulse.pulse_agent._SOURCES_PATH", str(sources_yml))

    agent = PulseAgent()
    t0 = _time.monotonic()
    with (
        patch("agents.pulse.pulse_agent.get_db_service", return_value=_mock_db()),
        patch("agents.pulse.pulse_agent.OllamaService", return_value=_mock_ollama()),
        patch("agents.pulse.pulse_agent.SemanticMemoryService", return_value=_mock_semantic_memory()),
        patch("agents.pulse.pulse_agent.get_qdrant_service"),
        patch("agents.pulse.pulse_agent.get_embedding_service"),
        patch("agents.pulse.pulse_agent._fetch_calendar_events", return_value=[]),
    ):
        await agent.process(_make_input())
    elapsed = _time.monotonic() - t0
    assert elapsed < 5.0
