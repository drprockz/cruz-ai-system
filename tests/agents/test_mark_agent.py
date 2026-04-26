"""
Tests for MarkAgent — documentation generation specialist.

Modes (via context["doc_type"]):
  "openapi"   — generate OpenAPI/Swagger YAML spec from source code
  "jsdoc"     — generate JSDoc comments for JS/TS source code
  "readme"    — generate a README.md for a project
  "changelog" — generate a changelog entry from a list of commit messages

Primary model: Qwen 2.5 Coder 14B via Ollama.
Fallback: Claude Haiku when Ollama is unavailable.

Output (AgentOutput.result):
  {
    "doc_type": "openapi" | "jsdoc" | "readme" | "changelog",
    "content":  "<generated documentation string>",
    "project":  "<project name>",
  }

Rules:
  - requires_approval=True — writing docs to GitHub/Notion is external
  - Approval prompt mentions doc_type and project
  - Ollama failure → Claude Haiku fallback
  - Unknown doc_type → success=False
  - self.log() on success and error paths
  - tokens_used=0 for Ollama (local); tracked for Claude fallback
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput, BaseAgent


# ─────────────────────────────────────────────
# KB service mock — autouse, applies to every test in this module
# ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_kb_service():
    """Mock KnowledgeBaseService for all MARK tests."""
    mock_kb = MagicMock()
    mock_kb.build_agent_context = AsyncMock(return_value="")
    mock_kb.record_agent_activity = AsyncMock()
    with patch("agents.mark.mark_agent.get_kb_service", return_value=mock_kb):
        yield mock_kb


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

_SAMPLE_CODE = """\
function calculateTax(amount, rate) {
  return amount * rate;
}
"""

_SAMPLE_COMMITS = [
    "feat(auth): add JWT refresh token support",
    "fix(api): handle null user in /me endpoint",
    "chore(deps): bump express from 4.18.1 to 4.18.2",
]


def _make_input(
    task: str = "Generate docs",
    doc_type: str = "openapi",
    project: str = "ama-website",
    code: str = _SAMPLE_CODE,
    commits: list | None = None,
) -> AgentInput:
    ctx: dict = {
        "doc_type": doc_type,
        "project": project,
        "code": code,
    }
    if commits is not None:
        ctx["commits"] = commits
    return {
        "task": task,
        "context": ctx,
        "trace_id": "trace-mark-001",
        "conversation_id": "conv-mark-001",
    }


def _mock_ollama(response_text: str = "generated docs"):
    mock = AsyncMock()
    mock.generate = AsyncMock(return_value={"response": response_text})
    return mock


def _mock_claude(response_text: str = "generated docs", input_tokens: int = 100, output_tokens: int = 50):
    mock_claude = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=response_text)]
    mock_resp.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    mock_claude.messages = MagicMock()
    mock_claude.messages.create = AsyncMock(return_value=mock_resp)
    return mock_claude


# ─────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────

class TestMarkAgentInterface:
    def test_mark_agent_can_be_imported(self):
        from agents.mark.mark_agent import MarkAgent  # noqa: F401

    def test_mark_agent_extends_base_agent(self):
        from agents.mark.mark_agent import MarkAgent
        assert issubclass(MarkAgent, BaseAgent)

    def test_mark_agent_name_is_MARK(self):
        from agents.mark.mark_agent import MarkAgent
        assert MarkAgent().name == "MARK"

    def test_process_is_coroutine(self):
        import asyncio
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService"), \
             patch("agents.mark.mark_agent.get_db_service"):
            coro = MarkAgent().process(_make_input())
            assert asyncio.iscoroutine(coro)
            coro.close()

    def test_uses_qwen_model(self):
        from agents.mark.mark_agent import _MODEL
        assert "qwen" in _MODEL.lower()


# ─────────────────────────────────────────────
# Output structure
# ─────────────────────────────────────────────

class TestMarkAgentOutput:
    async def test_returns_success_true_on_happy_path(self):
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama()), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input())
        assert result["success"] is True

    async def test_agent_name_is_MARK_in_output(self):
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama()), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input())
        assert result["agent"] == "MARK"

    async def test_result_contains_doc_type(self):
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama()), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input(doc_type="readme"))
        assert result["result"]["doc_type"] == "readme"

    async def test_result_contains_project(self):
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama()), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input(project="shooterista"))
        assert result["result"]["project"] == "shooterista"

    async def test_result_contains_content(self):
        from agents.mark.mark_agent import MarkAgent
        content = "openapi: 3.0.0\ninfo:\n  title: AMA API"
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama(content)), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input(doc_type="openapi"))
        assert result["result"]["content"] == content

    async def test_tokens_zero_for_ollama(self):
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama()), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input())
        assert result["tokens_used"] == 0


# ─────────────────────────────────────────────
# OpenAPI mode
# ─────────────────────────────────────────────

class TestMarkOpenAPI:
    async def test_openapi_code_sent_to_ollama(self):
        from agents.mark.mark_agent import MarkAgent
        mock_ollama = _mock_ollama()
        with patch("agents.mark.mark_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.mark.mark_agent.get_db_service"):
            await MarkAgent().process(_make_input(doc_type="openapi", code="def get_user(): pass"))
        prompt = mock_ollama.generate.call_args[1].get("prompt") or mock_ollama.generate.call_args[0][1]
        assert "get_user" in prompt

    async def test_openapi_doc_type_in_prompt(self):
        from agents.mark.mark_agent import MarkAgent
        mock_ollama = _mock_ollama()
        with patch("agents.mark.mark_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.mark.mark_agent.get_db_service"):
            await MarkAgent().process(_make_input(doc_type="openapi"))
        prompt = mock_ollama.generate.call_args[1].get("prompt") or mock_ollama.generate.call_args[0][1]
        assert "openapi" in prompt.lower() or "swagger" in prompt.lower() or "api" in prompt.lower()


# ─────────────────────────────────────────────
# JSDoc mode
# ─────────────────────────────────────────────

class TestMarkJSDoc:
    async def test_jsdoc_returns_success(self):
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama("/** @param {number} x */")), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input(doc_type="jsdoc"))
        assert result["success"] is True

    async def test_jsdoc_code_included_in_prompt(self):
        from agents.mark.mark_agent import MarkAgent
        mock_ollama = _mock_ollama()
        with patch("agents.mark.mark_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.mark.mark_agent.get_db_service"):
            await MarkAgent().process(_make_input(doc_type="jsdoc", code="function add(a, b) { return a + b; }"))
        prompt = mock_ollama.generate.call_args[1].get("prompt") or mock_ollama.generate.call_args[0][1]
        assert "add" in prompt


# ─────────────────────────────────────────────
# README mode
# ─────────────────────────────────────────────

class TestMarkReadme:
    async def test_readme_returns_success(self):
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama("# AMA Website\n...")), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input(doc_type="readme", project="ama"))
        assert result["success"] is True

    async def test_readme_project_name_in_prompt(self):
        from agents.mark.mark_agent import MarkAgent
        mock_ollama = _mock_ollama()
        with patch("agents.mark.mark_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.mark.mark_agent.get_db_service"):
            await MarkAgent().process(_make_input(doc_type="readme", project="suiteadvisors"))
        prompt = mock_ollama.generate.call_args[1].get("prompt") or mock_ollama.generate.call_args[0][1]
        assert "suiteadvisors" in prompt.lower()


# ─────────────────────────────────────────────
# Changelog mode
# ─────────────────────────────────────────────

class TestMarkChangelog:
    async def test_changelog_returns_success(self):
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama("## v1.2.0\n- Added auth")), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input(doc_type="changelog", commits=_SAMPLE_COMMITS))
        assert result["success"] is True

    async def test_changelog_commits_included_in_prompt(self):
        from agents.mark.mark_agent import MarkAgent
        mock_ollama = _mock_ollama()
        with patch("agents.mark.mark_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.mark.mark_agent.get_db_service"):
            await MarkAgent().process(_make_input(
                doc_type="changelog",
                commits=["feat: add payments", "fix: session timeout"],
            ))
        prompt = mock_ollama.generate.call_args[1].get("prompt") or mock_ollama.generate.call_args[0][1]
        assert "payments" in prompt

    async def test_changelog_uses_task_when_no_commits(self):
        """If commits not in context, use task string as source."""
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama("## Changelog")), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input(doc_type="changelog"))
        assert result["success"] is True


# ─────────────────────────────────────────────
# Claude fallback
# ─────────────────────────────────────────────

class TestMarkClaudeFallback:
    async def test_falls_back_to_claude_when_ollama_fails(self):
        from agents.mark.mark_agent import MarkAgent
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(side_effect=ConnectionError("Ollama down"))
        with patch("agents.mark.mark_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.mark.mark_agent.anthropic.AsyncAnthropic", return_value=_mock_claude()), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input())
        assert result["success"] is True

    async def test_claude_fallback_content_returned(self):
        from agents.mark.mark_agent import MarkAgent
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(side_effect=ConnectionError("down"))
        with patch("agents.mark.mark_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.mark.mark_agent.anthropic.AsyncAnthropic", return_value=_mock_claude("claude docs")), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input())
        assert result["result"]["content"] == "claude docs"

    async def test_claude_fallback_tokens_tracked(self):
        from agents.mark.mark_agent import MarkAgent
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(side_effect=ConnectionError("down"))
        with patch("agents.mark.mark_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.mark.mark_agent.anthropic.AsyncAnthropic",
                   return_value=_mock_claude(input_tokens=200, output_tokens=80)), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input())
        assert result["tokens_used"] == 280

    async def test_returns_error_when_both_ollama_and_claude_fail(self):
        from agents.mark.mark_agent import MarkAgent
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(side_effect=ConnectionError("down"))
        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(side_effect=Exception("Claude also down"))
        with patch("agents.mark.mark_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.mark.mark_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input())
        assert result["success"] is False


# ─────────────────────────────────────────────
# Unknown doc_type
# ─────────────────────────────────────────────

class TestMarkUnknownDocType:
    async def test_returns_error_for_unknown_doc_type(self):
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService"), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input(doc_type="wiki"))
        assert result["success"] is False
        assert result["error"] is not None


# ─────────────────────────────────────────────
# Approval gate
# ─────────────────────────────────────────────

class TestMarkApprovalGate:
    async def test_requires_approval_true_on_success(self):
        """Writing docs to GitHub/Notion is external — always gate."""
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama()), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input())
        assert result["requires_approval"] is True

    async def test_approval_prompt_mentions_doc_type_and_project(self):
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama()), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input(doc_type="readme", project="midar"))
        prompt = result["approval_prompt"].lower()
        assert "readme" in prompt
        assert "midar" in prompt

    async def test_requires_approval_false_on_error(self):
        from agents.mark.mark_agent import MarkAgent
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(side_effect=ConnectionError("down"))
        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(side_effect=Exception("also down"))
        with patch("agents.mark.mark_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.mark.mark_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input())
        assert result["requires_approval"] is False


# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

class TestMarkLogging:
    async def test_log_called_on_success(self):
        from agents.mark.mark_agent import MarkAgent
        agent = MarkAgent()
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama()), \
             patch("agents.mark.mark_agent.get_db_service"):
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input())
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "success"

    async def test_log_called_on_error(self):
        from agents.mark.mark_agent import MarkAgent
        agent = MarkAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(side_effect=ConnectionError("down"))
        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(side_effect=Exception("also down"))
        with patch("agents.mark.mark_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.mark.mark_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.mark.mark_agent.get_db_service"):
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input())
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "error"

    async def test_log_failure_does_not_crash_agent(self):
        from agents.mark.mark_agent import MarkAgent
        agent = MarkAgent()
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama()), \
             patch("agents.mark.mark_agent.get_db_service"):
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                mock_log.side_effect = Exception("DB dead")
                result = await agent.process(_make_input())
        assert result["success"] is True


# ─────────────────────────────────────────────
# R10 — Publish mode (context["send"]=True → push to GitHub and/or Notion)
# ─────────────────────────────────────────────

def _make_publish_input(
    target: str = "github",
    doc_type: str = "readme",
    project: str = "ama-website",
    repo: str = "drprockz/ama-website",
    path: str = "README.md",
    branch: str = "main",
    notion_parent_id: str = "notion-parent-123",
) -> AgentInput:
    ctx: dict = {
        "doc_type": doc_type,
        "project": project,
        "code": _SAMPLE_CODE,
        "send": True,
        "target": target,
    }
    if target in ("github", "both"):
        ctx["repo"] = repo
        ctx["path"] = path
        ctx["branch"] = branch
    if target in ("notion", "both"):
        ctx["notion_parent_id"] = notion_parent_id
    return {
        "task": "Publish docs",
        "context": ctx,
        "trace_id": "trace-mark-pub",
        "conversation_id": "conv-mark-pub",
    }


def _mock_github_service(result=None, raises=None):
    svc = MagicMock()
    if raises is not None:
        svc.create_or_update_file = AsyncMock(side_effect=raises)
    else:
        svc.create_or_update_file = AsyncMock(
            return_value=result or {
                "published": True,
                "html_url": "https://github.com/o/r/blob/main/README.md",
                "commit_sha": "abc123",
            }
        )
    return svc


def _mock_notion_service(result=None, raises=None):
    svc = MagicMock()
    if raises is not None:
        svc.create_page = AsyncMock(side_effect=raises)
    else:
        svc.create_page = AsyncMock(
            return_value=result or {
                "created": True,
                "page_id": "pg-777",
                "url": "https://notion.so/pg-777",
            }
        )
    return svc


@pytest.mark.asyncio
class TestMarkPublishMode:
    async def test_github_target_calls_create_or_update_file(self):
        from agents.mark.mark_agent import MarkAgent
        gh = _mock_github_service()
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama("# README")), \
             patch("agents.mark.mark_agent.GitHubService", return_value=gh), \
             patch("agents.mark.mark_agent.get_db_service"):
            await MarkAgent().process(_make_publish_input(target="github"))
        gh.create_or_update_file.assert_called_once()
        kwargs = gh.create_or_update_file.call_args.kwargs
        assert kwargs["owner"] == "drprockz"
        assert kwargs["repo"] == "ama-website"
        assert kwargs["path"] == "README.md"
        assert kwargs["content"] == "# README"

    async def test_github_target_commit_message_mentions_project_and_doc_type(self):
        from agents.mark.mark_agent import MarkAgent
        gh = _mock_github_service()
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama("x")), \
             patch("agents.mark.mark_agent.GitHubService", return_value=gh), \
             patch("agents.mark.mark_agent.get_db_service"):
            await MarkAgent().process(_make_publish_input(doc_type="readme", project="shooterista"))
        msg = gh.create_or_update_file.call_args.kwargs["message"]
        assert "readme" in msg.lower() or "MARK" in msg
        assert "shooterista" in msg.lower() or "MARK" in msg

    async def test_github_publish_result_has_html_url(self):
        from agents.mark.mark_agent import MarkAgent
        gh = _mock_github_service(result={
            "published": True,
            "html_url": "https://github.com/o/r/blob/main/docs.md",
            "commit_sha": "sha123",
        })
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama("x")), \
             patch("agents.mark.mark_agent.GitHubService", return_value=gh), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_publish_input(target="github"))
        assert result["result"]["published"]["github"] is True
        assert result["result"]["github_url"] == "https://github.com/o/r/blob/main/docs.md"

    async def test_notion_target_calls_create_page(self):
        from agents.mark.mark_agent import MarkAgent
        nt = _mock_notion_service()
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama("body")), \
             patch("agents.mark.mark_agent.NotionService", return_value=nt), \
             patch("agents.mark.mark_agent.get_db_service"):
            await MarkAgent().process(_make_publish_input(target="notion"))
        nt.create_page.assert_called_once()
        kwargs = nt.create_page.call_args.kwargs
        assert kwargs["parent_id"] == "notion-parent-123"
        assert kwargs["content"] == "body"

    async def test_notion_publish_result_has_url(self):
        from agents.mark.mark_agent import MarkAgent
        nt = _mock_notion_service(result={
            "created": True,
            "page_id": "pg-42",
            "url": "https://notion.so/pg-42",
        })
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama("x")), \
             patch("agents.mark.mark_agent.NotionService", return_value=nt), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_publish_input(target="notion"))
        assert result["result"]["published"]["notion"] is True
        assert result["result"]["notion_url"] == "https://notion.so/pg-42"

    async def test_both_target_publishes_to_github_and_notion(self):
        from agents.mark.mark_agent import MarkAgent
        gh = _mock_github_service()
        nt = _mock_notion_service()
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama("body")), \
             patch("agents.mark.mark_agent.GitHubService", return_value=gh), \
             patch("agents.mark.mark_agent.NotionService", return_value=nt), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_publish_input(target="both"))
        gh.create_or_update_file.assert_called_once()
        nt.create_page.assert_called_once()
        assert result["result"]["published"]["github"] is True
        assert result["result"]["published"]["notion"] is True

    async def test_github_failure_is_surfaced_without_aborting_notion(self):
        """If target=both and github fails, notion still attempted; overall success=False."""
        from agents.mark.mark_agent import MarkAgent
        gh = _mock_github_service(raises=RuntimeError("GitHub 401"))
        nt = _mock_notion_service()
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama("x")), \
             patch("agents.mark.mark_agent.GitHubService", return_value=gh), \
             patch("agents.mark.mark_agent.NotionService", return_value=nt), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_publish_input(target="both"))
        nt.create_page.assert_called_once()
        assert result["result"]["published"]["github"] is False
        assert result["result"]["published"]["notion"] is True
        # success reflects partial — at least one target landed
        assert result["success"] is True

    async def test_both_targets_fail_returns_success_false(self):
        from agents.mark.mark_agent import MarkAgent
        gh = _mock_github_service(raises=RuntimeError("GitHub 500"))
        nt = _mock_notion_service(raises=RuntimeError("Notion 503"))
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama("x")), \
             patch("agents.mark.mark_agent.GitHubService", return_value=gh), \
             patch("agents.mark.mark_agent.NotionService", return_value=nt), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_publish_input(target="both"))
        assert result["success"] is False
        assert result["result"]["published"]["github"] is False
        assert result["result"]["published"]["notion"] is False

    async def test_publish_returns_requires_approval_false(self):
        from agents.mark.mark_agent import MarkAgent
        gh = _mock_github_service()
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama("x")), \
             patch("agents.mark.mark_agent.GitHubService", return_value=gh), \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_publish_input(target="github"))
        assert result["requires_approval"] is False

    async def test_send_false_is_default_unchanged(self):
        """Without send=True, MARK still drafts + approval gate."""
        from agents.mark.mark_agent import MarkAgent
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama()), \
             patch("agents.mark.mark_agent.GitHubService") as gh_cls, \
             patch("agents.mark.mark_agent.NotionService") as nt_cls, \
             patch("agents.mark.mark_agent.get_db_service"):
            result = await MarkAgent().process(_make_input(doc_type="readme"))
        assert result["requires_approval"] is True
        gh_cls.assert_not_called()
        nt_cls.assert_not_called()


# ─────────────────────────────────────────────
# Knowledge Base integration
# ─────────────────────────────────────────────


from agents.mark.mark_agent import MarkAgent  # noqa: E402


@pytest.mark.asyncio
class TestMarkKnowledgeBase:
    async def test_mark_calls_kb_build_context(self, mock_kb_service):
        """build_agent_context and record_agent_activity must each fire once per process()."""
        with patch("agents.mark.mark_agent.OllamaService", return_value=_mock_ollama()), \
             patch("agents.mark.mark_agent.get_db_service"):
            await MarkAgent().process(_make_input())

        mock_kb_service.build_agent_context.assert_awaited_once()
        mock_kb_service.record_agent_activity.assert_awaited_once()

    def test_mark_declares_knowledge_rings(self):
        """KNOWLEDGE_RINGS must be declared on the class."""
        assert MarkAgent.KNOWLEDGE_RINGS == [
            "cruz_activities",
            "cruz_projects_docs",
        ]
