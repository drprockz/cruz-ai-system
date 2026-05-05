# SP4 — Browser Automation Layer (Layer 3)

**Date:** 2026-04-26
**Status:** Draft for user review
**Sub-project of:** CRUZ v2 Program Charter (`docs/superpowers/specs/2026-04-20-v2-program-charter.md`)
**Inherits:** All charter Section 3 rules. Exit gate from charter Section 5.1 — **rewritten in this spec under Rule 8 charter override; see §10**.
**Depends on:** SP1 (operational deployment) and SP2 (Knowledge Base) — both must close before SP4 implementation begins.
**Enables:** Future REACH-2.0 (LinkedIn outreach), v2.1 Job Hunter, v2.1 WhatsApp agent, plus on-demand web research for any current or future agent.

---

## 1. Goal and scope

**Goal.** Add a generic, agent-agnostic browser primitive layer to CRUZ. Any agent — existing or future — gains web-search, page-fetch, screenshot, text-extract, and download capability through a single service. The layer abstracts Playwright cleanly enough that consumers never see Playwright APIs in normal use, while leaving a low-level escape hatch for site-specific work.

**One-line description.** New `services/browser.py` singleton + named persistent Chrome contexts + 5 read-mostly task primitives + thin escape hatch + CRUZ `web_search` / `fetch_url` tools + retrofit RAW and PULSE.

### In scope

- `services/browser.py` — singleton service. Mid-level API: `search`, `fetch`, `screenshot`, `extract_text`, `download`, plus `session(profile=...)` escape hatch.
- Named Chromium contexts under `~/.cruz/browser-profiles/<name>/` — `default` (signed-out generic) and `personal` (manually signed-in once for sites where the user has accounts).
- Anti-detect posture: **minimal** — vanilla `playwright-chromium` + persistent profile + human-pacing. No stealth library in v1.
- Per-domain token-bucket rate limiter (default 10 req/min, configurable).
- CRUZ tool definitions: `web_search` and `fetch_url`, callable from any CRUZ conversation.
- RAW retrofit: nightly research run uses the layer for ≥1 real page fetch beyond RSS.
- PULSE retrofit: daily briefing pulls from ≥1 non-RSS source via the layer.
- Tests for the service (unit + 1 live integration test marked `@pytest.mark.live`).
- A daily browser health probe (one new ARQ task, fires once per day).
- A one-shot manual login script (`scripts/browser_login.py <profile>`) for re-authing the `personal` profile when cookies expire.

### Out of scope (deferred or migrated)

- Form-fill / click-driven `interact(url, actions=[...])` primitives — added when the first real consumer needs them.
- **LinkedIn agent** — TOS work in progress; lives in future REACH-2.0 sub-spec.
- **Job Hunter agent** — moves to v2.1 backlog.
- **WhatsApp agent** — moves to v2.1 backlog.
- 2Captcha integration (charter §4 mentions ~₹500/mo budget) — stays parked until a consumer surfaces a captcha wall.
- GENERAL and FORGE retrofits — not blocking any current product gap.
- Aggressive stealth (residential proxies, profile rotation, CDP patches) — no hostile target in scope for v1.
- Headed-via-Xvfb mode — deferred; v1 consumers don't require it.
- Redis-backed rate-limiter persistence across restarts.
- `robots.txt` enforcement at the layer level — caller's responsibility per polite-crawler convention.

### Charter override (Rule 8) — formal record

This sub-spec deviates from charter §2, §5.1, §6, and §7. Each deviation is itemized below; the user has approved them during brainstorming on 2026-04-26.

1. **§2 scope deviation.** SP4 originally included LinkedIn, Job Hunter, and WhatsApp agents. All three move out of SP4. Reason: LinkedIn TOS work is open-ended and parked separately; Job Hunter and WhatsApp depended on SP4 selector infrastructure that's no longer being built specifically for them.

2. **§5.1 exit gate rewrite.** Original gate referenced LinkedIn DMs (20/14d, zero account warnings) and Job Hunter applies (10 roles). Both unsatisfiable with new scope. Replacement gate is in §10 of this spec.

3. **§6 cut-order deviation.** Rows #7 (cut WhatsApp) and #8 (cut Job Hunter) become dead — those agents are no longer in SP4. Row #12 (cut SP4 entirely) still works. There is no internal cut-step inside SP4 v1 short of dropping the layer wholesale; an internal degradation order is documented in §6 of this spec for K2 scenarios.

4. **§7 success-criterion #4 migration.** "100+ LinkedIn DMs over 30 days, zero warnings" no longer attainable inside v2 scope. This criterion migrates to the future REACH-2.0 / LinkedIn effort. v2 success bar drops from "6 of 8" to "5 of 7", or — at user's option during a future charter-amend window — replaced with: "browser layer serves ≥50 real fetches across RAW + PULSE + CRUZ-tool over 30 days with zero hard failures."

**Budget consequence.** SP4 estimate drops from charter's 2–3 weeks to **5–7 working days**. K2 trigger threshold drops correspondingly to ~10 working days (50% over 7).

---

## 2. Architecture

### Service shape

`services/browser.py` exposes a `BrowserService` class plus a module-level `get_browser_service()` singleton — same pattern as `services/knowledge_base.py`, `services/qdrant.py`, `services/voice.py`. One process-wide instance, lazy-instantiated on first call.

### Browser process lifecycle

- **Start:** lazy. The first call to any layer method launches Chromium via Playwright async API. Cold-start cost (~1–2s) lands on the first caller; subsequent calls are warm.
- **Live:** kept alive 24/7 under PM2. The Chromium process is a child of the FastAPI worker; PM2 worker restart cycles take it with them.
- **Health:** `/health` endpoint adds a `browser` key — checks the Chromium process is alive and one CDP ping responds within 1s. Failure flips it to `degraded` and triggers re-init on next call.
- **Shutdown:** registered via `atexit` and FastAPI shutdown hook. Closes all contexts cleanly so cookie jars persist to disk.

### Named contexts model

Inside the single Chromium process, contexts are keyed by name and each maps to a directory under `~/.cruz/browser-profiles/<name>/`:

```
~/.cruz/browser-profiles/
  default/    # generic web, signed-out, used by RAW + PULSE + CRUZ web_search
  personal/   # manually signed-in once on the Mac Mini, used opt-in
```

- Contexts are created on first use of that profile name and cached in a dict on the service instance.
- A context is a Playwright `BrowserContext` — its own cookie jar, its own storage, its own renderer process tree.
- Switching contexts inside a single layer call is forbidden; consumers pick one profile per call.
- Future profiles (`linkedin`, `naukri`, `whatsapp`) slot in by name when their owning specs ship — zero changes to `services/browser.py`.

### Concurrency model

Per-context serialization, cross-context parallelism. Each context has an `asyncio.Lock`; calls into the same context queue, calls into different contexts run in parallel. Rationale: Playwright contexts are not concurrency-safe for shared `Page` objects, but the engine handles parallel contexts fine. Per-domain rate limiting (§4) layers on top of the lock and is global, not per-context.

### Profile management

- **Bootstrap.** On first launch, `default/` is created empty (Chromium auto-populates). `personal/` is created empty too — signing in happens via a one-shot debug script `scripts/browser_login.py <profile>` that opens a headed Chromium pointed at the profile dir. The user logs in by hand, closes the window. Cookies persist for headless reuse.
- **Backup.** The existing daily backup task picks up `~/.cruz/browser-profiles/` automatically (it's under the user home; backup config covers `~/.cruz/`). Verify scope at implementation time; one config-line update if needed.
- **Reset.** `scripts/browser_reset.py <profile>` deletes the directory. Logging back in is manual.

### Slot-in to existing v1

- `services/db.py`, `services/redis_client.py`, `services/knowledge_base.py` — unchanged.
- `agents/raw/raw_agent.py` — gains a lazy `get_browser_service()` reference, calls `await self._browser.fetch(url)` inside its existing research loop. KB writes (`record_agent_activity`, `write_domain_knowledge`) stay where they are.
- `agents/pulse/pulse_agent.py` — same pattern; gains a browser reference, adds 1–3 non-RSS sources to its source list via the layer.
- `agents/cruz/cruz_agent.py` — gains tool definitions `web_search` and `fetch_url` in its tool list. Tool executors call the layer.

### Logging contract

Every browser call writes one row to `agent_logs` with `agent='browser_service'` (Rule 5). `trace_id` propagates from the calling agent's input. Fields:

- `action` ∈ `{search, fetch, screenshot, extract_text, download, session_open}`
- `duration_ms`, `status`
- `input_data`: `{url or query (redacted if sensitive), profile, options}`
- `output_data`: `{status_code, byte_size, result_count}`

No `tokens_used` populated — no LLM calls inside the layer.

### Testing model

- **Unit tests** mock the Playwright API and exercise the service's logic (rate limit, context resolution, retry, error mapping).
- **One live integration test** marked `@pytest.mark.live`, skipped in CI, run manually pre-merge. Hits `https://example.com` and `https://duckduckgo.com/html/?q=cruz+ai`. Proves the real engine works end-to-end.
- **Retrofit tests** for RAW and PULSE — assert the layer is called, mock the layer at the test boundary.
- **Burst rate-limit test** — 15 requests at one domain in <1s, asserts the 11th raises `BrowserRateLimited`.

---

## 3. API surface

All five primitives are async. All accept an optional `profile: str = "default"` and an optional `trace_id: str = ""`. All return typed results.

```python
# 1. SEARCH — DuckDuckGo HTML by default; no API key, no captcha walls.
async def search(
    query: str,
    *,
    engine: str = "duckduckgo",
    limit: int = 10,
    profile: str = "default",
    trace_id: str = "",
) -> List[SearchResult]
# SearchResult = TypedDict{title: str, url: str, snippet: str, rank: int}

# 2. FETCH — render JS by default; return text + html + status.
async def fetch(
    url: str,
    *,
    render_js: bool = True,
    wait_for: Optional[str] = None,   # CSS selector, or None
    timeout_ms: int = 15000,
    profile: str = "default",
    trace_id: str = "",
) -> PageResult
# PageResult = TypedDict{
#     url: str, final_url: str, status: int, title: str,
#     html: str, text: str, byte_size: int
# }

# 3. SCREENSHOT — full page or viewport.
async def screenshot(
    url: str,
    *,
    full_page: bool = False,
    profile: str = "default",
    trace_id: str = "",
) -> bytes   # PNG

# 4. EXTRACT_TEXT — sugar over fetch + selector cascade. Returns plain text only.
async def extract_text(
    url: str,
    *,
    selector: Optional[str] = None,    # default: <article> ?? <main> ?? <body>
    profile: str = "default",
    trace_id: str = "",
) -> str

# 5. DOWNLOAD — write a binary URL to disk; return final path.
async def download(
    url: str,
    dest_path: str,
    *,
    profile: str = "default",
    trace_id: str = "",
) -> Path

# Escape hatch — last resort. "Use a primitive instead unless you can't."
@asynccontextmanager
async def session(
    *, profile: str = "default", trace_id: str = "",
) -> AsyncIterator[Page]   # Playwright Page
```

### Error model

One typed exception hierarchy in `services/browser.py`. Every primitive raises one of these; never returns silent error sentinels.

```python
class BrowserError(Exception): ...                # base
class BrowserTimeoutError(BrowserError): ...      # wait_for / page load timeout
class BrowserNavigationError(BrowserError): ...   # DNS, connection, SSL, http >= 500
class BrowserCaptchaDetected(BrowserError): ...   # heuristic match — surface, never solve
class BrowserRateLimited(BrowserError): ...       # per-domain bucket exhausted; includes retry_after_ms
class BrowserProfileError(BrowserError): ...      # bad profile name, profile dir corruption
```

**Retry policy.** Transient `BrowserNavigationError` and `BrowserTimeoutError` retry **once** with 2s backoff inside the primitive. Persistent failure surfaces. Captcha and rate-limit errors never retry — the caller decides.

### Captcha detection

After page load (or after `wait_for` resolves), the layer checks for any of:

- `iframe[src*="recaptcha"]`, `iframe[src*="hcaptcha"]`, `iframe[src*="turnstile"]`
- `[class*="captcha" i]`, `[id*="captcha" i]`
- A heuristic on body text matching `/please verify you are (a )?human|are you a robot|press and hold/i`

On match: raise `BrowserCaptchaDetected(url=..., kind=...)`. Caller can choose to escalate to user, queue for later, or abandon. **No auto-solve in v1.**

False-positive cost is low (caller falls back gracefully); false-negative cost is moderate (caller treats a captcha page as content). The heuristic deliberately over-detects.

### CRUZ tool definitions

Two tools added to the CRUZ agent's tool list:

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
            "max_chars": {"type": "integer", "default": 8000, "minimum": 500, "maximum": 30000},
        },
        "required": ["url"],
    },
},
```

Executor branches inside CRUZ's tool dispatch:

- `web_search` → `await get_browser_service().search(query, limit=limit, trace_id=self.trace_id)` → format as `1. <title> — <url>\n   <snippet>` numbered list, return as the tool result string.
- `fetch_url` → `await get_browser_service().extract_text(url, trace_id=self.trace_id)` → trim to `max_chars`, return.

Captcha or rate-limit errors from the layer surface as readable error strings inside the tool result so Claude can react ("the page asked me to verify I'm human; can you open it manually?"). They do not crash the conversation.

### Versioning

Public surface is the 5 primitives + `session` + 2 CRUZ tools. Anything else (helpers, internal context resolution, rate-limiter implementation) is private to the module — leading underscore convention. New primitives (`interact`, `submit_form`) when the first real consumer needs them, not before.

---

## 4. Anti-detect, pacing, and rate limits

The exit gate doesn't say "zero account warnings" anymore (no LinkedIn target), but the layer still needs to behave as a polite real-browser visitor: (a) future REACH-2.0 / Job Hunter / WhatsApp will inherit this layer's defaults; (b) DuckDuckGo and news sites do block aggressive bots — if RAW or PULSE looks bot-like, we get 429s or empty result pages.

### Anti-detect posture: minimal but defensible

- **Real Chromium via Playwright bundle.** `playwright-chromium`, headless. (No Xvfb in v1; revisit if a future hostile-target consumer needs headed mode.)
- **Persistent context, not incognito.** `launch_persistent_context()` with the profile directory. Defeats most "you've never been here" heuristics — cookies, localStorage, IndexedDB persist across calls.
- **Realistic user-agent.** Match the Chromium version we're shipping (Playwright surfaces it). No custom UA strings, no rotation.
- **`navigator.webdriver = undefined`.** Single most-checked automation tell. Patched via context-init script + the Chromium flag `--disable-blink-features=AutomationControlled` set on launch.
- **No stealth library in v1.** `rebrowser-playwright-stealth` and friends stay off. We add them only if v1 testing surfaces a real fingerprint-block.
- **No proxy, no VPN.** The Mac Mini's home IP is the same IP the user already uses for personal browsing. Most natural fingerprint on the network.
- **Viewport randomization at context creation.** Random pick from `[(1366,768), (1440,900), (1920,1080)]`. Locked for the lifetime of that context.

### Pacing

- **Inter-action delay.** Every primitive call sleeps a random `uniform(1.0, 3.0)` seconds **before** dispatching work. Implemented as a single decorator on the public methods. Disable via `BROWSER_PACE_DISABLED=1` env var for tests only.
- **Inter-fetch jitter inside one call.** `fetch()` with `wait_for=None` adds a random `uniform(0.5, 1.5)`s after the page settles before reading text/screenshotting.
- **Working-hours respect — deferred.** v1 consumers (RAW at 3 AM, PULSE at 6 AM) are already off-peak. Future hostile consumers manage their own working-hours gates.

### Rate limiting (per-domain token bucket)

This is where the brief's "daily-cap enforcement in code" requirement lands, scoped down. There's no per-account daily cap (no DM/apply primitives), but there's a per-domain request cap to prevent any agent from spamming a target site.

- **Mechanism.** In-process `dict[domain → TokenBucket]`. Each bucket has a `capacity` (max burst) and `refill_rate_per_sec`. Domain extracted via `urllib.parse.urlparse`.
- **Default policy.** `capacity=10, refill_rate=10/60` (10 requests per minute, burstable). Per-domain overrides via env: `CRUZ_BROWSER_RATE_LIMITS=duckduckgo.com:30:30/60,techcrunch.com:5:5/60`.
- **Enforcement is hard, not soft.** Bucket exhausted → primitive raises `BrowserRateLimited(retry_after_ms=...)`. Caller decides whether to back off or abandon.
- **State.** Process-local. We don't persist buckets across restarts. Restart cost is at most a brief re-burst window — accepted.
- **Test gate.** A synthetic burst test in `tests/services/test_browser_rate_limit.py` fires 15 requests at one domain in <1s, asserts the 11th raises `BrowserRateLimited`. Required for the exit gate.

### What the layer deliberately does *not* do

- No CAPTCHA solving. Detect → raise. v1 ends there.
- No proxy management.
- No daily request cap (per-account or global).
- No working-hours scheduling.
- No `robots.txt` parsing — caller's responsibility.
- No browser fingerprint randomization beyond viewport.

### Future-consumer hooks (documented, not implemented)

Names are reserved in the sub-spec so future PRs don't fight the layer's design:

```python
# Reserved for future hostile-target consumers (NOT implemented in v1):
# - browser.set_daily_cap(account, action, max_per_day)
# - browser.in_working_hours(profile) -> bool
# - browser.detect_account_warning(profile) -> Optional[Warning]
# - browser.solve_captcha(challenge) -> Solution      # via 2Captcha when budget unfreezes
```

---

## 5. Existing-agent retrofits (RAW + PULSE) and CRUZ tool wiring

Three files modified, no new agents.

### RAW retrofit (`agents/raw/raw_agent.py`)

RAW's job today is nightly research at 3 AM — pulls free RSS, drops summaries into `cruz_domain_knowledge`. The layer adds the ability to fetch arbitrary pages.

Changes:

1. Add a lazy reference to the browser service via `get_browser_service()` (matches the KB pattern).
2. Inside RAW's research loop: where it currently does "for each RSS feed: parse XML → summarize → write to KB", add a parallel branch "for each non-RSS source: `await self._browser.fetch(url)` → summarize the `text` field → write to KB".
3. Sources list moves from a hardcoded RSS array to a `sources.yml` config under `agents/raw/sources.yml` with two sections: `rss:` (existing) and `pages:` (new). Pages entries: `{url, selector, summarize_with}`. **Initial pages list left for the implementation step** (defaults TBD; representative picks during implementation: Anthropic blog + Hacker News front page).
4. KB write path unchanged — RAW still calls `write_domain_knowledge()` and `record_agent_activity()` exactly as today.
5. Failure isolation: a single `BrowserError` on one source skips that source and continues. RAW's overall run does not fail because one page 404'd.

Tests: existing `tests/agents/test_raw.py` gets new cases for the page-fetch branch. The browser service is mocked at `services.browser.get_browser_service`. One `@pytest.mark.live` end-to-end test fires a real fetch against a stable docs URL and asserts the KB write.

### PULSE retrofit (`agents/pulse/pulse_agent.py`)

PULSE today builds the 6 AM briefing from RSS + Hacker News + Reddit. The layer lets it pull from sites without RSS.

Changes:

1. Same lazy-init pattern as RAW.
2. PULSE's source list extends with 1–3 non-RSS news sources via a sibling `agents/pulse/sources.yml` (same shape as RAW's). Defaults TBD at implementation; representative picks: TechCrunch + Inc42.
3. The briefing template gains a "Web roundup" section that includes layer-fetched stories. If the layer call fails, the section is omitted with a one-line note in the briefing footer ("Web roundup unavailable: rate-limited at TechCrunch") — Rule 5 says we log it, but the user's morning briefing isn't broken because of one fetch.
4. No KB write changes; PULSE writes briefings to Notion as it does today.

Tests: `tests/agents/test_pulse.py` gets the same mock-and-assert pattern. Live test optional for PULSE — covered by RAW's live test for the layer itself.

### CRUZ tool wiring (`agents/cruz/cruz_agent.py`)

Tool definitions added to CRUZ's tool list. Executors call into `get_browser_service()`. See §3 for tool schemas and dispatch behavior.

### KB participation note (Rule 3 alignment)

The browser layer is a service, not an agent — Rule 3 binds agents, not services. Activity records continue to be written by the consuming agent (RAW writes its own, PULSE its own, CRUZ via its existing conversation/agent-log path). The layer writes its own structured rows under `agent='browser_service'` per Rule 5 for tracing, but does not write to KB rings. This keeps the KB rings semantically clean — `cruz_activities` describes *agent* work, not service plumbing.

If a future consumer wants a `cruz_domain_knowledge` write tied directly to a fetch (e.g. RAW reads a doc and immediately stashes its content as domain knowledge), the consumer does that write — not the layer.

### Build sequence (within the 5–7 day budget)

1. **Day 1–2:** `services/browser.py` skeleton, `BrowserService` class, named-context resolution, lazy lifecycle, error hierarchy. Unit tests.
2. **Day 2–3:** Implement the 5 primitives + `session()` escape hatch. Add the rate limiter. Add captcha detection. Unit tests for each. One live integration test marked `@pytest.mark.live`.
3. **Day 3–4:** CRUZ tool wiring (`web_search`, `fetch_url`). Manual end-to-end via `/command`. Update `/health` to include browser status.
4. **Day 4–5:** RAW retrofit + `agents/raw/sources.yml`. Mock + live tests. Confirm 3 AM cron job picks up the new branch.
5. **Day 5–6:** PULSE retrofit + `agents/pulse/sources.yml`. Mock + briefing-shape test.
6. **Day 6–7:** End-to-end exit-gate run on the Mac Mini. Burst-rate-limit test. Personal-profile login script + restart-persistence test. Document any caveats. Commit, PR, merge.

K2 trigger: ~10 working days.

---

## 6. Selector resilience, monitoring, and v2.1 hooks

### The three selector surfaces in v1, in order of fragility

1. **DuckDuckGo HTML parser.** `search()` parses `https://duckduckgo.com/html/?q=...`. Stable for years but not a contract. If DDG changes its markup, every `search()` call returns empty results and CRUZ's `web_search` tool silently degrades.
2. **Captcha-detection heuristic.** False negatives let captchas slip through as page content; false positives kill legitimate sites that mention "captcha" or use Turnstile cosmetically.
3. **Default `extract_text` cascade** (`<article>` → `<main>` → `<body>`). Sites that embed real content in unconventional containers fall back to whole-body extraction with sidebars and nav included. Quality degrades, doesn't break.

### Resilience tactics, by surface

**DDG parser.**

- Implementation lives in a single private module-level function `_parse_ddg_html(html: str) -> List[SearchResult]`. Selector strings are constants at the top of the function — easy to update in one place.
- A unit test fixture stores a real DDG HTML response (~50KB) in `tests/services/fixtures/ddg_search_cruz_ai.html`. The unit test asserts `_parse_ddg_html(fixture)` returns ≥5 results with the expected fields.
- A `@pytest.mark.live` test fires a real DDG search against a stable query and asserts ≥1 result. Catches DDG live-HTML divergence from the fixture before the manual fixture-refresh cycle.
- Fallback: if DDG returns 0 results when we expected some, the layer logs `agent_logs` with `status='degraded'` and `output_data={"reason": "ddg_zero_results", "query": "..."}`. Doesn't raise — consumer might want an empty list — but the log is greppable.

**Captcha detection.**

- Implementation lives in `_detect_captcha(page_html: str, page_url: str) -> Optional[str]`. Returns the kind (`"recaptcha" | "hcaptcha" | "turnstile" | "text_heuristic"`) or `None`. Pure function over HTML, fully testable with fixtures.
- Test fixtures: 4–6 saved HTML samples — real captcha pages (one per kind) + 2 known-false-positive pages (e.g. a docs page that mentions captcha in body text without showing one). Unit tests assert correct classification.

**`extract_text` cascade.**

- Cascade is intentionally simple. Quality issues are visible (caller gets junk text), so they're self-monitoring.
- Future optimization: a `readability`-style algorithm (mozilla/readability port) when one consumer's quality complaints justify the dependency. Out of scope for v1.

### Monitoring — how we know when something breaks

- **Daily health probe (cheap).** `/health` adds the `browser` block. Once a day, an internal probe runs `await browser.search("anthropic claude")` against a stable query, asserts ≥3 results. Failure flips browser to `degraded` and fires an existing Telegram alert via `services/alerts.py`. Lives in the existing scheduler — one new ARQ task `browser_health_probe` running daily.
- **Live integration tests on every PR touching `services/browser.py`.** The `@pytest.mark.live` tests are run pre-merge by hand (or via a `make browser-live-tests` target). CI does not run them.
- **Structured-log query for monthly review.** Documented in the runbook:
  ```sql
  SELECT action, status, COUNT(*)
  FROM agent_logs
  WHERE agent='browser_service' AND created_at > NOW() - INTERVAL '30 days'
  GROUP BY action, status;
  ```
  Sudden drop in `success` count or rise in `degraded` rows on `search` action means the parser is breaking. Visible during the existing first-of-month spend review (charter §4) — no new ritual needed.

### v2.1 hooks (documented, not built)

When LinkedIn / Job Hunter / WhatsApp eventually ship as agents, they bring their own selector surfaces — and *those* surfaces are the ones that genuinely change weekly. The v2.1 specs will own those problems. The layer reserves these extension points (interface-only):

- **Per-site selector adapter.** `services/browser/adapters/<site>.py` — one module per hostile target. Owns its own selectors, captcha-handling overrides, per-action delays. Uses the layer's `session()` escape hatch.
- **Selector-rot canary.** A future cron (one per high-stakes site) that runs a no-op probe ("can we still log in? can we still see the inbox?") daily and alerts on failure. Distinct from the v1 health probe because it requires a signed-in profile.
- **Action-warning detection.** When a site's UI shows a warning ("we noticed unusual activity"), the adapter raises a typed exception that the consuming agent catches and pauses itself for N hours. Layer doesn't know about this in v1.

These hooks are docstring stubs in the layer (or in the sub-spec) — no scaffolding, no abstract base classes. We implement them when a real consumer arrives.

### K2 internal degradation order (charter §6 supplement)

There is no charter cut-row inside SP4 v1 short of dropping the layer wholesale. If K2 fires, the internal sequence is:

1. **Drop PULSE retrofit.** Ship layer + RAW + CRUZ tool. Saves ~1 day.
2. **Drop RAW retrofit.** Ship layer + CRUZ tool only. Saves another ~1 day. The layer is still demonstrable through `web_search` in a CRUZ conversation.
3. **Do not drop the CRUZ tool.** Shipping the layer with no consumers violates the §10 exit gate. If we're at this point, the right call is to cut SP4 entirely (charter §6 row #12) and revisit later.

---

## 7. Risks, decisions, dependencies

### Top risks and mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | DDG HTML changes; `search()` returns empty results silently | Medium over 12 months | High (`web_search` degrades invisibly) | Fixture-based unit test catches drift; daily live health probe alerts via Telegram; structured `degraded` log for monthly review |
| 2 | Chromium process crashes mid-call; takes down all contexts at once | Low | Medium (next call cold-starts; ~2s blip) | `/health` reports browser status; lazy re-init on next call after crash; PM2 worker restart picks it up cleanly |
| 3 | `personal` profile cookies expire; signed-in fetches start failing | Medium per quarter | Low (only opt-in profile affected) | `scripts/browser_login.py <profile>` is the documented re-auth path; failure mode is a clear `BrowserNavigationError`, not a silent degrade |
| 4 | Rate limiter resets on PM2 restart; brief over-fetch window post-restart | Low | Low | Accepted — caps are throughput politeness, not safety |
| 5 | A consumer leaks the `session()` escape hatch into wide use; layer becomes a thin Playwright wrapper | Medium over 6 months | Medium (architectural drift) | Docstring on `session()` is explicit ("escape hatch"); code review catches new usages; v1 has zero `session()` callers in shipped code |
| 6 | Captcha detection false-negative — page returns a captcha as content; RAW/PULSE summarize garbage into KB | Medium per source | Low (one bad KB row, easily found and pruned) | Heuristic over-detects; consumers log + skip on `BrowserCaptchaDetected` |
| 7 | Headless Chromium fingerprint detected by a target site months from now | Medium long-term | Low for v1 targets, **High for v2.1+ hostile consumers** | v1 doesn't trigger this; v2.1 specs own the upgrade decision |
| 8 | "Minimal anti-detect" turns out wrong when REACH-2.0 lights up; layer needs a v2 redesign | Medium | Medium | Posture is documented as v1-scoped. The 5 primitives + `session()` API doesn't change when stealth gets harder — only the launch config does. Forward-compatible. |

### Decision log (for audit, not re-debate)

| # | Decision | Section | Alternative considered |
|---|---|---|---|
| 1 | SP4 = layer only; LinkedIn/Job Hunter/WhatsApp parked to v2.1 | §1 | Layer + 1 agent — rejected, no hostile target left to validate against |
| 2 | Mid-level API (5 primitives + escape hatch) | §3 | Thin Playwright-passthrough; thick intent-level |
| 3 | Named contexts inside one Chromium process | §2 | Single shared profile; multi-process pool |
| 4 | First consumers: RAW + PULSE | §5 | RAW only; RAW+PULSE+GENERAL+FORGE |
| 5 | CRUZ gets `web_search` + `fetch_url` tools | §3 + §5 | `web_search` only; no CRUZ tool at all |
| 6 | Anti-detect posture: minimal | §4 | Moderate (rebrowser-stealth); aggressive (proxies + multi-profile) |
| 7 | Headless, no Xvfb | §4 | Headed via Xvfb — deferred; no v1 consumer requires it |
| 8 | In-process token bucket; reset on restart | §4 | Redis-backed bucket — rejected for v1 simplicity |
| 9 | DuckDuckGo HTML as default search engine | §3 | Bing API; Google scraping; SerpAPI — rejected (paid or fragile) |
| 10 | Captcha detect-and-surface; no auto-solve | §3 | 2Captcha integration in v1 — deferred until a real consumer hits a wall |
| 11 | Layer is a service, not an agent; doesn't write to KB rings | §5 | Layer auto-records to `cruz_activities` — rejected, breaks Rule 1/3 boundary |
| 12 | Charter override per Rule 8 — exit gate rewritten, success criterion #4 migrates to REACH-2.0 | §1, §10 | Keep charter exit gate as-is — rejected, would be unsatisfiable |

### Dependencies

- **Hard:** SP1 (operational deployment) and SP2 (KB) closed.
- **Soft (not blocking):** None. SP3 is independent; SP5–7 are downstream consumers.
- **External:**
  - `playwright` Python package + `playwright install chromium` on the Mac Mini.
  - `~/.cruz/browser-profiles/` writable; existing daily backup task picks it up (verify scope at install).
  - DuckDuckGo HTML endpoint reachable. Fallback to Bing HTML scraping is a v1.1 addition if needed.
  - PM2 ecosystem config gains the browser process as a child of the FastAPI worker (no new PM2 process).

---

## 8. Project structure changes

```
services/
  browser.py               # NEW — BrowserService singleton + 5 primitives + session()

agents/
  cruz/
    cruz_agent.py          # MODIFIED — adds web_search + fetch_url tools
  raw/
    raw_agent.py           # MODIFIED — page-fetch branch alongside RSS
    sources.yml            # NEW — rss: + pages: source config
  pulse/
    pulse_agent.py         # MODIFIED — non-RSS source branch
    sources.yml            # NEW — same shape as raw/sources.yml

scripts/
  browser_login.py         # NEW — one-shot manual login for a named profile
  browser_reset.py         # NEW — wipe a named profile's directory

workers/tasks/
  browser_health.py        # NEW — daily browser_health_probe ARQ task

tests/
  services/
    test_browser.py                     # NEW — unit tests
    test_browser_rate_limit.py          # NEW — burst test
    test_browser_live.py                # NEW — @pytest.mark.live, manual run
    fixtures/
      ddg_search_cruz_ai.html           # NEW — DDG fixture
      captcha_recaptcha.html            # NEW — captcha fixtures
      captcha_hcaptcha.html
      captcha_turnstile.html
      captcha_false_positive_docs.html
      captcha_false_positive_widget.html
  agents/
    test_raw.py            # MODIFIED — adds page-fetch branch tests
    test_pulse.py          # MODIFIED — adds non-RSS source branch tests

docs/superpowers/specs/
  2026-04-26-sp4-browser-automation-design.md   # this file

~/.cruz/browser-profiles/  # NEW (runtime, gitignored)
  default/
  personal/                # populated by manual login script
```

No changes to `services/db.py`, `services/redis_client.py`, `services/knowledge_base.py`, `services/qdrant.py`, or any other agent module.

---

## 9. Environment variables (additions)

```bash
# SP4 — Browser automation
CRUZ_BROWSER_PROFILES_DIR=~/.cruz/browser-profiles    # optional override
CRUZ_BROWSER_RATE_LIMITS=                              # optional per-domain overrides, e.g. "duckduckgo.com:30:30/60"
BROWSER_PACE_DISABLED=                                 # set to 1 only in tests
```

No changes to existing env vars.

---

## 10. Exit gate (rewrite of charter §5.1 SP4 row)

All clauses must hold for SP4 to ship.

1. **Layer end-to-end.** `services/browser.py` runs a real `search()` and a real `fetch()` end-to-end on the Mac Mini against live sites (not mocks).
2. **RAW retrofit live.** RAW's 3 AM scheduled run uses the layer for ≥1 real fetch and produces a `cruz_domain_knowledge` write that v1 (RSS-only) wouldn't have produced.
3. **PULSE retrofit live.** PULSE's 6 AM briefing pulls from ≥1 non-RSS source via the layer; that content reaches the morning briefing output.
4. **CRUZ web_search live.** The CRUZ `web_search` tool returns plausible results for an ad-hoc query inside a streaming `/command` response.
5. **Personal profile persistence.** The `personal` context retains a manually-signed-in session across a server restart.
6. **Rate limit enforced in code.** Per-domain rate limit triggers under a synthetic burst test (the burst test in `tests/services/test_browser_rate_limit.py` passes).
7. **No latency regression.** P95 latency on existing RAW and PULSE runs does not increase >20% (mirrors SP2 latency gate).

A failure of any clause means SP4 enters a bounded fix window per charter §5.1. Fix-window time counts toward K2.

---

## 11. Hand-off

This sub-spec is written for the brainstorming → spec → plan → execute pipeline. After user approval of this spec:

1. **Spec review loop** — `spec-document-reviewer` subagent reviews this doc; iterate on its findings until approved (max 5 iterations, then escalate to user).
2. **User reviews the written spec.**
3. **Invoke `superpowers:writing-plans`** to produce a detailed implementation plan that lands every clause of §10's exit gate.
4. **Execute the plan** in a dedicated worktree (likely via `superpowers:executing-plans` or `superpowers:subagent-driven-development`).
5. **Run the SP4 exit gate** (§10) on the Mac Mini.
6. **If gate passes:** SP5 (Event Loop) brainstorming starts. **If fails:** bounded fix window or shelve.

The charter (`docs/superpowers/specs/2026-04-20-v2-program-charter.md`) itself is **not edited** by this sub-spec — per charter §8, the charter is stable and updated only when a gate fires. The override list in §1 of this spec is the user-approved record; whether to amend the charter document itself is a separate decision left to the user during a future charter-amend window.
