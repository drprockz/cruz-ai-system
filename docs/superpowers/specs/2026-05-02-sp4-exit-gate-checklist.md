# SP4 Exit-Gate Checklist (Task 5.4)

Manual verification you run on the Mac Mini before SP4 ships. All 8 steps must pass (Step 7 is advisory if a clean baseline wasn't captured before SP4 work began).

**Branch:** `claude/sleepy-elgamal-3fb2aa`
**Worktree:** `/Users/drprockz/Projects/cruz-ai-system/.claude/worktrees/sleepy-elgamal-3fb2aa`
**Spec §10 reference:** [2026-04-26-sp4-browser-automation-design.md](2026-04-26-sp4-browser-automation-design.md)

---

## Pre-flight

- [ ] Mac Mini has Chromium installed: `playwright install chromium`
- [ ] Postgres + Redis running: `brew services list | grep -E "postgresql|redis"` shows `started`
- [ ] CRUZ API running under PM2: `pm2 status | grep cruz-api`
- [ ] Worktree checked out: `cd /Users/drprockz/Projects/cruz-ai-system/.claude/worktrees/sleepy-elgamal-3fb2aa && git rev-parse HEAD` returns the SP4 head
- [ ] System pytest deps present: `pip install --user beautifulsoup4 playwright pytest-asyncio`

---

## Step 1 — Browser layer end-to-end

```bash
make browser-live-tests
```

**Expected:** 3 tests PASS against real DDG and example.com.

**Known risk:** DDG anti-bot blocks the dev network's IP. The Mac Mini's home IP fingerprint may differ — if `test_live_ddg_search_returns_results` fails here, options are: (a) try again from a different network, (b) switch the layer to a different search engine.

**Record:** which test passed, observed durations.

```
test_live_ddg_search_returns_results       — pass/fail, ___s
test_live_fetch_example_com                 — pass/fail, ___s
test_live_personal_profile_persistence      — pass/fail, ___s
```

---

## Step 2 — RAW retrofit live

```bash
cd /Users/drprockz/Projects/cruz-ai-system/.claude/worktrees/sleepy-elgamal-3fb2aa
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

**Note:** `agents/raw/sources.yml` ships empty (`pages: []`). To exercise the page-fetch branch, populate it first:

```yaml
rss: []
pages:
  - url: https://www.anthropic.com/news
    selector: main
    summarize_with: llama3.1:8b
```

**Expected:**
- `success=True` in the printed output
- ≥1 `browser_service.fetch` row in `agent_logs` for the trace
- `cruz_domain_knowledge` ring has at least one new vector

**Verify:**

```sql
SELECT action, status, COUNT(*)
FROM agent_logs
WHERE trace_id = 't-exit-gate' AND agent = 'browser_service'
GROUP BY action, status;
```

**Record:**

```
fetch rows logged: ___
domain_knowledge writes: ___
```

---

## Step 3 — PULSE retrofit live

Populate `agents/pulse/sources.yml` if you want a live roundup:

```yaml
pages:
  - url: https://techcrunch.com/
    selector: main
```

Then run:

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

**Expected:** `web_roundup` is a non-empty list; one item has the TechCrunch URL.

**Record:**

```
web_roundup item count: ___
first URL: ___
```

---

## Step 4 — CRUZ web_search live (streaming SSE)

```bash
curl -N -X POST http://localhost:3000/command \
  -H "Content-Type: application/json" \
  -d '{"message":"What did Anthropic announce most recently?","stream":true}'
```

**Expected:** streamed SSE events show:
- a `tool_call` event with `agent: web_search`
- intermediate text events
- final answer text references real Anthropic news

**Record:**

```
tool_call observed: yes/no
final text length: ___
```

---

## Step 5 — Personal profile persistence

```bash
# 5a. Open headed Chromium against the personal profile
python scripts/browser_login.py personal
# Sign into a known site (e.g. github.com), then close the window.

# 5b. Restart CRUZ to confirm cookies persist on disk, not in-process
pm2 restart cruz-api

# 5c. Verify session survives
python -c "
import asyncio
from services.browser import get_browser_service
async def main():
    svc = get_browser_service()
    ctx = await svc._get_context('personal')
    page = await ctx.new_page()
    await page.goto('https://github.com/')
    print('signed in?', 'Sign in' not in await page.content())
asyncio.run(main())
"
```

**Expected:** prints `signed in? True` after the restart.

**Record:**

```
signed in? ___
profile dir size: ___
```

---

## Step 6 — Rate limiter passes in CI shape

```bash
python3 -m pytest tests/services/test_browser_rate_limit.py -v
```

**Expected:** all 6 tests PASS.

**Record:**

```
pass count: ___ / 6
```

---

## Step 7 — P95 latency regression check (advisory if no clean baseline)

**Baseline (pre-SP4)** — capture from `main` branch, before SP4 changes ran on the Mac Mini:

```sql
SELECT
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms
FROM agent_logs
WHERE agent = 'raw' AND status = 'success'
  AND created_at > NOW() - INTERVAL '7 days';
```

**Post-SP4** — after RAW runs at least once on the new code:

```sql
SELECT
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms
FROM agent_logs
WHERE agent = 'raw' AND status = 'success'
  AND created_at > NOW() - INTERVAL '1 day';
```

**Threshold:** `(post_p95 - pre_p95) / pre_p95` must be ≤ 0.20 (20% increase).

**Repeat** for `agent = 'pulse'`.

**Record:**

```
RAW pre-SP4 p95:  ___ ms
RAW post-SP4 p95: ___ ms
RAW delta:        ___ %  (≤ 20% required)

PULSE pre-SP4 p95:  ___ ms
PULSE post-SP4 p95: ___ ms
PULSE delta:        ___ %  (≤ 20% required)
```

**If no clean baseline exists:** mark this step as advisory. Document the post-SP4 numbers anyway so the next change has a baseline.

---

## Step 8 — Document the exit-gate run

Append the record below to the design spec at `docs/superpowers/specs/2026-04-26-sp4-browser-automation-design.md` (end of file).

```markdown
---

## Exit-gate verification — YYYY-MM-DD

Run by: Darshan Parmar
Branch: claude/sleepy-elgamal-3fb2aa
Commit: <SHA at time of verification>

| Step | Result | Notes |
|---|---|---|
| 1. browser-live-tests | pass / fail | DDG behaviour: ___ |
| 2. RAW retrofit live | pass / fail | fetch rows: ___ |
| 3. PULSE retrofit live | pass / fail | roundup items: ___ |
| 4. CRUZ web_search streaming | pass / fail | tool_call observed: ___ |
| 5. Personal profile persistence | pass / fail | signed in after restart: ___ |
| 6. Rate limiter | pass / fail | 6/6 |
| 7. P95 latency regression | pass / fail / advisory | RAW Δ ___ %, PULSE Δ ___ % |

Verdict: ✅ ship / ❌ blocked

Follow-ups (if any):
- ...
```

---

## After all 8 steps pass

Run the wrap-up skill from the worktree:

```
/superpowers:finishing-a-development-branch
```

It guides the choice between merge / PR / rebase based on team conventions.

---

## Pre-existing failures to deal with separately (NOT blocking SP4)

These were broken before SP4 work started and are out of scope here, but worth queueing as separate cleanup:

- `tests/services/test_realtime_tts.py` — collection error: `ModuleNotFoundError: No module named 'respx'`. Fix: `pip install --user respx`.
- `tests/workers/test_backup_tasks.py` — 2 tests fail with `object MagicMock can't be used in 'await' expression`. The mocks need to be `AsyncMock` for the upload methods. Unrelated to SP4.

---

## Quick-reference: SP4 commits on this branch (for the record)

```
625245b test(sp4): add smoke-time bounds for RAW + PULSE full-run paths
bc80d7c feat(sp4): PULSE retrofit — Web roundup section via browser service
4a849a4 feat(sp4): RAW retrofit — load sources.yml; page-fetch branch via browser service
0f789de feat(sp4): daily browser health probe ARQ task with Telegram alerts
74b59f7 feat(sp4): add manual-login + reset scripts for browser profiles
b8f711c feat(sp4): web_search + fetch_url in CRUZ streaming path
1c22178 feat(sp4): add web_search + fetch_url tools to CRUZ (process path)
3b93334 test(sp4): add @pytest.mark.live integration tests + make target
7d8e629 feat(sp4): structured agent_logs write-through for every browser call
6fe7b87 feat(sp4): add captcha detection heuristic with fixtures
de4f52c feat(sp4): add per-domain token-bucket rate limiter
7ca8075 feat(sp4): add extract_text, screenshot, download, session escape hatch
b3df7c4 feat(sp4): add fetch() primitive with one-retry policy
22db0d4 feat(sp4): add search() primitive + DDG parser with fixture-locked tests
e6b7102 feat(sp4): expose browser service health on /health
5f02099 feat(sp4): lazy Playwright start + named persistent contexts
b0ce101 feat(sp4): add BrowserService skeleton + error hierarchy
6f83345 docs(sp4): document greenlet pin reason (forced by playwright)
dd0a246 chore(sp4): add Playwright 1.49.* dependency
```

198 tests pass across the SP4 suite. 0 blockers, 0 important issues, 5 NITs (defensible) flagged by final reviewer.
