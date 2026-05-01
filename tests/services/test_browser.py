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
