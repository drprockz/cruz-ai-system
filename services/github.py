"""
GitHubService — thin async wrapper around the GitHub REST API v3.

Scope (2026-04-14): PR reviews with inline comments (SENTINEL R9).
Will grow for MARK R10 (push file commits) and PM (issue creation).

Env vars:
    GITHUB_TOKEN — required. Personal access token or GitHub App token
                   with repo:write scope.

Usage:
    from services.github import GitHubService
    svc = GitHubService()
    result = await svc.post_pr_review(
        owner="drprockz",
        repo="ama-website",
        pr_number=42,
        body="Review summary in plain text or markdown.",
        comments=[
            {"path": "src/auth.js", "line": 84, "body": "SQL injection risk"},
        ],
    )
    # result = {"posted": True, "review_id": 12345}
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import httpx

logger = logging.getLogger("cruz.services.github")

_GITHUB_API = "https://api.github.com"


class GitHubService:
    """Async wrapper around a minimal slice of the GitHub REST API."""

    def __init__(self) -> None:
        # Token read at call time so tests can patch os.environ.
        pass

    async def post_pr_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        comments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Create a COMMENT-type review on a PR with optional inline comments.

        Args:
            owner:      GitHub org or user (e.g. "drprockz")
            repo:       repository name (e.g. "ama-website")
            pr_number:  PR number
            body:       top-level review body (markdown)
            comments:   list of {path, line, body} — may be empty

        Returns {"posted": True, "review_id": int}.
        Raises RuntimeError on missing token or non-2xx response.
        """
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "GITHUB_TOKEN is not set — cannot post PR review. "
                "Set it in .env (requires repo:write scope)."
            )

        url = f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        payload = {
            "body": body,
            "event": "COMMENT",
            "comments": list(comments),
        }

        async with httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20.0,
        ) as client:
            resp = await client.post(url, json=payload)

        if resp.status_code >= 300:
            raise RuntimeError(
                f"GitHub post_pr_review failed: HTTP {resp.status_code} — {resp.text}"
            )

        data = resp.json()
        review_id = data.get("id")
        logger.info(
            "GitHub PR review posted: %s/%s#%d review_id=%s comments=%d",
            owner, repo, pr_number, review_id, len(comments),
        )
        return {"posted": True, "review_id": review_id}
