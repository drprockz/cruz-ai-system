"""BrowserService — Playwright-backed browser primitive layer.

Public API: search, fetch, screenshot, extract_text, download primitives + session()
escape hatch. Singleton via get_browser_service().
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional

from services.browser.errors import BrowserProfileError

logger = logging.getLogger("cruz.services.browser")

# Module-level singleton
_instance: Optional["BrowserService"] = None

# Configurable via env; default ~/.cruz/browser-profiles
BROWSER_PROFILES_DIR: str = os.path.expanduser(
    os.environ.get("CRUZ_BROWSER_PROFILES_DIR", "~/.cruz/browser-profiles")
)

# Profile names: alphanumeric + underscore only, max 32 chars
_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9_]{1,32}$")

# Chromium launch args — apply minimal anti-detect (no stealth library in v1)
_CHROMIUM_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
]


async def _async_playwright_start():
    """Indirection so tests can monkeypatch the Playwright import without a
    real Chromium install."""
    from playwright.async_api import async_playwright
    return await async_playwright().start()


class BrowserService:
    """Singleton Playwright wrapper. Owns one Chromium process and a dict
    of named persistent BrowserContext objects."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None  # not used in persistent-context model, kept for /health
        self._contexts: dict[str, object] = {}
        self._context_locks: dict[str, asyncio.Lock] = {}
        self._init_lock = asyncio.Lock()

    async def _ensure_playwright(self) -> None:
        """Lazy-start the Playwright runtime. Idempotent, concurrency-safe."""
        if self._playwright is not None:
            return
        async with self._init_lock:
            if self._playwright is None:
                self._playwright = await _async_playwright_start()

    async def _get_context(self, profile: str):
        """Return the cached BrowserContext for `profile`, creating it on first
        call. Profile name is validated to avoid path traversal."""
        if not _PROFILE_NAME_RE.match(profile or ""):
            raise BrowserProfileError(f"invalid profile name: {profile!r}")

        if profile in self._contexts:
            return self._contexts[profile]

        await self._ensure_playwright()

        profile_dir = Path(BROWSER_PROFILES_DIR) / profile
        profile_dir.mkdir(parents=True, exist_ok=True)

        ctx = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=True,
            args=_CHROMIUM_ARGS,
            viewport={"width": 1440, "height": 900},
        )
        self._contexts[profile] = ctx
        self._context_locks[profile] = asyncio.Lock()
        return ctx

    async def health(self) -> dict:
        """Return a dict for /health: process alive + first-context CDP ping."""
        if self._playwright is None:
            return {"status": "not_started"}
        try:
            for ctx in self._contexts.values():
                pages = ctx.pages
                page = pages[0] if pages else await ctx.new_page()
                await asyncio.wait_for(page.evaluate("1"), timeout=1.0)
                return {"status": "alive", "contexts": list(self._contexts.keys())}
            return {"status": "alive", "contexts": []}
        except Exception as exc:
            return {"status": "degraded", "reason": str(exc)}

    async def shutdown(self) -> None:
        """Close all contexts and stop Playwright. Idempotent."""
        for ctx in list(self._contexts.values()):
            try:
                await ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        self._context_locks.clear()
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None


def get_browser_service() -> "BrowserService":
    """Return the module-level BrowserService singleton."""
    global _instance
    if _instance is None:
        _instance = BrowserService()
    return _instance
