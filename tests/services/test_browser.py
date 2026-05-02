"""Unit tests for services/browser — Playwright is mocked everywhere.

Live integration tests live in tests/services/test_browser_live.py
and are marked @pytest.mark.live (skipped in CI).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.browser.service as browser_mod
from services.browser import (
    BrowserService,
    BrowserError,
    BrowserTimeoutError,
    BrowserNavigationError,
    BrowserCaptchaDetected,
    BrowserRateLimited,
    BrowserProfileError,
    get_browser_service,
)


def test_singleton_returns_same_instance():
    browser_mod._instance = None
    a = get_browser_service()
    b = get_browser_service()
    assert a is b
    assert isinstance(a, BrowserService)


def test_error_hierarchy():
    for cls in (
        BrowserTimeoutError,
        BrowserNavigationError,
        BrowserCaptchaDetected,
        BrowserRateLimited,
        BrowserProfileError,
    ):
        assert issubclass(cls, BrowserError)


@pytest.mark.asyncio
async def test_lazy_start_no_chromium_before_first_use():
    browser_mod._instance = None
    svc = get_browser_service()
    assert svc._playwright is None
    assert svc._browser is None
    assert svc._contexts == {}


@pytest.mark.asyncio
async def test_get_context_creates_then_caches(monkeypatch, tmp_path):
    browser_mod._instance = None
    svc = get_browser_service()

    fake_pw = MagicMock()
    fake_pw.chromium.launch_persistent_context = AsyncMock(
        side_effect=lambda *a, **kw: MagicMock(name=f"ctx-{kw['user_data_dir']}")
    )
    monkeypatch.setattr(
        browser_mod, "_async_playwright_start",
        AsyncMock(return_value=fake_pw),
    )
    monkeypatch.setattr(
        browser_mod, "BROWSER_PROFILES_DIR", str(tmp_path)
    )

    ctx_a = await svc._get_context("default")
    ctx_b = await svc._get_context("default")
    ctx_c = await svc._get_context("personal")

    assert ctx_a is ctx_b   # same profile → cached
    assert ctx_a is not ctx_c   # different profile → distinct
    assert (tmp_path / "default").is_dir()
    assert (tmp_path / "personal").is_dir()


@pytest.mark.asyncio
async def test_get_context_rejects_invalid_profile_name():
    browser_mod._instance = None
    svc = get_browser_service()
    with pytest.raises(BrowserProfileError):
        await svc._get_context("../etc/passwd")
    with pytest.raises(BrowserProfileError):
        await svc._get_context("")


# --- Task 2.1: search() + DDG parser ---------------------------------------
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_parse_ddg_html_returns_search_results():
    from services.browser import _parse_ddg_html
    html = (FIXTURE_DIR / "ddg_search_cruz_ai.html").read_text()
    results = _parse_ddg_html(html)
    assert len(results) >= 5
    r0 = results[0]
    assert set(r0.keys()) == {"title", "url", "snippet", "rank"}
    assert r0["title"]
    assert r0["url"].startswith("http")
    assert r0["rank"] == 1


def test_parse_ddg_html_empty_on_garbage():
    from services.browser import _parse_ddg_html
    assert _parse_ddg_html("<html><body>no results</body></html>") == []


def test_parse_ddg_html_strips_redirector():
    """DDG sometimes wraps result URLs in /l/?uddg=… — parser must unwrap."""
    from services.browser import _parse_ddg_html
    html = (FIXTURE_DIR / "ddg_search_cruz_ai.html").read_text()
    results = _parse_ddg_html(html)
    urls = [r["url"] for r in results]
    # The fixture has one /l/?uddg=https%3A%2F%2Fanthropic.com%2Fclaude entry.
    assert "https://anthropic.com/claude" in urls
    # And no result URL should still contain the redirector.
    assert not any("/l/?uddg=" in u for u in urls)


@pytest.mark.asyncio
async def test_search_returns_top_n(monkeypatch, tmp_path):
    browser_mod._instance = None
    svc = get_browser_service()

    fixture_html = (FIXTURE_DIR / "ddg_search_cruz_ai.html").read_text()

    fake_page = MagicMock()
    fake_page.goto = AsyncMock()
    fake_page.content = AsyncMock(return_value=fixture_html)
    fake_page.url = "https://duckduckgo.com/html/?q=cruz+ai"
    fake_page.close = AsyncMock()
    fake_ctx = MagicMock()
    fake_ctx.new_page = AsyncMock(return_value=fake_page)
    monkeypatch.setattr(svc, "_get_context", AsyncMock(return_value=fake_ctx))
    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)

    results = await svc.search("cruz ai", limit=3, profile="default")
    assert len(results) == 3
    assert results[0]["rank"] == 1


# --- Task 2.2: fetch() + retry policy ---


@pytest.mark.asyncio
async def test_fetch_returns_page_result(monkeypatch):
    browser_mod._instance = None
    svc = get_browser_service()

    fake_page = MagicMock()
    fake_page.goto = AsyncMock(return_value=MagicMock(status=200))
    fake_page.content = AsyncMock(return_value="<html><body>hi</body></html>")
    fake_page.title = AsyncMock(return_value="Example")
    fake_page.url = "https://example.com/"
    fake_page.evaluate = AsyncMock(return_value="hi")
    fake_ctx = MagicMock()
    fake_ctx.new_page = AsyncMock(return_value=fake_page)
    monkeypatch.setattr(svc, "_get_context", AsyncMock(return_value=fake_ctx))
    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)

    result = await svc.fetch("https://example.com")
    assert result["status"] == 200
    assert result["title"] == "Example"
    assert result["text"] == "hi"
    assert result["byte_size"] > 0


@pytest.mark.asyncio
async def test_fetch_retries_once_then_surfaces(monkeypatch):
    from playwright.async_api import TimeoutError as PWTimeout

    browser_mod._instance = None
    svc = get_browser_service()

    fake_page = MagicMock()
    fake_page.goto = AsyncMock(side_effect=PWTimeout("timed out"))
    fake_page.close = AsyncMock()
    fake_ctx = MagicMock()
    fake_ctx.new_page = AsyncMock(return_value=fake_page)
    monkeypatch.setattr(svc, "_get_context", AsyncMock(return_value=fake_ctx))
    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)
    monkeypatch.setattr(browser_mod, "_RETRY_BACKOFF_S", 0.0)

    with pytest.raises(BrowserTimeoutError):
        await svc.fetch("https://example.com", timeout_ms=100)

    # Two goto attempts: original + one retry
    assert fake_page.goto.await_count == 2
