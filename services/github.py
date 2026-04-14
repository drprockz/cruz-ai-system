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

import base64
import logging
import os
from typing import Any, Dict, List, Optional

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

    async def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str = "main",
    ) -> Dict[str, Any]:
        """
        Create a new file, or update it in place if it already exists.

        GitHub's Contents API requires the existing file's SHA when updating.
        We GET first to discover it; 404 means "create fresh."

        Args:
            owner, repo: repository identifier
            path:        file path within the repo (e.g. "docs/api.md")
            content:     raw text content (base64 encoded for transport)
            message:     commit message
            branch:      target branch (default "main")

        Returns {"published": True, "html_url": str, "commit_sha": str}.
        Raises RuntimeError on missing token or non-2xx on PUT.
        """
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "GITHUB_TOKEN is not set — cannot publish file. "
                "Set it in .env (requires repo:write scope)."
            )

        url = f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        payload: Dict[str, Any] = {
            "message": message,
            "content": encoded,
            "branch": branch,
        }

        async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
            # 1. Look for existing file to get its sha (needed for update)
            get_resp = await client.get(url, params={"ref": branch})
            if get_resp.status_code == 200:
                existing_sha = get_resp.json().get("sha")
                if existing_sha:
                    payload["sha"] = existing_sha

            # 2. PUT creates or updates
            put_resp = await client.put(url, json=payload)

        if put_resp.status_code >= 300:
            raise RuntimeError(
                f"GitHub create_or_update_file failed: "
                f"HTTP {put_resp.status_code} — {put_resp.text}"
            )

        data = put_resp.json()
        html_url = (data.get("content") or {}).get("html_url", "")
        commit_sha = (data.get("commit") or {}).get("sha", "")
        logger.info(
            "GitHub file published: %s/%s/%s on %s commit=%s",
            owner, repo, path, branch, commit_sha,
        )
        return {
            "published": True,
            "html_url": html_url,
            "commit_sha": commit_sha,
        }
