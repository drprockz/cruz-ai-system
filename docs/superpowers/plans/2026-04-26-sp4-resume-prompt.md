# SP4 Resume Prompt — paste this into a fresh Claude Code session

Resume executing the SP4 browser automation plan. The first 5 of 19 implementation tasks are complete and committed on this branch; pick up at Task 2.2.

## Context

You are continuing **subagent-driven-development** execution of the SP4 implementation plan. The plan was brainstormed, spec'd, planned, and partially executed in a prior session. This session resumes execution from Task 2.2 onward.

Working directory: `/Users/drprockz/Projects/cruz-ai-system/.claude/worktrees/sleepy-elgamal-3fb2aa/`
Branch: `claude/sleepy-elgamal-3fb2aa`

**Plan:** `docs/superpowers/plans/2026-04-26-sp4-browser-automation.md`
**Spec:** `docs/superpowers/specs/2026-04-26-sp4-browser-automation-design.md`
**Charter:** `docs/superpowers/specs/2026-04-20-v2-program-charter.md`

## What's already done

**Commits on this branch (5 implementation tasks + plan/spec docs):**

```
22db0d4 feat(sp4): add search() primitive + DDG parser with fixture-locked tests   # Task 2.1
e6b7102 feat(sp4): expose browser service health on /health                        # Task 1.4
5f02099 feat(sp4): lazy Playwright start + named persistent contexts               # Task 1.3
b0ce101 feat(sp4): add BrowserService skeleton + error hierarchy                   # Task 1.2
6f83345 docs(sp4): document greenlet pin reason (forced by playwright)             # Task 1.1 follow-up
dd0a246 chore(sp4): add Playwright 1.49.* dependency                               # Task 1.1
ea888de docs(sp4): add SP4 browser automation implementation plan
c992b51 docs(sp4): add SP4 browser automation layer design spec
```

**Files in place:**

- `services/browser/__init__.py` — public re-exports (BrowserService, get_browser_service, errors, SearchResult, PageResult, _parse_ddg_html)
- `services/browser/service.py` — BrowserService class with `__init__`, `_ensure_playwright`, `_get_context`, `_pace`, `search`, `health`, `shutdown` methods, plus module-level `BROWSER_PROFILES_DIR`, `BROWSER_PACE_DISABLED`, `_PROFILE_NAME_RE`, `_CHROMIUM_ARGS`, `_async_playwright_start`
- `services/browser/errors.py` — 6-class exception hierarchy (`BrowserError` base + 5 specialized subclasses)
- `services/browser/parsers.py` — pure HTML helpers: `_parse_ddg_html`, `SearchResult`, `PageResult`
- `tests/services/test_browser.py` — 9 tests, all passing
- `tests/services/fixtures/ddg_search_cruz_ai.html` — hand-crafted DDG fixture (real DDG anomaly system blocks live capture; see Real-World Findings below)
- `tests/api/test_health_endpoint.py` — extended with `TestHealthBrowserBlock` class (5 new tests for the `/health` browser block)
- `backend/api/main.py` — `/health` handler extended with browser probe block
- `requirements.txt` — `playwright==1.49.*`, `beautifulsoup4==4.12.3`, comment above `greenlet==3.1.1` explaining the forced pin

**All 49 SP4-related tests pass under `python3 -m pytest tests/services/test_browser.py tests/api/test_health_endpoint.py -v`.**

## Real-world findings from prior session (carry these forward)

1. **DDG anti-bot is more aggressive than the spec assumed.** Plain `curl` and even our anti-detect headless Chromium (`--disable-blink-features=AutomationControlled` + persistent context + viewport) get the DDG anomaly modal from this network. The hand-crafted fixture (Task 2.1, Plan B) carries the parser tests; live-DDG validation lands in Task 3.4 — and may need to either run from the user's Mac Mini home IP (different fingerprint) or fall back to a different search engine. **Flag this back to the user when you reach Task 3.4** — they may want to discuss before pushing live tests through.

2. **Greenlet got pinned to 3.1.1** (forced by Playwright 1.49). Documented in `requirements.txt` with a comment + dedicated commit. No action needed.

3. **`bs4` was installed at user level** (`pip3 install --user beautifulsoup4 playwright pytest-asyncio`) so system pytest can find it. Subagents typically create their own ephemeral venvs and don't share state — this works because the system pytest also has access. If a subagent reports tests passing, verify via `python3 -m pytest <path> -v` from the worktree before accepting DONE.

## How to resume

1. Invoke the `superpowers:subagent-driven-development` skill. (You already have a plan in hand; jump straight to the execution loop.)

2. Recreate the TodoWrite with the 14 remaining tasks (the prior session's todos are listed below — copy them).

3. Begin with **Task 2.2: `fetch()` primitive + retry policy**. Extract its full text from the plan file:

   ```bash
   awk '/^### Task 2\.2:/,/^### Task 2\.3:/' docs/superpowers/plans/2026-04-26-sp4-browser-automation.md
   ```

   Paste the extracted task text into the implementer-prompt template. Working dir is the worktree root above.

4. After implementer returns, dispatch a **combined spec + code-quality review** in a single subagent call (the prior session found this efficient; the skill protocol still requires spec-first-then-quality, just done in one dispatch). Use haiku for review subagents on mechanical tasks.

5. Continue serially through Tasks 2.2 → 5.3. Each follows the same TDD cadence: failing test → run-fail → implement → run-pass → commit.

6. **Task 5.4 (exit-gate verification on the Mac Mini) is a USER task, not a subagent task.** It requires the running CRUZ system on the Mac Mini, `pm2 restart cruz-api`, real DDG calls, real RAW/PULSE invocations. When you reach it, hand back to the user with the exact verification checklist from the plan and DO NOT dispatch a subagent for it.

7. After Task 5.3 completes (or after Task 5.4 if user chooses to run it within this session), dispatch the **final code reviewer** for the whole implementation: `superpowers:code-reviewer` against the diff from `ea888de..HEAD`.

8. After final review approves, invoke `superpowers:finishing-a-development-branch` to wrap up.

## Remaining tasks (14)

Recreate as TodoWrite items:

- Task 2.2: `fetch()` primitive + retry policy
- Task 2.3: `extract_text`, `screenshot`, `download`, `session()` escape hatch
- Task 3.1: per-domain token-bucket rate limiter
- Task 3.2: captcha detection + fixtures
- Task 3.3: `agent_logs` write-through (Rule 5)
- Task 3.4: live integration tests + Makefile target — **flag DDG-block finding to user here**
- Task 4.1: CRUZ `web_search` / `fetch_url` tools (process path)
- Task 4.2: mirror dispatch into `stream_response` path
- Task 4.3: manual-login + reset scripts
- Task 4.4: daily health probe ARQ task
- Task 5.1: RAW retrofit (sources.yml + page-fetch branch)
- Task 5.2: PULSE retrofit (Web roundup section)
- Task 5.3: smoke time-bounds for RAW + PULSE
- Task 5.4: exit-gate verification on Mac Mini — **USER task, not subagent**
- Final code reviewer for entire implementation

## Important conventions to preserve

- **Sub-package layout.** When the plan says "Add to `services/browser.py`", it means split between `services/browser/service.py` (I/O methods on `BrowserService`), `services/browser/parsers.py` (pure HTML helpers), `services/browser/rate_limit.py` (Task 3.1; new file), and `services/browser/errors.py` (exceptions). The plan's §275 note covers this.

- **Tests use `import services.browser.service as browser_mod`** for module-level state monkeypatching (e.g. `_instance`, `BROWSER_PROFILES_DIR`, `BROWSER_PACE_DISABLED`).

- **Two-stage review per task.** Spec compliance first; code quality only if spec passes. Combine into one dispatch when possible to save context budget.

- **Use haiku for mechanical tasks and reviews. Use sonnet (default) for tasks requiring judgment** (e.g. Task 4.1 / 4.2 CRUZ tool wiring, where the implementer needs to read the existing `cruz_agent.py` and integrate carefully — these are not pure mechanical paste).

- **Never commit on `main`/`master`.** This branch (`claude/sleepy-elgamal-3fb2aa`) is the worktree branch — commit there.

- **Commit messages are exact** as the plan specifies. Do not paraphrase.

- **Self-contained prompts.** When dispatching subagents, paste the relevant task text inline. Don't tell them to read the plan file (skill red flag).

## First action when resuming

```bash
# Verify the resume state matches expectations:
git log --oneline -8
git status -s
python3 -m pytest tests/services/test_browser.py tests/api/test_health_endpoint.py -v 2>&1 | tail -10
```

Expected: 8 commits including `22db0d4 feat(sp4): add search() primitive...`, clean working tree, 49 tests pass.

If any check fails, STOP and surface to the user before continuing.

Then proceed to dispatch Task 2.2.
