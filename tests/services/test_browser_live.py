"""End-to-end integration tests against real sites.

Run manually:
    pytest -m live tests/services/test_browser_live.py -v

Skipped in CI by default.
"""
from __future__ import annotations

import pytest

import services.browser.service as browser_mod
from services.browser import get_browser_service


pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_live_ddg_search_returns_results():
    browser_mod._instance = None
    svc = get_browser_service()
    try:
        results = await svc.search("anthropic claude", limit=5)
        assert len(results) >= 3
        for r in results:
            assert r["title"]
            assert r["url"].startswith("http")
    finally:
        await svc.shutdown()


@pytest.mark.asyncio
async def test_live_fetch_example_com():
    browser_mod._instance = None
    svc = get_browser_service()
    try:
        result = await svc.fetch("https://example.com/")
        assert result["status"] == 200
        assert "Example Domain" in result["text"]
    finally:
        await svc.shutdown()


@pytest.mark.asyncio
async def test_live_personal_profile_persistence(tmp_path, monkeypatch):
    """Smoke: opening the personal profile twice reuses the same on-disk dir.

    Full sign-in persistence is verified manually post-`scripts/browser_login.py`;
    this just proves the dir is created and stable.
    """
    monkeypatch.setenv("CRUZ_BROWSER_PROFILES_DIR", str(tmp_path))
    browser_mod._instance = None
    browser_mod.BROWSER_PROFILES_DIR = str(tmp_path)
    svc = get_browser_service()
    try:
        ctx1 = await svc._get_context("personal")
        await svc.shutdown()

        browser_mod._instance = None
        svc2 = get_browser_service()
        ctx2 = await svc2._get_context("personal")
        # Profile dir reused
        assert (tmp_path / "personal").is_dir()
    finally:
        await svc2.shutdown()
