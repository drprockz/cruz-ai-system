"""
SentinelAgent — Claude-powered PR code reviewer and security auditor.

Flow:
  1. Fetch PR metadata + changed files from GitHub REST API via httpx
  2. Build a diff context string from all changed file patches
  3. Send to Claude Sonnet 4 with a security/quality review prompt
  4. Parse structured JSON from Claude's response
  5. Return review with requires_approval=True
     (posting inline comments to GitHub is visible to the whole team)

Review JSON structure (from Claude):
  {
    "summary": "<overall review>",
    "issues": [
      {
        "file":     "<filename>",
        "line":     <line number>,
        "severity": "critical" | "high" | "medium" | "low",
        "comment":  "<specific finding>"
      }
    ]
  }
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import anthropic  # kept for legacy tests that patch this attribute

from services.llm import chat as llm_chat
import httpx

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.db import get_db_service
from services.github import GitHubService
from services.knowledge_base import get_kb_service

logger = logging.getLogger("cruz.agents.SENTINEL")

_MODEL = "claude-sonnet-4-6"
_GITHUB_API = "https://api.github.com"

_REVIEW_SYSTEM = """\
You are SENTINEL, an expert code reviewer and security auditor embedded in the CRUZ AI system.

Given a GitHub pull request diff, perform a thorough code review focusing on:
1. Security vulnerabilities (OWASP Top 10, injection, XSS, auth issues)
2. Logic bugs and edge cases
3. Performance problems
4. Code quality and maintainability issues

Respond ONLY with valid JSON — no prose, no markdown, no explanation.

JSON format:
{
  "summary": "<2-3 sentence overall assessment of the PR>",
  "issues": [
    {
      "file":     "<filename where issue appears>",
      "line":     <approximate line number>,
      "severity": "critical" | "high" | "medium" | "low",
      "comment":  "<specific, actionable description of the issue>"
    }
  ]
}

Guidelines:
- summary: be direct — mention the most important finding upfront
- Only report real issues, not style preferences
- severity: critical=security risk, high=definite bug, medium=likely bug, low=code smell
- Empty issues array is valid for clean PRs
- line: use the line number from the diff hunk, or 1 if unavailable"""


class SentinelAgent(BaseAgent):
    """
    PR code review and security audit agent.

    Fetches the PR diff from GitHub, reviews it with Claude Sonnet 4,
    and returns structured findings. Always requires_approval=True —
    posting inline comments to a shared PR is visible to the team.
    """

    KNOWLEDGE_RINGS: list[str] = ["cruz_activities", "cruz_projects_docs"]

    def __init__(self) -> None:
        super().__init__()
        self.name = "SENTINEL"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        db = get_db_service()
        repo = input["context"].get("repo", "")
        pr_number = input["context"].get("pr_number", 0)
        output: Optional[AgentOutput] = None

        # ── KB context (fire-and-forget; never raises) ───────────────────
        kb = get_kb_service()
        kb_context = await kb.build_agent_context(
            input["task"],
            self.KNOWLEDGE_RINGS,
            input["trace_id"],
            project_id=input["context"].get("project_id"),
        )

        try:
            output = await self._do_review(input, start, db, repo, pr_number, kb_context)
            return output
        finally:
            # ── KB activity record (fire-and-forget; never raises) ────────
            try:
                if output is not None:
                    await kb.record_agent_activity(
                        "sentinel",
                        input["task"],
                        str(output.get("result", ""))[:200],
                        output["success"],
                        input["trace_id"],
                        project_id=input["context"].get("project_id"),
                        tokens_used=output.get("tokens_used"),
                    )
            except Exception:
                pass

    async def _do_review(
        self,
        input: AgentInput,
        start: float,
        db: Any,
        repo: str,
        pr_number: int,
        kb_context: str,
    ) -> AgentOutput:
        # ── Fetch PR from GitHub ──────────────────────────────────────────
        try:
            pr_meta, files = await self._fetch_pr(repo, pr_number)
        except Exception as exc:
            err = f"GitHub API error: {exc}"
            logger.warning("[%s] %s", input["trace_id"], err)
            try:
                await self.log(
                    db=db,
                    trace_id=input["trace_id"],
                    status="error",
                    input_data={"repo": repo, "pr_number": pr_number},
                    output_data={"error": err},
                    tokens_used=0,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            except Exception:
                pass
            return AgentOutput(
                success=False,
                result=None,
                agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0,
                error=err,
                requires_approval=False,
                approval_prompt=None,
            )

        # ── Build diff context ────────────────────────────────────────────
        diff_context = _build_diff_context(pr_meta, files)

        # ── Review with Claude ────────────────────────────────────────────
        try:
            review, tokens_used = await self._review_with_claude(diff_context, input["trace_id"], kb_context)
        except Exception as exc:
            err = f"Claude review failed: {exc}"
            logger.warning("[%s] %s", input["trace_id"], err)
            try:
                await self.log(
                    db=db,
                    trace_id=input["trace_id"],
                    status="error",
                    input_data={"repo": repo, "pr_number": pr_number},
                    output_data={"error": err},
                    tokens_used=0,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            except Exception:
                pass
            return AgentOutput(
                success=False,
                result=None,
                agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0,
                error=err,
                requires_approval=False,
                approval_prompt=None,
            )

        # ── Build result ──────────────────────────────────────────────────
        issues: List[Dict[str, Any]] = review.get("issues", [])
        critical_count = sum(1 for i in issues if i.get("severity") == "critical")
        high_count = sum(1 for i in issues if i.get("severity") == "high")
        total_issues = len(issues)

        result = {
            "repo": repo,
            "pr_number": pr_number,
            "summary": review.get("summary", ""),
            "issues": issues,
            "critical_count": critical_count,
            "high_count": high_count,
        }

        # ── Send mode: context["send"]=True → post review to GitHub ──────
        if input["context"].get("send") is True:
            owner, _, repo_name = repo.partition("/")
            comments = [
                {
                    "path": issue["file"],
                    "line": issue["line"],
                    "body": f"**[{issue['severity'].upper()}]** {issue['comment']}",
                }
                for issue in issues
                if issue.get("file") and issue.get("line")
            ]
            try:
                post_result = await GitHubService().post_pr_review(
                    owner=owner,
                    repo=repo_name,
                    pr_number=pr_number,
                    body=review.get("summary", ""),
                    comments=comments,
                )
            except Exception as post_exc:
                err = str(post_exc)
                duration = int((time.monotonic() - start) * 1000)
                try:
                    await self.log(
                        db=db,
                        trace_id=input["trace_id"],
                        status="error",
                        input_data={"repo": repo, "pr_number": pr_number, "mode": "send"},
                        output_data={"error": err, "total_issues": total_issues},
                        tokens_used=tokens_used,
                        duration_ms=duration,
                    )
                except Exception:
                    pass
                return AgentOutput(
                    success=False,
                    result={**result, "posted": False},
                    agent=self.name,
                    duration_ms=duration,
                    tokens_used=tokens_used,
                    error=err,
                    requires_approval=False,
                    approval_prompt=None,
                )

            result["posted"] = post_result.get("posted", False)
            result["review_id"] = post_result.get("review_id")

            duration = int((time.monotonic() - start) * 1000)
            try:
                await self.log(
                    db=db,
                    trace_id=input["trace_id"],
                    status="success",
                    input_data={"repo": repo, "pr_number": pr_number, "mode": "send"},
                    output_data={
                        "total_issues": total_issues,
                        "review_id": result["review_id"],
                    },
                    tokens_used=tokens_used,
                    duration_ms=duration,
                )
            except Exception:
                pass

            return AgentOutput(
                success=True,
                result=result,
                agent=self.name,
                duration_ms=duration,
                tokens_used=tokens_used,
                error=None,
                requires_approval=False,
                approval_prompt=None,
            )

        # ── Draft-only (default): approval gate ──────────────────────────
        approval_prompt = (
            f"Post {total_issues} review comment{'s' if total_issues != 1 else ''} "
            f"on PR #{pr_number} in {repo}?\n"
            f"  Critical: {critical_count}  High: {high_count}\n"
            f"  Summary: {review.get('summary', '')[:100]}\n\n"
            f"Reply 'yes' to post to GitHub or 'no' to discard."
        )

        duration = int((time.monotonic() - start) * 1000)
        try:
            await self.log(
                db=db,
                trace_id=input["trace_id"],
                status="success",
                input_data={"repo": repo, "pr_number": pr_number},
                output_data={"total_issues": total_issues, "critical": critical_count},
                tokens_used=tokens_used,
                duration_ms=duration,
            )
        except Exception:
            pass

        return AgentOutput(
            success=True,
            result=result,
            agent=self.name,
            duration_ms=duration,
            tokens_used=tokens_used,
            error=None,
            requires_approval=True,
            approval_prompt=approval_prompt,
        )

    async def _fetch_pr(
        self, repo: str, pr_number: int
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Fetch PR metadata and changed files from GitHub API."""
        token = os.environ.get("GITHUB_TOKEN", "")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with httpx.AsyncClient(headers=headers) as client:
            pr_resp = await client.get(
                f"{_GITHUB_API}/repos/{repo}/pulls/{pr_number}"
            )
            pr_resp.raise_for_status()
            pr_meta = pr_resp.json()

            files_resp = await client.get(
                f"{_GITHUB_API}/repos/{repo}/pulls/{pr_number}/files"
            )
            files_resp.raise_for_status()
            files = files_resp.json()

        return pr_meta, files

    async def _review_with_claude(
        self, diff_context: str, trace_id: str, kb_context: str = ""
    ) -> tuple[Dict[str, Any], int]:
        """Send diff to Claude and parse review JSON. Returns (review, tokens_used)."""
        system_prompt = _REVIEW_SYSTEM
        if kb_context:
            system_prompt = kb_context + "\n\n" + system_prompt
        response = await llm_chat(
            system="",  # SENTINEL folds the system prompt into the user message
            messages=[
                {
                    "role": "user",
                    "content": f"{system_prompt}\n\nPull request diff:\n\n{diff_context}",
                }
            ],
            max_tokens=4096,
        )
        raw_text = response.content[0].text
        tokens_used = response.usage.input_tokens + response.usage.output_tokens

        review = _parse_review(raw_text)
        if review is None:
            logger.warning("[%s] Could not parse review JSON — returning empty review", trace_id)
            review = {"summary": raw_text[:500], "issues": []}

        return review, tokens_used


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _build_diff_context(pr_meta: Dict[str, Any], files: List[Dict[str, Any]]) -> str:
    """Build a readable diff string from PR metadata and changed files."""
    lines = [
        f"PR #{pr_meta.get('number', '?')}: {pr_meta.get('title', '')}",
        f"Description: {pr_meta.get('body', '') or 'No description'}",
        "",
        "Changed files:",
    ]
    for f in files:
        lines.append(f"\n--- {f.get('filename', '?')} ({f.get('status', '?')}) ---")
        patch = f.get("patch", "")
        if patch:
            lines.append(patch)
    return "\n".join(lines)


def _parse_review(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract review JSON from a model response.

    Handles: pure JSON, ```json fenced, JSON embedded in prose.
    Required fields: summary, issues.
    Returns None on parse failure.
    """
    if not text or not text.strip():
        return None

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    candidate = _try_parse_review(text.strip())
    if candidate is not None:
        return candidate

    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return _try_parse_review(brace_match.group(0))

    return None


def _try_parse_review(text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON and validate required fields."""
    try:
        data = json.loads(text)
        if "summary" in data:
            return {
                "summary": str(data["summary"]),
                "issues": [
                    {
                        "file": str(i.get("file", "")),
                        "line": int(i.get("line", 1)),
                        "severity": str(i.get("severity", "low")),
                        "comment": str(i.get("comment", "")),
                    }
                    for i in data.get("issues", [])
                ],
            }
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None
