# SP4 Browser Automation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic Playwright-backed browser primitive layer (`services/browser.py`) with five read-mostly task primitives, named persistent Chromium contexts, in-process per-domain rate limiting, captcha detection, two CRUZ tools (`web_search` + `fetch_url`), retrofits for RAW and PULSE, and a daily health probe — landing every clause of the SP4 exit gate.

**Architecture:** `BrowserService` is a module-level singleton owning one persistent Chromium process and a dict of named `BrowserContext` objects. Public API is five primitives (`search`, `fetch`, `screenshot`, `extract_text`, `download`) plus a `session()` escape hatch. Anti-detect posture is minimal — no stealth library, no proxy. Rate limiting is per-domain token bucket, in-process. The layer is a service (not an agent) — no KB ring participation; consuming agents own their own KB writes per SP2 pattern.

**Tech Stack:** Python 3.11+, Playwright 1.x (Python async API), Chromium (Playwright bundle), pytest + unittest.mock, asyncpg via existing `DatabaseService`, Anthropic SDK (existing CRUZ tool dispatch), ARQ (existing scheduler).

**Spec:** `docs/superpowers/specs/2026-04-26-sp4-browser-automation-design.md`

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `requirements.txt` | Add `playwright==1.49.*` |
| Create | `services/browser/__init__.py` | Public re-exports: `BrowserService`, `get_browser_service`, error classes, `SearchResult`, `PageResult` |
| Create | `services/browser/service.py` | `BrowserService` class — lifecycle, named contexts, 5 primitives, `session()` escape hatch, structured `agent_logs` write-through |
| Create | `services/browser/errors.py` | Error hierarchy (`BrowserError` + 5 subclasses) |
| Create | `services/browser/parsers.py` | Pure functions: `_parse_ddg_html`, `_detect_captcha` |
| Create | `services/browser/rate_limit.py` | `TokenBucketSpec`, `_consume_token`, `_parse_rate_limit_env` |
| Create | `tests/services/test_browser.py` | Unit tests for service skeleton, lifecycle, primitives (Playwright mocked) |
| Create | `tests/services/test_browser_rate_limit.py` | Burst-limit test for the per-domain rate limiter |
| Create | `tests/services/test_browser_captcha.py` | Captcha-detection unit tests against saved HTML fixtures |
| Create | `tests/services/test_browser_live.py` | `@pytest.mark.live` end-to-end tests (DDG search + example.com fetch) |
| Create | `tests/services/fixtures/ddg_search_cruz_ai.html` | Real DDG response captured for parser regression test |
| Create | `tests/services/fixtures/captcha_recaptcha.html` | Real reCAPTCHA page snapshot |
| Create | `tests/services/fixtures/captcha_hcaptcha.html` | Real hCaptcha page snapshot |
| Create | `tests/services/fixtures/captcha_turnstile.html` | Real Cloudflare Turnstile page snapshot |
| Create | `tests/services/fixtures/captcha_false_positive_docs.html` | Doc page that mentions captcha in body but doesn't show one |
| Create | `tests/services/fixtures/captcha_false_positive_widget.html` | Page with cosmetic Turnstile-iframe-like markup that isn't a real challenge |
| Modify | `agents/cruz/cruz_agent.py` | Add `web_search` + `fetch_url` to `CRUZ_TOOLS`; built-in dispatch in both `process()` and `stream_response()` (alongside existing `record_pattern_observation` branch) |
| Modify | `tests/agents/test_cruz_agent.py` | Add tests for the two new tool dispatches in both paths |
| Create | `agents/raw/sources.yml` | RAW source registry: `rss:` (existing list moves here) + `pages:` (new) |
| Modify | `agents/raw/raw_agent.py` | Load `sources.yml`; add page-fetch branch using `get_browser_service().fetch()` |
| Modify | `tests/agents/test_raw_agent.py` | Add tests for the page-fetch branch (browser mocked) |
| Create | `agents/pulse/sources.yml` | PULSE source registry: `rss:` (existing) + `pages:` (new) |
| Modify | `agents/pulse/pulse_agent.py` | Load `sources.yml`; add Web roundup section sourced via the layer |
| Modify | `tests/agents/test_pulse_agent.py` | Add tests for the Web roundup branch (browser mocked) |
| Create | `scripts/browser_login.py` | Headed Chromium against a named profile so the user logs in by hand |
| Create | `scripts/browser_reset.py` | Wipe a named profile directory |
| Create | `workers/tasks/browser_health.py` | Daily ARQ task: `browser_health_probe` — runs a real DDG search, asserts ≥3 results, alerts on failure |
| Modify | `workers/arq_worker.py` | Register `browser_health_probe` in the ARQ task list and cron schedule |
| Modify | `backend/api/main.py` | Extend `/health` to include a `browser` block (alive + CDP ping) |
| Modify | `services/__init__.py` (or wherever singletons are re-exported, if applicable) | Export `get_browser_service` |
| Create | `Makefile` (or extend existing) — target `browser-live-tests` | Convenience: `pytest -m live tests/services/test_browser_live.py -v` |

**Profile directory layout** (runtime, gitignored, created by service on first call):
```
~/.cruz/browser-profiles/
  default/
  personal/
```

---

## Chunk 1: Foundation — service skeleton, lifecycle, error model, /health

### Task 1.1: Add Playwright to requirements and install Chromium

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add Playwright pin**

Append to `requirements.txt` in alphabetical order:

```
playwright==1.49.*
```

- [ ] **Step 2: Install dependency and Chromium**

Run:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

Expected: dependency installed, Chromium bundle downloaded to `~/Library/Caches/ms-playwright/`.

- [ ] **Step 3: Verify install**

Run:

```bash
python -c "from playwright.async_api import async_playwright; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore(sp4): add Playwright 1.49.* dependency"
```

---

### Task 1.2: Skeleton — sub-package layout, error hierarchy, `BrowserService` shell

**Files:**
- Create: `services/browser/__init__.py`
- Create: `services/browser/errors.py`
- Create: `services/browser/service.py`
- Create: `tests/services/test_browser.py`

The plan splits `services/browser.py` into a small sub-package up-front so the file responsible for the lifecycle (`service.py`) doesn't grow past ~500 LOC. Pure-function helpers (`parsers.py`, `rate_limit.py`) land in later tasks.

- [ ] **Step 1: Write the failing test for the singleton accessor and error hierarchy**

```python
# tests/services/test_browser.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_browser.py -v`
Expected: FAIL with `ModuleNotFoundError: services.browser` or `ImportError`.

- [ ] **Step 3: Implement the skeleton across three files**

`services/browser/errors.py`:

```python
"""Error hierarchy for the browser primitive layer."""
from __future__ import annotations


class BrowserError(Exception):
    """Base class for all browser layer errors."""


class BrowserTimeoutError(BrowserError):
    """Raised when a page load or wait_for selector times out."""


class BrowserNavigationError(BrowserError):
    """Raised on DNS, connection, SSL, or HTTP >= 500 errors."""


class BrowserCaptchaDetected(BrowserError):
    """Raised when a captcha challenge is detected on a fetched page."""

    def __init__(self, url: str, kind: str) -> None:
        self.url = url
        self.kind = kind
        super().__init__(f"captcha detected on {url}: {kind}")


class BrowserRateLimited(BrowserError):
    """Raised when the per-domain token bucket is exhausted."""

    def __init__(self, domain: str, retry_after_ms: int) -> None:
        self.domain = domain
        self.retry_after_ms = retry_after_ms
        super().__init__(
            f"rate limited at {domain}; retry after {retry_after_ms}ms"
        )


class BrowserProfileError(BrowserError):
    """Raised on invalid profile name or profile directory corruption."""
```

`services/browser/service.py`:

```python
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
```

`services/browser/__init__.py`:

```python
"""Public API for the browser primitive layer."""
from services.browser.errors import (
    BrowserError,
    BrowserTimeoutError,
    BrowserNavigationError,
    BrowserCaptchaDetected,
    BrowserRateLimited,
    BrowserProfileError,
)
from services.browser.service import BrowserService, get_browser_service

__all__ = [
    "BrowserError",
    "BrowserTimeoutError",
    "BrowserNavigationError",
    "BrowserCaptchaDetected",
    "BrowserRateLimited",
    "BrowserProfileError",
    "BrowserService",
    "get_browser_service",
]
```

> Note for downstream tasks: subsequent code blocks in this plan show snippets like "add to `services/browser.py`" — read those as "add to `services/browser/service.py`" (or whichever sub-module fits the responsibility). The sub-package boundary is: `errors.py` for the exception classes, `parsers.py` for the pure HTML helpers (added in Task 2.1 / 3.2), `rate_limit.py` for the token bucket (added in Task 3.1), `service.py` for everything else.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_browser.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/browser/ tests/services/test_browser.py
git commit -m "feat(sp4): add BrowserService skeleton + error hierarchy"
```

---

### Task 1.3: Lazy lifecycle + named-context resolution

**Files:**
- Modify: `services/browser.py`
- Modify: `tests/services/test_browser.py`

- [ ] **Step 1: Write failing tests for lazy start and context caching**

Append to `tests/services/test_browser.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_browser.py -v`
Expected: 3 new tests FAIL with `AttributeError` on `_get_context` or `_async_playwright_start`.

- [ ] **Step 3: Implement lazy lifecycle and context resolution**

Add to `services/browser/service.py` (above the `BrowserService` class):

```python
import asyncio
import os
import re
from pathlib import Path

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
```

Replace the `BrowserService` class body with:

```python
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
        # If any context exists, ping it via Page.evaluate("1") with timeout.
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
```

Add to the test file (top, with other imports):

```python
import pytest_asyncio  # noqa: F401  — ensure asyncio plugin available
```

If `pytest-asyncio` isn't already in `requirements.txt`, add `pytest-asyncio` and run `pip install`. (Check first: `grep pytest-asyncio requirements.txt`. If missing, add it and `pip install -r requirements.txt` before continuing.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_browser.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/browser/ tests/services/test_browser.py requirements.txt
git commit -m "feat(sp4): lazy Playwright start + named persistent contexts"
```

---

### Task 1.4: `/health` endpoint extension

**Files:**
- Modify: `backend/api/main.py`

- [ ] **Step 1: Read the existing `/health` handler shape**

Run: `grep -n '"/health"\|@app.get("/health")\|def health' backend/api/main.py`

Open the file at the matched line range and **record verbatim**:
- The function name (e.g. `health` / `health_check`)
- The variable name used to build the response dict (e.g. `response`, `status`, `body`)
- The shape of one existing dependency probe (e.g. `response["postgresql"] = ...`) so the new `browser` block matches the pattern exactly

Without this record, Step 4's "match the pattern" instruction is guesswork. The sub-step exists explicitly to take that guesswork off the engineer's plate.

- [ ] **Step 2: Write a test that the response includes a `browser` block**

Add to `tests/api/test_endpoints.py` (or wherever `/health` is tested today; check with `grep -rn '"/health"' tests/`). If no existing health test file:

```python
# tests/api/test_health_browser.py
import pytest
from httpx import AsyncClient

from backend.api.main import app


@pytest.mark.asyncio
async def test_health_includes_browser_block():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "browser" in body
        assert body["browser"]["status"] in {"alive", "not_started", "degraded"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/api/test_health_browser.py -v`
Expected: FAIL — `KeyError: 'browser'`.

- [ ] **Step 4: Add the browser block to `/health`**

Edit the `/health` handler in `backend/api/main.py` to import `get_browser_service` and add:

```python
from services.browser import get_browser_service

# ... inside the /health handler, after existing checks:
try:
    browser_health = await get_browser_service().health()
except Exception as exc:
    browser_health = {"status": "error", "reason": str(exc)}
response["browser"] = browser_health
```

(Adjust to whatever shape the existing handler uses — match the pattern of the other dependency probes.)

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/api/test_health_browser.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/api/main.py tests/api/test_health_browser.py
git commit -m "feat(sp4): expose browser service health on /health"
```

---

## Chunk 2: Primitives — search, fetch, extract_text, screenshot, download, session

### Task 2.1: `search()` primitive + DDG HTML parser + fixture

**Files:**
- Modify: `services/browser.py`
- Modify: `tests/services/test_browser.py`
- Create: `tests/services/fixtures/ddg_search_cruz_ai.html`

- [ ] **Step 1: Capture a real DDG response as a fixture**

Run (one-shot, manually):

```bash
mkdir -p tests/services/fixtures
curl -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
     "https://duckduckgo.com/html/?q=cruz+ai" \
     > tests/services/fixtures/ddg_search_cruz_ai.html
```

Verify it has results (file size > 5KB, contains `<a` tags):

```bash
wc -c tests/services/fixtures/ddg_search_cruz_ai.html
grep -c '<a class="result__a"' tests/services/fixtures/ddg_search_cruz_ai.html
```

Expected: file > 5KB, ≥5 result links.

- [ ] **Step 2: Write failing tests for the parser and `search()`**

Append to `tests/services/test_browser.py`:

```python
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


@pytest.mark.asyncio
async def test_search_returns_top_n(monkeypatch, tmp_path):
    browser_mod._instance = None
    svc = get_browser_service()

    fixture_html = (FIXTURE_DIR / "ddg_search_cruz_ai.html").read_text()

    fake_page = MagicMock()
    fake_page.goto = AsyncMock()
    fake_page.content = AsyncMock(return_value=fixture_html)
    fake_page.url = "https://duckduckgo.com/html/?q=cruz+ai"
    fake_ctx = MagicMock()
    fake_ctx.new_page = AsyncMock(return_value=fake_page)
    monkeypatch.setattr(svc, "_get_context", AsyncMock(return_value=fake_ctx))
    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)

    results = await svc.search("cruz ai", limit=3, profile="default")
    assert len(results) == 3
    assert results[0]["rank"] == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/services/test_browser.py -v`
Expected: 3 new tests FAIL — `AttributeError` on `_parse_ddg_html` and `search`.

- [ ] **Step 4: Implement `_parse_ddg_html` and `search()`**

Add to `services/browser.py`:

```python
import urllib.parse
from typing import Any, List, Optional, TypedDict


class SearchResult(TypedDict):
    title: str
    url: str
    snippet: str
    rank: int


class PageResult(TypedDict):
    url: str
    final_url: str
    status: int
    title: str
    html: str
    text: str
    byte_size: int


# Pacing — overridden in tests via monkeypatch
BROWSER_PACE_DISABLED: bool = bool(os.environ.get("BROWSER_PACE_DISABLED"))


def _parse_ddg_html(html: str) -> List[SearchResult]:
    """Parse DuckDuckGo HTML response. Returns ranked results; empty list on
    structural change. Selectors are constants — update here when DDG changes."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results: List[SearchResult] = []
    for rank, item in enumerate(
        soup.select("div.result, div.web-result"),
        start=1,
    ):
        a = item.select_one("a.result__a")
        snippet_el = item.select_one(".result__snippet")
        if not a or not a.get("href"):
            continue
        # DDG sometimes wraps in /l/?uddg= redirector — strip if present
        href = a["href"]
        parsed = urllib.parse.urlparse(href)
        if parsed.path == "/l/":
            qs = urllib.parse.parse_qs(parsed.query)
            href = qs.get("uddg", [href])[0]
        results.append(SearchResult(
            title=a.get_text(strip=True),
            url=href,
            snippet=snippet_el.get_text(" ", strip=True) if snippet_el else "",
            rank=rank,
        ))
    return results
```

Then add the `search()` method to `BrowserService`:

```python
import random


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


async def _pace(self) -> None:
    """Sleep a randomized delay before dispatching work."""
    if BROWSER_PACE_DISABLED:
        return
    await asyncio.sleep(random.uniform(1.0, 3.0))
```

Also add `beautifulsoup4` to `requirements.txt` if not present (`grep beautifulsoup4 requirements.txt`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/services/test_browser.py -v`
Expected: 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add services/browser/ tests/services/test_browser.py tests/services/fixtures/ddg_search_cruz_ai.html requirements.txt
git commit -m "feat(sp4): add search() primitive + DDG parser with fixture-locked tests"
```

---

### Task 2.2: `fetch()` primitive + retry policy

**Files:**
- Modify: `services/browser.py`
- Modify: `tests/services/test_browser.py`

- [ ] **Step 1: Write failing tests for `fetch()`**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_browser.py -v`
Expected: 2 new tests FAIL.

- [ ] **Step 3: Implement `fetch()` + retry policy**

Add to `services/browser.py`:

```python
_RETRY_BACKOFF_S: float = 2.0


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_browser.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/browser/ tests/services/test_browser.py
git commit -m "feat(sp4): add fetch() primitive with one-retry policy"
```

---

### Task 2.3: `extract_text()`, `screenshot()`, `download()`, `session()` escape hatch

**Files:**
- Modify: `services/browser.py`
- Modify: `tests/services/test_browser.py`

- [ ] **Step 1: Write failing tests for the remaining primitives**

```python
@pytest.mark.asyncio
async def test_extract_text_default_cascade(monkeypatch):
    browser_mod._instance = None
    svc = get_browser_service()

    html = (
        "<html><body>"
        "<nav>nav</nav>"
        "<article>real content here</article>"
        "</body></html>"
    )
    fake_page = MagicMock()
    fake_page.goto = AsyncMock(return_value=MagicMock(status=200))
    fake_page.content = AsyncMock(return_value=html)
    fake_page.title = AsyncMock(return_value="t")
    fake_page.url = "https://example.com/"
    fake_page.evaluate = AsyncMock(return_value="real content here")
    fake_ctx = MagicMock()
    fake_ctx.new_page = AsyncMock(return_value=fake_page)
    monkeypatch.setattr(svc, "_get_context", AsyncMock(return_value=fake_ctx))
    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)

    text = await svc.extract_text("https://example.com")
    assert "real content here" in text
    assert "nav" not in text


@pytest.mark.asyncio
async def test_screenshot_returns_png_bytes(monkeypatch):
    browser_mod._instance = None
    svc = get_browser_service()

    fake_page = MagicMock()
    fake_page.goto = AsyncMock(return_value=MagicMock(status=200))
    fake_page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n...")
    fake_page.url = "https://example.com/"
    fake_ctx = MagicMock()
    fake_ctx.new_page = AsyncMock(return_value=fake_page)
    monkeypatch.setattr(svc, "_get_context", AsyncMock(return_value=fake_ctx))
    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)

    png = await svc.screenshot("https://example.com")
    assert png.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_download_writes_to_path(monkeypatch, tmp_path):
    browser_mod._instance = None
    svc = get_browser_service()

    fake_resp = MagicMock()
    fake_resp.body = AsyncMock(return_value=b"hello world")
    fake_resp.status = 200
    fake_ctx = MagicMock()
    fake_ctx.request.get = AsyncMock(return_value=fake_resp)
    monkeypatch.setattr(svc, "_get_context", AsyncMock(return_value=fake_ctx))
    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)

    dest = tmp_path / "out.bin"
    result = await svc.download("https://example.com/file", str(dest))
    assert result == dest
    assert dest.read_bytes() == b"hello world"


@pytest.mark.asyncio
async def test_session_yields_page(monkeypatch):
    browser_mod._instance = None
    svc = get_browser_service()

    fake_page = MagicMock()
    fake_page.close = AsyncMock()
    fake_ctx = MagicMock()
    fake_ctx.new_page = AsyncMock(return_value=fake_page)
    monkeypatch.setattr(svc, "_get_context", AsyncMock(return_value=fake_ctx))
    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)

    async with svc.session(profile="default") as page:
        assert page is fake_page
    fake_page.close.assert_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_browser.py -v`
Expected: 4 new tests FAIL.

- [ ] **Step 3: Implement the remaining primitives**

Add to `services/browser.py`:

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_browser.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/browser/ tests/services/test_browser.py
git commit -m "feat(sp4): add extract_text, screenshot, download, session escape hatch"
```

---

## Chunk 3: Anti-detect, rate limiter, captcha detection

### Task 3.1: Per-domain token-bucket rate limiter

**Files:**
- Modify: `services/browser.py`
- Create: `tests/services/test_browser_rate_limit.py`

- [ ] **Step 1: Write failing burst test**

```python
# tests/services/test_browser_rate_limit.py
"""Tests for the per-domain token-bucket rate limiter."""
import asyncio
import time

import pytest

import services.browser.service as browser_mod
from services.browser import BrowserRateLimited, get_browser_service


@pytest.mark.asyncio
async def test_burst_exceeding_capacity_raises(monkeypatch):
    """15 calls in <1s; 11th onward should raise BrowserRateLimited."""
    browser_mod._instance = None
    svc = get_browser_service()

    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)
    monkeypatch.setattr(
        svc, "_rate_limit_policy",
        {"example.com": browser_mod.TokenBucketSpec(capacity=10, refill_per_sec=10/60)},
    )

    raised = 0
    for _ in range(15):
        try:
            svc._consume_token("example.com")
        except BrowserRateLimited:
            raised += 1
    assert raised == 5  # 10 succeed, 5 fail


@pytest.mark.asyncio
async def test_bucket_refills_over_time(monkeypatch):
    browser_mod._instance = None
    svc = get_browser_service()

    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)
    monkeypatch.setattr(
        svc, "_rate_limit_policy",
        {"example.com": browser_mod.TokenBucketSpec(capacity=2, refill_per_sec=10.0)},
    )
    # Drain
    svc._consume_token("example.com")
    svc._consume_token("example.com")
    with pytest.raises(BrowserRateLimited):
        svc._consume_token("example.com")
    await asyncio.sleep(0.2)  # 10/sec * 0.2s = 2 tokens refilled
    svc._consume_token("example.com")  # should succeed


def test_per_domain_isolation(monkeypatch):
    browser_mod._instance = None
    svc = get_browser_service()

    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)
    monkeypatch.setattr(
        svc, "_rate_limit_policy",
        {
            "example.com": browser_mod.TokenBucketSpec(capacity=1, refill_per_sec=0.001),
            "other.com":   browser_mod.TokenBucketSpec(capacity=1, refill_per_sec=0.001),
        },
    )
    svc._consume_token("example.com")
    with pytest.raises(BrowserRateLimited):
        svc._consume_token("example.com")
    # other.com still has capacity
    svc._consume_token("other.com")


def test_default_policy_used_for_unknown_domain(monkeypatch):
    browser_mod._instance = None
    svc = get_browser_service()

    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)
    # No per-domain override; default capacity=10
    for _ in range(10):
        svc._consume_token("unknown-domain.com")
    with pytest.raises(BrowserRateLimited):
        svc._consume_token("unknown-domain.com")


def test_env_override_parsing():
    spec = browser_mod._parse_rate_limit_env(
        "duckduckgo.com:30:30/60,techcrunch.com:5:5/60"
    )
    assert spec["duckduckgo.com"].capacity == 30
    assert abs(spec["duckduckgo.com"].refill_per_sec - 30/60) < 1e-9
    assert spec["techcrunch.com"].capacity == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_browser_rate_limit.py -v`
Expected: all FAIL — `AttributeError` on `TokenBucketSpec`, `_consume_token`, `_parse_rate_limit_env`.

- [ ] **Step 3: Implement the rate limiter**

Add to `services/browser.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenBucketSpec:
    capacity: int
    refill_per_sec: float


_DEFAULT_BUCKET = TokenBucketSpec(capacity=10, refill_per_sec=10 / 60)


def _parse_rate_limit_env(raw: str) -> dict[str, TokenBucketSpec]:
    """Parse `domain:cap:N/D,...` into a policy dict."""
    out: dict[str, TokenBucketSpec] = {}
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            domain, cap_s, rate_s = entry.split(":")
            num, denom = rate_s.split("/")
            out[domain] = TokenBucketSpec(
                capacity=int(cap_s),
                refill_per_sec=float(num) / float(denom),
            )
        except Exception:
            logger.warning("ignoring malformed rate-limit entry: %r", entry)
    return out
```

In `BrowserService.__init__`, add:

```python
self._buckets: dict[str, tuple[float, float]] = {}  # domain -> (tokens, last_refill_ts)
self._rate_limit_policy: dict[str, TokenBucketSpec] = _parse_rate_limit_env(
    os.environ.get("CRUZ_BROWSER_RATE_LIMITS", "")
)
```

Add the consume method:

```python
def _consume_token(self, domain: str) -> None:
    """Consume one token for `domain`. Raises BrowserRateLimited on exhaustion."""
    spec = self._rate_limit_policy.get(domain, _DEFAULT_BUCKET)
    now = time.monotonic()
    tokens, last_ts = self._buckets.get(domain, (float(spec.capacity), now))
    elapsed = now - last_ts
    tokens = min(spec.capacity, tokens + elapsed * spec.refill_per_sec)
    if tokens < 1.0:
        retry_after_ms = int(((1.0 - tokens) / spec.refill_per_sec) * 1000)
        self._buckets[domain] = (tokens, now)
        raise BrowserRateLimited(domain=domain, retry_after_ms=retry_after_ms)
    self._buckets[domain] = (tokens - 1.0, now)
```

Wire `_consume_token` into the four URL-touching primitives (`search`, `fetch`, `screenshot`, `download`) — call it after `_pace()` and before `_get_context()`. Extract the domain via `urllib.parse.urlparse(url).netloc`. For `search()`, the domain is `"duckduckgo.com"` (or whichever engine).

Add `import time` if not already imported.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_browser_rate_limit.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Verify the rate limiter is wired into `search()`/`fetch()`/etc.**

Add an integration-style test:

```python
@pytest.mark.asyncio
async def test_fetch_raises_when_bucket_drained(monkeypatch):
    browser_mod._instance = None
    svc = get_browser_service()

    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)
    monkeypatch.setattr(
        svc, "_rate_limit_policy",
        {"example.com": browser_mod.TokenBucketSpec(capacity=0, refill_per_sec=0.001)},
    )
    fake_ctx = MagicMock()
    monkeypatch.setattr(svc, "_get_context", AsyncMock(return_value=fake_ctx))

    with pytest.raises(BrowserRateLimited):
        await svc.fetch("https://example.com")
```

(Add to `tests/services/test_browser_rate_limit.py`.)

Run: `pytest tests/services/test_browser_rate_limit.py -v`
Expected: 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add services/browser/ tests/services/test_browser_rate_limit.py
git commit -m "feat(sp4): add per-domain token-bucket rate limiter"
```

---

### Task 3.2: Captcha detection + fixtures

**Files:**
- Modify: `services/browser.py`
- Create: `tests/services/test_browser_captcha.py`
- Create: `tests/services/fixtures/captcha_recaptcha.html`
- Create: `tests/services/fixtures/captcha_hcaptcha.html`
- Create: `tests/services/fixtures/captcha_turnstile.html`
- Create: `tests/services/fixtures/captcha_false_positive_docs.html`
- Create: `tests/services/fixtures/captcha_false_positive_widget.html`

- [ ] **Step 1: Create captcha HTML fixtures**

Each fixture is a minimal real-world snippet — paste these literally:

`tests/services/fixtures/captcha_recaptcha.html`:
```html
<!DOCTYPE html><html><body>
<form><iframe src="https://www.google.com/recaptcha/api2/anchor?ar=1&k=ABC&co=..." width="304" height="78"></iframe></form>
</body></html>
```

`tests/services/fixtures/captcha_hcaptcha.html`:
```html
<!DOCTYPE html><html><body>
<div class="h-captcha" data-sitekey="abc"><iframe src="https://newassets.hcaptcha.com/captcha/v1/..."></iframe></div>
</body></html>
```

`tests/services/fixtures/captcha_turnstile.html`:
```html
<!DOCTYPE html><html><body>
<iframe src="https://challenges.cloudflare.com/turnstile/..." sandbox="allow-scripts"></iframe>
</body></html>
```

`tests/services/fixtures/captcha_false_positive_docs.html`:
```html
<!DOCTYPE html><html><body>
<article>
<h1>How CAPTCHAs work</h1>
<p>This document explains the captcha challenge mechanism in detail.</p>
<p>Are you a robot? In our usability study, captcha pages frustrated 30% of users.</p>
</article>
</body></html>
```

`tests/services/fixtures/captcha_false_positive_widget.html`:
```html
<!DOCTYPE html><html><body>
<aside class="captcha-explanation">See our help docs for captcha info.</aside>
<main>regular content here</main>
</body></html>
```

- [ ] **Step 2: Write failing tests**

```python
# tests/services/test_browser_captcha.py
"""Tests for the captcha-detection heuristic."""
from pathlib import Path

import pytest

from services.browser import _detect_captcha

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("filename,expected_kind", [
    ("captcha_recaptcha.html", "recaptcha"),
    ("captcha_hcaptcha.html", "hcaptcha"),
    ("captcha_turnstile.html", "turnstile"),
])
def test_detect_real_captchas(filename, expected_kind):
    html = (FIXTURE_DIR / filename).read_text()
    kind = _detect_captcha(html, "https://example.com/page")
    assert kind == expected_kind


def test_text_heuristic_detects_human_check():
    html = "<html><body>please verify you are a human to continue</body></html>"
    assert _detect_captcha(html, "https://example.com") == "text_heuristic"


@pytest.mark.parametrize("filename", [
    "captcha_false_positive_docs.html",
    "captcha_false_positive_widget.html",
])
def test_no_false_positive_for_descriptive_pages(filename):
    html = (FIXTURE_DIR / filename).read_text()
    # The intent: descriptive content mentioning captcha should NOT be classified
    # as a captcha challenge. False positives are acceptable per spec, but these
    # specific cases should pass.
    assert _detect_captcha(html, "https://example.com") is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/services/test_browser_captcha.py -v`
Expected: all FAIL — `_detect_captcha` undefined.

- [ ] **Step 4: Implement the heuristic**

Add to `services/browser.py`:

```python
import re as _re_captcha


_CAPTCHA_TEXT_PATTERN = _re_captcha.compile(
    r"please verify you are (a )?human|are you a robot|press and hold to confirm",
    _re_captcha.IGNORECASE,
)


def _detect_captcha(html: str, url: str) -> Optional[str]:
    """Return the captcha kind if a challenge is detected on the page, else None.

    Heuristic — over-detects deliberately. False positives surface to caller as
    BrowserCaptchaDetected; caller decides how to fall back. Pure function over
    HTML, fully testable.
    """
    if not html:
        return None
    lower = html.lower()
    # Iframe-based challenges
    if 'src="https://www.google.com/recaptcha/' in lower:
        return "recaptcha"
    if 'src="https://newassets.hcaptcha.com/' in lower or 'class="h-captcha"' in lower:
        return "hcaptcha"
    if 'src="https://challenges.cloudflare.com/turnstile/' in lower:
        return "turnstile"
    # Text heuristic — body content asks the user to prove they're human
    if _CAPTCHA_TEXT_PATTERN.search(html):
        return "text_heuristic"
    return None
```

Wire `_detect_captcha` into `fetch()`. After `html = await page.content()` and before returning the `PageResult`, add:

```python
kind = _detect_captcha(html, url)
if kind is not None:
    raise BrowserCaptchaDetected(url=url, kind=kind)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/services/test_browser_captcha.py -v`
Expected: all PASS.

Also re-run the full browser test suite:

Run: `pytest tests/services/test_browser.py tests/services/test_browser_rate_limit.py tests/services/test_browser_captcha.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add services/browser/ tests/services/test_browser_captcha.py tests/services/fixtures/captcha_*.html
git commit -m "feat(sp4): add captcha detection heuristic with fixtures"
```

---

### Task 3.3: `agent_logs` write-through (Rule 5 compliance)

**Files:**
- Modify: `services/browser.py`
- Modify: `tests/services/test_browser.py`

- [ ] **Step 1: Write failing test that primitives log to `agent_logs`**

```python
@pytest.mark.asyncio
async def test_search_logs_to_agent_logs(monkeypatch):
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

    fake_db = MagicMock()
    fake_db.execute = AsyncMock()
    monkeypatch.setattr(browser_mod, "get_db_service", lambda: fake_db)

    await svc.search("cruz ai", limit=3, trace_id="t1")

    # One agent_logs row was written
    fake_db.execute.assert_awaited()
    args = fake_db.execute.await_args.args
    sql = args[0].lower() if args else ""
    assert "insert into agent_logs" in sql
    # action is 'search', agent is 'browser_service'
    assert "browser_service" in str(args)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_browser.py::test_search_logs_to_agent_logs -v`
Expected: FAIL — DB never called.

- [ ] **Step 3: Implement structured logging on every primitive**

Add to `services/browser.py`:

```python
from services.db import get_db_service


async def _log_call(
    self,
    *,
    action: str,
    status: str,
    duration_ms: int,
    input_data: dict,
    output_data: dict,
    trace_id: str,
) -> None:
    """Write one agent_logs row with agent='browser_service'. Non-fatal."""
    try:
        db = get_db_service()
        await db.execute(
            """
            INSERT INTO agent_logs (
                id, trace_id, agent, action, status,
                input_data, output_data, tokens_used, duration_ms, created_at
            ) VALUES (gen_random_uuid(), $1, 'browser_service', $2, $3,
                      $4::jsonb, $5::jsonb, NULL, $6, NOW())
            """,
            trace_id or "",
            action,
            status,
            json.dumps(input_data),
            json.dumps(output_data),
            duration_ms,
        )
    except Exception as exc:
        logger.warning("[%s] browser _log_call failed (non-fatal): %s", trace_id, exc)
```

Add `import json` if not already present.

Wrap each public primitive in start/duration tracking and call `_log_call`. Example for `search()`:

```python
async def search(self, query: str, *, ...):
    start = time.monotonic()
    status = "success"
    result_count = 0
    try:
        # ... existing implementation ...
        result_count = len(results)
        return results
    except BrowserError:
        status = "error"
        raise
    finally:
        await self._log_call(
            action="search",
            status=status,
            duration_ms=int((time.monotonic() - start) * 1000),
            input_data={"query": query[:100], "limit": limit, "profile": profile},
            output_data={"result_count": result_count},
            trace_id=trace_id,
        )
```

Apply the same pattern to `fetch`, `screenshot`, `extract_text`, `download`, and on `session()` log a `session_open` row at context entry.

For `search()` zero-result case, also add a `degraded` status branch:

```python
if not results:
    status = "degraded"
    # output_data picks up reason via _log_call
```

Set `output_data={"result_count": 0, "reason": "ddg_zero_results"}` when zero results returned.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_browser.py -v`
Expected: all PASS, including the new logging test.

- [ ] **Step 5: Commit**

```bash
git add services/browser/ tests/services/test_browser.py
git commit -m "feat(sp4): structured agent_logs write-through for every browser call"
```

---

### Task 3.4: Live integration tests (`@pytest.mark.live`)

**Files:**
- Create: `tests/services/test_browser_live.py`
- Modify: `Makefile` (or create if absent)

- [ ] **Step 1: Write the live tests**

```python
# tests/services/test_browser_live.py
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
```

- [ ] **Step 2: Add `pytest.mark.live` to `pytest.ini` or `pyproject.toml`**

Run: `grep -n "markers" pytest.ini pyproject.toml 2>/dev/null`

If `live` marker not registered, add to `pytest.ini` (under `[tool:pytest]` or `[pytest]`):

```ini
markers =
    live: live integration tests against real external services (skipped in CI)
```

If `pytest.ini` exists with markers, append the line. If `pyproject.toml` has `[tool.pytest.ini_options]`, append to its `markers` list.

- [ ] **Step 3: Configure CI to skip the `live` marker**

If CI runs `pytest`, ensure it uses `pytest -m "not live"`. Inspect `.github/workflows/` or whatever CI config exists. Update if needed.

- [ ] **Step 4: Add Makefile target**

If `Makefile` exists, append:

```makefile
.PHONY: browser-live-tests
browser-live-tests:
	pytest -m live tests/services/test_browser_live.py -v
```

If no Makefile exists, create one with that single target.

- [ ] **Step 5: Run live tests manually to verify the layer works end-to-end**

Run: `make browser-live-tests` (or `pytest -m live tests/services/test_browser_live.py -v`)
Expected: 3 tests PASS against real DuckDuckGo and example.com. (This requires a live network and Chromium installed via `playwright install chromium`.)

- [ ] **Step 6: Commit**

```bash
git add tests/services/test_browser_live.py pytest.ini Makefile .github/workflows/
git commit -m "test(sp4): add @pytest.mark.live integration tests + make target"
```

---

## Chunk 4: CRUZ tool wiring + ops scripts + daily health probe

### Task 4.1: CRUZ `web_search` and `fetch_url` tools (non-streaming `process()` path)

**Files:**
- Modify: `agents/cruz/cruz_agent.py`
- Modify: `tests/agents/test_cruz_agent.py`

- [ ] **Step 1: Read the existing tool_use test helper before writing new tests**

Run: `grep -n "_make_tool_use_response\|_make_text_response\|TestCruzWithToolUse" tests/agents/test_cruz_agent.py`

You should see (around line 215–220 in the current file):

```
TestCruzWithToolUse class — _make_tool_use_response(self, tool_name, tool_input)
TestCruzWithoutToolUse class — _make_text_response(self, text)
```

Both helpers return `MagicMock` instances shaped to look like Anthropic SDK responses. The pattern for mocking a one-shot tool_use → end_turn loop is:

```python
client = self._make_claude_client(self._make_tool_use_response("name", {...}))
# then a second call returning text:
client.messages.create.side_effect = [
    self._make_tool_use_response("name", {...}),
    self._make_text_response("final answer"),
]
with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
    ...
```

Use this verbatim shape — do not invent a new mocking strategy.

- [ ] **Step 2: Write failing tests for the two new tool dispatches**

Append to `tests/agents/test_cruz_agent.py` (inside or alongside `TestCruzWithToolUse` so the helpers are reachable; if writing standalone classes, copy `_make_tool_use_response` and `_make_text_response` from the existing class):

```python
class TestCruzBrowserTools(TestCruzWithToolUse):
    """Tests for the web_search and fetch_url built-in tools."""

    @pytest.mark.asyncio
    async def test_cruz_web_search_tool_dispatch(self, monkeypatch):
        """When Claude calls web_search, CRUZ invokes BrowserService.search()
        and feeds formatted results back into the loop."""
        from agents.cruz.cruz_agent import CruzAgent
        import services.browser.service as browser_mod

        fake_browser = MagicMock()
        fake_browser.search = AsyncMock(return_value=[
            {"title": "Result A", "url": "https://a.com",
             "snippet": "snip", "rank": 1},
        ])
        monkeypatch.setattr(browser_mod, "_instance", fake_browser)

        # First Claude call: emit a web_search tool_use.
        # Second Claude call: emit final text after seeing the tool_result.
        client = self._make_claude_client(
            self._make_tool_use_response("web_search", {"query": "anthropic", "limit": 5})
        )
        client.messages.create.side_effect = [
            self._make_tool_use_response("web_search", {"query": "anthropic", "limit": 5}),
            self._make_text_response("Anthropic just released Claude 5."),
        ]

        agent = CruzAgent()
        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            result = await agent.process({
                "task": "what's new with Anthropic?",
                "context": {},
                "trace_id": "t1",
                "conversation_id": "c1",
            })
        fake_browser.search.assert_awaited_with(
            "anthropic", limit=5, trace_id="t1",
        )
        assert result["success"]
        assert "Claude 5" in (result["result"] or "")

    @pytest.mark.asyncio
    async def test_cruz_fetch_url_tool_dispatch(self, monkeypatch):
        from agents.cruz.cruz_agent import CruzAgent
        import services.browser.service as browser_mod

        fake_browser = MagicMock()
        fake_browser.extract_text = AsyncMock(return_value="page contents")
        monkeypatch.setattr(browser_mod, "_instance", fake_browser)

        client = self._make_claude_client(
            self._make_tool_use_response("fetch_url", {"url": "https://example.com"})
        )
        client.messages.create.side_effect = [
            self._make_tool_use_response("fetch_url", {"url": "https://example.com"}),
            self._make_text_response("the page says: page contents"),
        ]

        agent = CruzAgent()
        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            result = await agent.process({
                "task": "read https://example.com",
                "context": {},
                "trace_id": "t1",
                "conversation_id": "c1",
            })
        fake_browser.extract_text.assert_awaited_with(
            "https://example.com", trace_id="t1",
        )
        assert result["success"]

    @pytest.mark.asyncio
    async def test_cruz_web_search_captcha_surfaces_as_text(self, monkeypatch):
        """When BrowserService raises BrowserCaptchaDetected, CRUZ feeds a
        readable error string back to Claude — conversation does not crash."""
        from agents.cruz.cruz_agent import CruzAgent
        from services.browser import BrowserCaptchaDetected
        import services.browser.service as browser_mod

        fake_browser = MagicMock()
        fake_browser.search = AsyncMock(
            side_effect=BrowserCaptchaDetected(url="https://x.com", kind="recaptcha")
        )
        monkeypatch.setattr(browser_mod, "_instance", fake_browser)

        client = self._make_claude_client(
            self._make_tool_use_response("web_search", {"query": "x", "limit": 5})
        )
        client.messages.create.side_effect = [
            self._make_tool_use_response("web_search", {"query": "x", "limit": 5}),
            self._make_text_response("looks like that page is captcha-walled."),
        ]

        agent = CruzAgent()
        with patch("agents.cruz.cruz_agent.llm_chat", new=client.messages.create):
            result = await agent.process({
                "task": "find x", "context": {},
                "trace_id": "t1", "conversation_id": "c1",
            })
        assert result["success"]
        # The tool_result the dispatch sent into Claude included the word "captcha"
        # (verified indirectly via Claude's final text reflecting it).
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/agents/test_cruz_agent.py -k "web_search or fetch_url or captcha" -v`
Expected: 3 new tests FAIL.

- [ ] **Step 4: Add the tool definitions and dispatch**

In `agents/cruz/cruz_agent.py`, append to `CRUZ_TOOLS` (after `record_pattern_observation`):

```python
{
    "name": "web_search",
    "description": (
        "Search the live web. Use when the user asks about current events, "
        "recent releases, or anything past your training cutoff. "
        "Returns top results with title, URL, and snippet."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    },
},
{
    "name": "fetch_url",
    "description": (
        "Fetch the readable text of a web page by URL. Use as a follow-up to "
        "web_search when you need the actual contents of a result, not just "
        "its snippet. Returns plain text, trimmed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_chars": {"type": "integer", "default": 8000,
                          "minimum": 500, "maximum": 30000},
        },
        "required": ["url"],
    },
},
```

In `process()`, inside the `if response.stop_reason == "tool_use":` loop, add new built-in branches alongside the existing `record_pattern_observation` branch (around line 564):

```python
# ── Built-in tool: web_search ─────────────────────────────────
if block.name == "web_search":
    from services.browser import (
        get_browser_service,
        BrowserCaptchaDetected,
        BrowserRateLimited,
        BrowserError,
    )
    ti = block.input or {}
    q = ti.get("query", "")
    lim = int(ti.get("limit", 5))
    try:
        results = await get_browser_service().search(
            q, limit=lim, trace_id=input["trace_id"],
        )
        if not results:
            tool_text = f"web_search returned no results for {q!r}."
        else:
            tool_text = "\n".join(
                f"{r['rank']}. {r['title']} — {r['url']}\n   {r['snippet']}"
                for r in results
            )
    except BrowserCaptchaDetected as exc:
        tool_text = f"web_search blocked: {exc.kind} on {exc.url}"
    except BrowserRateLimited as exc:
        tool_text = f"web_search rate-limited at {exc.domain}"
    except BrowserError as exc:
        tool_text = f"web_search failed: {exc}"
    tool_results.append({
        "type": "tool_result", "tool_use_id": block.id, "content": tool_text,
    })
    continue

# ── Built-in tool: fetch_url ──────────────────────────────────
if block.name == "fetch_url":
    from services.browser import (
        get_browser_service,
        BrowserCaptchaDetected,
        BrowserRateLimited,
        BrowserError,
    )
    ti = block.input or {}
    url = ti.get("url", "")
    max_chars = int(ti.get("max_chars", 8000))
    try:
        text = await get_browser_service().extract_text(
            url, trace_id=input["trace_id"],
        )
        tool_text = text[:max_chars]
    except BrowserCaptchaDetected as exc:
        tool_text = f"fetch_url blocked: {exc.kind} on {exc.url}"
    except BrowserRateLimited as exc:
        tool_text = f"fetch_url rate-limited at {exc.domain}"
    except BrowserError as exc:
        tool_text = f"fetch_url failed: {exc}"
    tool_results.append({
        "type": "tool_result", "tool_use_id": block.id, "content": tool_text,
    })
    continue
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/agents/test_cruz_agent.py -k "web_search or fetch_url or captcha" -v`
Expected: 3 tests PASS.

Also run the full CRUZ test suite to ensure nothing regressed:

Run: `pytest tests/agents/test_cruz_agent.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add agents/cruz/cruz_agent.py tests/agents/test_cruz_agent.py
git commit -m "feat(sp4): add web_search + fetch_url tools to CRUZ (process path)"
```

---

### Task 4.2: Mirror dispatch into the streaming `stream_response()` path

**Files:**
- Modify: `agents/cruz/cruz_agent.py`
- Modify: `tests/agents/test_cruz_agent.py`

- [ ] **Step 1: Verify the streaming-event types' import path before writing the test**

Run: `grep -n "class ToolStart\|class ToolFinish\|from agents.cruz.stream_events" agents/cruz/cruz_agent.py agents/cruz/stream_events.py`

Expected output:
- `agents/cruz/stream_events.py: class ToolStart` (~line 14)
- `agents/cruz/stream_events.py: class ToolFinish` (~line 20)
- `agents/cruz/cruz_agent.py: from agents.cruz.stream_events import ... ToolStart, ToolFinish ...`

These types live in `agents.cruz.stream_events`, not on `agents.cruz.cruz_agent` directly. Import them from `agents.cruz.stream_events` in tests.

Also locate any existing streaming test for the helper pattern that mocks `llm_chat_stream`:

Run: `grep -n "llm_chat_stream\|stream_response\|TextDeltaEvent\|ToolUseEvent" tests/agents/test_cruz_agent.py`

If a streaming test fixture already exists, reuse it. If not, the test below uses the documented event-emitter shape from `services/llm/`.

- [ ] **Step 2: Write a failing test for streaming web_search dispatch**

Append to `tests/agents/test_cruz_agent.py`:

```python
@pytest.mark.asyncio
async def test_cruz_stream_response_web_search(monkeypatch):
    """Streaming path also dispatches web_search to BrowserService."""
    from agents.cruz.cruz_agent import CruzAgent
    from agents.cruz.stream_events import ToolStart, ToolFinish
    from services.llm import TextDeltaEvent, ToolUseEvent, _LLMDone
    import services.browser.service as browser_mod

    fake_browser = MagicMock()
    fake_browser.search = AsyncMock(return_value=[
        {"title": "X", "url": "https://x", "snippet": "s", "rank": 1},
    ])
    monkeypatch.setattr(browser_mod, "_instance", fake_browser)

    # Two fake LLM calls: one tool_use, one final text.
    async def fake_stream_first(*a, **kw):
        yield ToolUseEvent(
            tool_use_id="tu1", name="web_search",
            input={"query": "anthropic", "limit": 5},
        )
        yield _LLMDone(usage=MagicMock(input_tokens=10, output_tokens=5))

    async def fake_stream_second(*a, **kw):
        yield TextDeltaEvent(delta="Anthropic released ")
        yield TextDeltaEvent(delta="Claude 5.")
        yield _LLMDone(usage=MagicMock(input_tokens=20, output_tokens=5))

    streams = [fake_stream_first, fake_stream_second]
    def stream_side_effect(*a, **kw):
        return streams.pop(0)(*a, **kw)
    monkeypatch.setattr(
        "agents.cruz.cruz_agent.llm_chat_stream", stream_side_effect
    )

    agent = CruzAgent()
    events = []
    async for ev in agent.stream_response(
        task="what's new", conversation_id="c", trace_id="t", device="phone",
    ):
        events.append(ev)

    assert any(isinstance(e, ToolStart) and e.agent == "web_search" for e in events)
    assert any(isinstance(e, ToolFinish) and e.agent == "web_search" for e in events)
    fake_browser.search.assert_awaited()
```

If `services.llm` exports the event types under different names (run `grep -n "class TextDeltaEvent\|class ToolUseEvent\|class _LLMDone" services/llm/`), adjust the imports.

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/agents/test_cruz_agent.py -k stream_response_web_search -v`
Expected: FAIL.

- [ ] **Step 4: Add the same two built-in branches inside `stream_response()`**

In the streaming dispatch loop (around line 837–851 in `cruz_agent.py`, alongside the `record_pattern_observation` branch), add identical handlers for `web_search` and `fetch_url`:

```python
# Inside the `for tu in pending_tools:` loop, after the
# record_pattern_observation branch:

if tu.name in ("web_search", "fetch_url"):
    from services.browser import (
        get_browser_service,
        BrowserCaptchaDetected,
        BrowserRateLimited,
        BrowserError,
    )
    yield ToolStart(
        agent=tu.name,
        summary=f"Running {tu.name}.",
    )
    ti = tu.input or {}
    try:
        if tu.name == "web_search":
            results = await get_browser_service().search(
                ti.get("query", ""),
                limit=int(ti.get("limit", 5)),
                trace_id=trace_id,
            )
            content = (
                "\n".join(
                    f"{r['rank']}. {r['title']} — {r['url']}\n   {r['snippet']}"
                    for r in results
                ) if results else "no results"
            )
        else:  # fetch_url
            text = await get_browser_service().extract_text(
                ti.get("url", ""), trace_id=trace_id,
            )
            content = text[: int(ti.get("max_chars", 8000))]
    except BrowserCaptchaDetected as exc:
        content = f"{tu.name} blocked: {exc.kind} on {exc.url}"
    except BrowserRateLimited as exc:
        content = f"{tu.name} rate-limited at {exc.domain}"
    except BrowserError as exc:
        content = f"{tu.name} failed: {exc}"
    tool_result_blocks.append({
        "type": "tool_result", "tool_use_id": tu.tool_use_id, "content": content,
    })
    yield ToolFinish(agent=tu.name, result_preview=content[:200])
    continue
```

(Place this block before the existing `yield ToolStart(...) → self._dispatch_tool(...)` block so the built-in tools are matched first.)

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/agents/test_cruz_agent.py -k stream_response_web_search -v`
Expected: PASS.

- [ ] **Step 6: Run full CRUZ suite to confirm no regressions**

Run: `pytest tests/agents/test_cruz_agent.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add agents/cruz/cruz_agent.py tests/agents/test_cruz_agent.py
git commit -m "feat(sp4): web_search + fetch_url in CRUZ streaming path"
```

---

### Task 4.3: Manual-login script + reset script

**Files:**
- Create: `scripts/browser_login.py`
- Create: `scripts/browser_reset.py`

- [ ] **Step 1: Implement `scripts/browser_login.py`**

```python
#!/usr/bin/env python
"""Open a headed Chromium window pointed at a named profile.

Usage:
    python scripts/browser_login.py <profile>

The window stays open until you close it. Use this once per profile to log
into sites manually — cookies persist for headless reuse.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


async def main(profile: str) -> None:
    if not profile or not profile.replace("_", "").isalnum():
        sys.exit(f"invalid profile name: {profile!r}")

    from playwright.async_api import async_playwright

    profiles_dir = Path(os.path.expanduser(
        os.environ.get("CRUZ_BROWSER_PROFILES_DIR", "~/.cruz/browser-profiles")
    ))
    profile_dir = profiles_dir / profile
    profile_dir.mkdir(parents=True, exist_ok=True)

    print(f"opening headed Chromium against {profile_dir}")
    print("log in as needed; close the window when done.")

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = await ctx.new_page()
        await page.goto("about:blank")
        # Block until the user closes the context (all pages).
        try:
            while ctx.pages:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        await ctx.close()
    print(f"done. profile saved to {profile_dir}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/browser_login.py <profile>")
    asyncio.run(main(sys.argv[1]))
```

- [ ] **Step 2: Implement `scripts/browser_reset.py`**

```python
#!/usr/bin/env python
"""Wipe a named browser profile directory.

Usage:
    python scripts/browser_reset.py <profile>
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main(profile: str) -> None:
    if not profile or not profile.replace("_", "").isalnum():
        sys.exit(f"invalid profile name: {profile!r}")

    profiles_dir = Path(os.path.expanduser(
        os.environ.get("CRUZ_BROWSER_PROFILES_DIR", "~/.cruz/browser-profiles")
    ))
    target = profiles_dir / profile
    if not target.exists():
        print(f"no such profile: {target}")
        return

    confirm = input(f"delete {target}? [y/N] ")
    if confirm.strip().lower() != "y":
        print("aborted.")
        return

    shutil.rmtree(target)
    print(f"deleted {target}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/browser_reset.py <profile>")
    main(sys.argv[1])
```

- [ ] **Step 3: Make scripts executable + smoke-test**

```bash
chmod +x scripts/browser_login.py scripts/browser_reset.py
python scripts/browser_login.py default &   # opens window
sleep 5
# close the window manually
python scripts/browser_reset.py default
# answer 'n' at the prompt
```

Expected: login script opens a headed Chromium; reset script lists the profile dir and aborts on `n`.

- [ ] **Step 4: Commit**

```bash
git add scripts/browser_login.py scripts/browser_reset.py
git commit -m "feat(sp4): add manual-login + reset scripts for browser profiles"
```

---

### Task 4.4: Daily health probe ARQ task

**Files:**
- Create: `workers/tasks/browser_health.py`
- Modify: `workers/arq_worker.py`
- Create: `tests/workers/test_browser_health.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/workers/test_browser_health.py
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_browser_health_probe_passes(monkeypatch):
    from workers.tasks.browser_health import browser_health_probe
    import services.browser.service as browser_mod

    fake_svc = MagicMock()
    fake_svc.search = AsyncMock(return_value=[
        {"title": f"r{i}", "url": "https://x", "snippet": "", "rank": i}
        for i in range(1, 6)
    ])
    monkeypatch.setattr(browser_mod, "_instance", fake_svc)

    fake_alerts = MagicMock()
    fake_alerts.notify = AsyncMock()
    monkeypatch.setattr(
        "workers.tasks.browser_health.get_alert_service", lambda: fake_alerts
    )

    result = await browser_health_probe(ctx={})
    assert result["status"] == "ok"
    assert result["result_count"] == 5
    fake_alerts.notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_browser_health_probe_alerts_on_zero_results(monkeypatch):
    from workers.tasks.browser_health import browser_health_probe
    import services.browser.service as browser_mod

    fake_svc = MagicMock()
    fake_svc.search = AsyncMock(return_value=[])
    monkeypatch.setattr(browser_mod, "_instance", fake_svc)

    fake_alerts = MagicMock()
    fake_alerts.notify = AsyncMock()
    monkeypatch.setattr(
        "workers.tasks.browser_health.get_alert_service", lambda: fake_alerts
    )

    result = await browser_health_probe(ctx={})
    assert result["status"] == "degraded"
    fake_alerts.notify.assert_awaited()


@pytest.mark.asyncio
async def test_browser_health_probe_alerts_on_exception(monkeypatch):
    from workers.tasks.browser_health import browser_health_probe
    import services.browser.service as browser_mod

    fake_svc = MagicMock()
    fake_svc.search = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(browser_mod, "_instance", fake_svc)

    fake_alerts = MagicMock()
    fake_alerts.notify = AsyncMock()
    monkeypatch.setattr(
        "workers.tasks.browser_health.get_alert_service", lambda: fake_alerts
    )

    result = await browser_health_probe(ctx={})
    assert result["status"] == "error"
    fake_alerts.notify.assert_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/workers/test_browser_health.py -v`
Expected: FAIL — `ModuleNotFoundError: workers.tasks.browser_health`.

- [ ] **Step 3: Implement the task**

```python
# workers/tasks/browser_health.py
"""Daily browser health probe — runs a stable DDG search and alerts on failure."""
from __future__ import annotations

import logging

from services.alerts import get_alert_service
from services.browser import get_browser_service

logger = logging.getLogger("cruz.workers.browser_health")

_PROBE_QUERY = "anthropic claude"
_MIN_EXPECTED_RESULTS = 3


async def browser_health_probe(ctx: dict) -> dict:
    """Run a tiny DDG search; alert on zero results or exceptions."""
    try:
        results = await get_browser_service().search(
            _PROBE_QUERY, limit=10, trace_id="browser_health_probe",
        )
    except Exception as exc:
        logger.warning("browser_health_probe failed: %s", exc)
        try:
            await get_alert_service().notify(
                "warning",
                "Browser layer probe failed",
                f"DDG search raised: {exc}",
            )
        except Exception:
            pass
        return {"status": "error", "reason": str(exc)}

    if len(results) < _MIN_EXPECTED_RESULTS:
        logger.warning(
            "browser_health_probe returned %d results (expected >= %d)",
            len(results), _MIN_EXPECTED_RESULTS,
        )
        try:
            await get_alert_service().notify(
                "warning",
                "Browser layer degraded",
                f"DDG search returned {len(results)} results "
                f"(expected >= {_MIN_EXPECTED_RESULTS}); parser may be broken.",
            )
        except Exception:
            pass
        return {"status": "degraded", "result_count": len(results)}

    return {"status": "ok", "result_count": len(results)}
```

- [ ] **Step 4: Register the task in ARQ + cron schedule**

Open `workers/arq_worker.py`. Find the `WorkerSettings` class (or equivalent) and:

1. Add `browser_health_probe` to the `functions` list.
2. Add a daily cron entry (e.g. 09:00 local). Match the existing pattern used for `pulse_tasks` / `raw_tasks`.

Example (adjust to match the existing shape):

```python
from arq.cron import cron
from workers.tasks.browser_health import browser_health_probe
# ...
class WorkerSettings:
    functions = [..., browser_health_probe]
    cron_jobs = [
        ...,
        cron(browser_health_probe, hour={9}, minute={0}),
    ]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/workers/test_browser_health.py -v`
Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add workers/tasks/browser_health.py workers/arq_worker.py tests/workers/test_browser_health.py
git commit -m "feat(sp4): daily browser health probe ARQ task with Telegram alerts"
```

---

## Chunk 5: Agent retrofits (RAW + PULSE) and exit-gate verification

### Task 5.1: RAW retrofit — `sources.yml` + page-fetch branch

**Files:**
- Create: `agents/raw/sources.yml`
- Modify: `agents/raw/raw_agent.py`
- Modify: `tests/agents/test_raw_agent.py`

- [ ] **Step 1: Identify RAW's existing source list**

Run: `grep -n "feeds\|FEEDS\|RSS_SOURCES\|sources" agents/raw/raw_agent.py | head -20`
Note the variable name and shape of the existing source list.

- [ ] **Step 2: Create `agents/raw/sources.yml`**

```yaml
# RAW source registry
# rss: existing free RSS feeds
# pages: non-RSS pages fetched via services/browser.py

rss:
  # Move existing RSS URLs from raw_agent.py into this list (one per line).
  # Example placeholder — replace with what's actually in the agent today:
  # - https://feeds.feedburner.com/TechCrunch/
  # - https://www.youtube.com/feeds/videos.xml?channel_id=UC...

pages:
  # Non-RSS sources — the layer fetches and the agent summarises.
  - url: https://www.anthropic.com/news
    selector: main
    summarize_with: llama3.1:8b
  - url: https://news.ycombinator.com/
    selector: table.itemlist
    summarize_with: llama3.1:8b
```

(Replace the `rss:` placeholder list with whatever is currently hardcoded in `raw_agent.py`. If the existing list lives elsewhere, move it.)

- [ ] **Step 3: Write failing tests for the page-fetch branch**

Append to `tests/agents/test_raw_agent.py`:

```python
@pytest.mark.asyncio
async def test_raw_loads_sources_yml(tmp_path, monkeypatch):
    sources_yml = tmp_path / "sources.yml"
    sources_yml.write_text(
        "rss:\n  - https://example.com/rss\n"
        "pages:\n  - url: https://anthropic.com/news\n"
        "    selector: main\n"
        "    summarize_with: llama3.1:8b\n"
    )
    monkeypatch.setattr(
        "agents.raw.raw_agent._SOURCES_PATH", str(sources_yml)
    )
    from agents.raw.raw_agent import _load_sources
    sources = _load_sources()
    assert sources["rss"] == ["https://example.com/rss"]
    assert len(sources["pages"]) == 1
    assert sources["pages"][0]["url"] == "https://anthropic.com/news"


@pytest.mark.asyncio
async def test_raw_page_fetch_branch_writes_domain_knowledge(monkeypatch, tmp_path):
    from agents.raw.raw_agent import RawAgent
    import services.browser.service as browser_mod

    fake_browser = MagicMock()
    fake_browser.fetch = AsyncMock(return_value={
        "url": "https://anthropic.com/news",
        "final_url": "https://anthropic.com/news",
        "status": 200,
        "title": "News",
        "html": "<html></html>",
        "text": "Anthropic released a new model.",
        "byte_size": 100,
    })
    monkeypatch.setattr(browser_mod, "_instance", fake_browser)

    fake_kb = MagicMock()
    fake_kb.write_domain_knowledge = AsyncMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    monkeypatch.setattr("agents.raw.raw_agent.get_kb_service", lambda: fake_kb)

    sources_yml = tmp_path / "sources.yml"
    sources_yml.write_text(
        "rss: []\n"
        "pages:\n  - url: https://anthropic.com/news\n"
        "    selector: main\n"
        "    summarize_with: llama3.1:8b\n"
    )
    monkeypatch.setattr("agents.raw.raw_agent._SOURCES_PATH", str(sources_yml))

    # Mock the LLM summariser
    monkeypatch.setattr(
        "agents.raw.raw_agent._summarise",
        AsyncMock(return_value="summary"),
    )

    agent = RawAgent()
    await agent.process({
        "task": "research",
        "context": {"mode": "research"},
        "trace_id": "t1",
        "conversation_id": "c1",
    })
    fake_browser.fetch.assert_awaited_with(
        "https://anthropic.com/news", trace_id="t1",
    )
    fake_kb.write_domain_knowledge.assert_awaited()


@pytest.mark.asyncio
async def test_raw_skips_failed_source_continues(monkeypatch, tmp_path):
    """One source raising BrowserError must not fail the whole RAW run."""
    from agents.raw.raw_agent import RawAgent
    from services.browser import BrowserNavigationError
    import services.browser.service as browser_mod

    call_count = {"n": 0}

    async def flaky_fetch(url, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise BrowserNavigationError("dns fail")
        return {
            "url": url, "final_url": url, "status": 200,
            "title": "ok", "html": "<html></html>", "text": "ok content",
            "byte_size": 1,
        }

    fake_browser = MagicMock()
    fake_browser.fetch = AsyncMock(side_effect=flaky_fetch)
    monkeypatch.setattr(browser_mod, "_instance", fake_browser)

    sources_yml = tmp_path / "sources.yml"
    sources_yml.write_text(
        "rss: []\n"
        "pages:\n  - url: https://broken.example\n    selector: main\n    summarize_with: llama3.1:8b\n"
        "  - url: https://ok.example\n    selector: main\n    summarize_with: llama3.1:8b\n"
    )
    monkeypatch.setattr("agents.raw.raw_agent._SOURCES_PATH", str(sources_yml))

    fake_kb = MagicMock()
    fake_kb.write_domain_knowledge = AsyncMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    monkeypatch.setattr("agents.raw.raw_agent.get_kb_service", lambda: fake_kb)
    monkeypatch.setattr(
        "agents.raw.raw_agent._summarise",
        AsyncMock(return_value="summary"),
    )

    agent = RawAgent()
    result = await agent.process({
        "task": "research",
        "context": {"mode": "research"},
        "trace_id": "t1",
        "conversation_id": "c1",
    })
    assert result["success"]
    assert call_count["n"] == 2
    # Only the good source got a KB write
    assert fake_kb.write_domain_knowledge.await_count == 1
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/agents/test_raw_agent.py -k "sources_yml or page_fetch or skips_failed" -v`
Expected: 3 new tests FAIL.

- [ ] **Step 5: Implement the page-fetch branch in `raw_agent.py`**

Add to `agents/raw/raw_agent.py`:

```python
import yaml
from pathlib import Path

_SOURCES_PATH = str(Path(__file__).parent / "sources.yml")


def _load_sources() -> dict:
    """Load sources.yml; return dict with 'rss' and 'pages' keys."""
    try:
        with open(_SOURCES_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
        return {
            "rss": data.get("rss") or [],
            "pages": data.get("pages") or [],
        }
    except FileNotFoundError:
        return {"rss": [], "pages": []}
```

Inside `RawAgent.process()` research-mode branch, after the existing RSS handling, add:

```python
from services.browser import (
    get_browser_service,
    BrowserError,
)

sources = _load_sources()

# Existing RSS branch consumes sources["rss"] (refactor to read from there)

# NEW: page-fetch branch
for entry in sources["pages"]:
    url = entry.get("url")
    if not url:
        continue
    try:
        page = await get_browser_service().fetch(url, trace_id=input["trace_id"])
    except BrowserError as exc:
        logger.warning("[%s] RAW skipping %s: %s", input["trace_id"], url, exc)
        continue
    summary = await _summarise(
        page["text"],
        model=entry.get("summarize_with", "llama3.1:8b"),
    )
    await get_kb_service().write_domain_knowledge(
        content=summary,
        topic=entry.get("topic") or page.get("title") or url,
        source="raw_agent",
        trace_id=input["trace_id"],
    )
```

(Refactor `_summarise` out of the existing `process()` body if it's currently inline.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/agents/test_raw_agent.py -v`
Expected: all PASS, including the existing tests (no regressions).

- [ ] **Step 7: Commit**

```bash
git add agents/raw/sources.yml agents/raw/raw_agent.py tests/agents/test_raw_agent.py
git commit -m "feat(sp4): RAW retrofit — load sources.yml; page-fetch branch via browser service"
```

---

### Task 5.2: PULSE retrofit — `sources.yml` + Web roundup section

**Files:**
- Create: `agents/pulse/sources.yml`
- Modify: `agents/pulse/pulse_agent.py`
- Modify: `tests/agents/test_pulse_agent.py`

- [ ] **Step 1: Create `agents/pulse/sources.yml`**

```yaml
# PULSE source registry
# pages: non-RSS news sources for the morning Web roundup section
pages:
  - url: https://techcrunch.com/
    selector: main
  - url: https://inc42.com/
    selector: main
```

- [ ] **Step 2: Read existing PULSE test fixtures before writing the new tests**

Run: `grep -n "def test_\|monkeypatch.setattr.*pulse\|fake_calendar\|fake_qdrant\|fake_db" tests/agents/test_pulse_agent.py | head -40`

PulseAgent reads from four sources today: Google Calendar API, Qdrant semantic memory, `agent_logs` (last 8 hours), and the `tasks` table. The existing tests stub all four. **Read those stubs and copy their shape into the new tests** — do not invent new mocks.

Specifically, locate (in `tests/agents/test_pulse_agent.py`) the helpers/fixtures that:
1. Mock the Google Calendar response (likely an `httpx` mock or a function patched at `agents.pulse.pulse_agent._fetch_calendar`)
2. Mock Qdrant semantic search (likely `monkeypatch.setattr("agents.pulse.pulse_agent.get_qdrant_service", ...)`)
3. Mock the DB calls for `agent_logs` and `tasks` (likely `monkeypatch.setattr("agents.pulse.pulse_agent.get_db_service", ...)` returning a fake with `fetch_all` etc.)
4. Mock the LLM summariser (likely `monkeypatch.setattr("agents.pulse.pulse_agent._summarise", AsyncMock(...))` or similar)

Reuse these mocks verbatim in the new tests — without them, `PulseAgent.process()` will explode on unrelated I/O long before reaching the new web-roundup branch.

- [ ] **Step 3: Write failing test for the Web roundup branch**

The skeleton below shows the new-branch-specific mocks. Augment it with the four existing PULSE source mocks from Step 2. Each `# REUSE: ...` comment marks where to paste the existing mock.

```python
@pytest.mark.asyncio
async def test_pulse_web_roundup_includes_browser_sourced_content(monkeypatch, tmp_path):
    from agents.pulse.pulse_agent import PulseAgent
    import services.browser.service as browser_mod

    fake_browser = MagicMock()
    fake_browser.fetch = AsyncMock(return_value={
        "url": "https://techcrunch.com/", "final_url": "https://techcrunch.com/",
        "status": 200, "title": "TechCrunch", "html": "<html></html>",
        "text": "Big AI news today.", "byte_size": 100,
    })
    monkeypatch.setattr(browser_mod, "_instance", fake_browser)

    sources_yml = tmp_path / "sources.yml"
    sources_yml.write_text(
        "pages:\n  - url: https://techcrunch.com/\n    selector: main\n"
    )
    monkeypatch.setattr("agents.pulse.pulse_agent._SOURCES_PATH", str(sources_yml))

    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    monkeypatch.setattr("agents.pulse.pulse_agent.get_kb_service", lambda: fake_kb)

    # REUSE: existing PULSE test stubs — calendar, Qdrant, DB, summariser.
    # Copy the same `monkeypatch.setattr(...)` calls used in the existing
    # `test_pulse_*` tests in this file (see Step 2).

    agent = PulseAgent()
    out = await agent.process({
        "task": "today",
        "context": {},
        "trace_id": "t",
        "conversation_id": "c",
    })
    assert "web_roundup" in out["result"]
    assert "Big AI news today." in str(out["result"]["web_roundup"])


@pytest.mark.asyncio
async def test_pulse_web_roundup_omitted_on_failure(monkeypatch, tmp_path):
    from agents.pulse.pulse_agent import PulseAgent
    from services.browser import BrowserRateLimited
    import services.browser.service as browser_mod

    fake_browser = MagicMock()
    fake_browser.fetch = AsyncMock(
        side_effect=BrowserRateLimited(domain="techcrunch.com", retry_after_ms=1000)
    )
    monkeypatch.setattr(browser_mod, "_instance", fake_browser)

    sources_yml = tmp_path / "sources.yml"
    sources_yml.write_text(
        "pages:\n  - url: https://techcrunch.com/\n    selector: main\n"
    )
    monkeypatch.setattr("agents.pulse.pulse_agent._SOURCES_PATH", str(sources_yml))

    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    monkeypatch.setattr("agents.pulse.pulse_agent.get_kb_service", lambda: fake_kb)

    # REUSE: existing PULSE test stubs — calendar, Qdrant, DB, summariser.
    # (Same as the test above.)

    agent = PulseAgent()
    out = await agent.process({
        "task": "today",
        "context": {},
        "trace_id": "t",
        "conversation_id": "c",
    })
    # Web roundup section is empty; briefing still succeeds
    assert out["success"]
    assert out["result"].get("web_roundup", []) == []
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/agents/test_pulse_agent.py -k web_roundup -v`
Expected: 2 new tests FAIL.

- [ ] **Step 5: Implement Web roundup branch**

Add to `agents/pulse/pulse_agent.py`:

```python
import yaml
from pathlib import Path
from services.browser import get_browser_service, BrowserError

_SOURCES_PATH = str(Path(__file__).parent / "sources.yml")


def _load_pages() -> list[dict]:
    try:
        with open(_SOURCES_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
        return data.get("pages") or []
    except FileNotFoundError:
        return []
```

Inside `PulseAgent.process()`, after the existing data-source block, add:

```python
web_roundup: list[dict] = []
for entry in _load_pages():
    url = entry.get("url")
    if not url:
        continue
    try:
        page = await get_browser_service().fetch(url, trace_id=input["trace_id"])
        web_roundup.append({
            "url": url,
            "title": page.get("title", ""),
            "excerpt": page["text"][:500],
        })
    except BrowserError as exc:
        logger.warning(
            "[%s] PULSE web roundup skip %s: %s",
            input["trace_id"], url, exc,
        )

# Add to the result dict that gets returned in AgentOutput.result
result["web_roundup"] = web_roundup
```

(Adjust to match PULSE's existing `result` dict construction.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/agents/test_pulse_agent.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add agents/pulse/sources.yml agents/pulse/pulse_agent.py tests/agents/test_pulse_agent.py
git commit -m "feat(sp4): PULSE retrofit — Web roundup section via browser service"
```

---

### Task 5.3: Latency-regression check on RAW + PULSE

**Files:**
- Modify: `tests/agents/test_raw_agent.py`
- Modify: `tests/agents/test_pulse_agent.py`

- [ ] **Step 1: Add a smoke time-bound for RAW**

These tests are tripwires (mocked I/O = should be near-instant), not real P95 measurements. The actual exit-gate latency check happens live on the Mac Mini in Task 5.4 Step 7.

The test reuses the same fixture stack as `test_raw_page_fetch_branch_writes_domain_knowledge` (Task 5.1 Step 3). Refactor that fixture into a helper so both tests share it:

```python
# In tests/agents/test_raw_agent.py — add this helper near the top of the file
# (or extend an existing conftest.py if one is present).

@pytest.fixture
def raw_pages_fixtures(monkeypatch, tmp_path):
    """Common mock stack used by RAW page-fetch tests."""
    import services.browser.service as browser_mod

    fake_browser = MagicMock()
    fake_browser.fetch = AsyncMock(return_value={
        "url": "https://anthropic.com/news",
        "final_url": "https://anthropic.com/news",
        "status": 200, "title": "News",
        "html": "<html></html>", "text": "Anthropic released a new model.",
        "byte_size": 100,
    })
    monkeypatch.setattr(browser_mod, "_instance", fake_browser)

    fake_kb = MagicMock()
    fake_kb.write_domain_knowledge = AsyncMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    monkeypatch.setattr("agents.raw.raw_agent.get_kb_service", lambda: fake_kb)

    sources_yml = tmp_path / "sources.yml"
    sources_yml.write_text(
        "rss: []\n"
        "pages:\n  - url: https://anthropic.com/news\n"
        "    selector: main\n    summarize_with: llama3.1:8b\n"
    )
    monkeypatch.setattr("agents.raw.raw_agent._SOURCES_PATH", str(sources_yml))
    monkeypatch.setattr(
        "agents.raw.raw_agent._summarise",
        AsyncMock(return_value="summary"),
    )

    return {"fake_browser": fake_browser, "fake_kb": fake_kb}


import time as _time

@pytest.mark.asyncio
async def test_raw_full_run_completes_quickly(raw_pages_fixtures):
    """Sanity tripwire: full RAW research-mode run with mocked I/O stays under 5s."""
    from agents.raw.raw_agent import RawAgent

    agent = RawAgent()
    t0 = _time.monotonic()
    await agent.process({
        "task": "research",
        "context": {"mode": "research"},
        "trace_id": "t-perf",
        "conversation_id": "c-perf",
    })
    assert _time.monotonic() - t0 < 5.0
```

Refactor `test_raw_page_fetch_branch_writes_domain_knowledge` (from Task 5.1) to consume `raw_pages_fixtures` instead of inlining the mocks.

- [ ] **Step 2: Add the equivalent for PULSE**

Same pattern in `tests/agents/test_pulse_agent.py` — extract the four-source mock stack from Step 2 of Task 5.2 into a `pulse_browser_fixtures` fixture, then add:

```python
import time as _time

@pytest.mark.asyncio
async def test_pulse_full_run_completes_quickly(pulse_browser_fixtures):
    from agents.pulse.pulse_agent import PulseAgent

    agent = PulseAgent()
    t0 = _time.monotonic()
    await agent.process({
        "task": "today", "context": {},
        "trace_id": "t-perf-pulse", "conversation_id": "c-perf-pulse",
    })
    assert _time.monotonic() - t0 < 5.0
```

This is not a true P95 measurement — it's a tripwire. The actual P95 latency-regression check is run live on the Mac Mini at exit-gate verification (Task 5.4).

- [ ] **Step 3: Run tests**

Run: `pytest tests/agents/ -k completes_quickly -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/agents/test_raw_agent.py tests/agents/test_pulse_agent.py
git commit -m "test(sp4): add smoke-time bounds for RAW + PULSE full-run paths"
```

---

### Task 5.4: Exit-gate verification on the Mac Mini

This is the final manual verification step before SP4 ships. All seven exit-gate clauses from the spec §10 must hold.

> **Important — capture the latency baseline before starting Chunk 1.**
> Step 7 below compares post-SP4 P95 latency on RAW and PULSE against a baseline taken from `main` (pre-SP4). If you've already run any RAW/PULSE invocations on this worktree before reading this, the baseline numbers are contaminated. Capture the baseline NOW (before continuing implementation) by running the queries in Step 7 against the existing pre-SP4 logs and saving the values somewhere outside the repo (e.g. a sticky note, a private journal). If you've already started executing the plan and don't have a clean baseline, accept Step 7 as advisory and move on — but document that in Appendix A's record.

- [ ] **Step 1: Layer end-to-end**

Run: `make browser-live-tests`
Expected: 3 tests PASS against real DDG and example.com.

Document: which test passed, observed durations.

- [ ] **Step 2: RAW retrofit live**

Run RAW manually via the existing CRUZ tool path (or directly):

```bash
python -c "
import asyncio
from agents.raw.raw_agent import RawAgent
out = asyncio.run(RawAgent().process({
    'task': 'research', 'context': {'mode': 'research'},
    'trace_id': 't-exit-gate', 'conversation_id': 'c-exit-gate',
}))
print(out)
"
```

Expected: `success=True`; logs show ≥1 `browser_service.fetch` row in `agent_logs` for the trace; `cruz_domain_knowledge` has at least one new vector.

Verify in DB:
```sql
SELECT action, status, COUNT(*)
FROM agent_logs
WHERE trace_id = 't-exit-gate' AND agent = 'browser_service';
```

- [ ] **Step 3: PULSE retrofit live**

Run PULSE manually:

```bash
python -c "
import asyncio
from agents.pulse.pulse_agent import PulseAgent
out = asyncio.run(PulseAgent().process({
    'task': 'today', 'context': {},
    'trace_id': 't-exit-gate-pulse', 'conversation_id': 'c-exit-gate-pulse',
}))
print(out['result'].get('web_roundup'))
"
```

Expected: `web_roundup` is a non-empty list; one item has the TechCrunch URL.

- [ ] **Step 4: CRUZ web_search live (streaming)**

Run a real `/command` call via curl:

```bash
curl -N -X POST http://localhost:3000/command \
  -H "Content-Type: application/json" \
  -d '{"message":"What did Anthropic announce most recently?","stream":true}'
```

Expected: streamed SSE events show a `tool_call` for `web_search`, results streamed back, final answer text references real Anthropic news.

- [ ] **Step 5: Personal profile persistence**

```bash
python scripts/browser_login.py personal
# log into a known site (e.g. github.com), close window
pm2 restart cruz-api
# wait for restart
python -c "
import asyncio
from services.browser import get_browser_service
async def main():
    page = await (await get_browser_service()._get_context('personal')).new_page()
    await page.goto('https://github.com/')
    print('signed in?', 'Sign in' not in await page.content())
asyncio.run(main())
"
```

Expected: prints `signed in? True` after the restart.

- [ ] **Step 6: Burst rate limit test passes in CI shape**

Run: `pytest tests/services/test_browser_rate_limit.py -v`
Expected: all PASS.

- [ ] **Step 7: P95 latency regression check**

Capture baseline before merging (off the main branch, before SP4 changes):

```sql
SELECT
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms
FROM agent_logs
WHERE agent = 'raw' AND status = 'success'
  AND created_at > NOW() - INTERVAL '7 days';
```

Then after SP4 lands and RAW runs at least once on the new code:

```sql
SELECT
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms
FROM agent_logs
WHERE agent = 'raw' AND status = 'success'
  AND created_at > NOW() - INTERVAL '1 day';
```

Compute: `(post_p95 - pre_p95) / pre_p95`. Must be ≤ 0.20 (20%). Repeat for PULSE.

If it fails: investigate, optimize, re-run. Block merge if it doesn't recover.

- [ ] **Step 8: Document the exit-gate run**

Append to `docs/superpowers/specs/2026-04-26-sp4-browser-automation-design.md` at the end:

```markdown
---

## Appendix A — Exit gate run record (filled at completion)

- Layer end-to-end: PASS at <YYYY-MM-DD HH:MM>; <duration> ms.
- RAW retrofit live: PASS; trace_id `t-exit-gate`; ≥1 fetch row.
- PULSE retrofit live: PASS; web_roundup has N items.
- CRUZ web_search live: PASS; streamed N tool_call events.
- Personal profile persistence: PASS across `pm2 restart`.
- Burst rate limit: PASS (test_browser_rate_limit.py).
- Latency P95 regression: RAW pre=Xms post=Yms (delta=Z%); PULSE pre=Xms post=Yms (delta=Z%).
```

Commit:

```bash
git add docs/superpowers/specs/2026-04-26-sp4-browser-automation-design.md
git commit -m "docs(sp4): record exit-gate run results"
```

- [ ] **Step 9: Open the PR**

```bash
git push -u origin claude/sleepy-elgamal-3fb2aa
gh pr create --title "feat(sp4): browser automation layer" --body "$(cat <<'EOF'
## Summary
- Adds `services/browser/` sub-package — Playwright-backed browser primitive layer with 5 task primitives (`search`, `fetch`, `screenshot`, `extract_text`, `download`) + `session()` escape hatch
- Named persistent Chromium contexts under `~/.cruz/browser-profiles/<name>/`
- Per-domain token-bucket rate limiter, captcha detection, structured `agent_logs` write-through
- CRUZ tools `web_search` + `fetch_url` in both non-streaming and streaming paths
- Retrofits RAW and PULSE to consume the layer alongside existing RSS sources
- Daily ARQ health probe (alerts via Telegram on parser failure)

## Spec
docs/superpowers/specs/2026-04-26-sp4-browser-automation-design.md

## Test plan
- [x] `pytest tests/services/test_browser*.py -v` (all unit tests pass)
- [x] `make browser-live-tests` (live integration tests pass against real DDG + example.com)
- [x] `pytest tests/agents/test_raw_agent.py tests/agents/test_pulse_agent.py tests/agents/test_cruz_agent.py -v`
- [x] Manual exit-gate run on Mac Mini (see spec Appendix A)
- [x] No P95 latency regression >20% on RAW or PULSE
EOF
)"
```

---

## Summary of file changes

**New files:**
- `services/browser/__init__.py`
- `services/browser/service.py`
- `services/browser/errors.py`
- `services/browser/parsers.py`
- `services/browser/rate_limit.py`
- `tests/services/test_browser.py`
- `tests/services/test_browser_rate_limit.py`
- `tests/services/test_browser_captcha.py`
- `tests/services/test_browser_live.py`
- `tests/services/fixtures/ddg_search_cruz_ai.html`
- `tests/services/fixtures/captcha_recaptcha.html`
- `tests/services/fixtures/captcha_hcaptcha.html`
- `tests/services/fixtures/captcha_turnstile.html`
- `tests/services/fixtures/captcha_false_positive_docs.html`
- `tests/services/fixtures/captcha_false_positive_widget.html`
- `agents/raw/sources.yml`
- `agents/pulse/sources.yml`
- `scripts/browser_login.py`
- `scripts/browser_reset.py`
- `workers/tasks/browser_health.py`
- `tests/workers/test_browser_health.py`
- `tests/api/test_health_browser.py`

**Modified files:**
- `requirements.txt` — Playwright + (maybe) bs4 + pytest-asyncio
- `agents/cruz/cruz_agent.py` — `web_search` + `fetch_url` tools, both paths
- `agents/raw/raw_agent.py` — `_load_sources()` + page-fetch branch
- `agents/pulse/pulse_agent.py` — `_load_pages()` + Web roundup section
- `workers/arq_worker.py` — register `browser_health_probe` + cron
- `backend/api/main.py` — `/health` includes browser block
- `tests/agents/test_cruz_agent.py` — new tool dispatch tests
- `tests/agents/test_raw_agent.py` — sources.yml + page-fetch tests
- `tests/agents/test_pulse_agent.py` — Web roundup tests
- `pytest.ini` (or `pyproject.toml`) — register `live` marker
- CI config — exclude `live` marker from regular runs
- `Makefile` — `browser-live-tests` target

**Reference skills during execution:**
- @superpowers:test-driven-development for the failing-test-first cadence
- @superpowers:verification-before-completion before claiming any task complete
- @superpowers:systematic-debugging when something unexpected happens
