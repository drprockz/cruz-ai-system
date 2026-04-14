"""
Tests for GitHubService — thin async wrapper around GitHub REST API.

Scope for R9: post PR reviews with inline comments.
Grows later for R10 (MARK file commits) and PM (issue creation).

Contract:
  await svc.post_pr_review(owner, repo, pr_number, body, comments)
    comments = [{"path": str, "line": int, "body": str}, ...]
    → {"posted": True, "review_id": int}
    → raises RuntimeError on missing token or non-2xx
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_response(status: int = 201, review_id: int = 999):
    resp = MagicMock()
    resp.status_code = status
    resp.text = "" if status < 300 else "unauthorized"
    resp.json = MagicMock(return_value={"id": review_id, "state": "COMMENTED"})
    return resp


def _patch_httpx(response):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)
    return patch("services.github.httpx.AsyncClient", return_value=client), client


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class TestGitHubServiceInterface:
    def test_can_be_imported(self):
        from services.github import GitHubService  # noqa: F401

    def test_post_pr_review_is_coroutine(self):
        import asyncio
        from services.github import GitHubService
        svc = GitHubService()
        assert asyncio.iscoroutinefunction(svc.post_pr_review)


# ---------------------------------------------------------------------------
# post_pr_review()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPostPrReview:
    async def test_posts_to_correct_github_url(self):
        from services.github import GitHubService
        resp = _mock_response()
        pc, client = _patch_httpx(resp)
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False), pc:
            svc = GitHubService()
            await svc.post_pr_review(
                owner="drprockz",
                repo="ama-website",
                pr_number=42,
                body="Review summary",
                comments=[],
            )
        call_url = client.post.call_args[0][0]
        assert "api.github.com/repos/drprockz/ama-website/pulls/42/reviews" in call_url

    async def test_posts_correct_payload(self):
        from services.github import GitHubService
        resp = _mock_response()
        pc, client = _patch_httpx(resp)
        comments = [
            {"path": "src/auth.js", "line": 84, "body": "SQL injection risk"},
            {"path": "src/auth.js", "line": 90, "body": "Password timing"},
        ]
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp"}, clear=False), pc:
            svc = GitHubService()
            await svc.post_pr_review(
                owner="o", repo="r", pr_number=1,
                body="Summary here",
                comments=comments,
            )
        payload = client.post.call_args.kwargs["json"]
        assert payload["body"] == "Summary here"
        assert payload["event"] == "COMMENT"
        assert len(payload["comments"]) == 2
        assert payload["comments"][0]["path"] == "src/auth.js"
        assert payload["comments"][0]["line"] == 84

    async def test_returns_posted_true_and_review_id_on_success(self):
        from services.github import GitHubService
        resp = _mock_response(status=201, review_id=12345)
        pc, _ = _patch_httpx(resp)
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp"}, clear=False), pc:
            svc = GitHubService()
            result = await svc.post_pr_review(
                owner="o", repo="r", pr_number=1, body="x", comments=[]
            )
        assert result["posted"] is True
        assert result["review_id"] == 12345

    async def test_raises_on_non_2xx(self):
        from services.github import GitHubService
        resp = _mock_response(status=401)
        pc, _ = _patch_httpx(resp)
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_bad"}, clear=False), pc:
            svc = GitHubService()
            with pytest.raises(RuntimeError, match="GitHub"):
                await svc.post_pr_review(
                    owner="o", repo="r", pr_number=1, body="x", comments=[]
                )

    async def test_raises_when_token_missing(self):
        from services.github import GitHubService
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=True):
            svc = GitHubService()
            with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
                await svc.post_pr_review(
                    owner="o", repo="r", pr_number=1, body="x", comments=[]
                )

    async def test_review_with_no_comments_posts_body_only(self):
        """Empty comments list → still valid review, just the body."""
        from services.github import GitHubService
        resp = _mock_response()
        pc, client = _patch_httpx(resp)
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp"}, clear=False), pc:
            svc = GitHubService()
            result = await svc.post_pr_review(
                owner="o", repo="r", pr_number=1,
                body="Looks clean, no issues.",
                comments=[],
            )
        assert result["posted"] is True
        payload = client.post.call_args.kwargs["json"]
        assert payload["comments"] == []


# ---------------------------------------------------------------------------
# create_or_update_file() — R10 MARK doc publish
# ---------------------------------------------------------------------------

def _mock_get_response(exists: bool, sha: str = "oldsha123"):
    resp = MagicMock()
    resp.status_code = 200 if exists else 404
    resp.text = "" if exists else "Not Found"
    resp.json = MagicMock(return_value={"sha": sha} if exists else {})
    return resp


def _mock_put_response(status: int = 201, commit_sha: str = "newsha456", html_url: str = "https://github.com/o/r/blob/main/docs/api.md"):
    resp = MagicMock()
    resp.status_code = status
    resp.text = "" if status < 300 else "conflict"
    resp.json = MagicMock(return_value={
        "content": {"html_url": html_url},
        "commit": {"sha": commit_sha},
    })
    return resp


def _patch_httpx_get_put(get_resp, put_resp):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(return_value=get_resp)
    client.put = AsyncMock(return_value=put_resp)
    return patch("services.github.httpx.AsyncClient", return_value=client), client


@pytest.mark.asyncio
class TestCreateOrUpdateFile:
    async def test_creates_new_file_when_absent(self):
        """GET returns 404 → PUT without sha."""
        from services.github import GitHubService
        get_r = _mock_get_response(exists=False)
        put_r = _mock_put_response(status=201)
        pc, client = _patch_httpx_get_put(get_r, put_r)
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp"}, clear=False), pc:
            svc = GitHubService()
            await svc.create_or_update_file(
                owner="o", repo="r",
                path="docs/api.md",
                content="# API",
                message="docs: init",
            )
        # PUT called once (create path — no sha in payload)
        client.put.assert_called_once()
        payload = client.put.call_args.kwargs["json"]
        assert "sha" not in payload
        assert payload["message"] == "docs: init"
        # content must be base64-encoded
        import base64
        assert base64.b64decode(payload["content"]).decode() == "# API"

    async def test_updates_existing_file_includes_sha(self):
        """GET returns 200 → PUT with existing sha to avoid conflict."""
        from services.github import GitHubService
        get_r = _mock_get_response(exists=True, sha="existing-sha-abc")
        put_r = _mock_put_response(status=200)
        pc, client = _patch_httpx_get_put(get_r, put_r)
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp"}, clear=False), pc:
            svc = GitHubService()
            await svc.create_or_update_file(
                owner="o", repo="r",
                path="README.md",
                content="updated",
                message="docs: refresh",
            )
        payload = client.put.call_args.kwargs["json"]
        assert payload["sha"] == "existing-sha-abc"

    async def test_default_branch_is_main(self):
        from services.github import GitHubService
        get_r = _mock_get_response(exists=False)
        put_r = _mock_put_response()
        pc, client = _patch_httpx_get_put(get_r, put_r)
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp"}, clear=False), pc:
            svc = GitHubService()
            await svc.create_or_update_file(
                owner="o", repo="r",
                path="a.md", content="x", message="m",
            )
        payload = client.put.call_args.kwargs["json"]
        assert payload["branch"] == "main"

    async def test_branch_override(self):
        from services.github import GitHubService
        get_r = _mock_get_response(exists=False)
        put_r = _mock_put_response()
        pc, client = _patch_httpx_get_put(get_r, put_r)
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp"}, clear=False), pc:
            svc = GitHubService()
            await svc.create_or_update_file(
                owner="o", repo="r",
                path="a.md", content="x", message="m",
                branch="docs-update",
            )
        assert client.put.call_args.kwargs["json"]["branch"] == "docs-update"

    async def test_returns_published_html_url_and_commit_sha(self):
        from services.github import GitHubService
        get_r = _mock_get_response(exists=False)
        put_r = _mock_put_response(
            status=201,
            commit_sha="commit123",
            html_url="https://github.com/o/r/blob/main/a.md",
        )
        pc, _ = _patch_httpx_get_put(get_r, put_r)
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp"}, clear=False), pc:
            svc = GitHubService()
            result = await svc.create_or_update_file(
                owner="o", repo="r",
                path="a.md", content="x", message="m",
            )
        assert result["published"] is True
        assert result["commit_sha"] == "commit123"
        assert result["html_url"] == "https://github.com/o/r/blob/main/a.md"

    async def test_raises_when_token_missing(self):
        from services.github import GitHubService
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=True):
            svc = GitHubService()
            with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
                await svc.create_or_update_file(
                    owner="o", repo="r",
                    path="a.md", content="x", message="m",
                )

    async def test_raises_when_put_fails(self):
        from services.github import GitHubService
        get_r = _mock_get_response(exists=False)
        put_r = _mock_put_response(status=409)
        pc, _ = _patch_httpx_get_put(get_r, put_r)
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp"}, clear=False), pc:
            svc = GitHubService()
            with pytest.raises(RuntimeError, match="GitHub"):
                await svc.create_or_update_file(
                    owner="o", repo="r",
                    path="a.md", content="x", message="m",
                )
