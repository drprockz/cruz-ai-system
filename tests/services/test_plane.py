"""
Tests for PlaneService — thin async wrapper around Plane.so REST API.

Targets self-hosted Plane at PLANE_BASE_URL (e.g. https://pm.simpleinc.cloud).
Cloud Plane users can point at https://api.plane.so instead.

Scope for R12+R13: create an issue in a workspace + project.
Used by PM (sprint tickets) and CATCH (meeting action items).

Contract:
  await svc.create_issue(workspace_slug, project_id, title,
                         description="", priority="none", labels=None)
    → {"created": True, "issue_id": str, "url": str}
    → raises RuntimeError on missing key/base-url or non-2xx
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_plane_response(
    status: int = 201,
    issue_id: str = "issue-abc-123",
    sequence_id: int = 42,
):
    resp = MagicMock()
    resp.status_code = status
    resp.text = "" if status < 300 else "forbidden"
    resp.json = MagicMock(return_value={
        "id": issue_id,
        "sequence_id": sequence_id,
        "name": "Sample",
    })
    return resp


def _patch_httpx(response):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)
    return patch("services.plane.httpx.AsyncClient", return_value=client), client


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class TestPlaneServiceInterface:
    def test_can_be_imported(self):
        from services.plane import PlaneService  # noqa: F401

    def test_create_issue_is_coroutine(self):
        import asyncio
        from services.plane import PlaneService
        svc = PlaneService()
        assert asyncio.iscoroutinefunction(svc.create_issue)


# ---------------------------------------------------------------------------
# create_issue()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPlaneCreateIssue:
    async def test_posts_to_workspace_project_issues_url(self):
        from services.plane import PlaneService
        resp = _mock_plane_response()
        pc, client = _patch_httpx(resp)
        env = {
            "PLANEIO_API_KEY": "plane_test_key",
            "PLANE_BASE_URL": "https://pm.simpleinc.cloud",
        }
        with patch.dict(os.environ, env, clear=False), pc:
            svc = PlaneService()
            await svc.create_issue(
                workspace_slug="simpleinc",
                project_id="proj-xyz",
                title="Ship AMA homepage",
            )
        call_url = client.post.call_args[0][0]
        assert "pm.simpleinc.cloud" in call_url
        assert "workspaces/simpleinc/projects/proj-xyz/issues" in call_url

    async def test_payload_includes_title_and_description(self):
        from services.plane import PlaneService
        resp = _mock_plane_response()
        pc, client = _patch_httpx(resp)
        env = {"PLANEIO_API_KEY": "k", "PLANE_BASE_URL": "https://pm.x.cloud"}
        with patch.dict(os.environ, env, clear=False), pc:
            svc = PlaneService()
            await svc.create_issue(
                workspace_slug="ws",
                project_id="p",
                title="Refactor API",
                description="Swap Express for Fastify",
            )
        payload = client.post.call_args.kwargs["json"]
        assert payload["name"] == "Refactor API"
        assert "Swap Express for Fastify" in (
            payload.get("description_html") or payload.get("description") or ""
        )

    async def test_priority_mapped_to_plane_values(self):
        """Plane accepts: urgent | high | medium | low | none."""
        from services.plane import PlaneService
        resp = _mock_plane_response()
        pc, client = _patch_httpx(resp)
        env = {"PLANEIO_API_KEY": "k", "PLANE_BASE_URL": "https://x"}
        with patch.dict(os.environ, env, clear=False), pc:
            svc = PlaneService()
            await svc.create_issue(
                workspace_slug="ws", project_id="p",
                title="t", priority="high",
            )
        assert client.post.call_args.kwargs["json"]["priority"] == "high"

    async def test_default_priority_is_none(self):
        from services.plane import PlaneService
        resp = _mock_plane_response()
        pc, client = _patch_httpx(resp)
        env = {"PLANEIO_API_KEY": "k", "PLANE_BASE_URL": "https://x"}
        with patch.dict(os.environ, env, clear=False), pc:
            svc = PlaneService()
            await svc.create_issue(
                workspace_slug="ws", project_id="p", title="t",
            )
        assert client.post.call_args.kwargs["json"]["priority"] == "none"

    async def test_auth_header_is_x_api_key(self):
        """Plane uses X-API-Key, not Bearer. Verify via AsyncClient kwargs."""
        from services.plane import PlaneService
        resp = _mock_plane_response()
        with patch("services.plane.httpx.AsyncClient") as cls:
            inner = AsyncMock()
            inner.__aenter__ = AsyncMock(return_value=inner)
            inner.__aexit__ = AsyncMock(return_value=None)
            inner.post = AsyncMock(return_value=resp)
            cls.return_value = inner

            env = {"PLANEIO_API_KEY": "plane_secret", "PLANE_BASE_URL": "https://x"}
            with patch.dict(os.environ, env, clear=False):
                svc = PlaneService()
                await svc.create_issue(
                    workspace_slug="ws", project_id="p", title="t",
                )

        headers = cls.call_args.kwargs.get("headers", {})
        assert headers.get("X-API-Key") == "plane_secret"

    async def test_returns_created_true_with_issue_id(self):
        from services.plane import PlaneService
        resp = _mock_plane_response(issue_id="abc-def", sequence_id=7)
        pc, _ = _patch_httpx(resp)
        env = {
            "PLANEIO_API_KEY": "k",
            "PLANE_BASE_URL": "https://pm.simpleinc.cloud",
        }
        with patch.dict(os.environ, env, clear=False), pc:
            svc = PlaneService()
            result = await svc.create_issue(
                workspace_slug="simpleinc", project_id="proj",
                title="t",
            )
        assert result["created"] is True
        assert result["issue_id"] == "abc-def"
        # URL can be constructed client-side since Plane response doesn't
        # include a web URL directly — verify it points at the correct workspace
        assert "simpleinc" in result["url"]
        assert "proj" in result["url"]

    async def test_raises_when_api_key_missing(self):
        from services.plane import PlaneService
        with patch.dict(os.environ, {"PLANEIO_API_KEY": ""}, clear=True):
            svc = PlaneService()
            with pytest.raises(RuntimeError, match="PLANEIO_API_KEY"):
                await svc.create_issue(
                    workspace_slug="ws", project_id="p", title="t",
                )

    async def test_raises_when_base_url_missing(self):
        from services.plane import PlaneService
        env = {"PLANEIO_API_KEY": "k"}  # PLANE_BASE_URL missing
        with patch.dict(os.environ, env, clear=True):
            svc = PlaneService()
            with pytest.raises(RuntimeError, match="PLANE_BASE_URL"):
                await svc.create_issue(
                    workspace_slug="ws", project_id="p", title="t",
                )

    async def test_raises_on_non_2xx(self):
        from services.plane import PlaneService
        resp = _mock_plane_response(status=403)
        pc, _ = _patch_httpx(resp)
        env = {"PLANEIO_API_KEY": "bad", "PLANE_BASE_URL": "https://x"}
        with patch.dict(os.environ, env, clear=False), pc:
            svc = PlaneService()
            with pytest.raises(RuntimeError, match="Plane"):
                await svc.create_issue(
                    workspace_slug="ws", project_id="p", title="t",
                )

    async def test_labels_passed_in_payload(self):
        from services.plane import PlaneService
        resp = _mock_plane_response()
        pc, client = _patch_httpx(resp)
        env = {"PLANEIO_API_KEY": "k", "PLANE_BASE_URL": "https://x"}
        with patch.dict(os.environ, env, clear=False), pc:
            svc = PlaneService()
            await svc.create_issue(
                workspace_slug="ws", project_id="p", title="t",
                labels=["backend", "api"],
            )
        payload = client.post.call_args.kwargs["json"]
        assert payload.get("labels") == ["backend", "api"] or \
               payload.get("label_ids") == ["backend", "api"]
