"""BrowserService — Playwright-backed browser primitive layer.

Public API: search, fetch, screenshot, extract_text, download primitives + session()
escape hatch. Singleton via get_browser_service().
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("cruz.services.browser")

# Module-level singleton
_instance: Optional["BrowserService"] = None


class BrowserService:
    """Singleton Playwright wrapper. Owns one Chromium process and a dict
    of named persistent BrowserContext objects."""

    def __init__(self) -> None:
        # Real Playwright/Chromium handles populate lazily on first call.
        self._playwright = None
        self._browser = None
        self._contexts: dict = {}
        self._context_locks: dict = {}


def get_browser_service() -> "BrowserService":
    """Return the module-level BrowserService singleton."""
    global _instance
    if _instance is None:
        _instance = BrowserService()
    return _instance
