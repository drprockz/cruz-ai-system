"""
Tests for SentinelAgent — Claude-powered PR code reviewer.

Flow:
  1. Fetch PR metadata + diff from GitHub API via httpx
  2. Send diff to Claude Sonnet 4 with security/quality review prompt
  3. Parse structured review JSON from Claude's response
  4. Return review with requires_approval=True (posting inline comments
     is visible to the whole team — gate before publishing)

Context dict:
  {
    "repo":     "owner/repo",
    "pr_number": 42,
  }
  GitHub token sourced from GITHUB_TOKEN env var.

Output (AgentOutput.result):
  {
    "repo":           "owner/repo",
    "pr_number":      42,
    "summary":        "<overall review summary>",
    "issues":         [{"file", "line", "severity", "comment"}, ...],
    "critical_count": <int>,
    "high_count":     <int>,
  }

Rules:
  - requires_approval=True — posting inline comments is visible to team
  - Uses Claude Sonnet 4 (no Ollama — security review needs quality)
  - GitHub API failure → success=False
  - Empty diff is valid — returns clean review with zero issues
  - self.log() on success and error paths
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput, BaseAgent


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_input(
    task: str = "Review PR #42 in drprockz/ama-website",
    repo: str = "drprockz/ama-website",
    pr_number: int = 42,
) -> AgentInput:
    return {
        "task": task,
        "context": {"repo": repo, "pr_number": pr_number},
        "trace_id": "trace-sentinel-001",
        "conversation_id": "conv-sentinel-001",
    }


def _pr_files(patches: list | None = None) -> list:
    if patches is None:
        patches = [
            {
                "filename": "src/api/auth.js",
                "patch": "@@ -80,6 +80,10 @@ function login(req, res) {\n"
                         "+  const query = `SELECT * FROM users WHERE email='${email}'`;\n"
                         "+  db.query(query, callback);\n",
                "status": "modified",
                "additions": 2,
                "deletions": 0,
            }
        ]
    return patches


def _clean_review() -> dict:
    return {
        "summary": "Code looks clean. One minor style issue noted.",
        "issues": [],
    }


def _critical_review() -> dict:
    return {
        "summary": "Critical SQL injection vulnerability found.",
        "issues": [
            {
                "file": "src/api/auth.js",
                "line": 84,
                "severity": "critical",
                "comment": "Direct string interpolation in SQL query — use parameterised queries.",
            },
            {
                "file": "src/api/auth.js",
                "line": 90,
                "severity": "high",
                "comment": "Password compared without constant-time equality.",
            },
        ],
    }


def _setup_github_mock(mock_client_cls, files: list | None = None):
    """Mock httpx.AsyncClient for two sequential GitHub GET calls."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    pr_meta = MagicMock()
    pr_meta.json.return_value = {
        "title": "Add auth endpoint",
        "body": "Implements login/logout",
        "number": 42,
        "head": {"sha": "abc123"},
    }
    pr_meta.raise_for_status = MagicMock()

    files_resp = MagicMock()
    files_resp.json.return_value = _pr_files(files)
    files_resp.raise_for_status = MagicMock()

    mock_client.get = AsyncMock(side_effect=[pr_meta, files_resp])
    mock_client_cls.return_value = mock_client
    return mock_client


def _setup_claude_mock(mock_anthropic_cls, review: dict):
    mock_claude = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=json.dumps(review))]
    mock_resp.usage = MagicMock(input_tokens=500, output_tokens=200)
    mock_claude.messages = MagicMock()
    mock_claude.messages.create = AsyncMock(return_value=mock_resp)
    mock_anthropic_cls.return_value = mock_claude
    return mock_claude


# ─────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────

class TestSentinelAgentInterface:
    def test_sentinel_agent_can_be_imported(self):
        from agents.sentinel.sentinel_agent import SentinelAgent  # noqa: F401

    def test_sentinel_agent_extends_base_agent(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        assert issubclass(SentinelAgent, BaseAgent)

    def test_sentinel_agent_name_is_SENTINEL(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        assert SentinelAgent().name == "SENTINEL"

    def test_process_is_coroutine(self):
        import asyncio
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient"), \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            coro = SentinelAgent().process(_make_input())
            assert asyncio.iscoroutine(coro)
            coro.close()

    def test_parse_review_is_exported(self):
        from agents.sentinel.sentinel_agent import _parse_review  # noqa: F401


# ─────────────────────────────────────────────
# AgentOutput structure
# ─────────────────────────────────────────────

class TestSentinelAgentOutput:
    async def test_returns_success_true_on_clean_pr(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            _setup_claude_mock(ma, _clean_review())
            result = await SentinelAgent().process(_make_input())
        assert result["success"] is True

    async def test_agent_name_is_SENTINEL_in_output(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            _setup_claude_mock(ma, _clean_review())
            result = await SentinelAgent().process(_make_input())
        assert result["agent"] == "SENTINEL"

    async def test_result_contains_repo_and_pr_number(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            _setup_claude_mock(ma, _clean_review())
            result = await SentinelAgent().process(_make_input(repo="drprockz/ama", pr_number=7))
        assert result["result"]["repo"] == "drprockz/ama"
        assert result["result"]["pr_number"] == 7

    async def test_result_contains_summary(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            _setup_claude_mock(ma, _clean_review())
            result = await SentinelAgent().process(_make_input())
        assert "summary" in result["result"]

    async def test_result_contains_issues_list(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            _setup_claude_mock(ma, _critical_review())
            result = await SentinelAgent().process(_make_input())
        assert isinstance(result["result"]["issues"], list)
        assert len(result["result"]["issues"]) == 2

    async def test_result_contains_critical_and_high_counts(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            _setup_claude_mock(ma, _critical_review())
            result = await SentinelAgent().process(_make_input())
        assert result["result"]["critical_count"] == 1
        assert result["result"]["high_count"] == 1

    async def test_tokens_tracked(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            _setup_claude_mock(ma, _clean_review())
            result = await SentinelAgent().process(_make_input())
        assert result["tokens_used"] == 700  # 500 + 200


# ─────────────────────────────────────────────
# GitHub API fetch
# ─────────────────────────────────────────────

class TestSentinelGitHubFetch:
    async def test_calls_github_pr_metadata_endpoint(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            mock_client = _setup_github_mock(mc)
            _setup_claude_mock(ma, _clean_review())
            await SentinelAgent().process(_make_input(repo="owner/repo", pr_number=5))
        first_call = mock_client.get.call_args_list[0]
        url = first_call[0][0]
        assert "pulls/5" in url
        assert "owner/repo" in url

    async def test_calls_github_files_endpoint(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            mock_client = _setup_github_mock(mc)
            _setup_claude_mock(ma, _clean_review())
            await SentinelAgent().process(_make_input(repo="owner/repo", pr_number=5))
        second_call = mock_client.get.call_args_list[1]
        url = second_call[0][0]
        assert "files" in url

    async def test_returns_error_on_github_api_failure(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("GitHub API error"))
            mc.return_value = mock_client
            result = await SentinelAgent().process(_make_input())
        assert result["success"] is False
        assert result["error"] is not None

    async def test_github_token_sent_in_headers(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        import os
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"), \
             patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test123"}):
            mock_client = _setup_github_mock(mc)
            _setup_claude_mock(ma, _clean_review())
            await SentinelAgent().process(_make_input())
        # Client is constructed — check headers were passed via AsyncClient constructor
        init_kwargs = mc.call_args[1]
        headers = init_kwargs.get("headers", {})
        assert "ghp_test123" in headers.get("Authorization", "")

    async def test_empty_diff_returns_clean_review(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc, files=[])
            _setup_claude_mock(ma, _clean_review())
            result = await SentinelAgent().process(_make_input())
        assert result["success"] is True


# ─────────────────────────────────────────────
# Claude review
# ─────────────────────────────────────────────

class TestSentinelClaudeReview:
    async def test_diff_sent_to_claude(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            mock_claude = _setup_claude_mock(ma, _clean_review())
            await SentinelAgent().process(_make_input())
        create_call = mock_claude.messages.create.call_args
        messages = create_call[1].get("messages") or create_call[0][0]
        full_text = json.dumps(messages)
        # The patch text from _pr_files should appear in the prompt
        assert "auth.js" in full_text or "SELECT" in full_text

    async def test_uses_claude_sonnet_model(self):
        from agents.sentinel.sentinel_agent import SentinelAgent, _MODEL
        assert "claude" in _MODEL.lower()
        assert "sonnet" in _MODEL.lower()

    async def test_each_issue_has_required_fields(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            _setup_claude_mock(ma, _critical_review())
            result = await SentinelAgent().process(_make_input())
        for issue in result["result"]["issues"]:
            for field in ("file", "line", "severity", "comment"):
                assert field in issue, f"Issue missing field '{field}'"

    async def test_clean_pr_has_zero_critical_issues(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            _setup_claude_mock(ma, _clean_review())
            result = await SentinelAgent().process(_make_input())
        assert result["result"]["critical_count"] == 0
        assert result["result"]["high_count"] == 0


# ─────────────────────────────────────────────
# Approval gate
# ─────────────────────────────────────────────

class TestSentinelApprovalGate:
    async def test_requires_approval_true_on_success(self):
        """Posting inline comments to GitHub is visible to team — always gate."""
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            _setup_claude_mock(ma, _clean_review())
            result = await SentinelAgent().process(_make_input())
        assert result["requires_approval"] is True

    async def test_approval_prompt_mentions_issue_count(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            _setup_claude_mock(ma, _critical_review())
            result = await SentinelAgent().process(_make_input())
        assert "2" in result["approval_prompt"]

    async def test_requires_approval_false_on_github_failure(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("down"))
            mc.return_value = mock_client
            result = await SentinelAgent().process(_make_input())
        assert result["requires_approval"] is False


# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

class TestSentinelLogging:
    async def test_log_called_on_success(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        agent = SentinelAgent()
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            _setup_claude_mock(ma, _clean_review())
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input())
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "success"

    async def test_log_called_on_github_failure(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        agent = SentinelAgent()
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("timeout"))
            mc.return_value = mock_client
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input())
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "error"

    async def test_log_failure_does_not_crash_agent(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        agent = SentinelAgent()
        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as mc, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as ma, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(mc)
            _setup_claude_mock(ma, _clean_review())
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                mock_log.side_effect = Exception("DB dead")
                result = await agent.process(_make_input())
        assert result["success"] is True


# ─────────────────────────────────────────────
# Review parsing helpers
# ─────────────────────────────────────────────

class TestReviewParsing:
    def test_parses_clean_json(self):
        from agents.sentinel.sentinel_agent import _parse_review
        review = _parse_review(json.dumps(_clean_review()))
        assert review["summary"] == _clean_review()["summary"]
        assert review["issues"] == []

    def test_parses_json_in_code_fence(self):
        from agents.sentinel.sentinel_agent import _parse_review
        fenced = f"```json\n{json.dumps(_clean_review())}\n```"
        review = _parse_review(fenced)
        assert review is not None

    def test_parses_json_embedded_in_prose(self):
        from agents.sentinel.sentinel_agent import _parse_review
        prose = f"Here is my review:\n{json.dumps(_clean_review())}\nEnd of review."
        review = _parse_review(prose)
        assert review is not None

    def test_returns_none_on_invalid_json(self):
        from agents.sentinel.sentinel_agent import _parse_review
        assert _parse_review("not json at all") is None

    def test_returns_none_when_summary_missing(self):
        from agents.sentinel.sentinel_agent import _parse_review
        assert _parse_review(json.dumps({"issues": []})) is None

    def test_returns_none_on_empty_string(self):
        from agents.sentinel.sentinel_agent import _parse_review
        assert _parse_review("") is None


# ─────────────────────────────────────────────
# R9 — Send mode (context["send"]=True → post to GitHub)
# ─────────────────────────────────────────────

def _make_send_input(
    repo: str = "drprockz/ama-website",
    pr_number: int = 42,
) -> AgentInput:
    return {
        "task": f"Review PR #{pr_number} in {repo}",
        "context": {"repo": repo, "pr_number": pr_number, "send": True},
        "trace_id": "trace-sentinel-send",
        "conversation_id": "conv-sentinel-send",
    }


def _mock_github_service(result=None, raises=None):
    svc = MagicMock()
    if raises is not None:
        svc.post_pr_review = AsyncMock(side_effect=raises)
    else:
        svc.post_pr_review = AsyncMock(
            return_value=result or {"posted": True, "review_id": 777}
        )
    return svc


@pytest.mark.asyncio
class TestSentinelSendMode:
    async def test_send_true_posts_review_to_github(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        gh_svc = _mock_github_service()

        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as httpx_cls, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as claude_cls, \
             patch("agents.sentinel.sentinel_agent.GitHubService", return_value=gh_svc), \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(httpx_cls)
            _setup_claude_mock(claude_cls, _critical_review())
            await SentinelAgent().process(_make_send_input())

        gh_svc.post_pr_review.assert_called_once()

    async def test_send_true_splits_repo_into_owner_and_name(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        gh_svc = _mock_github_service()

        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as httpx_cls, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as claude_cls, \
             patch("agents.sentinel.sentinel_agent.GitHubService", return_value=gh_svc), \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(httpx_cls)
            _setup_claude_mock(claude_cls, _critical_review())
            await SentinelAgent().process(
                _make_send_input(repo="drprockz/ama", pr_number=7)
            )

        kwargs = gh_svc.post_pr_review.call_args.kwargs
        assert kwargs["owner"] == "drprockz"
        assert kwargs["repo"] == "ama"
        assert kwargs["pr_number"] == 7

    async def test_send_true_maps_issues_to_github_comments(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        gh_svc = _mock_github_service()

        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as httpx_cls, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as claude_cls, \
             patch("agents.sentinel.sentinel_agent.GitHubService", return_value=gh_svc), \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(httpx_cls)
            _setup_claude_mock(claude_cls, _critical_review())
            await SentinelAgent().process(_make_send_input())

        comments = gh_svc.post_pr_review.call_args.kwargs["comments"]
        # _critical_review has 2 issues — both should be mapped
        assert len(comments) == 2
        assert comments[0]["path"] == "src/api/auth.js"
        assert comments[0]["line"] == 84
        assert "SQL" in comments[0]["body"] or "injection" in comments[0]["body"].lower()

    async def test_send_true_returns_requires_approval_false(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        gh_svc = _mock_github_service()

        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as httpx_cls, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as claude_cls, \
             patch("agents.sentinel.sentinel_agent.GitHubService", return_value=gh_svc), \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(httpx_cls)
            _setup_claude_mock(claude_cls, _critical_review())
            result = await SentinelAgent().process(_make_send_input())

        assert result["requires_approval"] is False

    async def test_send_true_result_includes_posted_and_review_id(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        gh_svc = _mock_github_service(
            result={"posted": True, "review_id": 42424}
        )

        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as httpx_cls, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as claude_cls, \
             patch("agents.sentinel.sentinel_agent.GitHubService", return_value=gh_svc), \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(httpx_cls)
            _setup_claude_mock(claude_cls, _critical_review())
            result = await SentinelAgent().process(_make_send_input())

        assert result["result"]["posted"] is True
        assert result["result"]["review_id"] == 42424

    async def test_github_post_failure_returns_success_false(self):
        from agents.sentinel.sentinel_agent import SentinelAgent
        gh_svc = _mock_github_service(raises=RuntimeError("GitHub 401"))

        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as httpx_cls, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as claude_cls, \
             patch("agents.sentinel.sentinel_agent.GitHubService", return_value=gh_svc), \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(httpx_cls)
            _setup_claude_mock(claude_cls, _critical_review())
            result = await SentinelAgent().process(_make_send_input())

        assert result["success"] is False
        assert "GitHub" in (result["error"] or "")
        assert result["requires_approval"] is False

    async def test_send_false_is_default_unchanged(self):
        """Without context.send, SENTINEL still returns requires_approval=True."""
        from agents.sentinel.sentinel_agent import SentinelAgent

        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as httpx_cls, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as claude_cls, \
             patch("agents.sentinel.sentinel_agent.GitHubService") as gh_cls, \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(httpx_cls)
            _setup_claude_mock(claude_cls, _critical_review())
            result = await SentinelAgent().process(_make_input())

        assert result["requires_approval"] is True
        gh_cls.assert_not_called()

    async def test_send_with_no_issues_still_posts_summary(self):
        """Clean review → post summary body with no inline comments."""
        from agents.sentinel.sentinel_agent import SentinelAgent
        gh_svc = _mock_github_service()

        with patch("agents.sentinel.sentinel_agent.httpx.AsyncClient") as httpx_cls, \
             patch("agents.sentinel.sentinel_agent.anthropic.AsyncAnthropic") as claude_cls, \
             patch("agents.sentinel.sentinel_agent.GitHubService", return_value=gh_svc), \
             patch("agents.sentinel.sentinel_agent.get_db_service"):
            _setup_github_mock(httpx_cls)
            _setup_claude_mock(claude_cls, _clean_review())
            await SentinelAgent().process(_make_send_input())

        kwargs = gh_svc.post_pr_review.call_args.kwargs
        assert kwargs["comments"] == []
        assert len(kwargs["body"]) > 0
