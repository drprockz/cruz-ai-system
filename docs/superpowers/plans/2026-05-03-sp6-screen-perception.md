# SP6 — Screen Perception (Layer 5, scoped) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship on-demand screen perception for CRUZ — a `screen_perception` tool that captures a Mac screenshot, calls Claude Vision, and answers "what am I working on?", plus active-app context (with allowlisted window title for dev tools) injected into CRUZ's runtime context on every request.

**Architecture:** New singleton service `services/screen_perception.py` with two methods (`get_active_window` for fast metadata reads, `analyze` for screenshot + Vision). One CRUZ tool registered in `agents/cruz/cruz_agent.py`, dispatched directly to the service (no specialist agent). Active-app injected as one line in CRUZ's existing `runtime_context` block in both `process()` and `stream_response()`. Vision answer is sanitized via `privacy_engine.sanitize()` at the source before flowing into any persistence path.

**Tech Stack:** Python 3.11+, `osascript`/`screencapture` (macOS built-ins, reused via `services/mac_controller.py`), `services/llm` LLMRouter (Anthropic backend pinned for vision), `agents/cruz/persona/privacy_engine.py` (sanitize), pytest + `pytest-asyncio` for tests, `unittest.mock.AsyncMock` for subprocess/LLM mocking.

**Spec:** [`docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md`](../specs/2026-05-03-sp6-screen-perception-design.md)
**Charter:** [`docs/superpowers/specs/2026-04-20-v2-program-charter.md`](../specs/2026-04-20-v2-program-charter.md) (§2 SP6, §5.1 SP6 exit gate, §6 cut-list row #3)
**Worktree:** `claude/silly-goldwasser-aac011` (current)
**Build budget:** 3–4 days. Bounded fix window: ≤1 day past day 4. K2 fires at day 6+.

---

## File structure

### New files
- `services/screen_perception.py` — singleton service (~200 LOC).
- `tests/services/test_screen_perception.py` — unit tier (mocks subprocess + llm).
- `tests/services/test_screen_perception_live.py` — live tier, env-gated `CRUZ_LIVE_MAC_TESTS=1`.
- `tests/agents/test_cruz_screen_perception.py` — CRUZ integration tests.
- `docs/perf/sp6-exit-gate.md` — exit-gate manual checklist.
- `docs/perf/sp6-forge-improvement-test.md` — A/B test record for charter Gate 2.

### Modified files
- `services/mac_controller.py` — promote `_APP_NAME_RE` → `APP_NAME_RE`, `_escape_applescript_string` → `escape_applescript_string`, and `_run_osascript` → `run_osascript` (all three with backward-compat aliases) + add `timeout` parameter to `run_osascript`.
- `tests/services/test_mac_controller.py` — update import to public `escape_applescript_string`.
- `agents/cruz/cruz_agent.py` — add `screen_perception` tool, dispatch method, dispatch branch, active-app runtime-context injection (in both `process` and `stream_response`), stream-path tool events.
- `PROGRESS.md` — append SP6 sign-off block at the end.

### No changes
- No DB migration, no Alembic version.
- No new env vars (only an optional runtime flag `CRUZ_DISABLE_ACTIVE_APP=1` read by code, no schema).
- No new pip dependencies.

---

## Conventions used by this plan

- **Working directory:** the worktree root `/Users/drprockz/Projects/cruz-ai-system/.claude/worktrees/silly-goldwasser-aac011`. All file paths in commands are relative to that directory.
- **Activate venv before pytest:** `source venv/bin/activate` (existing project pattern).
- **Pytest filter syntax:** `pytest tests/path/test_file.py::test_name -v`.
- **TDD discipline:** every code change starts with a failing test. Run the test, watch it fail, write minimal code to pass, run again, commit.
- **Commit format** (from CLAUDE.md):
  ```
  feat(sp6): <scope> — <imperative summary>
  fix(sp6): ...
  test(sp6): ...
  refactor(mac_controller): ...   ← when touching mac_controller
  docs(sp6): ...
  ```
  Use scope `mac_controller` for changes inside that module; scope `sp6` for screen_perception code, CRUZ wiring, and SP6 docs.
- **No `--no-verify` ever.** If a pre-commit hook fails, fix the underlying issue and create a new commit. Do not amend.

---

## Chunk 1: Mac controller refactor + screen_perception scaffolding

This chunk does two things: (a) promotes the two private helpers in `mac_controller.py` to public names so SP6 can import them cleanly, and (b) creates the `services/screen_perception.py` skeleton with types and singleton, plus the bare test file.

**Why first:** the spec (§4) makes the rename a Day-1 prerequisite. Doing this before any new code keeps the diff small and keeps each commit atomic.

### Task 1.1: Promote `_escape_applescript_string` to public name

**Files:**
- Modify: `services/mac_controller.py:66-77` (function definition) and `services/mac_controller.py:129,144,145,175,176` (internal callers)
- Test: `tests/services/test_mac_controller.py:13` (import)

- [ ] **Step 1: Read current state**

```bash
grep -n "_escape_applescript_string" services/mac_controller.py
grep -n "_escape_applescript_string" tests/services/test_mac_controller.py
```

Expected: 6 hits in `services/mac_controller.py` (1 def + 5 calls), 2 hits in the test (1 import + 1 use in `test_escape_applescript_string`).

- [ ] **Step 2: Rename in `services/mac_controller.py`**

Edit the function definition:

```python
# Old:
def _escape_applescript_string(raw: str) -> str:

# New:
def escape_applescript_string(raw: str) -> str:
```

Update all 5 internal callers in the same file (lines ~129, 144, 145, 175, 176). Then add a backward-compat alias just below the function definition:

```python
# Backward-compat alias — internal callers may keep using the leading-underscore form.
_escape_applescript_string = escape_applescript_string
```

- [ ] **Step 3: Update `tests/services/test_mac_controller.py` import**

Replace the import line:

```python
# Old:
from services.mac_controller import (
    MacControllerError,
    MacControllerService,
    _escape_applescript_string,
    get_mac_controller_service,
)

# New:
from services.mac_controller import (
    MacControllerError,
    MacControllerService,
    escape_applescript_string,
    get_mac_controller_service,
)
```

Then update the body of `test_escape_applescript_string` (the single use) to call `escape_applescript_string(raw)` instead of the underscore form.

- [ ] **Step 4: Run mac_controller tests, verify green**

```bash
source venv/bin/activate
pytest tests/services/test_mac_controller.py -v
```

Expected: all existing tests pass (unchanged behavior; only the symbol name moved). If any fail, revert and investigate.

- [ ] **Step 5: Commit**

```bash
git add services/mac_controller.py tests/services/test_mac_controller.py
git commit -m "refactor(mac_controller): promote _escape_applescript_string to public name

SP6 needs to import this from services/screen_perception.py. Importing
single-underscore names cross-module violates PEP 8 and hides the
contract. Backward-compat alias preserves existing internal callers.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §4"
```

### Task 1.2: Promote `_APP_NAME_RE` to public name

**Files:**
- Modify: `services/mac_controller.py:35` (definition) and `services/mac_controller.py:138` (single caller)

- [ ] **Step 1: Edit `services/mac_controller.py`**

Rename the regex constant:

```python
# Old:
_APP_NAME_RE = re.compile(r"^[A-Za-z0-9 ._-]+$")

# New:
APP_NAME_RE = re.compile(r"^[A-Za-z0-9 ._-]+$")
# Backward-compat alias.
_APP_NAME_RE = APP_NAME_RE
```

Update the one internal caller (in `open_app`):

```python
# Old:
if not _APP_NAME_RE.match(name):

# New:
if not APP_NAME_RE.match(name):
```

Also update the docstring on `open_app` (line ~135) that mentions `_APP_NAME_RE` — change to `APP_NAME_RE`.

- [ ] **Step 2: Run tests, verify green**

```bash
pytest tests/services/test_mac_controller.py -v
```

Expected: all existing tests pass.

- [ ] **Step 3: Commit**

```bash
git add services/mac_controller.py
git commit -m "refactor(mac_controller): promote _APP_NAME_RE to public name

Same rationale as the escape helper rename — SP6 imports this for
input validation when interpolating frontmost-app names into
AppleScript. Backward-compat alias preserved.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §4"
```

### Task 1.3: Promote `_run_osascript` to public + add `timeout` parameter

**Why:** SP6's `screen_perception.py` calls this helper cross-module. Like the two helpers in tasks 1.1/1.2, importing the underscore-prefixed name across modules violates PEP 8 and hides the contract. We promote it to `run_osascript` (with a backward-compat private alias) at the same time as adding the `timeout` parameter — both changes are small and naturally co-located. The new parameter is needed because `get_active_window` wants a tighter 1.0s budget per call instead of the 10s default existing callers get.

**Files:**
- Modify: `services/mac_controller.py:192-214` (`_run_osascript` method)

- [ ] **Step 1: Write a failing test for the new parameter**

Add to `tests/services/test_mac_controller.py` at the bottom of the file:

```python
@pytest.mark.asyncio
async def test_run_osascript_custom_timeout() -> None:
    """run_osascript respects a custom timeout, raising MacControllerError on overrun."""
    svc = MacControllerService()
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_proc.kill = lambda: None
    mock_proc.wait = AsyncMock(return_value=0)
    with patch(
        "services.mac_controller.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ):
        with pytest.raises(MacControllerError, match="timed out after 1.0s"):
            await svc.run_osascript("return 1", timeout=1.0)


@pytest.mark.asyncio
async def test_run_osascript_private_alias_still_works() -> None:
    """Backward-compat: existing callers using _run_osascript continue to work."""
    svc = MacControllerService()
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"ok\n", b""))
    mock_proc.returncode = 0
    with patch(
        "services.mac_controller.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ):
        result = await svc._run_osascript("return 1")
    assert result == "ok\n"
```

- [ ] **Step 2: Run test, verify it fails**

```bash
pytest tests/services/test_mac_controller.py::test_run_osascript_custom_timeout -v
```

Expected: FAIL with `TypeError: _run_osascript() got an unexpected keyword argument 'timeout'`.

- [ ] **Step 3: Promote to public name and add the parameter**

In `services/mac_controller.py`, rename the method and add the `timeout` parameter. Old:

```python
async def _run_osascript(self, script: str) -> str:
```

New:

```python
async def run_osascript(self, script: str, timeout: Optional[float] = None) -> str:
    """Run a single AppleScript snippet, return stdout (str). Raise on error.

    timeout: optional override for the wait_for budget. Defaults to
    _SUBPROCESS_TIMEOUT (10s) for backward compatibility.
    """
```

Add a backward-compat alias just after the method body (still inside the class), so internal callers and any external code that imports the underscore form keeps working:

```python
    # Backward-compat alias.
    _run_osascript = run_osascript
```

Replace the existing `wait_for` line. Old:

```python
stdout_b, stderr_b = await asyncio.wait_for(
    proc.communicate(), timeout=_SUBPROCESS_TIMEOUT
)
# ...
raise MacControllerError(
    f"osascript timed out after {_SUBPROCESS_TIMEOUT}s"
)
```

New:

```python
effective_timeout = timeout if timeout is not None else _SUBPROCESS_TIMEOUT
try:
    stdout_b, stderr_b = await asyncio.wait_for(
        proc.communicate(), timeout=effective_timeout
    )
except asyncio.TimeoutError:
    proc.kill()
    await proc.wait()
    raise MacControllerError(
        f"osascript timed out after {effective_timeout}s"
    )
```

Note: the existing code already has a try/except around `wait_for` — keep that structure, just parameterise the timeout value.

- [ ] **Step 4: Run new test, verify pass**

```bash
pytest tests/services/test_mac_controller.py::test_run_osascript_custom_timeout -v
```

Expected: PASS.

- [ ] **Step 5: Run full mac_controller tests, verify no regression**

```bash
pytest tests/services/test_mac_controller.py -v
```

Expected: all tests pass (existing tests don't pass `timeout` so they get the 10s default).

- [ ] **Step 6: Commit**

```bash
git add services/mac_controller.py tests/services/test_mac_controller.py
git commit -m "feat(mac_controller): promote _run_osascript and add optional timeout

SP6's get_active_window calls this cross-module and needs a 1s budget
per AppleScript read instead of the default 10s. Promotes to public
run_osascript with backward-compat _run_osascript alias. Existing
callers (still using the underscore form) unchanged.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §4"
```

### Task 1.4: Create `services/screen_perception.py` skeleton

**Files:**
- Create: `services/screen_perception.py`
- Test: `tests/services/test_screen_perception.py`

- [ ] **Step 1: Write failing skeleton tests**

Create `tests/services/test_screen_perception.py`:

```python
"""Unit tests for services.screen_perception — subprocess + LLM mocked."""

from __future__ import annotations

import pytest

from services.screen_perception import (
    ActiveWindow,
    ScreenAnalysis,
    ScreenPerceptionError,
    ScreenPerceptionService,
    WINDOW_TITLE_ALLOWLIST,
    get_screen_perception_service,
)


def test_singleton_returns_same_instance() -> None:
    a = get_screen_perception_service()
    b = get_screen_perception_service()
    assert a is b
    assert isinstance(a, ScreenPerceptionService)


def test_screen_perception_error_is_runtime_error() -> None:
    err = ScreenPerceptionError("boom")
    assert isinstance(err, RuntimeError)
    assert str(err) == "boom"


def test_window_title_allowlist_contains_dev_tools() -> None:
    """Sanity: the allowlist is the set the spec §4 defines, no extras."""
    expected = {
        "Code", "Cursor", "Xcode", "Terminal", "iTerm2",
        "PyCharm", "WebStorm", "Sublime Text", "Zed", "Ghostty",
    }
    assert WINDOW_TITLE_ALLOWLIST == expected


def test_active_window_to_context_line_app_only() -> None:
    aw = ActiveWindow(app="Mail", window_title=None, captured_at=0.0)
    assert aw.to_context_line() == "- Active app: Mail"


def test_active_window_to_context_line_with_title() -> None:
    aw = ActiveWindow(
        app="Code",
        window_title="orders.js — ama-solutions",
        captured_at=0.0,
    )
    assert aw.to_context_line() == "- Active app: Code — orders.js — ama-solutions"


def test_screen_analysis_dataclass_fields() -> None:
    """Confirm the dataclass shape the dispatch path depends on."""
    aw = ActiveWindow(app="Code", window_title="x", captured_at=1.0)
    sa = ScreenAnalysis(
        answer="hello",
        active_window=aw,
        image_bytes_len=42,
        duration_ms=100,
        tokens_used=200,
    )
    assert sa.answer == "hello"
    assert sa.active_window is aw
    assert sa.image_bytes_len == 42
    assert sa.duration_ms == 100
    assert sa.tokens_used == 200
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/services/test_screen_perception.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'services.screen_perception'`.

- [ ] **Step 3: Create the skeleton service file**

Create `services/screen_perception.py`:

```python
"""
ScreenPerceptionService — Layer 5 on-demand screen perception.

Two public methods exposed via one CRUZ tool (`screen_perception`):
  - get_active_window — fast (~50ms) AppleScript read of frontmost
    process name and (allowlisted) window title. Used to inject
    active-app context into CRUZ's runtime_context on every request.
  - analyze(question?) — captures a screenshot via mac_controller,
    calls Claude Vision (Sonnet 4.6), runs the answer through
    privacy_engine.sanitize, returns a ScreenAnalysis.

The dispatch path in agents/cruz/cruz_agent.py wraps `analyze` and
returns the sanitized answer string as the tool result.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("cruz.services.screen_perception")

# Module-level singleton
_instance: Optional["ScreenPerceptionService"] = None

# Apps where the window title is safe to capture (dev tools whose titles
# typically contain file paths or project names — useful context).
# Everything else: app name only. Extend with care; each addition is a
# privacy decision. Lookup is exact-case; macOS process names are
# exact-case in practice.
WINDOW_TITLE_ALLOWLIST = frozenset({
    "Code",          # VS Code (process name is "Code")
    "Cursor",
    "Xcode",
    "Terminal",
    "iTerm2",
    "PyCharm",
    "WebStorm",
    "Sublime Text",
    "Zed",
    "Ghostty",
})


class ScreenPerceptionError(RuntimeError):
    """Raised by analyze() when screenshot or Vision call fails.

    get_active_window() never raises — it returns a fallback
    ActiveWindow(app='unknown', window_title=None) on failure.
    """


@dataclass(frozen=True)
class ActiveWindow:
    """Frontmost-app metadata for runtime-context injection.

    app: always present; "unknown" on failure.
    window_title: only set when app is in WINDOW_TITLE_ALLOWLIST and
                  the OS returned a non-empty title.
    captured_at: time.monotonic() at capture time; for debugging.
    """
    app: str
    window_title: Optional[str]
    captured_at: float

    def to_context_line(self) -> str:
        """Format for inclusion in CRUZ's runtime_context system prompt."""
        if self.window_title:
            return f"- Active app: {self.app} — {self.window_title}"
        return f"- Active app: {self.app}"


@dataclass(frozen=True)
class ScreenAnalysis:
    """Result of analyze(). `answer` is already PII-sanitized."""
    answer: str
    active_window: ActiveWindow
    image_bytes_len: int     # for logging only; bytes never persist
    duration_ms: int
    tokens_used: int


def get_screen_perception_service() -> "ScreenPerceptionService":
    """Return the module-level ScreenPerceptionService singleton."""
    global _instance
    if _instance is None:
        _instance = ScreenPerceptionService()
    return _instance


class ScreenPerceptionService:
    """Two public async methods. See module docstring."""

    async def get_active_window(self) -> ActiveWindow:
        """Implemented in Chunk 2."""
        raise NotImplementedError("Chunk 2 deliverable")

    async def analyze(self, question: Optional[str] = None) -> ScreenAnalysis:
        """Implemented in Chunk 3."""
        raise NotImplementedError("Chunk 3 deliverable")
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/services/test_screen_perception.py -v
```

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add services/screen_perception.py tests/services/test_screen_perception.py
git commit -m "feat(sp6): add screen_perception service skeleton

Types (ActiveWindow, ScreenAnalysis, ScreenPerceptionError),
WINDOW_TITLE_ALLOWLIST constant, singleton accessor.
get_active_window and analyze stubbed; implemented in chunks 2-3.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §4"
```

---

## Chunk 2: get_active_window — frontmost-app + allowlisted title

This chunk implements the fast metadata read. It's pure mocked-subprocess testing — Linux-compatible.

### Task 2.1: Test scaffolding for `get_active_window`

**Files:**
- Modify: `tests/services/test_screen_perception.py` (add tests)

- [ ] **Step 1: Add the test fixtures and the first failing test**

Append to `tests/services/test_screen_perception.py`:

```python
import asyncio
from unittest.mock import AsyncMock, patch

from services.screen_perception import ScreenPerceptionService


@pytest.mark.asyncio
async def test_get_active_window_app_only_non_allowlisted() -> None:
    """Non-allowlisted app: only app name is captured, no window title."""
    svc = ScreenPerceptionService()
    # Patch the helper that runs osascript so step-1 returns "Mail".
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Mail"),
    ) as step1, patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value=""),
    ) as step2:
        aw = await svc.get_active_window()
    assert aw.app == "Mail"
    assert aw.window_title is None
    step1.assert_awaited_once()
    # Step-2 must NOT be called for non-allowlisted apps.
    step2.assert_not_called()
```

(We're naming the internal helpers `_run_osascript_for_step1` and `_run_osascript_for_step2` so each can be mocked independently — a pure refactor of the production code into two helpers.)

- [ ] **Step 2: Run test, verify it fails**

```bash
pytest tests/services/test_screen_perception.py::test_get_active_window_app_only_non_allowlisted -v
```

Expected: FAIL with `NotImplementedError: Chunk 2 deliverable` (or `AttributeError` on the patched helpers — whichever surfaces first).

### Task 2.2: Implement `get_active_window` step-1 (frontmost app)

**Files:**
- Modify: `services/screen_perception.py`

- [ ] **Step 1: Replace the stub with a real implementation**

Edit `services/screen_perception.py`. Replace the `get_active_window` stub with:

```python
import asyncio

from services.mac_controller import (
    APP_NAME_RE,
    MacControllerError,
    escape_applescript_string,
    get_mac_controller_service,
)

# Per-step osascript timeout. Total wall-clock budget enforced by
# asyncio.wait_for in the runtime-context injection path (2s).
_STEP_TIMEOUT_S = 1.0

# AppleScript snippets — kept module-level for testability.
_STEP1_SCRIPT = (
    'tell application "System Events"\n'
    '  set frontApp to name of first process whose frontmost is true\n'
    'end tell\n'
    'return frontApp'
)

def _step2_script(app_name: str) -> str:
    """Build step-2 script with the app name interpolated. Caller MUST
    have validated app_name against APP_NAME_RE before calling."""
    app_esc = escape_applescript_string(app_name)
    return (
        'tell application "System Events"\n'
        f'  tell process "{app_esc}"\n'
        '    try\n'
        '      set winName to name of front window\n'
        '    on error\n'
        '      set winName to ""\n'
        '    end try\n'
        '  end tell\n'
        'end tell\n'
        'return winName'
    )


# (inside ScreenPerceptionService)

    async def _run_osascript_for_step1(self) -> str:
        """Run step-1 (frontmost app) AppleScript. Internal — mocked by tests.

        Returns stripped stdout. Raises MacControllerError on failure.
        """
        mac = get_mac_controller_service()
        out = await mac.run_osascript(_STEP1_SCRIPT, timeout=_STEP_TIMEOUT_S)
        return out.strip()

    async def _run_osascript_for_step2(self, app_name: str) -> str:
        """Run step-2 (window title) AppleScript. Internal — mocked by tests."""
        mac = get_mac_controller_service()
        out = await mac.run_osascript(
            _step2_script(app_name), timeout=_STEP_TIMEOUT_S
        )
        return out.strip()

    async def get_active_window(self) -> ActiveWindow:
        captured_at = time.monotonic()

        # Step 1 — frontmost process name. Never raises out of this method.
        try:
            app_name = await self._run_osascript_for_step1()
        except Exception as exc:
            logger.warning("get_active_window step-1 failed: %s", exc)
            return ActiveWindow(app="unknown", window_title=None, captured_at=captured_at)

        if not app_name:
            return ActiveWindow(app="unknown", window_title=None, captured_at=captured_at)

        # Step 2 — only if allowlisted AND app name passes injection-defense regex.
        if app_name not in WINDOW_TITLE_ALLOWLIST:
            return ActiveWindow(app=app_name, window_title=None, captured_at=captured_at)

        if not APP_NAME_RE.match(app_name):
            logger.warning(
                "get_active_window: allowlisted app %r failed APP_NAME_RE; skipping step-2",
                app_name,
            )
            return ActiveWindow(app=app_name, window_title=None, captured_at=captured_at)

        try:
            title = await self._run_osascript_for_step2(app_name)
        except Exception as exc:
            logger.warning("get_active_window step-2 failed for %r: %s", app_name, exc)
            return ActiveWindow(app=app_name, window_title=None, captured_at=captured_at)

        return ActiveWindow(
            app=app_name,
            window_title=title or None,   # empty string → None
            captured_at=captured_at,
        )
```

Note: the imports at the top of the file (`asyncio`, `MacControllerError`, etc.) need to be added below the existing module imports. Keep the existing imports intact.

- [ ] **Step 2: Run the first test, verify pass**

```bash
pytest tests/services/test_screen_perception.py::test_get_active_window_app_only_non_allowlisted -v
```

Expected: PASS.

- [ ] **Step 3: Add and run the rest of the get_active_window tests**

Append all of these tests to `tests/services/test_screen_perception.py`:

```python
@pytest.mark.asyncio
async def test_get_active_window_with_title_allowlisted() -> None:
    """Allowlisted app: window title captured."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Code"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value="orders.js — ama-solutions"),
    ) as step2:
        aw = await svc.get_active_window()
    assert aw.app == "Code"
    assert aw.window_title == "orders.js — ama-solutions"
    step2.assert_awaited_once_with("Code")


@pytest.mark.asyncio
async def test_get_active_window_blocks_title_for_non_allowlisted() -> None:
    """Safari is NOT in the allowlist — step-2 must not be called."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Safari"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value="should-not-appear"),
    ) as step2:
        aw = await svc.get_active_window()
    assert aw.app == "Safari"
    assert aw.window_title is None
    step2.assert_not_called()


@pytest.mark.asyncio
async def test_get_active_window_allowlist_is_case_sensitive() -> None:
    """Lowercase 'code' (vs allowlisted 'Code') falls through to app-only."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="code"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value="should-not-appear"),
    ) as step2:
        aw = await svc.get_active_window()
    assert aw.app == "code"
    assert aw.window_title is None
    step2.assert_not_called()


@pytest.mark.asyncio
async def test_get_active_window_step1_failure_returns_unknown() -> None:
    """Step-1 raising → returns ActiveWindow(app='unknown', ...); never raises."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(side_effect=MacControllerError("osascript not found")),
    ):
        aw = await svc.get_active_window()
    assert aw.app == "unknown"
    assert aw.window_title is None


@pytest.mark.asyncio
async def test_get_active_window_step1_empty_returns_unknown() -> None:
    """Step-1 returning '' → ActiveWindow(app='unknown', ...)."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value=""),
    ):
        aw = await svc.get_active_window()
    assert aw.app == "unknown"
    assert aw.window_title is None


@pytest.mark.asyncio
async def test_get_active_window_step2_failure_returns_app_only() -> None:
    """Step-2 raising → app preserved, window_title=None."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Code"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(side_effect=MacControllerError("window not found")),
    ):
        aw = await svc.get_active_window()
    assert aw.app == "Code"
    assert aw.window_title is None


@pytest.mark.asyncio
async def test_get_active_window_step2_empty_string_becomes_none() -> None:
    """Step-2 returning '' (no front window) → window_title=None, not ''."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Terminal"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value=""),
    ):
        aw = await svc.get_active_window()
    assert aw.app == "Terminal"
    assert aw.window_title is None


@pytest.mark.asyncio
async def test_get_active_window_app_name_regex_rejects_injection() -> None:
    """If step-1 somehow returns a string that fails APP_NAME_RE,
    step-2 must not be called even if the name is in the allowlist."""
    svc = ScreenPerceptionService()
    # Construct a string that isn't in the allowlist by exact match
    # but would also fail the regex. Tests defense-in-depth: allowlist
    # is the primary block, regex is the secondary one for any future
    # allowlist entry that contains unsafe characters.
    # We monkeypatch the allowlist to include the malicious string so
    # we exercise the regex check specifically.
    import services.screen_perception as sp_mod
    original = sp_mod.WINDOW_TITLE_ALLOWLIST
    sp_mod.WINDOW_TITLE_ALLOWLIST = frozenset({'Bad"; rm -rf /'})
    try:
        with patch.object(
            svc, "_run_osascript_for_step1",
            new=AsyncMock(return_value='Bad"; rm -rf /'),
        ), patch.object(
            svc, "_run_osascript_for_step2",
            new=AsyncMock(return_value="should-not-appear"),
        ) as step2:
            aw = await svc.get_active_window()
        assert aw.app == 'Bad"; rm -rf /'
        assert aw.window_title is None
        step2.assert_not_called()
    finally:
        sp_mod.WINDOW_TITLE_ALLOWLIST = original
```

- [ ] **Step 4: Run all tests, verify pass**

```bash
pytest tests/services/test_screen_perception.py -v
```

Expected: 15 tests pass (6 from chunk 1 + 9 new).

- [ ] **Step 5: Commit**

```bash
git add services/screen_perception.py tests/services/test_screen_perception.py
git commit -m "feat(sp6): implement ScreenPerceptionService.get_active_window

Two-step AppleScript: frontmost process name (always), then window
title (only for allowlisted dev tools). Allowlist match is case-
sensitive. Defense-in-depth via APP_NAME_RE before any interpolation.
Never raises — returns ActiveWindow(app='unknown', ...) on failure.

Per-step timeout 1s; total budget enforced by caller via wait_for.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §4"
```

---

## Chunk 3: analyze() — screenshot + Vision + sanitize

This chunk implements the heavy on-demand path. Reuses `mac_controller.screenshot()` for the PNG, calls Anthropic via `services.llm.chat` (backend pinned), runs the answer through `privacy_engine.sanitize`.

### Task 3.1: Default Vision prompt + analyze happy-path

**Files:**
- Modify: `services/screen_perception.py`
- Modify: `tests/services/test_screen_perception.py`

- [ ] **Step 1: Add the failing happy-path test**

Append to `tests/services/test_screen_perception.py`:

```python
@pytest.mark.asyncio
async def test_analyze_happy_path() -> None:
    """analyze() returns a ScreenAnalysis with sanitized answer + window metadata."""
    from types import SimpleNamespace
    svc = ScreenPerceptionService()

    # Mock mac_controller.screenshot
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200

    # Mock active window
    aw_fixed = ActiveWindow(app="Code", window_title="hello.py", captured_at=1.0)

    # Mock LLM response — duck-typed shape from anthropic_chat.
    # Use a deliberately bland string that no current OR foreseeable
    # privacy_engine regex can match (no URLs, no credentials, no
    # accounts, no key prefixes, no digit runs). This decouples the
    # happy-path assertion from sanitize evolution; the dedicated
    # test_analyze_sanitizes_output below exercises sanitize behavior.
    bland_answer = "User is editing code."
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=bland_answer)],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )

    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw_fixed),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(return_value=fake_response),
    ) as mock_llm:
        mock_mac.return_value.screenshot = AsyncMock(return_value=fake_png)
        result = await svc.analyze()

    assert isinstance(result, ScreenAnalysis)
    assert result.answer == bland_answer
    assert result.active_window is aw_fixed
    assert result.image_bytes_len == len(fake_png)
    assert result.tokens_used == 120
    assert result.duration_ms >= 0

    # Verify llm.chat was called with anthropic backend + sonnet model
    call = mock_llm.await_args
    assert call.kwargs["backend"] == "anthropic"
    assert call.kwargs["model"] == "claude-sonnet-4-6"
```

- [ ] **Step 2: Run test, verify it fails**

```bash
pytest tests/services/test_screen_perception.py::test_analyze_happy_path -v
```

Expected: FAIL — `NotImplementedError: Chunk 3 deliverable` (the analyze stub is still there).

- [ ] **Step 3: Implement `analyze()` minimally to pass**

In `services/screen_perception.py`:

Add at the top of the file (with the other imports):

```python
import base64

from services.llm import chat as llm_chat
```

Then add this constant near the other module constants:

```python
_VISION_MODEL = "claude-sonnet-4-6"
_VISION_BACKEND = "anthropic"
_VISION_SYSTEM = (
    "You analyze a screenshot of the user's Mac desktop and answer "
    "concisely, in plain prose, no markdown."
)
_DEFAULT_QUESTION = (
    "Look at this screenshot of a Mac desktop and tell me concisely "
    "what the user is currently working on. Mention the active app, "
    "the file or document if visible, and any obvious task in progress. "
    "Two sentences max."
)
_VISION_MAX_TOKENS = 400
```

Replace the `analyze` stub:

```python
    async def analyze(self, question: Optional[str] = None) -> ScreenAnalysis:
        start = time.monotonic()

        # 1. Screenshot
        mac = get_mac_controller_service()
        try:
            png_bytes = await mac.screenshot()
        except MacControllerError as exc:
            raise ScreenPerceptionError(f"screenshot failed: {exc}") from exc

        # 2. Active window (best-effort; never raises)
        active = await self.get_active_window()

        # 3. Vision call (Anthropic backend pinned)
        prompt = question or _DEFAULT_QUESTION
        b64_png = base64.standard_b64encode(png_bytes).decode("ascii")
        try:
            response = await llm_chat(
                system=_VISION_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64_png,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
                max_tokens=_VISION_MAX_TOKENS,
                backend=_VISION_BACKEND,
                model=_VISION_MODEL,
            )
        except Exception as exc:
            raise ScreenPerceptionError(f"vision call failed: {exc}") from exc

        # 4. Extract text + sanitize
        raw_answer = _extract_text(response.content)
        try:
            from agents.cruz.persona.privacy_engine import sanitize
            answer = sanitize(raw_answer)
        except Exception as exc:
            logger.warning("sanitize failed (returning raw text): %s", exc)
            answer = raw_answer

        # 5. Build result
        usage = getattr(response, "usage", None)
        tokens = 0
        if usage is not None:
            tokens = (
                getattr(usage, "input_tokens", 0) or 0
            ) + (getattr(usage, "output_tokens", 0) or 0)

        return ScreenAnalysis(
            answer=answer,
            active_window=active,
            image_bytes_len=len(png_bytes),
            duration_ms=int((time.monotonic() - start) * 1000),
            tokens_used=tokens,
        )
```

Add this helper at module level (just below `get_screen_perception_service`):

```python
def _extract_text(content) -> str:
    """Extract plain text from an Anthropic content-block list. Returns
    '' if no text block present."""
    if not content:
        return ""
    for block in content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
    return ""
```

- [ ] **Step 4: Run the test, verify pass**

```bash
pytest tests/services/test_screen_perception.py::test_analyze_happy_path -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/screen_perception.py tests/services/test_screen_perception.py
git commit -m "feat(sp6): implement ScreenPerceptionService.analyze (happy path)

Captures screenshot via mac_controller, calls Claude Vision with
anthropic backend pinned and Sonnet 4.6, sanitizes the answer via
privacy_engine. Returns ScreenAnalysis with byte-length only; PNG
bytes never leave RAM after the Vision call.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §4"
```

### Task 3.2: analyze() error paths + content-block shape + sanitize coverage

**Files:**
- Modify: `tests/services/test_screen_perception.py`

- [ ] **Step 1: Add error-path tests**

Append to `tests/services/test_screen_perception.py`:

```python
@pytest.mark.asyncio
async def test_analyze_screenshot_failure_raises() -> None:
    """mac.screenshot raising MacControllerError → ScreenPerceptionError."""
    svc = ScreenPerceptionService()
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac:
        mock_mac.return_value.screenshot = AsyncMock(
            side_effect=MacControllerError("screencapture: error 1")
        )
        with pytest.raises(ScreenPerceptionError, match="screenshot failed"):
            await svc.analyze()


@pytest.mark.asyncio
async def test_analyze_vision_failure_raises() -> None:
    """llm.chat raising → ScreenPerceptionError('vision call failed: ...')."""
    from types import SimpleNamespace
    svc = ScreenPerceptionService()
    aw = ActiveWindow(app="X", window_title=None, captured_at=0.0)
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(side_effect=RuntimeError("anthropic: 503")),
    ):
        mock_mac.return_value.screenshot = AsyncMock(return_value=b"\x89PNG")
        with pytest.raises(ScreenPerceptionError, match="vision call failed"):
            await svc.analyze()


@pytest.mark.asyncio
async def test_analyze_default_question_uses_canonical_prompt() -> None:
    """When question=None, the canonical prompt template is used."""
    from types import SimpleNamespace
    svc = ScreenPerceptionService()
    aw = ActiveWindow(app="X", window_title=None, captured_at=0.0)
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(return_value=fake_response),
    ) as mock_llm:
        mock_mac.return_value.screenshot = AsyncMock(return_value=b"\x89PNG")
        await svc.analyze()
    msgs = mock_llm.await_args.kwargs["messages"]
    text_block = next(b for b in msgs[0]["content"] if b["type"] == "text")
    assert "currently working on" in text_block["text"].lower()


@pytest.mark.asyncio
async def test_analyze_custom_question_passed_through() -> None:
    """Custom question appears verbatim in the Vision prompt."""
    from types import SimpleNamespace
    svc = ScreenPerceptionService()
    aw = ActiveWindow(app="X", window_title=None, captured_at=0.0)
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(return_value=fake_response),
    ) as mock_llm:
        mock_mac.return_value.screenshot = AsyncMock(return_value=b"\x89PNG")
        await svc.analyze(question="What error is shown in the terminal?")
    msgs = mock_llm.await_args.kwargs["messages"]
    text_block = next(b for b in msgs[0]["content"] if b["type"] == "text")
    assert text_block["text"] == "What error is shown in the terminal?"


@pytest.mark.asyncio
async def test_analyze_image_content_block_shape() -> None:
    """Image content block: type=image, source.type=base64,
    media_type=image/png, data is STANDARD base64 (not URL-safe)."""
    import base64 as _b64
    from types import SimpleNamespace
    svc = ScreenPerceptionService()
    aw = ActiveWindow(app="X", window_title=None, captured_at=0.0)
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    # Use bytes that produce '+' or '/' in standard base64 (so URL-safe
    # variant would have '-' or '_' instead — assertable difference).
    png = bytes(range(256))
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(return_value=fake_response),
    ) as mock_llm:
        mock_mac.return_value.screenshot = AsyncMock(return_value=png)
        await svc.analyze()
    msgs = mock_llm.await_args.kwargs["messages"]
    image_block = msgs[0]["content"][0]
    assert image_block["type"] == "image"
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == "image/png"
    data = image_block["source"]["data"]
    # Standard base64 alphabet uses '+' and '/'. URL-safe uses '-' and '_'.
    assert "_" not in data and "-" not in data
    # Round-trip: standard_b64decode must equal the original bytes.
    assert _b64.standard_b64decode(data) == png


@pytest.mark.asyncio
async def test_analyze_sanitizes_output() -> None:
    """Vision answer containing a URL password is sanitized in result.answer."""
    from types import SimpleNamespace
    svc = ScreenPerceptionService()
    aw = ActiveWindow(app="X", window_title=None, captured_at=0.0)
    leaky = "Connection: postgres://user:topsecret@db/cruz"
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=leaky)],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(return_value=fake_response),
    ):
        mock_mac.return_value.screenshot = AsyncMock(return_value=b"\x89PNG")
        result = await svc.analyze()
    assert "topsecret" not in result.answer
    assert "[REDACTED_PW]" in result.answer


@pytest.mark.asyncio
async def test_analyze_empty_text_response_returns_empty_string() -> None:
    """If Vision returns no text block (refusal / weird), answer is ''
    and the call still succeeds (caller decides what to do)."""
    from types import SimpleNamespace
    svc = ScreenPerceptionService()
    aw = ActiveWindow(app="X", window_title=None, captured_at=0.0)
    fake_response = SimpleNamespace(
        content=[],   # no text blocks
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=0),
    )
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(return_value=fake_response),
    ):
        mock_mac.return_value.screenshot = AsyncMock(return_value=b"\x89PNG")
        result = await svc.analyze()
    assert result.answer == ""
```

- [ ] **Step 2: Run all screen_perception tests, verify pass**

```bash
pytest tests/services/test_screen_perception.py -v
```

Expected: 23 tests pass (15 from chunks 1-2 + 8 new).

- [ ] **Step 3: Commit**

```bash
git add tests/services/test_screen_perception.py
git commit -m "test(sp6): cover analyze error paths, prompt shape, sanitize, base64 variant

Confirms: screenshot failure → ScreenPerceptionError; vision failure →
ScreenPerceptionError; default vs custom question routing; image
content block uses standard base64 (Anthropic requirement); URL
passwords are redacted via privacy_engine; empty text response is
not an error.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §9"
```

---

## Chunk 4: CRUZ wiring — tool registration, dispatch, runtime context

This chunk wires the service into CRUZ. Six surgical edits to `agents/cruz/cruz_agent.py`, plus a new test file `tests/agents/test_cruz_screen_perception.py`.

### Task 4.1: Add the `screen_perception` tool to CRUZ_TOOLS

**Files:**
- Modify: `agents/cruz/cruz_agent.py` (`CRUZ_TOOLS` list, ~line 478 — append)
- Test: `tests/agents/test_cruz_screen_perception.py` (new file)

- [ ] **Step 1: Create the test file with the registration check**

Create `tests/agents/test_cruz_screen_perception.py`:

```python
"""Integration tests: CRUZ ↔ screen_perception tool + runtime-context injection."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agents.cruz.cruz_agent import CRUZ_TOOLS, CruzAgent
from services.screen_perception import (
    ActiveWindow,
    ScreenAnalysis,
    ScreenPerceptionError,
)


def test_screen_perception_tool_registered() -> None:
    """CRUZ_TOOLS must contain a `screen_perception` entry with an
    optional `question` string parameter."""
    matches = [t for t in CRUZ_TOOLS if t["name"] == "screen_perception"]
    assert len(matches) == 1, "screen_perception not registered in CRUZ_TOOLS"
    tool = matches[0]
    assert "question" in tool["input_schema"]["properties"]
    assert tool["input_schema"]["properties"]["question"]["type"] == "string"
    # question is optional — not in required list
    assert "question" not in tool["input_schema"].get("required", [])
```

- [ ] **Step 2: Run, verify it fails**

```bash
pytest tests/agents/test_cruz_screen_perception.py::test_screen_perception_tool_registered -v
```

Expected: FAIL — `screen_perception not registered in CRUZ_TOOLS`.

- [ ] **Step 3: Add the tool entry to CRUZ_TOOLS**

In `agents/cruz/cruz_agent.py`, append this entry to the `CRUZ_TOOLS` list (after `fetch_url`, before the closing `]`):

```python
    {
        "name": "screen_perception",
        "description": (
            "Look at what's currently on the user's Mac Mini screen and answer "
            "a question about it. Use when the user asks 'what am I working on?', "
            "'what's on my screen?', 'help me with this error' (referring to "
            "something visible), or any question that requires seeing the screen. "
            "Captures a fresh screenshot every call. Returns a sanitized text answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": (
                        "Optional specific question to ask about the screen. "
                        "Omit to get the canonical 'what is the user working on?' summary."
                    ),
                },
            },
            "required": [],
        },
    },
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/agents/test_cruz_screen_perception.py::test_screen_perception_tool_registered -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/cruz/cruz_agent.py tests/agents/test_cruz_screen_perception.py
git commit -m "feat(sp6): register screen_perception tool in CRUZ_TOOLS

Optional question parameter; description routes Claude to use this for
'what am I working on?' / 'what's on my screen?' / 'help me with this error'.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §6"
```

### Task 4.2: Implement `_dispatch_screen_perception_tool`

**Files:**
- Modify: `agents/cruz/cruz_agent.py` (add new method on `CruzAgent`, add dispatch branch in `_dispatch_tool`, add import at top)

- [ ] **Step 1: Add failing dispatch tests**

Append to `tests/agents/test_cruz_screen_perception.py`:

```python
@pytest.mark.asyncio
async def test_dispatch_screen_perception_success() -> None:
    """Successful analyze() → AgentOutput.success=True, result is the
    sanitized answer string (NOT a dict)."""
    cruz = CruzAgent()
    aw = ActiveWindow(app="Code", window_title="x.py", captured_at=0.0)
    sa = ScreenAnalysis(
        answer="Editing x.py.",
        active_window=aw,
        image_bytes_len=512,
        duration_ms=200,
        tokens_used=120,
    )
    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp:
        mock_get_sp.return_value.analyze = AsyncMock(return_value=sa)
        out = await cruz._dispatch_screen_perception_tool(
            tool_input={}, trace_id="t1",
        )
    assert out["success"] is True
    assert out["result"] == "Editing x.py."   # plain string, not a dict
    assert out["agent"] == cruz.name
    assert out["error"] is None
    assert out["requires_approval"] is False


@pytest.mark.asyncio
async def test_dispatch_screen_perception_with_question() -> None:
    """`question` from tool_input is forwarded to analyze()."""
    cruz = CruzAgent()
    aw = ActiveWindow(app="Code", window_title=None, captured_at=0.0)
    sa = ScreenAnalysis(
        answer="A connection error.", active_window=aw,
        image_bytes_len=1, duration_ms=1, tokens_used=1,
    )
    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp:
        mock_get_sp.return_value.analyze = AsyncMock(return_value=sa)
        await cruz._dispatch_screen_perception_tool(
            tool_input={"question": "what's the error?"}, trace_id="t1",
        )
    mock_get_sp.return_value.analyze.assert_awaited_once_with(
        question="what's the error?"
    )


@pytest.mark.asyncio
async def test_dispatch_screen_perception_failure_returns_error_output() -> None:
    """ScreenPerceptionError → AgentOutput.success=False with error text."""
    cruz = CruzAgent()
    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp:
        mock_get_sp.return_value.analyze = AsyncMock(
            side_effect=ScreenPerceptionError("vision call failed: 503")
        )
        out = await cruz._dispatch_screen_perception_tool(
            tool_input={}, trace_id="t1",
        )
    assert out["success"] is False
    assert out["result"] is None
    assert "vision call failed: 503" in out["error"]
    assert out["requires_approval"] is False


@pytest.mark.asyncio
async def test_dispatch_tool_routes_screen_perception_correctly() -> None:
    """_dispatch_tool routes name='screen_perception' to the new method."""
    cruz = CruzAgent()
    with patch.object(
        cruz, "_dispatch_screen_perception_tool", new=AsyncMock(
            return_value={"success": True, "result": "x", "agent": "CRUZ",
                          "duration_ms": 0, "tokens_used": 0, "error": None,
                          "requires_approval": False, "approval_prompt": None},
        ),
    ) as mock_method:
        await cruz._dispatch_tool(
            tool_name="screen_perception",
            tool_input={"question": "q"},
            trace_id="t",
            conversation_id="c",
        )
    mock_method.assert_awaited_once_with({"question": "q"}, "t")
```

- [ ] **Step 2: Run, verify all four fail**

```bash
pytest tests/agents/test_cruz_screen_perception.py -v -k dispatch
```

Expected: FAIL — `AttributeError: 'CruzAgent' object has no attribute '_dispatch_screen_perception_tool'`.

- [ ] **Step 3: Wire into `agents/cruz/cruz_agent.py`**

(a) Add import near the existing service imports (~line 50):

```python
from services.screen_perception import (
    ScreenPerceptionError,
    get_screen_perception_service,
)
```

(b) Add a dispatch branch inside `_dispatch_tool` (existing method, ~line 920) — place it just BEFORE the `if tool_name.startswith("mac_"):` line:

```python
        # Screen perception (services/screen_perception.py)
        if tool_name == "screen_perception":
            return await self._dispatch_screen_perception_tool(tool_input, trace_id)
```

(c) Add the new method on `CruzAgent` — place it right AFTER `_dispatch_mac_tool` (after line ~1011):

```python
    async def _dispatch_screen_perception_tool(
        self,
        tool_input: Dict[str, Any],
        trace_id: str,
    ) -> AgentOutput:
        """Route the screen_perception tool to ScreenPerceptionService.analyze.

        Returns AgentOutput with `result` as the sanitized answer string
        (NOT a dict) so that record_agent_activity's str(result)[:200]
        path persists only sanitized text — see spec §6 'Why a plain
        string, not a dict'.
        """
        start = time.monotonic()
        sp = get_screen_perception_service()
        try:
            analysis = await sp.analyze(question=tool_input.get("question"))
        except ScreenPerceptionError as exc:
            return AgentOutput(
                success=False, result=None, agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0, error=str(exc),
                requires_approval=False, approval_prompt=None,
            )

        return AgentOutput(
            success=True,
            result=analysis.answer,                # plain string, fully sanitized
            agent=self.name,
            duration_ms=analysis.duration_ms,
            tokens_used=analysis.tokens_used,
            error=None, requires_approval=False, approval_prompt=None,
        )
```

- [ ] **Step 4: Run dispatch tests, verify pass**

```bash
pytest tests/agents/test_cruz_screen_perception.py -v -k dispatch
```

Expected: 4 tests pass.

- [ ] **Step 5: Run all CRUZ tests to confirm no regressions**

```bash
pytest tests/agents/test_cruz_screen_perception.py tests/agents/test_cruz_agent.py tests/agents/test_cruz_conversation.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add agents/cruz/cruz_agent.py tests/agents/test_cruz_screen_perception.py
git commit -m "feat(sp6): dispatch screen_perception tool through CruzAgent

Adds _dispatch_screen_perception_tool method that returns result as a
plain sanitized string (not a dict). Per spec §6, this avoids
window_title/active_app being persisted unsanitized via
record_agent_activity's str(result)[:200] path. Branch added to
_dispatch_tool above the existing mac_* branch.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §6"
```

### Task 4.3: Inject active-app into runtime_context (process path)

**Files:**
- Modify: `agents/cruz/cruz_agent.py` (`process()` method, runtime_context block ~line 610)
- Test: `tests/agents/test_cruz_screen_perception.py`

- [ ] **Step 1: Add the failing runtime-context test**

Append to `tests/agents/test_cruz_screen_perception.py`:

```python
@pytest.mark.asyncio
async def test_process_runtime_context_includes_active_app() -> None:
    """process() injects an 'Active app:' line into the system prompt
    passed to llm.chat."""
    cruz = CruzAgent()
    aw = ActiveWindow(app="Code", window_title="x.py", captured_at=0.0)

    captured_system: dict = {}

    from types import SimpleNamespace

    async def fake_llm_chat(*, system, messages, tools, max_tokens, **_):
        captured_system["value"] = system
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    # Patch all the heavy collaborators so we exercise just the
    # runtime_context construction.
    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp, patch(
        "agents.cruz.cruz_agent.get_kb_service",
    ) as mock_kb, patch(
        "agents.cruz.cruz_agent.get_db_service",
    ) as mock_db, patch(
        "agents.cruz.cruz_agent.ConversationService",
    ) as mock_conv_cls, patch(
        "agents.cruz.cruz_agent.SemanticMemoryService",
    ) as mock_sem_cls, patch(
        "agents.cruz.cruz_agent.llm_chat",
        new=AsyncMock(side_effect=fake_llm_chat),
    ):
        mock_get_sp.return_value.get_active_window = AsyncMock(return_value=aw)
        mock_kb.return_value.build_agent_context = AsyncMock(return_value="")
        mock_kb.return_value.record_agent_activity = AsyncMock()
        mock_conv = mock_conv_cls.return_value
        mock_conv.get_or_create_conversation = AsyncMock()
        mock_conv.load_history = AsyncMock(return_value=[])
        mock_conv.save_exchange = AsyncMock()
        mock_sem = mock_sem_cls.return_value
        mock_sem.search_similar = AsyncMock(return_value=[])
        mock_sem.store = AsyncMock()

        await cruz.process({
            "task": "hi",
            "context": {},
            "trace_id": "t1",
            "conversation_id": "c1",
        })

    sys_prompt = captured_system["value"]
    assert "- Active app: Code — x.py" in sys_prompt


@pytest.mark.asyncio
async def test_process_runtime_context_omits_active_app_on_failure() -> None:
    """If get_active_window raises, the request still completes and the
    'Active app:' line is omitted from system prompt."""
    cruz = CruzAgent()

    captured_system: dict = {}

    from types import SimpleNamespace

    async def fake_llm_chat(*, system, messages, tools, max_tokens, **_):
        captured_system["value"] = system
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp, patch(
        "agents.cruz.cruz_agent.get_kb_service",
    ) as mock_kb, patch(
        "agents.cruz.cruz_agent.get_db_service",
    ), patch(
        "agents.cruz.cruz_agent.ConversationService",
    ) as mock_conv_cls, patch(
        "agents.cruz.cruz_agent.SemanticMemoryService",
    ) as mock_sem_cls, patch(
        "agents.cruz.cruz_agent.llm_chat",
        new=AsyncMock(side_effect=fake_llm_chat),
    ):
        mock_get_sp.return_value.get_active_window = AsyncMock(
            side_effect=RuntimeError("osascript missing")
        )
        mock_kb.return_value.build_agent_context = AsyncMock(return_value="")
        mock_kb.return_value.record_agent_activity = AsyncMock()
        mock_conv = mock_conv_cls.return_value
        mock_conv.get_or_create_conversation = AsyncMock()
        mock_conv.load_history = AsyncMock(return_value=[])
        mock_conv.save_exchange = AsyncMock()
        mock_sem = mock_sem_cls.return_value
        mock_sem.search_similar = AsyncMock(return_value=[])
        mock_sem.store = AsyncMock()

        out = await cruz.process({
            "task": "hi",
            "context": {},
            "trace_id": "t1",
            "conversation_id": "c1",
        })

    assert out["success"] is True
    assert "Active app:" not in captured_system["value"]


@pytest.mark.asyncio
async def test_process_runtime_context_omits_on_timeout() -> None:
    """If get_active_window hangs > 2s, wait_for cancels and the
    'Active app:' line is omitted. This is the load-bearing latency
    test for spec §5 (voice-mode ~3.6s SLO must not regress)."""
    cruz = CruzAgent()

    captured_system: dict = {}

    from types import SimpleNamespace

    async def fake_llm_chat(*, system, messages, tools, max_tokens, **_):
        captured_system["value"] = system
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    async def hang_forever() -> ActiveWindow:
        await asyncio.sleep(60)   # cancelled by wait_for(timeout=2.0)
        return ActiveWindow(app="never", window_title=None, captured_at=0.0)

    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp, patch(
        "agents.cruz.cruz_agent.get_kb_service",
    ) as mock_kb, patch(
        "agents.cruz.cruz_agent.get_db_service",
    ), patch(
        "agents.cruz.cruz_agent.ConversationService",
    ) as mock_conv_cls, patch(
        "agents.cruz.cruz_agent.SemanticMemoryService",
    ) as mock_sem_cls, patch(
        "agents.cruz.cruz_agent.llm_chat",
        new=AsyncMock(side_effect=fake_llm_chat),
    ), patch(
        # Speed up the test — patch the wait_for budget so we don't
        # actually wait 2 real seconds. Verifies the cancellation path
        # without slowing the suite.
        "agents.cruz.cruz_agent.asyncio.wait_for",
        new=AsyncMock(side_effect=asyncio.TimeoutError()),
    ):
        mock_get_sp.return_value.get_active_window = hang_forever
        mock_kb.return_value.build_agent_context = AsyncMock(return_value="")
        mock_kb.return_value.record_agent_activity = AsyncMock()
        mock_conv = mock_conv_cls.return_value
        mock_conv.get_or_create_conversation = AsyncMock()
        mock_conv.load_history = AsyncMock(return_value=[])
        mock_conv.save_exchange = AsyncMock()
        mock_sem = mock_sem_cls.return_value
        mock_sem.search_similar = AsyncMock(return_value=[])
        mock_sem.store = AsyncMock()

        out = await cruz.process({
            "task": "hi",
            "context": {},
            "trace_id": "t1",
            "conversation_id": "c1",
        })

    # Request still completes
    assert out["success"] is True
    # No active-app line in the system prompt
    assert "Active app:" not in captured_system["value"]


@pytest.mark.asyncio
async def test_process_runtime_context_omits_when_disabled_via_env(monkeypatch) -> None:
    """CRUZ_DISABLE_ACTIVE_APP=1 short-circuits the injection (used for
    Gate 2 control runs in the exit-gate test plan)."""
    monkeypatch.setenv("CRUZ_DISABLE_ACTIVE_APP", "1")

    cruz = CruzAgent()
    captured_system: dict = {}

    from types import SimpleNamespace

    async def fake_llm_chat(*, system, messages, tools, max_tokens, **_):
        captured_system["value"] = system
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    aw = ActiveWindow(app="Code", window_title="x.py", captured_at=0.0)

    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp, patch(
        "agents.cruz.cruz_agent.get_kb_service",
    ) as mock_kb, patch(
        "agents.cruz.cruz_agent.get_db_service",
    ), patch(
        "agents.cruz.cruz_agent.ConversationService",
    ) as mock_conv_cls, patch(
        "agents.cruz.cruz_agent.SemanticMemoryService",
    ) as mock_sem_cls, patch(
        "agents.cruz.cruz_agent.llm_chat",
        new=AsyncMock(side_effect=fake_llm_chat),
    ):
        get_aw = AsyncMock(return_value=aw)
        mock_get_sp.return_value.get_active_window = get_aw
        mock_kb.return_value.build_agent_context = AsyncMock(return_value="")
        mock_kb.return_value.record_agent_activity = AsyncMock()
        mock_conv = mock_conv_cls.return_value
        mock_conv.get_or_create_conversation = AsyncMock()
        mock_conv.load_history = AsyncMock(return_value=[])
        mock_conv.save_exchange = AsyncMock()
        mock_sem = mock_sem_cls.return_value
        mock_sem.search_similar = AsyncMock(return_value=[])
        mock_sem.store = AsyncMock()

        await cruz.process({
            "task": "hi",
            "context": {},
            "trace_id": "t1",
            "conversation_id": "c1",
        })

    # Disabled flag → service must not be called and prompt has no line
    get_aw.assert_not_called()
    assert "Active app:" not in captured_system["value"]
```

- [ ] **Step 2: Run the new tests, verify they fail**

```bash
pytest tests/agents/test_cruz_screen_perception.py -v -k runtime_context
```

Expected: FAIL — `assert "- Active app: Code — x.py" in sys_prompt` is False (the line isn't there yet).

- [ ] **Step 3a: Add `import asyncio` to `agents/cruz/cruz_agent.py`**

The runtime-context injection in Step 3b uses `asyncio.wait_for` and `asyncio.TimeoutError`. Confirm with:

```bash
grep -n '^import asyncio\|^from asyncio' agents/cruz/cruz_agent.py
```

If no hits, add `import asyncio` to the top-level imports. Place it just below `import logging` (alphabetical with the other stdlib imports). Run a quick sanity check:

```bash
python -c "import agents.cruz.cruz_agent"
```

Expected: no error. If `NameError` or `ImportError`, fix before proceeding.

- [ ] **Step 3b: Add the injection in `process()`**

In `agents/cruz/cruz_agent.py`, find the `runtime_context = (...)` block in `process()` (around line 610-618). Just AFTER that block (BEFORE `system_prompt = _SYSTEM_PROMPT + runtime_context`), add:

```python
            # SP6 — active-app context injection. Fail-soft, never blocks request.
            # Disabled via CRUZ_DISABLE_ACTIVE_APP=1 for exit-gate Gate 2 control runs.
            if os.environ.get("CRUZ_DISABLE_ACTIVE_APP") != "1":
                try:
                    sp = get_screen_perception_service()
                    active = await asyncio.wait_for(
                        sp.get_active_window(), timeout=2.0
                    )
                    runtime_context += f"\n{active.to_context_line()}"
                except asyncio.TimeoutError:
                    logger.warning(
                        "[%s] active-window injection timed out (2s)",
                        input["trace_id"],
                    )
                except Exception as exc:
                    logger.warning(
                        "[%s] active-window injection skipped: %s",
                        input["trace_id"], exc,
                    )
```

Note: `os` is already imported. `asyncio` was added in Step 3a above.

- [ ] **Step 4: Run the runtime-context tests, verify pass**

```bash
pytest tests/agents/test_cruz_screen_perception.py -v -k runtime_context
```

Expected: 4 tests pass (active app present, omitted on failure, omitted on timeout, omitted on env flag).

**Note on `test_persona_not_bypassed`:** spec §9 lists this as an integration test. The persona augmentation already has its own dedicated test coverage in `tests/agents/test_cruz_persona*.py` (existing); the Step 5 regression-suite run below validates that those tests stay green after SP6's wiring changes. We deliberately skip a duplicate test here — sign-off documents this deviation in Task 5.5.

- [ ] **Step 5: Run wider CRUZ test suite to confirm no regressions**

```bash
pytest tests/agents/test_cruz_agent.py tests/agents/test_cruz_screen_perception.py -v
```

Expected: all pass. The active-app injection is a fail-soft addition; existing tests that don't mock `get_screen_perception_service` will trigger a real (or attempted) AppleScript call which will raise on Linux CI and fall through the `except` clause — request still completes. If any existing test fails here, it's because it asserts an exact system-prompt string that didn't include "Active app:". In that case, look at the failing test, decide whether to update it (preferred — match the new injection) or assert via substring (acceptable).

- [ ] **Step 6: Commit**

```bash
git add agents/cruz/cruz_agent.py tests/agents/test_cruz_screen_perception.py
git commit -m "feat(sp6): inject active-app context into CRUZ process() runtime_context

Adds 'Active app: <name> — <title?>' line to runtime_context on every
process() call, with 2s wait_for timeout, fail-soft on errors, and
CRUZ_DISABLE_ACTIVE_APP=1 escape hatch for exit-gate control runs.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §5"
```

### Task 4.4: Inject active-app into runtime_context (stream_response path)

**Files:**
- Modify: `agents/cruz/cruz_agent.py` (`stream_response()` method, runtime_context block ~line 1069)
- Test: `tests/agents/test_cruz_screen_perception.py`

- [ ] **Step 1: Add the failing stream-path test**

Append to `tests/agents/test_cruz_screen_perception.py`:

```python
@pytest.mark.asyncio
async def test_stream_response_runtime_context_includes_active_app() -> None:
    """stream_response also injects active-app into runtime_context."""
    from types import SimpleNamespace
    from services.llm.stream_events import (
        TextDeltaEvent, DoneEvent as _LLMDone, UsageInfo,
    )

    cruz = CruzAgent()
    aw = ActiveWindow(app="Terminal", window_title=None, captured_at=0.0)

    captured_system: dict = {}

    async def fake_llm_chat_stream(*, system, messages, tools, max_tokens, **_):
        captured_system["value"] = system
        yield TextDeltaEvent(delta="ok")
        yield _LLMDone(stop_reason="end_turn",
                       usage=UsageInfo(input_tokens=1, output_tokens=1))

    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp, patch(
        "agents.cruz.cruz_agent.get_kb_service",
    ) as mock_kb, patch(
        "agents.cruz.cruz_agent.get_db_service",
    ), patch(
        "agents.cruz.cruz_agent.ConversationService",
    ) as mock_conv_cls, patch(
        "agents.cruz.cruz_agent.SemanticMemoryService",
    ) as mock_sem_cls, patch(
        "agents.cruz.cruz_agent.llm_chat_stream",
        new=fake_llm_chat_stream,
    ):
        mock_get_sp.return_value.get_active_window = AsyncMock(return_value=aw)
        mock_kb.return_value.build_agent_context = AsyncMock(return_value="")
        mock_kb.return_value.record_agent_activity = AsyncMock()
        mock_conv = mock_conv_cls.return_value
        mock_conv.get_or_create_conversation = AsyncMock()
        mock_conv.load_history = AsyncMock(return_value=[])
        mock_conv.save_exchange = AsyncMock()
        mock_sem = mock_sem_cls.return_value
        mock_sem.search_similar = AsyncMock(return_value=[])
        mock_sem.store = AsyncMock()

        # Drain the iterator
        async for _ in cruz.stream_response(
            task="hi", conversation_id="c1", trace_id="t1", device=None,
        ):
            pass

    assert "- Active app: Terminal" in captured_system["value"]
```

- [ ] **Step 2: Run, verify it fails**

```bash
pytest tests/agents/test_cruz_screen_perception.py::test_stream_response_runtime_context_includes_active_app -v
```

Expected: FAIL — assertion that 'Active app: Terminal' is in system prompt.

- [ ] **Step 3: Add the injection in `stream_response()`**

In `agents/cruz/cruz_agent.py`, find the `runtime_context = (...)` block in `stream_response()` (around line 1069-1077). Just AFTER that block (BEFORE `system_prompt = _SYSTEM_PROMPT + runtime_context`), add the same injection block as Task 4.3 Step 3 — but use the `trace_id` parameter directly (not `input["trace_id"]`) since `stream_response`'s signature names it `trace_id`:

```python
            # SP6 — active-app context injection. Fail-soft, never blocks request.
            if os.environ.get("CRUZ_DISABLE_ACTIVE_APP") != "1":
                try:
                    sp = get_screen_perception_service()
                    active = await asyncio.wait_for(
                        sp.get_active_window(), timeout=2.0
                    )
                    runtime_context += f"\n{active.to_context_line()}"
                except asyncio.TimeoutError:
                    logger.warning(
                        "[%s] active-window injection timed out (2s)",
                        trace_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "[%s] active-window injection skipped: %s",
                        trace_id, exc,
                    )
```

- [ ] **Step 4: Run the test, verify pass**

```bash
pytest tests/agents/test_cruz_screen_perception.py::test_stream_response_runtime_context_includes_active_app -v
```

Expected: PASS.

- [ ] **Step 5: Run all CRUZ tests, no regressions**

```bash
pytest tests/agents/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add agents/cruz/cruz_agent.py tests/agents/test_cruz_screen_perception.py
git commit -m "feat(sp6): inject active-app into CRUZ stream_response runtime_context

Mirrors process() pattern. Voice-mode and SSE-streaming requests now
also see active-app context. Same 2s timeout + fail-soft + env-flag
escape hatch.

DEFERRED.md note: process() and stream_response() runtime_context
construction is now duplicated 3x (KB context, persona, active-app);
rule-of-three threshold reached — add to follow-up refactor list.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §5"
```

### Task 4.5: Stream-path tool events for screen_perception

**Files:**
- Modify: `agents/cruz/cruz_agent.py` (`stream_response`, after web_search/fetch_url branch ~line 1200)
- Test: `tests/agents/test_cruz_screen_perception.py`

- [ ] **Step 1: Add the failing stream-event test**

Append to `tests/agents/test_cruz_screen_perception.py`:

```python
@pytest.mark.asyncio
async def test_stream_response_emits_tool_events_for_screen_perception() -> None:
    """When Claude calls screen_perception in streaming mode, the
    iterator emits ToolStart and ToolFinish events."""
    from types import SimpleNamespace
    from services.llm.stream_events import (
        TextDeltaEvent, ToolUseEvent, DoneEvent as _LLMDone, UsageInfo,
    )
    from agents.cruz.stream_events import ToolStart, ToolFinish

    cruz = CruzAgent()
    aw = ActiveWindow(app="Code", window_title=None, captured_at=0.0)
    sa = ScreenAnalysis(
        answer="Editing code.", active_window=aw,
        image_bytes_len=1, duration_ms=1, tokens_used=1,
    )

    # Two-pass stream: first call emits a tool_use; second call emits
    # plain text after the tool result is fed back.
    call_count = {"n": 0}

    async def fake_llm_chat_stream(*, system, messages, tools, max_tokens, **_):
        call_count["n"] += 1
        if call_count["n"] == 1:
            yield ToolUseEvent(
                tool_use_id="tu_1", name="screen_perception", input={},
            )
            yield _LLMDone(stop_reason="tool_use",
                           usage=UsageInfo(input_tokens=1, output_tokens=1))
        else:
            yield TextDeltaEvent(delta="Done.")
            yield _LLMDone(stop_reason="end_turn",
                           usage=UsageInfo(input_tokens=1, output_tokens=1))

    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp, patch(
        "agents.cruz.cruz_agent.get_kb_service",
    ) as mock_kb, patch(
        "agents.cruz.cruz_agent.get_db_service",
    ), patch(
        "agents.cruz.cruz_agent.ConversationService",
    ) as mock_conv_cls, patch(
        "agents.cruz.cruz_agent.SemanticMemoryService",
    ) as mock_sem_cls, patch(
        "agents.cruz.cruz_agent.llm_chat_stream",
        new=fake_llm_chat_stream,
    ):
        mock_get_sp.return_value.get_active_window = AsyncMock(return_value=aw)
        mock_get_sp.return_value.analyze = AsyncMock(return_value=sa)
        mock_kb.return_value.build_agent_context = AsyncMock(return_value="")
        mock_kb.return_value.record_agent_activity = AsyncMock()
        mock_conv = mock_conv_cls.return_value
        mock_conv.get_or_create_conversation = AsyncMock()
        mock_conv.load_history = AsyncMock(return_value=[])
        mock_conv.save_exchange = AsyncMock()
        mock_sem = mock_sem_cls.return_value
        mock_sem.search_similar = AsyncMock(return_value=[])
        mock_sem.store = AsyncMock()

        events = []
        async for ev in cruz.stream_response(
            task="what am i working on?",
            conversation_id="c1", trace_id="t1", device=None,
        ):
            events.append(ev)

    starts = [e for e in events if isinstance(e, ToolStart)]
    finishes = [e for e in events if isinstance(e, ToolFinish)]
    assert any(s.agent == "screen_perception" for s in starts)
    assert any(f.agent == "screen_perception" for f in finishes)
    sp_finish = next(f for f in finishes if f.agent == "screen_perception")
    assert "Editing code." in sp_finish.result_preview
```

- [ ] **Step 2: Run, verify it fails**

```bash
pytest tests/agents/test_cruz_screen_perception.py::test_stream_response_emits_tool_events_for_screen_perception -v
```

Expected: FAIL — likely "Unknown tool: 'screen_perception'" because the stream-path doesn't yet have a branch for it.

- [ ] **Step 3: Add the stream-path branch**

In `agents/cruz/cruz_agent.py`, find the section in `stream_response` that handles built-in tools (`record_pattern_observation`, then `web_search`/`fetch_url`, around line 1142–1202). After the `web_search`/`fetch_url` branch (after the `continue` at the end of that block), BEFORE the generic `yield ToolStart(... _TOOL_INTRO ...)` line, add:

```python
                    # ── Built-in tool: screen_perception ──────────────
                    if tu.name == "screen_perception":
                        yield ToolStart(
                            agent=tu.name,
                            summary="Looking at your screen.",
                        )
                        out = await self._dispatch_screen_perception_tool(
                            tu.input or {}, trace_id,
                        )
                        if out.get("success"):
                            answer = out.get("result", "") or ""
                            tool_result_blocks.append({
                                "type": "tool_result",
                                "tool_use_id": tu.tool_use_id,
                                "content": answer,
                            })
                            yield ToolFinish(
                                agent=tu.name,
                                result_preview=answer[:200],
                            )
                        else:
                            err = out.get("error") or "unknown error"
                            tool_result_blocks.append({
                                "type": "tool_result",
                                "tool_use_id": tu.tool_use_id,
                                "content": f"screen_perception failed: {err}",
                            })
                            yield ToolFinish(
                                agent=tu.name,
                                result_preview=f"failed: {err}",
                            )
                        continue
```

- [ ] **Step 4: Run the test, verify pass**

```bash
pytest tests/agents/test_cruz_screen_perception.py::test_stream_response_emits_tool_events_for_screen_perception -v
```

Expected: PASS.

- [ ] **Step 5: Run full agents/ test suite, no regressions**

```bash
pytest tests/agents/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add agents/cruz/cruz_agent.py tests/agents/test_cruz_screen_perception.py
git commit -m "feat(sp6): emit ToolStart/ToolFinish for screen_perception in stream path

Mirrors web_search/fetch_url pattern. Voice mode now surfaces a
'Looking at your screen.' tool-start event followed by a tool-finish
preview of the sanitized answer.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §6"
```

---

## Chunk 5: Live tier + exit-gate verification + sign-off

This chunk runs only on the Mac Mini. It validates the system end-to-end against real osascript, real screencapture, and real Claude Vision; then ticks the charter §5.1 SP6 exit-gate boxes.

### Task 5.1: Live-tier tests (env-gated)

**Files:**
- Create: `tests/services/test_screen_perception_live.py`

- [ ] **Step 1: Create the live test file**

Create `tests/services/test_screen_perception_live.py`:

```python
"""
Live tier — runs only on the Mac Mini with CRUZ_LIVE_MAC_TESTS=1.

These tests hit real osascript / screencapture / Claude Vision.
Skipped in CI. Run manually before SP6 sign-off.

⚠️  PRIVACY WARNING: these tests upload a screenshot of the operator's
ACTUAL Mac screen to Anthropic. Before running:
  • Close any browser tab / window with personal or sensitive data
    (banking, password manager, private chats, draft emails).
  • Lock or hide notification banners that may pop in mid-test.
  • Do NOT run on a screen showing client data unless you have
    consent.

Usage:
    CRUZ_LIVE_MAC_TESTS=1 ANTHROPIC_API_KEY=... \\
        pytest tests/services/test_screen_perception_live.py -v
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CRUZ_LIVE_MAC_TESTS") != "1",
    reason="live mac tests disabled (set CRUZ_LIVE_MAC_TESTS=1 to enable)",
)


@pytest.mark.asyncio
async def test_live_get_active_window_returns_real_app() -> None:
    """Real osascript: returns a non-empty app name."""
    from services.screen_perception import get_screen_perception_service
    sp = get_screen_perception_service()
    aw = await sp.get_active_window()
    assert aw.app
    assert aw.app != "unknown", "step-1 unexpectedly failed on the real Mac"
    print(f"\nactive app: {aw.app!r} title: {aw.window_title!r}")


@pytest.mark.asyncio
async def test_live_analyze_returns_text() -> None:
    """Real screenshot + real Claude Vision call: non-empty answer."""
    from services.screen_perception import get_screen_perception_service
    sp = get_screen_perception_service()
    result = await sp.analyze()
    assert result.answer, "Vision returned empty text"
    assert len(result.answer) <= 1000  # canonical prompt asks for 2 sentences
    print(f"\nVision answer: {result.answer}")
    print(f"active_window: {result.active_window}")
    print(f"tokens: {result.tokens_used}")


@pytest.mark.asyncio
async def test_live_analyze_with_custom_question() -> None:
    """Real Vision answers a custom question. Open TextEdit and type a
    known string before running this test (or eyeball the answer)."""
    from services.screen_perception import get_screen_perception_service
    sp = get_screen_perception_service()
    result = await sp.analyze(
        question="In one short sentence, name the application that is "
                "currently in focus on this Mac. Do not describe contents."
    )
    assert result.answer
    print(f"\nactive: {result.active_window.app}")
    print(f"vision said: {result.answer}")
```

- [ ] **Step 2: Verify it skips when the env flag is unset**

```bash
pytest tests/services/test_screen_perception_live.py -v
```

Expected: 3 tests skipped with reason "live mac tests disabled".

- [ ] **Step 3: Run live on the Mac Mini (operator step)**

⚠️ Before running, close any browser tab / window with personal or sensitive data — the screenshot is uploaded to Anthropic.

On the Mac Mini, with the worktree checked out:

```bash
source venv/bin/activate
CRUZ_LIVE_MAC_TESTS=1 \
  ANTHROPIC_API_KEY="$(cat ~/.config/cruz/anthropic-key)" \
  pytest tests/services/test_screen_perception_live.py -v -s
```

Expected: 3 tests pass; the `-s` flag prints the Vision answers and active-window data so you can eyeball them. If any test fails, stop and investigate before proceeding to the exit gate.

- [ ] **Step 4: Commit**

```bash
git add tests/services/test_screen_perception_live.py
git commit -m "test(sp6): add live-tier tests (env-gated CRUZ_LIVE_MAC_TESTS=1)

Three smoke tests against real osascript/screencapture/Claude Vision.
Skipped in CI. Run manually on the Mac Mini before SP6 sign-off.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §9"
```

### Task 5.2: Exit-gate checklist documents

**Files:**
- Create: `docs/perf/sp6-exit-gate.md`
- Create: `docs/perf/sp6-forge-improvement-test.md`

- [ ] **Step 1: Create `docs/perf/sp6-exit-gate.md`**

```markdown
# SP6 — Screen Perception Exit-Gate Verification

**Charter:** §5.1 SP6 row.
**Spec:** [`docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md`](../superpowers/specs/2026-05-03-sp6-screen-perception-design.md)
**Date completed:** _to fill in at sign-off_

## Gate 1 — "What am I working on?" 10/10 across 10 distinct app contexts

For each row, set up the app context, then run from any device:

```
curl -X POST http://<mac-mini-or-tunnel>/command \\
  -H 'Content-Type: application/json' \\
  -d '{"message": "what am I working on?", "stream": false}'
```

Tick the row if the answer is materially correct (mentions the right app + a true-ish description of what's visible). False details, hallucinations, or wrong app = fail.

| # | App context | Answer (truncated to 200 chars) | Correct? |
|---|---|---|---|
| 1 | VS Code editing a real file | | [ ] |
| 2 | Browser on a documentation page | | [ ] |
| 3 | Mail composing an email | | [ ] |
| 4 | Terminal running a process | | [ ] |
| 5 | PDF reader (Preview) | | [ ] |
| 6 | Design tool (Figma / Sketch) | | [ ] |
| 7 | Slack | | [ ] |
| 8 | Calendar app | | [ ] |
| 9 | Music app (Spotify / Music) | | [ ] |
| 10 | Blank desktop / Finder | | [ ] |

**Pass condition:** 10/10. Anything less = SP6 not ready to ship; investigate Vision prompt or screenshot quality.

## Gate 2 — Active-app context reaches FORGE on a test case

See `sp6-forge-improvement-test.md` for the full A/B procedure. Outcome:

- [ ] FORGE's output references the active file when active-app injection is enabled.
- [ ] FORGE's output asks for the file or guesses wrong when injection is disabled (control).
- [ ] Difference is materially better in the enabled run.

## Gate 3 — No regression on existing CRUZ tests

```
source venv/bin/activate
pytest tests/agents/test_cruz_agent.py tests/agents/test_cruz_conversation.py tests/agents/test_cruz_streaming.py -v
```

- [ ] All pre-existing CRUZ tests pass.

## Gate 4 — No P95 latency regression > 100ms on /command warm-cache

Run the existing load harness with the active-app injection in place. Compare to the SP1/SP2 baseline in `docs/perf/load_results.md`.

```
./scripts/load/run_scenarios.sh agent_mix --duration 5m
```

- [ ] P95 of `/command` warm-cache requests is within +100ms of the previous baseline.
- [ ] Recorded in `docs/perf/load_results.md` under an "SP6" row.

## Sign-off

Append to `PROGRESS.md` once all four gates are ticked:

```
## SP6 — Screen Perception (sign-off YYYY-MM-DD)

✅ Gate 1: 10/10 ad-hoc accuracy (see docs/perf/sp6-exit-gate.md)
✅ Gate 2: Active-app reaches FORGE; A/B improvement demonstrated
   (see docs/perf/sp6-forge-improvement-test.md)
✅ Gate 3: All pre-existing CRUZ tests green
✅ Gate 4: P95 /command latency within +<X>ms of baseline

Branch: claude/silly-goldwasser-aac011 → merged to main
Tests added: 23 unit + 11 CRUZ integration + 3 live (env-gated)
Files added: services/screen_perception.py + 4 test/doc files
Files modified: agents/cruz/cruz_agent.py + services/mac_controller.py (refactor)
```
```

- [ ] **Step 2: Create `docs/perf/sp6-forge-improvement-test.md`**

```markdown
# SP6 Gate 2 — FORGE Active-App A/B Test Record

**Charter §5.1 SP6 criterion:** "active-app context reaches at least one agent and improves its output on a test case"

## Setup

1. On the Mac Mini, open a project file in VS Code that has a known, isolated bug. Recommended: a single-file Python script with an obvious off-by-one (line range ≤30 lines).
2. Note the file path and the bug for the answer-key column.

## Procedure

### Run A — control (active-app injection disabled)

```
CRUZ_DISABLE_ACTIVE_APP=1 curl -X POST http://localhost:3000/command \\
  -H 'Content-Type: application/json' \\
  -d '{"message": "Fix the bug in the file I have open. Output a unified diff and nothing else.", "stream": false}'
```

Record FORGE's response.

### Run B — treatment (active-app injection enabled)

```
curl -X POST http://localhost:3000/command \\
  -H 'Content-Type: application/json' \\
  -d '{"message": "Fix the bug in the file I have open. Output a unified diff and nothing else.", "stream": false}'
```

Record FORGE's response.

## Comparison

| | Run A (control) | Run B (treatment) |
|---|---|---|
| Identified the right file? | | |
| Identified the bug? | | |
| Diff applies cleanly? | | |
| Asked clarifying questions? | | |

## Verdict

- [ ] Run B is materially better than Run A (e.g., correctly identifies the file in B but asks for it in A; or identifies the bug only in B).
- [ ] Recorded above.

If verdict is no, do NOT sign off SP6 — invoke charter §6 cut-list row #3 (defer SP6 entirely) or escalate via cut-trigger #2 in the spec (drop A/B and ship with weaker improvement claim — requires explicit Darshan approval).
```

- [ ] **Step 3: Commit the docs**

```bash
git add docs/perf/sp6-exit-gate.md docs/perf/sp6-forge-improvement-test.md
git commit -m "docs(sp6): add exit-gate checklist and FORGE A/B test record

Charter §5.1 SP6 has two criteria; this file is the canonical place
to tick them. forge-improvement-test.md is the structured A/B record
referenced by Gate 2.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §9"
```

### Task 5.3: Run the full unit-test suite to confirm nothing is broken

- [ ] **Step 1: Run all tests touched by SP6**

```bash
source venv/bin/activate
pytest tests/services/test_screen_perception.py \
       tests/services/test_mac_controller.py \
       tests/agents/test_cruz_screen_perception.py \
       tests/agents/test_cruz_agent.py \
       tests/agents/test_cruz_conversation.py \
       tests/agents/test_cruz_streaming.py -v
```

Expected: every test passes.

- [ ] **Step 2: Run the entire repo test suite**

```bash
pytest tests/ -v --ignore=tests/services/test_screen_perception_live.py \
       --ignore=tests/services/test_mac_controller_live.py \
       --ignore=tests/agents/test_calendar_live.py
```

Expected: every non-live test passes. Treat any new failure as a regression and fix BEFORE moving on.

### Task 5.4: Operator runs the live exit gate on the Mac Mini

This is operator work — a person on the Mac Mini physically. Each box must be ticked in `docs/perf/sp6-exit-gate.md`.

- [ ] **Step 1: Run live tier on Mac Mini**

```bash
CRUZ_LIVE_MAC_TESTS=1 ANTHROPIC_API_KEY=... \
  pytest tests/services/test_screen_perception_live.py -v -s
```

- [ ] **Step 2: Walk Gate 1's 10 contexts and tick each row**

Open the relevant app, run the curl command, paste the answer (truncated) into the row. If any row fails, decide: investigate (good) or invoke a cut (Section 11 of the spec).

- [ ] **Step 3: Run Gate 2's A/B and fill in the comparison table**

- [ ] **Step 4: Run Gate 3's regression suite once more on the Mac Mini**

```bash
pytest tests/agents/test_cruz_agent.py tests/agents/test_cruz_conversation.py tests/agents/test_cruz_streaming.py -v
```

- [ ] **Step 5: Run Gate 4's load harness and record P95 in `docs/perf/load_results.md`**

```bash
./scripts/load/run_scenarios.sh agent_mix --duration 5m
```

- [ ] **Step 6: Commit the filled-in exit-gate docs**

```bash
git add docs/perf/sp6-exit-gate.md docs/perf/sp6-forge-improvement-test.md docs/perf/load_results.md
git commit -m "docs(sp6): record exit-gate verification results

All four charter §5.1 SP6 criteria ticked.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md §9"
```

### Task 5.5: Append SP6 sign-off to PROGRESS.md

**Files:**
- Modify: `PROGRESS.md` (append)

- [ ] **Step 1: Append the sign-off block**

Append to `PROGRESS.md` (use today's date in YYYY-MM-DD form):

```markdown

---

## SP6 — Screen Perception (sign-off YYYY-MM-DD)

✅ Gate 1: 10/10 ad-hoc "what am I working on?" accuracy across 10 apps
   (see docs/perf/sp6-exit-gate.md)
✅ Gate 2: Active-app context reaches FORGE; A/B improvement demonstrated
   (see docs/perf/sp6-forge-improvement-test.md)
✅ Gate 3: All pre-existing CRUZ tests green; no regressions
✅ Gate 4: P95 /command latency within +<X>ms of baseline
   (see docs/perf/load_results.md)

Branch: claude/silly-goldwasser-aac011 → merged to main
Tests added: 23 unit + 11 CRUZ integration + 3 live (env-gated)
Files added:
  - services/screen_perception.py
  - tests/services/test_screen_perception.py
  - tests/services/test_screen_perception_live.py
  - tests/agents/test_cruz_screen_perception.py
  - docs/perf/sp6-exit-gate.md
  - docs/perf/sp6-forge-improvement-test.md
Files modified:
  - agents/cruz/cruz_agent.py (tool registration + dispatch + runtime context)
  - services/mac_controller.py (refactor: APP_NAME_RE / escape_applescript_string public + timeout param)
  - tests/services/test_mac_controller.py (import update + new timeout test)

Charter overrides: none
In-build cuts triggered: none
```

- [ ] **Step 2: Commit and tag**

```bash
git add PROGRESS.md
git commit -m "docs(sp6): SP6 sign-off — all four exit-gate criteria met

Per charter §5.1 SP6: 10/10 ad-hoc accuracy + FORGE A/B improvement +
no test regressions + no P95 latency regression > 100ms.

Spec: docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md"
```

(Optionally, after PR merge to main, tag the commit: `git tag sp6-shipped`. Not required.)

### Task 5.6: Open the PR

- [ ] **Step 1: Push branch and open PR**

```bash
git push -u origin claude/silly-goldwasser-aac011

gh pr create --title "feat(sp6): on-demand screen perception with active-app context injection" \
  --body "$(cat <<'EOF'
## Summary

- New `services/screen_perception.py` singleton with two methods:
  `get_active_window` (fast metadata for runtime context) and
  `analyze` (screenshot + Claude Vision + sanitize)
- One CRUZ tool `screen_perception` registered, dispatched directly
  to the service (no specialist agent — per charter §2 SP6: "no
  Context Tracker agent")
- Active-app context injected into CRUZ runtime_context on every
  request (both `process()` and `stream_response()`); allowlisted
  window-title capture for dev tools
- Vision answer sanitized at source via `privacy_engine.sanitize`
  before flowing into any persistence path; PNG bytes never leave
  RAM

## Charter compliance

- §2 SP6 scope: on-demand only ✓ no periodic capture, no Context
  Tracker agent ✓
- §5.1 SP6 exit gate: all four criteria documented in
  `docs/perf/sp6-exit-gate.md` and ticked
- §6 cut-list: row #3 ("SP6 entirely") not invoked; in-build cuts
  none
- §3 shared rules: no overrides

## Test plan

- [x] 23 unit tests in `tests/services/test_screen_perception.py`
- [x] 11 integration tests in `tests/agents/test_cruz_screen_perception.py`
- [x] 3 live-tier tests env-gated `CRUZ_LIVE_MAC_TESTS=1`
- [x] Refactor: `_APP_NAME_RE` → `APP_NAME_RE` and
  `_escape_applescript_string` → `escape_applescript_string` in
  `mac_controller.py` with backward-compat aliases
- [x] Exit-gate Gate 1: 10/10 "what am I working on?" accuracy
- [x] Exit-gate Gate 2: FORGE A/B improvement demonstrated
- [x] Exit-gate Gate 3: no regression on existing CRUZ tests
- [x] Exit-gate Gate 4: P95 /command latency regression < 100ms

Spec: `docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md`
Plan: `docs/superpowers/plans/2026-05-03-sp6-screen-perception.md`
EOF
)"
```

- [ ] **Step 2: Wait for CI green + Darshan review**

If CI flags anything red, fix on this branch and push — do not amend prior commits.

- [ ] **Step 3: After merge, archive related TODO entries**

`docs/superpowers/DEFERRED.md` — add SP6 follow-ups if any surfaced:
- Refactor `process()` / `stream_response()` runtime_context builders into a shared helper (rule of three now reached: KB context, persona, active-app)
- Consider extending `privacy_engine` patterns if Vision-output PII false-negatives surface in real use
- Sub-region screenshot capture, if a real caller appears

---

## Plan complete

After Task 5.6 step 3, SP6 is shipped. Next sub-project per charter §2 is SP7 (Multi-modal polish), which depends on SP1 (already deployed) — not on SP6. Charter §6 cut-list row #3 is fully consumed; subsequent cuts skip it.
