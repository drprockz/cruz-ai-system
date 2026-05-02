"""
Tests for RawAgent — 3 AM tech research and dependency scan.

Modes (via context["mode"]):
  "research"     — Llama summarises a tech topic, stores in Qdrant
  "dependencies" — runs pip/npm outdated, Llama analyses output, stores in Qdrant
  default        — "research"

Primary model: Llama 3.1 8B via Ollama (local, zero cost)
Fallback: Claude Haiku when Ollama unavailable

Output (AgentOutput.result):
  {
    "mode":    "research" | "dependencies",
    "topic":   "<topic or package manager>",
    "summary": "<LLM-generated summary>",
    "stored":  True | False,
    "items":   [<list of research points or outdated packages>],
  }

requires_approval=False — research and dependency scanning are read-only/internal.
self.log() on both success and error paths.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput, BaseAgent


# ---------------------------------------------------------------------------
# KB service mock — autouse, applies to every test in this module
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_kb_service():
    """Mock KnowledgeBaseService for all RAW tests."""
    mock_kb = MagicMock()
    mock_kb.build_agent_context = AsyncMock(return_value="")
    mock_kb.record_agent_activity = AsyncMock()
    mock_kb.write_domain_knowledge = AsyncMock()
    with patch("agents.raw.raw_agent.get_kb_service", return_value=mock_kb):
        yield mock_kb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_input(
    task: str = "Research latest Python async frameworks",
    mode: str = "research",
    topic: str = "Python async frameworks",
) -> AgentInput:
    return {
        "task": task,
        "context": {"mode": mode, "topic": topic},
        "trace_id": "trace-raw-001",
        "conversation_id": "conv-raw-001",
    }


def _mock_ollama(response_text: str = "Research summary here."):
    """Return a mock OllamaService whose .generate() returns response_text."""
    svc = MagicMock()
    svc.generate = AsyncMock(return_value={"response": response_text})
    return svc


def _mock_claude(
    response_text: str = "Claude fallback summary.",
    input_tokens: int = 100,
    output_tokens: int = 50,
):
    """Return a mock Anthropic client for Claude Haiku fallback."""
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]
    msg.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=msg)
    return client


def _mock_semantic_memory(store_result=None):
    """Return a mock SemanticMemoryService."""
    svc = AsyncMock()
    svc.store = AsyncMock(return_value=store_result)
    return svc


def _mock_db():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=None)
    return db


# ---------------------------------------------------------------------------
# Interface tests
# ---------------------------------------------------------------------------

class TestRawAgentInterface:
    def test_raw_agent_can_be_imported(self):
        from agents.raw.raw_agent import RawAgent
        assert RawAgent is not None

    def test_raw_agent_extends_base_agent(self):
        from agents.raw.raw_agent import RawAgent
        assert issubclass(RawAgent, BaseAgent)

    def test_raw_agent_name_is_RAW(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        assert agent.name == "RAW"

    def test_process_is_coroutine(self):
        import asyncio
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        assert asyncio.iscoroutinefunction(agent.process)

    def test_uses_llama_model(self):
        from agents.raw import raw_agent
        assert "llama" in raw_agent._MODEL.lower()


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------

class TestRawAgentOutput:
    @pytest.mark.asyncio
    async def test_returns_agent_output_typeddict(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input())
        assert isinstance(out, dict)
        for key in ("success", "result", "agent", "duration_ms", "tokens_used"):
            assert key in out

    @pytest.mark.asyncio
    async def test_success_true_on_happy_path(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input())
        assert out["success"] is True

    @pytest.mark.asyncio
    async def test_result_contains_mode(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input())
        assert out["result"]["mode"] == "research"

    @pytest.mark.asyncio
    async def test_result_contains_topic(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input())
        assert "topic" in out["result"]

    @pytest.mark.asyncio
    async def test_result_contains_summary(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama("Great summary")),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input())
        assert out["result"]["summary"] == "Great summary"

    @pytest.mark.asyncio
    async def test_result_contains_stored_flag(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input())
        assert "stored" in out["result"]

    @pytest.mark.asyncio
    async def test_result_contains_items_list(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input())
        assert isinstance(out["result"]["items"], list)

    @pytest.mark.asyncio
    async def test_tokens_zero_for_ollama(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input())
        assert out["tokens_used"] == 0


# ---------------------------------------------------------------------------
# Research mode
# ---------------------------------------------------------------------------

class TestRawResearchMode:
    @pytest.mark.asyncio
    async def test_research_mode_stores_in_qdrant(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama("Summary text")),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input(mode="research"))
        sem.store.assert_called_once()
        assert out["result"]["stored"] is True

    @pytest.mark.asyncio
    async def test_research_mode_topic_from_context(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input(topic="FastAPI vs Django"))
        assert out["result"]["topic"] == "FastAPI vs Django"

    @pytest.mark.asyncio
    async def test_research_mode_topic_falls_back_to_task(self):
        """If context has no topic, use the task string as topic."""
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        inp = {
            "task": "Research asyncio improvements",
            "context": {"mode": "research"},
            "trace_id": "trace-raw-001",
            "conversation_id": "conv-raw-001",
        }
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(inp)
        assert out["result"]["topic"] == "Research asyncio improvements"

    @pytest.mark.asyncio
    async def test_research_mode_default_when_no_mode(self):
        """No mode in context → defaults to research."""
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        inp = {
            "task": "Check latest security advisories",
            "context": {},
            "trace_id": "trace-raw-001",
            "conversation_id": "conv-raw-001",
        }
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(inp)
        assert out["result"]["mode"] == "research"
        assert out["success"] is True


# ---------------------------------------------------------------------------
# Dependencies mode
# ---------------------------------------------------------------------------

class TestRawDependenciesMode:
    @pytest.mark.asyncio
    async def test_dependencies_mode_runs_pip_outdated(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        inp = _make_input(mode="dependencies", topic="pip")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"Package  Version  Latest\nfastapi  0.109.0  0.110.0\n", b"")
        )
        mock_proc.returncode = 0

        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama("fastapi needs update")),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec,
        ):
            out = await agent.process(inp)
        mock_exec.assert_called_once()
        assert out["result"]["mode"] == "dependencies"
        assert out["success"] is True

    @pytest.mark.asyncio
    async def test_dependencies_mode_result_has_items(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        inp = _make_input(mode="dependencies", topic="pip")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"Package  Version  Latest\nfastapi  0.109.0  0.110.0\n", b"")
        )
        mock_proc.returncode = 0

        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama("analysis")),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            out = await agent.process(inp)
        assert isinstance(out["result"]["items"], list)

    @pytest.mark.asyncio
    async def test_dependencies_mode_stores_in_qdrant(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        inp = _make_input(mode="dependencies", topic="pip")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama("All up to date")),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            out = await agent.process(inp)
        sem.store.assert_called_once()
        assert out["result"]["stored"] is True


# ---------------------------------------------------------------------------
# Claude Haiku fallback
# ---------------------------------------------------------------------------

class TestRawClaudeFallback:
    @pytest.mark.asyncio
    async def test_falls_back_to_claude_when_ollama_fails(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        bad_ollama = MagicMock()
        bad_ollama.generate = AsyncMock(side_effect=Exception("Ollama down"))
        claude = _mock_claude("Claude research summary")
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=bad_ollama),
            patch("agents.raw.raw_agent.anthropic.AsyncAnthropic", return_value=claude),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input())
        assert out["success"] is True
        assert out["result"]["summary"] == "Claude research summary"

    @pytest.mark.asyncio
    async def test_claude_fallback_tracks_tokens(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        bad_ollama = MagicMock()
        bad_ollama.generate = AsyncMock(side_effect=Exception("Ollama down"))
        claude = _mock_claude("Summary", input_tokens=200, output_tokens=80)
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=bad_ollama),
            patch("agents.raw.raw_agent.anthropic.AsyncAnthropic", return_value=claude),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input())
        assert out["tokens_used"] == 280

    @pytest.mark.asyncio
    async def test_returns_error_when_both_fail(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        bad_ollama = MagicMock()
        bad_ollama.generate = AsyncMock(side_effect=Exception("Ollama down"))
        bad_claude = MagicMock()
        bad_claude.messages = MagicMock()
        bad_claude.messages.create = AsyncMock(side_effect=Exception("Claude down"))
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=bad_ollama),
            patch("agents.raw.raw_agent.anthropic.AsyncAnthropic", return_value=bad_claude),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input())
        assert out["success"] is False
        assert out["error"] is not None


# ---------------------------------------------------------------------------
# Approval gate
# ---------------------------------------------------------------------------

class TestRawApprovalGate:
    @pytest.mark.asyncio
    async def test_requires_approval_false(self):
        """RAW is a read-only/internal agent — no approval needed."""
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input())
        assert out["requires_approval"] is False


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class TestRawLogging:
    @pytest.mark.asyncio
    async def test_log_called_on_success(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        agent.log = AsyncMock()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            await agent.process(_make_input())
        agent.log.assert_called_once()
        assert agent.log.call_args.kwargs["status"] == "success"

    @pytest.mark.asyncio
    async def test_log_called_on_error(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        agent.log = AsyncMock()
        db = _mock_db()
        sem = _mock_semantic_memory()
        bad_ollama = MagicMock()
        bad_ollama.generate = AsyncMock(side_effect=Exception("fail"))
        bad_claude = MagicMock()
        bad_claude.messages = MagicMock()
        bad_claude.messages.create = AsyncMock(side_effect=Exception("fail"))
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=bad_ollama),
            patch("agents.raw.raw_agent.anthropic.AsyncAnthropic", return_value=bad_claude),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            await agent.process(_make_input())
        agent.log.assert_called_once()
        assert agent.log.call_args.kwargs["status"] == "error"

    @pytest.mark.asyncio
    async def test_log_failure_does_not_crash_agent(self):
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        agent.log = AsyncMock(side_effect=Exception("DB down"))
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            out = await agent.process(_make_input())
        assert out["success"] is True  # log failure must not crash agent


# ---------------------------------------------------------------------------
# Knowledge Base integration
# ---------------------------------------------------------------------------

class TestRawKnowledgeBase:
    def test_raw_declares_knowledge_rings(self):
        """KNOWLEDGE_RINGS must be declared on the class."""
        from agents.raw.raw_agent import RawAgent
        assert RawAgent.KNOWLEDGE_RINGS == ["cruz_activities", "cruz_domain_knowledge"]

    @pytest.mark.asyncio
    async def test_raw_calls_kb_build_context_and_record_activity(self, mock_kb_service):
        """build_agent_context and record_agent_activity must each fire once per process()."""
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama()),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            await agent.process(_make_input())
        mock_kb_service.build_agent_context.assert_awaited_once()
        mock_kb_service.record_agent_activity.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raw_calls_write_domain_knowledge(self, mock_kb_service):
        """RAW must write its research output to cruz_domain_knowledge."""
        from agents.raw.raw_agent import RawAgent
        agent = RawAgent()
        db = _mock_db()
        sem = _mock_semantic_memory()
        with (
            patch("agents.raw.raw_agent.get_db_service", return_value=db),
            patch("agents.raw.raw_agent.OllamaService", return_value=_mock_ollama("Research findings about asyncio")),
            patch("agents.raw.raw_agent.SemanticMemoryService", return_value=sem),
            patch("agents.raw.raw_agent.get_qdrant_service"),
            patch("agents.raw.raw_agent.get_embedding_service"),
        ):
            await agent.process(_make_input())
        assert mock_kb_service.write_domain_knowledge.await_count >= 1


# ---------------------------------------------------------------------------
# sources.yml + page-fetch branch (SP4 retrofit)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_raw_loads_sources_yml(tmp_path, monkeypatch):
    sources_yml = tmp_path / "sources.yml"
    sources_yml.write_text(
        "rss:\n  - https://example.com/rss\n"
        "pages:\n  - url: https://anthropic.com/news\n"
        "    selector: main\n"
        "    summarize_with: llama3.1:8b\n"
    )
    monkeypatch.setattr(
        "agents.raw.raw_agent._SOURCES_PATH", str(sources_yml)
    )
    from agents.raw.raw_agent import _load_sources
    sources = _load_sources()
    assert sources["rss"] == ["https://example.com/rss"]
    assert len(sources["pages"]) == 1
    assert sources["pages"][0]["url"] == "https://anthropic.com/news"


@pytest.mark.asyncio
async def test_raw_page_fetch_branch_writes_domain_knowledge(
    monkeypatch, tmp_path, mock_kb_service,
):
    """The page-fetch branch fetches each page, summarises, and writes KB."""
    from agents.raw.raw_agent import RawAgent
    import services.browser.service as browser_mod

    fake_browser = MagicMock()
    fake_browser.fetch = AsyncMock(return_value={
        "url": "https://anthropic.com/news",
        "final_url": "https://anthropic.com/news",
        "status": 200,
        "title": "News",
        "html": "<html></html>",
        "text": "Anthropic released a new model.",
        "byte_size": 100,
    })
    monkeypatch.setattr(browser_mod, "_instance", fake_browser)

    sources_yml = tmp_path / "sources.yml"
    sources_yml.write_text(
        "rss: []\n"
        "pages:\n  - url: https://anthropic.com/news\n"
        "    selector: main\n"
        "    summarize_with: llama3.1:8b\n"
    )
    monkeypatch.setattr("agents.raw.raw_agent._SOURCES_PATH", str(sources_yml))

    # Mock the existing topic-research path so we don't hit Ollama
    monkeypatch.setattr(
        RawAgent, "_research",
        AsyncMock(return_value=("topic-summary", 0)),
    )
    # Mock the new page summariser
    monkeypatch.setattr(
        "agents.raw.raw_agent._summarise",
        AsyncMock(return_value="page summary"),
    )
    # Skip Qdrant
    monkeypatch.setattr(
        "agents.raw.raw_agent.SemanticMemoryService",
        MagicMock(return_value=AsyncMock(store=AsyncMock())),
    )
    monkeypatch.setattr("agents.raw.raw_agent.get_qdrant_service", lambda: MagicMock())
    monkeypatch.setattr("agents.raw.raw_agent.get_embedding_service", lambda: MagicMock())
    monkeypatch.setattr("agents.raw.raw_agent.get_db_service", lambda: AsyncMock())

    agent = RawAgent()
    result = await agent.process({
        "task": "research",
        "context": {"mode": "research"},
        "trace_id": "t1",
        "conversation_id": "c1",
    })
    assert result["success"]
    fake_browser.fetch.assert_awaited_with(
        "https://anthropic.com/news", trace_id="t1",
    )
    # write_domain_knowledge was called for the page (in addition to topic write)
    assert mock_kb_service.write_domain_knowledge.await_count >= 1


@pytest.mark.asyncio
async def test_raw_skips_failed_source_continues(
    monkeypatch, tmp_path, mock_kb_service,
):
    """One source raising BrowserError must not fail the whole RAW run."""
    from agents.raw.raw_agent import RawAgent
    from services.browser import BrowserNavigationError
    import services.browser.service as browser_mod

    call_count = {"n": 0}

    async def flaky_fetch(url, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise BrowserNavigationError("dns fail")
        return {
            "url": url, "final_url": url, "status": 200,
            "title": "ok", "html": "<html></html>", "text": "ok content",
            "byte_size": 1,
        }

    fake_browser = MagicMock()
    fake_browser.fetch = AsyncMock(side_effect=flaky_fetch)
    monkeypatch.setattr(browser_mod, "_instance", fake_browser)

    sources_yml = tmp_path / "sources.yml"
    sources_yml.write_text(
        "rss: []\n"
        "pages:\n"
        "  - url: https://broken.example\n    selector: main\n    summarize_with: llama3.1:8b\n"
        "  - url: https://ok.example\n    selector: main\n    summarize_with: llama3.1:8b\n"
    )
    monkeypatch.setattr("agents.raw.raw_agent._SOURCES_PATH", str(sources_yml))

    monkeypatch.setattr(
        RawAgent, "_research",
        AsyncMock(return_value=("topic-summary", 0)),
    )
    monkeypatch.setattr(
        "agents.raw.raw_agent._summarise",
        AsyncMock(return_value="page summary"),
    )
    monkeypatch.setattr(
        "agents.raw.raw_agent.SemanticMemoryService",
        MagicMock(return_value=AsyncMock(store=AsyncMock())),
    )
    monkeypatch.setattr("agents.raw.raw_agent.get_qdrant_service", lambda: MagicMock())
    monkeypatch.setattr("agents.raw.raw_agent.get_embedding_service", lambda: MagicMock())
    monkeypatch.setattr("agents.raw.raw_agent.get_db_service", lambda: AsyncMock())

    # Reset the autouse mock's call count for clean assertion
    mock_kb_service.write_domain_knowledge.reset_mock()

    agent = RawAgent()
    result = await agent.process({
        "task": "research",
        "context": {"mode": "research"},
        "trace_id": "t1",
        "conversation_id": "c1",
    })
    assert result["success"]
    assert call_count["n"] == 2
    # The topic-summary path also writes KB (1 call) plus 1 successful page = 2 total.
    # The failing page should NOT have triggered a write.
    # We assert at least 1 page write succeeded:
    assert any(
        # one of the calls is for the OK page
        "ok content" in str(call) or "page summary" in str(call) or "ok.example" in str(call)
        for call in mock_kb_service.write_domain_knowledge.await_args_list
    )
