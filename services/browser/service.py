"""BrowserService — Playwright-backed browser primitive layer.

Public API: search, fetch, screenshot, extract_text, download primitives + session()
escape hatch. Singleton via get_browser_service().
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import urllib.parse
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, List, Optional

from services.browser.errors import (
    BrowserError,
    BrowserProfileError,
    BrowserTimeoutError,
    BrowserNavigationError,
)
from services.browser.parsers import (
    PageResult,
    SearchResult,
    _parse_ddg_html,
)

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

# Pacing — overridden in tests via monkeypatch. Set BROWSER_PACE_DISABLED=1 in
# the environment to skip the random pre-dispatch sleep.
BROWSER_PACE_DISABLED: bool = bool(os.environ.get("BROWSER_PACE_DISABLED"))

# Retry backoff for fetch() on transient failures (timeout, network errors, 5xx)
_RETRY_BACKOFF_S: float = 2.0


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

    async def _pace(self) -> None:
        """Sleep a randomized delay before dispatching work."""
        if BROWSER_PACE_DISABLED:
            return
        await asyncio.sleep(random.uniform(1.0, 3.0))

    async def search(
        self,
        query: str,
        *,
        engine: str = "duckduckgo",
        limit: int = 10,
        profile: str = "default",
        trace_id: str = "",
    ) -> List[SearchResult]:
        """Run a web search; return top-N results."""
        if engine != "duckduckgo":
            raise BrowserError(f"unsupported engine: {engine}")
        await self._pace()
        ctx = await self._get_context(profile)
        page = await ctx.new_page()
        try:
            url = "https://duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            html = await page.content()
            results = _parse_ddg_html(html)[:limit]
            return results
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def fetch(
        self,
        url: str,
        *,
        render_js: bool = True,
        wait_for: Optional[str] = None,
        timeout_ms: int = 15000,
        profile: str = "default",
        trace_id: str = "",
    ) -> PageResult:
        """Fetch a URL; render JS by default; return rendered html + text."""
        from playwright.async_api import TimeoutError as PWTimeout, Error as PWError

        await self._pace()
        ctx = await self._get_context(profile)
        page = await ctx.new_page()
        try:
            attempt = 0
            last_exc: Optional[BaseException] = None
            while attempt < 2:
                try:
                    wait_until = "domcontentloaded" if not render_js else "networkidle"
                    resp = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                    if wait_for:
                        await page.wait_for_selector(wait_for, timeout=timeout_ms)
                    # Inter-fetch jitter
                    if not BROWSER_PACE_DISABLED and wait_for is None:
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                    html = await page.content()
                    title = await page.title()
                    text = await page.evaluate("document.body ? document.body.innerText : ''")
                    status = resp.status if resp else 0
                    if status >= 500:
                        last_exc = BrowserNavigationError(f"http {status} from {url}")
                        raise last_exc
                    return PageResult(
                        url=url,
                        final_url=page.url,
                        status=status,
                        title=title or "",
                        html=html,
                        text=text or "",
                        byte_size=len(html),
                    )
                except PWTimeout as exc:
                    last_exc = BrowserTimeoutError(f"timeout on {url}: {exc}")
                except PWError as exc:
                    last_exc = BrowserNavigationError(f"navigation error on {url}: {exc}")
                except BrowserNavigationError:
                    # Already a 5xx — retry
                    pass
                attempt += 1
                if attempt < 2:
                    await asyncio.sleep(_RETRY_BACKOFF_S)
            assert last_exc is not None
            raise last_exc
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def extract_text(
        self,
        url: str,
        *,
        selector: Optional[str] = None,
        profile: str = "default",
        trace_id: str = "",
    ) -> str:
        """Fetch URL and return plain text from the first matching container."""
        page_result = await self.fetch(url, profile=profile, trace_id=trace_id)
        if selector:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(page_result["html"], "html.parser")
            el = soup.select_one(selector)
            return el.get_text(" ", strip=True) if el else ""
        # Default cascade: <article> → <main> → <body>
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page_result["html"], "html.parser")
        for sel in ("article", "main", "body"):
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                return el.get_text(" ", strip=True)
        return page_result["text"]

    async def screenshot(
        self,
        url: str,
        *,
        full_page: bool = False,
        profile: str = "default",
        trace_id: str = "",
    ) -> bytes:
        """Navigate to URL and return a PNG screenshot."""
        await self._pace()
        ctx = await self._get_context(profile)
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
            return await page.screenshot(full_page=full_page, type="png")
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def download(
        self,
        url: str,
        dest_path: str,
        *,
        profile: str = "default",
        trace_id: str = "",
    ) -> Path:
        """Download a binary URL via Playwright's APIRequestContext; write to disk."""
        await self._pace()
        ctx = await self._get_context(profile)
        resp = await ctx.request.get(url)
        if resp.status >= 400:
            raise BrowserNavigationError(f"http {resp.status} from {url}")
        body = await resp.body()
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return dest

    @asynccontextmanager
    async def session(
        self,
        *,
        profile: str = "default",
        trace_id: str = "",
    ) -> AsyncIterator[Any]:
        """Escape hatch — yield a raw Playwright Page. Prefer a primitive instead.

        The page is closed on context exit. Use only when the five primitives
        can't express the interaction you need.
        """
        await self._pace()
        ctx = await self._get_context(profile)
        page = await ctx.new_page()
        try:
            yield page
        finally:
            try:
                await page.close()
            except Exception:
                pass

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
