"""
PlaneService — thin async wrapper around the Plane.so REST API.

Targets either self-hosted Plane (e.g. pm.simpleinc.cloud) or cloud Plane
(api.plane.so) — decided by PLANE_BASE_URL env var.

Used by PM (sprint ticket creation) and CATCH (meeting action items).

Env vars:
    PLANEIO_API_KEY  — required. API token from workspace settings.
    PLANE_BASE_URL   — required. e.g. "https://pm.simpleinc.cloud"
                       (no trailing slash, no /api).

Auth uses the `X-API-Key` header (not Bearer, unlike most GitHub/SendGrid
integrations).

Usage:
    from services.plane import PlaneService
    svc = PlaneService()
    result = await svc.create_issue(
        workspace_slug="simpleinc",
        project_id="...",
        title="Ship AMA homepage",
        description="Next.js + Tailwind deploy",
        priority="high",
        labels=["frontend"],
    )
    # result = {"created": True, "issue_id": "...", "url": "..."}
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("cruz.services.plane")

_PLANE_PRIORITIES = ("urgent", "high", "medium", "low", "none")


class PlaneService:
    """Async wrapper around a minimal slice of the Plane REST API."""

    def __init__(self) -> None:
        # Env read at call time so tests can patch os.environ.
        pass

    async def create_issue(
        self,
        workspace_slug: str,
        project_id: str,
        title: str,
        description: str = "",
        priority: str = "none",
        labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a single issue in a Plane workspace + project.

        Args:
            workspace_slug:  workspace identifier from the Plane URL
            project_id:      UUID of the project
            title:           issue title (Plane field: `name`)
            description:     markdown/HTML body (default empty)
            priority:        urgent | high | medium | low | none
            labels:          list of label names or IDs to attach

        Returns {"created": True, "issue_id": str, "url": str}.
        Raises RuntimeError on missing config or non-2xx response.
        """
        api_key = os.environ.get("PLANEIO_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "PLANEIO_API_KEY is not set — cannot create Plane issue. "
                "Generate one in Plane workspace settings and put it in .env."
            )

        base_url = os.environ.get("PLANE_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            raise RuntimeError(
                "PLANE_BASE_URL is not set (e.g. https://pm.simpleinc.cloud). "
                "Set it in .env."
            )

        if priority not in _PLANE_PRIORITIES:
            priority = "none"

        url = (
            f"{base_url}/api/v1/workspaces/{workspace_slug}"
            f"/projects/{project_id}/issues/"
        )
        payload: Dict[str, Any] = {
            "name": title,
            "description_html": _markdown_to_html(description),
            "priority": priority,
        }
        if labels:
            payload["labels"] = list(labels)

        async with httpx.AsyncClient(
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            },
            timeout=20.0,
        ) as client:
            resp = await client.post(url, json=payload)

        if resp.status_code >= 300:
            raise RuntimeError(
                f"Plane create_issue failed: HTTP {resp.status_code} — {resp.text}"
            )

        data = resp.json()
        issue_id = data.get("id", "")
        # Plane doesn't return a direct web URL in the API response;
        # construct a stable one from the base URL + ids.
        issue_url = (
            f"{base_url}/{workspace_slug}/projects/{project_id}/issues/{issue_id}"
        )
        logger.info(
            "Plane issue created: workspace=%s project=%s id=%s",
            workspace_slug, project_id, issue_id,
        )
        return {"created": True, "issue_id": issue_id, "url": issue_url}


# ── Helpers ───────────────────────────────────────────────────────────────

def _markdown_to_html(text: str) -> str:
    """
    Minimal markdown → HTML for Plane's description_html field.

    Plane's editor accepts HTML. We don't pull in a full markdown lib for
    one method — newlines become <br/>, nothing else is transformed.
    If callers need richer formatting later, switch to `markdown` package.
    """
    if not text:
        return ""
    escaped = (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )
    return "<p>" + escaped.replace("\n\n", "</p><p>").replace("\n", "<br/>") + "</p>"
