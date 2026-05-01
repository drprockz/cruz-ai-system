"""Unit tests for services/browser — Playwright is mocked everywhere.

Live integration tests live in tests/services/test_browser_live.py
and are marked @pytest.mark.live (skipped in CI).
"""
from __future__ import annotations

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
