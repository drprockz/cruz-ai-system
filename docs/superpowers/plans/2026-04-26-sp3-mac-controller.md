# SP3 Mac Controller Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Layer 2 of CRUZ v2 — `services/mac_controller.py` (5 typed CRUZ tools backed by 4 AppleScript primitives) + `agents/calendar/calendar_agent.py` (Google Calendar primary write + Calendar.app AppleScript mirror; 3 tools).

**Architecture:** Mac Controller is a module-level singleton (matches `services/knowledge_base.py`). All AppleScript runs via `asyncio.create_subprocess_exec("osascript", "-e", script)` with a 10s timeout. Calendar agent is a `BaseAgent` subclass that delegates to `services/gcal.py` (Google API wrapper) for source-of-truth writes and to `mac_controller._calendar_create_local` for the AppleScript mirror. Self-only events auto-create; events with attendees require approval gate (per Charter Override #1). KB participation per charter Rule 3 — `KNOWLEDGE_RINGS = ["cruz_activities", "cruz_user_patterns"]`, `build_agent_context` at start, `record_agent_activity` at end.

**Tech Stack:** Python 3.11+, `asyncio.create_subprocess_exec`, AppleScript via `osascript`, `google-auth` + `google-auth-oauthlib` + `google-api-python-client`, pytest + `unittest.mock`, existing `BaseAgent` / `LLMRouter` / `KnowledgeBaseService`.

**Spec:** [`docs/superpowers/specs/2026-04-26-sp3-mac-controller-design.md`](../specs/2026-04-26-sp3-mac-controller-design.md)

**Charter:** [`docs/superpowers/specs/2026-04-20-v2-program-charter.md`](../specs/2026-04-20-v2-program-charter.md) — §3 shared rules, §5.1 SP3 exit gate, §6 cut-list rows 9–11.

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Create | `services/mac_controller.py` | Singleton: 4 AppleScript primitives + Calendar.app local helper + escape utility |
| Create | `tests/services/test_mac_controller.py` | Unit tests (subprocess mocked) — primitives, escaping, errors |
| Create | `tests/services/test_mac_controller_live.py` | Live tier (env-gated) — real `osascript` on Mac Mini |
| Create | `services/gcal.py` | Google Calendar OAuth wrapper — `create_event`, `list_events`, `delete_event`, token refresh |
| Create | `tests/services/test_gcal.py` | Unit tests for gcal (Google client mocked) |
| Create | `scripts/gcal_auth.py` | One-time OAuth flow runner — writes refresh token to `~/.config/cruz/gcal-token.json` |
| Create | `agents/calendar/__init__.py` | Package marker |
| Create | `agents/calendar/calendar_agent.py` | `CalendarAgent`: 3 tools, dual-write, approval gate, KB hooks |
| Create | `tests/agents/test_calendar_agent.py` | Unit tests for CalendarAgent |
| Create | `tests/agents/test_calendar_agent_live.py` | Live tier (env-gated) — real Google Calendar API + Calendar.app |
| Create | `docs/perf/sp3-exit-gate.md` | Manual exit-gate verification checklist |
| Modify | `agents/cruz/cruz_agent.py` | Add 8 tool entries (5 mac + 3 calendar) + 5 mac dispatch branches; register `calendar` in `_TOOL_AGENT_MAP` |
| Modify | `tests/agents/test_cruz_tools_registry.py` | Assert 8 new tools present in `CRUZ_TOOLS` |
| Modify | `requirements.txt` | Add `google-auth`, `google-auth-oauthlib`, `google-api-python-client` |
| Modify | `.env.example` | Add `GCAL_CLIENT_ID`, `GCAL_CLIENT_SECRET`, `GCAL_TOKEN_PATH`, `GCAL_DEFAULT_CALENDAR_ID` |
| Modify | `docs/superpowers/PROGRESS.md` | Append SP3 sign-off block at task 13 |

---

## Chunk 1: Mac Controller service (`services/mac_controller.py`)

Spec §3. Day 1 of build order.

### Task 1: Module skeleton + escape helper

**Files:**
- Create: `services/mac_controller.py`
- Create: `tests/services/test_mac_controller.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/services/test_mac_controller.py
"""Unit tests for services.mac_controller — subprocess mocked, no real osascript."""

from __future__ import annotations

import pytest

from services.mac_controller import (
    MacControllerError,
    MacControllerService,
    _escape_applescript_string,
    get_mac_controller_service,
)


# ── Escape helper ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("hello", "hello"),
        ('she said "hi"', 'she said \\"hi\\"'),
        (r"path\to\file", r"path\\to\\file"),
        ("line1\nline2", 'line1" & return & "line2'),
        ("tab\there", 'tab" & tab & "here'),
        ("emoji 🚀 ok", "emoji 🚀 ok"),
        ("", ""),
    ],
)
def test_escape_applescript_string(raw: str, expected: str) -> None:
    assert _escape_applescript_string(raw) == expected


def test_singleton_returns_same_instance() -> None:
    a = get_mac_controller_service()
    b = get_mac_controller_service()
    assert a is b
    assert isinstance(a, MacControllerService)


def test_mac_controller_error_is_runtime_error() -> None:
    err = MacControllerError("boom")
    assert isinstance(err, RuntimeError)
    assert str(err) == "boom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_mac_controller.py -v`
Expected: FAIL with `ImportError: cannot import name ... from 'services.mac_controller'`

- [ ] **Step 3: Write the module skeleton + escape helper**

```python
# services/mac_controller.py
"""
MacControllerService — Layer 2 macOS host control via AppleScript.

Four primitives exposed as five typed CRUZ tools:
  screenshot, clipboard_read, clipboard_write, open_app, notify.

Plus one internal helper used only by the Calendar agent for
the AppleScript mirror of Google Calendar events:
  _calendar_create_local

All AppleScript is executed via `osascript` subprocess with a 10s
timeout. Non-zero return code raises MacControllerError(stderr).
No silent failures.

Spec: docs/superpowers/specs/2026-04-26-sp3-mac-controller-design.md §3
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger("cruz.services.mac_controller")

# Module-level singleton
_instance: Optional["MacControllerService"] = None

# Subprocess timeout (seconds) for any osascript / screencapture call.
_SUBPROCESS_TIMEOUT = 10.0

# Allowed characters for app names — defends against AppleScript injection
# via the open_app primitive. Letters, digits, spaces, dots, hyphens, underscores.
_APP_NAME_RE = re.compile(r"^[A-Za-z0-9 ._-]+$")


class MacControllerError(RuntimeError):
    """Raised when an osascript / screencapture call returns non-zero."""


def get_mac_controller_service() -> "MacControllerService":
    """Return the module-level MacControllerService singleton."""
    global _instance
    if _instance is None:
        _instance = MacControllerService()
    return _instance


def _escape_applescript_string(raw: str) -> str:
    """Escape a Python string for safe inclusion inside an AppleScript double-quoted string.

    AppleScript string literals don't support \\n / \\t escapes — newlines and
    tabs are concatenated using `" & return & "` and `" & tab & "`.
    """
    if raw == "":
        return ""
    out = raw.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", '" & return & "').replace("\t", '" & tab & "')
    return out


class MacControllerService:
    """All public methods are async. All raise MacControllerError on failure."""

    # ── Public primitives ─────────────────────────────────────────────
    # (filled in by subsequent tasks)

    # ── Internal subprocess runner ────────────────────────────────────

    async def _run_osascript(self, script: str) -> str:
        """Run a single AppleScript snippet, return stdout (str). Raise on error."""
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=_SUBPROCESS_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise MacControllerError(
                f"osascript timed out after {_SUBPROCESS_TIMEOUT}s"
            )

        if proc.returncode != 0:
            err = stderr_b.decode("utf-8", errors="replace").strip()
            raise MacControllerError(err or "osascript returned non-zero")

        return stdout_b.decode("utf-8", errors="replace")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_mac_controller.py -v`
Expected: PASS — 9 tests (7 escape parametrized + singleton + error class).

- [ ] **Step 5: Commit**

```bash
git add services/mac_controller.py tests/services/test_mac_controller.py
git commit -m "feat(mac): mac_controller skeleton + AppleScript escape helper

Module-level singleton, _run_osascript helper with 10s timeout,
MacControllerError on non-zero exit. Escape helper handles \\, \",
newline (via & return &), tab (via & tab &). UTF-8 emoji passes through.

Spec: docs/superpowers/specs/2026-04-26-sp3-mac-controller-design.md §3"
```

---

### Task 2: `notify` primitive

**Files:**
- Modify: `services/mac_controller.py`
- Modify: `tests/services/test_mac_controller.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/test_mac_controller.py`:

```python
# ── notify ────────────────────────────────────────────────────────────

from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_notify_basic() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc.notify("Hi", "Body text")
    run.assert_awaited_once()
    script = run.await_args.args[0]
    assert 'display notification "Body text"' in script
    assert 'with title "Hi"' in script
    assert "sound name" not in script


@pytest.mark.asyncio
async def test_notify_with_sound() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc.notify("Hi", "Body", sound=True)
    script = run.await_args.args[0]
    assert 'sound name "Submarine"' in script


@pytest.mark.asyncio
async def test_notify_escapes_quotes_and_newlines() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc.notify('She said "hi"', "line1\nline2")
    script = run.await_args.args[0]
    assert '\\"hi\\"' in script
    assert '" & return & "' in script


@pytest.mark.asyncio
async def test_notify_propagates_error() -> None:
    svc = MacControllerService()
    with patch.object(
        svc, "_run_osascript",
        new=AsyncMock(side_effect=MacControllerError("permission denied")),
    ):
        with pytest.raises(MacControllerError, match="permission denied"):
            await svc.notify("x", "y")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_mac_controller.py -k notify -v`
Expected: FAIL with `AttributeError: 'MacControllerService' object has no attribute 'notify'`

- [ ] **Step 3: Implement `notify`**

Add inside `class MacControllerService` in `services/mac_controller.py`:

```python
    async def notify(self, title: str, body: str, sound: bool = False) -> None:
        """Fire a macOS Notification Center banner."""
        title_esc = _escape_applescript_string(title)
        body_esc = _escape_applescript_string(body)
        script = f'display notification "{body_esc}" with title "{title_esc}"'
        if sound:
            script += ' sound name "Submarine"'
        await self._run_osascript(script)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_mac_controller.py -k notify -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add services/mac_controller.py tests/services/test_mac_controller.py
git commit -m "feat(mac): notify primitive

osascript 'display notification' with optional Submarine sound.
Title and body escaped via _escape_applescript_string."
```

---

### Task 3: `clipboard_read` and `clipboard_write` primitives

**Files:**
- Modify: `services/mac_controller.py`
- Modify: `tests/services/test_mac_controller.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/test_mac_controller.py`:

```python
# ── clipboard ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clipboard_read_basic() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="hello\n")) as run:
        result = await svc.clipboard_read()
    assert result == "hello"
    script = run.await_args.args[0]
    assert "the clipboard as text" in script


@pytest.mark.asyncio
async def test_clipboard_read_empty() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="\n")):
        assert await svc.clipboard_read() == ""


@pytest.mark.asyncio
async def test_clipboard_write_basic() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc.clipboard_write("paste me")
    script = run.await_args.args[0]
    assert 'set the clipboard to "paste me"' in script


@pytest.mark.asyncio
async def test_clipboard_write_escapes_quotes() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc.clipboard_write('say "hi"')
    script = run.await_args.args[0]
    assert '\\"hi\\"' in script


@pytest.mark.asyncio
async def test_clipboard_write_empty_string_ok() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")):
        await svc.clipboard_write("")  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_mac_controller.py -k clipboard -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Implement clipboard primitives**

Add inside `class MacControllerService`:

```python
    async def clipboard_read(self) -> str:
        """Return the current clipboard contents as text. Empty clipboard → ''."""
        out = await self._run_osascript("the clipboard as text")
        return out.rstrip("\n")

    async def clipboard_write(self, text: str) -> None:
        """Replace the clipboard with the given text."""
        text_esc = _escape_applescript_string(text)
        await self._run_osascript(f'set the clipboard to "{text_esc}"')
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_mac_controller.py -k clipboard -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add services/mac_controller.py tests/services/test_mac_controller.py
git commit -m "feat(mac): clipboard_read and clipboard_write primitives"
```

---

### Task 4: `open_app` primitive

**Files:**
- Modify: `services/mac_controller.py`
- Modify: `tests/services/test_mac_controller.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
# ── open_app ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_app_basic() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc.open_app("TextEdit")
    script = run.await_args.args[0]
    assert 'tell application "TextEdit" to activate' == script


@pytest.mark.asyncio
async def test_open_app_allows_safe_chars() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")):
        await svc.open_app("Visual Studio Code")
        await svc.open_app("Plane.so")
        await svc.open_app("My_App-1")  # no raise


@pytest.mark.asyncio
async def test_open_app_rejects_injection() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")):
        with pytest.raises(MacControllerError, match="invalid app name"):
            await svc.open_app('TextEdit"; do shell script "rm -rf /')
        with pytest.raises(MacControllerError, match="invalid app name"):
            await svc.open_app("TextEdit\nMail")
        with pytest.raises(MacControllerError, match="invalid app name"):
            await svc.open_app("")


@pytest.mark.asyncio
async def test_open_app_propagates_osascript_error() -> None:
    svc = MacControllerService()
    with patch.object(
        svc, "_run_osascript",
        new=AsyncMock(side_effect=MacControllerError("application not found")),
    ):
        with pytest.raises(MacControllerError, match="application not found"):
            await svc.open_app("NonexistentApp")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_mac_controller.py -k open_app -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Implement `open_app`**

Add inside `class MacControllerService`:

```python
    async def open_app(self, name: str) -> None:
        """Activate (launch + foreground) a macOS app by name.

        App name is validated against _APP_NAME_RE to defend against
        AppleScript injection through this primitive.
        """
        if not _APP_NAME_RE.match(name):
            raise MacControllerError(f"invalid app name: {name!r}")
        await self._run_osascript(f'tell application "{name}" to activate')
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_mac_controller.py -k open_app -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add services/mac_controller.py tests/services/test_mac_controller.py
git commit -m "feat(mac): open_app primitive with injection-safe name validation"
```

---

### Task 5: `screenshot` primitive

**Files:**
- Modify: `services/mac_controller.py`
- Modify: `tests/services/test_mac_controller.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
# ── screenshot ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_screenshot_full_screen() -> None:
    svc = MacControllerService()
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(fake_png, b""))
    mock_proc.returncode = 0
    with patch(
        "services.mac_controller.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ) as create:
        result = await svc.screenshot()
    assert result == fake_png
    args = create.await_args.args
    assert args[0] == "screencapture"
    assert "-x" in args
    assert "-t" in args and "png" in args
    assert "-" in args  # stdout marker
    assert "-R" not in args  # no region


@pytest.mark.asyncio
async def test_screenshot_with_region() -> None:
    svc = MacControllerService()
    fake_png = b"\x89PNG"
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(fake_png, b""))
    mock_proc.returncode = 0
    with patch(
        "services.mac_controller.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ) as create:
        await svc.screenshot(region=(100, 200, 800, 600))
    args = create.await_args.args
    assert "-R" in args
    r_idx = args.index("-R")
    assert args[r_idx + 1] == "100,200,800,600"


@pytest.mark.asyncio
async def test_screenshot_propagates_error() -> None:
    svc = MacControllerService()
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b"screencapture: error"))
    mock_proc.returncode = 1
    with patch(
        "services.mac_controller.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ):
        with pytest.raises(MacControllerError, match="screencapture: error"):
            await svc.screenshot()


@pytest.mark.asyncio
async def test_screenshot_timeout() -> None:
    svc = MacControllerService()
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_proc.kill = lambda: None
    mock_proc.wait = AsyncMock(return_value=0)
    with patch(
        "services.mac_controller.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ):
        with pytest.raises(MacControllerError, match="timed out"):
            await svc.screenshot()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_mac_controller.py -k screenshot -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Implement `screenshot`**

Add at the top of `services/mac_controller.py` (after existing imports):

```python
from typing import Tuple
```

(If `Tuple` already imported via `typing`, skip.)

Add inside `class MacControllerService`:

```python
    async def screenshot(
        self,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> bytes:
        """Capture the screen and return raw PNG bytes.

        region: optional (x, y, width, height) tuple to capture a sub-rectangle.
                Coordinates are screen pixels; origin top-left.
        Uses `screencapture` (not osascript) because it natively writes PNG to stdout.
        """
        cmd = ["screencapture", "-x", "-t", "png"]
        if region is not None:
            x, y, w, h = region
            cmd += ["-R", f"{x},{y},{w},{h}"]
        cmd.append("-")  # write to stdout

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=_SUBPROCESS_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise MacControllerError(
                f"screencapture timed out after {_SUBPROCESS_TIMEOUT}s"
            )

        if proc.returncode != 0:
            err = stderr_b.decode("utf-8", errors="replace").strip()
            raise MacControllerError(err or "screencapture returned non-zero")

        return stdout_b
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_mac_controller.py -k screenshot -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add services/mac_controller.py tests/services/test_mac_controller.py
git commit -m "feat(mac): screenshot primitive via screencapture -> stdout PNG bytes"
```

---

### Task 6: `_calendar_create_local` internal helper

**Files:**
- Modify: `services/mac_controller.py`
- Modify: `tests/services/test_mac_controller.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
# ── _calendar_create_local ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calendar_create_local_basic() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc._calendar_create_local(
            title="Deep work",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T12:00:00",
            calendar_name="Calendar",
        )
    script = run.await_args.args[0]
    assert 'tell application "Calendar"' in script
    assert 'tell calendar "Calendar"' in script
    assert "make new event" in script
    assert "Deep work" in script
    # AppleScript date literal — _iso_to_applescript_date converts ISO to MM/DD/YYYY HH:MM:SS
    assert 'date "05/01/2026 10:00:00"' in script
    assert 'date "05/01/2026 12:00:00"' in script


@pytest.mark.asyncio
async def test_calendar_create_local_escapes_title() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc._calendar_create_local(
            title='Call "Acme Inc."',
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T11:00:00",
        )
    script = run.await_args.args[0]
    assert '\\"Acme Inc.\\"' in script


@pytest.mark.asyncio
async def test_calendar_create_local_propagates_error() -> None:
    svc = MacControllerService()
    with patch.object(
        svc, "_run_osascript",
        new=AsyncMock(side_effect=MacControllerError("calendar not found")),
    ):
        with pytest.raises(MacControllerError, match="calendar not found"):
            await svc._calendar_create_local(
                title="x",
                start_iso="2026-05-01T10:00:00",
                end_iso="2026-05-01T11:00:00",
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_mac_controller.py -k calendar_create_local -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Implement `_calendar_create_local`**

Add inside `class MacControllerService`:

```python
    async def _calendar_create_local(
        self,
        title: str,
        start_iso: str,
        end_iso: str,
        calendar_name: str = "Calendar",
    ) -> None:
        """Create a Calendar.app event in the named local calendar.

        Internal helper used by the Calendar agent for the AppleScript
        mirror of Google Calendar events. NOT a CRUZ tool.

        start_iso / end_iso must be ISO 8601 with seconds (e.g. 2026-05-01T10:00:00).
        Calendar.app requires AppleScript date literals — we build them with
        `date "<MM/DD/YYYY HH:MM:SS>"` form which AppleScript parses unambiguously.
        """
        title_esc = _escape_applescript_string(title)
        cal_esc = _escape_applescript_string(calendar_name)
        start_as = _iso_to_applescript_date(start_iso)
        end_as = _iso_to_applescript_date(end_iso)

        script = (
            f'tell application "Calendar"\n'
            f'  tell calendar "{cal_esc}"\n'
            f'    make new event with properties '
            f'{{summary:"{title_esc}", start date:{start_as}, end date:{end_as}}}\n'
            f'  end tell\n'
            f'end tell'
        )
        await self._run_osascript(script)
```

Add a module-level helper near `_escape_applescript_string`:

```python
def _iso_to_applescript_date(iso: str) -> str:
    """Convert ISO 8601 datetime to an AppleScript `date "..."` expression.

    AppleScript's `date` function reliably parses 'MM/DD/YYYY HH:MM:SS'.
    Strips timezone if present (Calendar.app uses local tz of the Mac).
    """
    from datetime import datetime
    # Tolerate trailing Z or +HH:MM
    cleaned = iso.replace("Z", "")
    if "+" in cleaned[10:]:
        cleaned = cleaned[: cleaned.rindex("+")]
    dt = datetime.fromisoformat(cleaned)
    formatted = dt.strftime("%m/%d/%Y %H:%M:%S")
    return f'date "{formatted}"'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_mac_controller.py -v`
Expected: PASS — full suite (~20 tests).

- [ ] **Step 5: Commit**

```bash
git add services/mac_controller.py tests/services/test_mac_controller.py
git commit -m "feat(mac): _calendar_create_local helper for Calendar.app mirror

Internal helper used by Calendar agent (not a CRUZ tool). ISO datetime
converted to AppleScript date literal via _iso_to_applescript_date."
```

---

## Chunk 2: CRUZ tool registration + live mac tests

Spec §3 (CRUZ tool registration), §5 (live tier). Day 2 of build order.

### Task 7: Register 5 mac tools in `CRUZ_TOOLS`

**Files:**
- Modify: `agents/cruz/cruz_agent.py`
- Modify: `tests/agents/test_cruz_tools_registry.py`

- [ ] **Step 1: Write the failing test**

Open `tests/agents/test_cruz_tools_registry.py` and add a new test (or extend an existing one) that asserts the 5 mac tools are present:

```python
# tests/agents/test_cruz_tools_registry.py
# Append at the end of the existing file.

def test_mac_controller_tools_present() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    names = {t["name"] for t in CRUZ_TOOLS}
    expected = {
        "mac_screenshot",
        "mac_clipboard_read",
        "mac_clipboard_write",
        "mac_open_app",
        "mac_notify",
    }
    assert expected <= names, f"missing mac tools: {expected - names}"


def test_mac_clipboard_write_schema_requires_text() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    tool = next(t for t in CRUZ_TOOLS if t["name"] == "mac_clipboard_write")
    schema = tool["input_schema"]
    assert "text" in schema["required"]
    assert schema["properties"]["text"]["type"] == "string"


def test_mac_notify_schema_has_optional_sound() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    tool = next(t for t in CRUZ_TOOLS if t["name"] == "mac_notify")
    schema = tool["input_schema"]
    assert {"title", "body"} <= set(schema["required"])
    assert "sound" not in schema["required"]
    assert schema["properties"]["sound"]["type"] == "boolean"


def test_mac_screenshot_schema_has_optional_region() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    tool = next(t for t in CRUZ_TOOLS if t["name"] == "mac_screenshot")
    schema = tool["input_schema"]
    # region is an optional 4-tuple
    assert "region" in schema["properties"]
    assert schema["properties"]["region"]["type"] == "array"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agents/test_cruz_tools_registry.py -k mac_ -v`
Expected: FAIL — tools not found.

- [ ] **Step 3: Add the 5 tool entries to `CRUZ_TOOLS`**

In `agents/cruz/cruz_agent.py`, locate the closing `]` of `CRUZ_TOOLS` (around line 307, after the existing `record_pattern_observation` tool). Add 5 new entries immediately before the closing `]`:

```python
    # ── Mac Controller (Layer 2 — services/mac_controller.py) ─────────
    {
        "name": "mac_screenshot",
        "description": (
            "Capture the screen on the Mac Mini and return PNG bytes. "
            "Optional region [x, y, width, height] in screen pixels. "
            "Use for 'what's on my screen' or grabbing visual context for vision tasks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 4,
                    "maxItems": 4,
                    "description": "Optional [x, y, width, height] sub-rectangle.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "mac_clipboard_read",
        "description": "Read the current macOS clipboard contents as text.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "mac_clipboard_write",
        "description": (
            "Replace the macOS clipboard with the given text. "
            "Use for 'copy this for me' or staging text the user will paste."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to place on the clipboard."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "mac_open_app",
        "description": (
            "Launch (or bring to front) a macOS app by name. "
            "Examples: 'TextEdit', 'Visual Studio Code', 'Mail'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Exact app name as it appears in /Applications."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "mac_notify",
        "description": (
            "Fire a macOS Notification Center banner. "
            "Use for reminders, soft alerts, or confirming background work."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body":  {"type": "string"},
                "sound": {"type": "boolean", "description": "Play Submarine sound (default false)."},
            },
            "required": ["title", "body"],
        },
    },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agents/test_cruz_tools_registry.py -k mac_ -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add agents/cruz/cruz_agent.py tests/agents/test_cruz_tools_registry.py
git commit -m "feat(cruz): register 5 mac_controller tools in CRUZ_TOOLS

mac_screenshot, mac_clipboard_read, mac_clipboard_write, mac_open_app,
mac_notify — typed JSON schemas for tool_use routing."
```

---

### Task 8: Dispatch mac tools in `_dispatch_tool`

The 5 mac tools are NOT agents — they don't go through `_TOOL_AGENT_MAP`. They dispatch directly to `MacControllerService` and return a synthetic `AgentOutput`.

**Files:**
- Modify: `agents/cruz/cruz_agent.py`
- Create: `tests/agents/test_cruz_mac_dispatch.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_cruz_mac_dispatch.py
"""Verify CruzAgent._dispatch_tool routes mac_* tools to MacControllerService."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.cruz.cruz_agent import CruzAgent


@pytest.mark.asyncio
async def test_dispatch_mac_screenshot_returns_png_meta() -> None:
    cruz = CruzAgent()
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    with patch(
        "agents.cruz.cruz_agent.get_mac_controller_service"
    ) as mock_get:
        mock_get.return_value.screenshot = AsyncMock(return_value=fake_png)
        out = await cruz._dispatch_tool(
            tool_name="mac_screenshot",
            tool_input={},
            trace_id="t1",
            conversation_id="c1",
        )
    assert out["success"] is True
    assert out["result"]["bytes_len"] == len(fake_png)
    assert out["result"]["mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_dispatch_mac_clipboard_read() -> None:
    cruz = CruzAgent()
    with patch("agents.cruz.cruz_agent.get_mac_controller_service") as mock_get:
        mock_get.return_value.clipboard_read = AsyncMock(return_value="hello")
        out = await cruz._dispatch_tool(
            tool_name="mac_clipboard_read",
            tool_input={},
            trace_id="t1",
            conversation_id="c1",
        )
    assert out["success"] is True
    assert out["result"] == "hello"


@pytest.mark.asyncio
async def test_dispatch_mac_clipboard_write() -> None:
    cruz = CruzAgent()
    with patch("agents.cruz.cruz_agent.get_mac_controller_service") as mock_get:
        mock_get.return_value.clipboard_write = AsyncMock(return_value=None)
        out = await cruz._dispatch_tool(
            tool_name="mac_clipboard_write",
            tool_input={"text": "paste me"},
            trace_id="t1",
            conversation_id="c1",
        )
    assert out["success"] is True
    mock_get.return_value.clipboard_write.assert_awaited_once_with("paste me")


@pytest.mark.asyncio
async def test_dispatch_mac_open_app() -> None:
    cruz = CruzAgent()
    with patch("agents.cruz.cruz_agent.get_mac_controller_service") as mock_get:
        mock_get.return_value.open_app = AsyncMock(return_value=None)
        out = await cruz._dispatch_tool(
            tool_name="mac_open_app",
            tool_input={"name": "TextEdit"},
            trace_id="t1",
            conversation_id="c1",
        )
    assert out["success"] is True
    mock_get.return_value.open_app.assert_awaited_once_with("TextEdit")


@pytest.mark.asyncio
async def test_dispatch_mac_notify() -> None:
    cruz = CruzAgent()
    with patch("agents.cruz.cruz_agent.get_mac_controller_service") as mock_get:
        mock_get.return_value.notify = AsyncMock(return_value=None)
        out = await cruz._dispatch_tool(
            tool_name="mac_notify",
            tool_input={"title": "Hi", "body": "Body", "sound": True},
            trace_id="t1",
            conversation_id="c1",
        )
    assert out["success"] is True
    mock_get.return_value.notify.assert_awaited_once_with("Hi", "Body", sound=True)


@pytest.mark.asyncio
async def test_dispatch_mac_tool_error_returns_failure() -> None:
    from services.mac_controller import MacControllerError
    cruz = CruzAgent()
    with patch("agents.cruz.cruz_agent.get_mac_controller_service") as mock_get:
        mock_get.return_value.notify = AsyncMock(
            side_effect=MacControllerError("permission denied")
        )
        out = await cruz._dispatch_tool(
            tool_name="mac_notify",
            tool_input={"title": "x", "body": "y"},
            trace_id="t1",
            conversation_id="c1",
        )
    assert out["success"] is False
    assert "permission denied" in out["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agents/test_cruz_mac_dispatch.py -v`
Expected: FAIL — `_dispatch_tool` doesn't recognize `mac_*`, returns "Unknown tool".

- [ ] **Step 3: Add mac tool dispatch to `_dispatch_tool`**

In `agents/cruz/cruz_agent.py`:

(a) Add the import at the top of the file (with the other `from services...` imports):

```python
from services.mac_controller import MacControllerError, get_mac_controller_service
```

(b) In `_dispatch_tool`, immediately after the function's docstring and before `agent_cls = _TOOL_AGENT_MAP.get(tool_name)`, insert:

```python
        # ── Mac Controller dispatch (services, not agents) ─────────────
        if tool_name.startswith("mac_"):
            return await self._dispatch_mac_tool(tool_name, tool_input, trace_id)
```

(c) Add the new method to `CruzAgent`:

```python
    async def _dispatch_mac_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        trace_id: str,
    ) -> AgentOutput:
        """Route mac_* tools directly to MacControllerService."""
        import time as _time
        start = _time.monotonic()
        mac = get_mac_controller_service()
        try:
            if tool_name == "mac_screenshot":
                region = tool_input.get("region")
                region_t = tuple(region) if region else None
                png = await mac.screenshot(region=region_t)
                result: Any = {
                    "bytes_len": len(png),
                    "mime_type": "image/png",
                    # Note: raw bytes are NOT included in result to keep
                    # tool_result text size manageable. Caller (e.g. SP6)
                    # invokes mac.screenshot() directly when bytes are needed.
                }
            elif tool_name == "mac_clipboard_read":
                result = await mac.clipboard_read()
            elif tool_name == "mac_clipboard_write":
                await mac.clipboard_write(tool_input["text"])
                result = {"written": True, "chars": len(tool_input["text"])}
            elif tool_name == "mac_open_app":
                await mac.open_app(tool_input["name"])
                result = {"opened": tool_input["name"]}
            elif tool_name == "mac_notify":
                await mac.notify(
                    tool_input["title"],
                    tool_input["body"],
                    sound=tool_input.get("sound", False),
                )
                result = {"notified": True}
            else:
                return AgentOutput(
                    success=False, result=None, agent=self.name,
                    duration_ms=int((_time.monotonic() - start) * 1000),
                    tokens_used=0,
                    error=f"Unknown mac tool: {tool_name!r}",
                    requires_approval=False, approval_prompt=None,
                )
        except MacControllerError as exc:
            return AgentOutput(
                success=False, result=None, agent=self.name,
                duration_ms=int((_time.monotonic() - start) * 1000),
                tokens_used=0,
                error=str(exc),
                requires_approval=False, approval_prompt=None,
            )

        return AgentOutput(
            success=True, result=result, agent=self.name,
            duration_ms=int((_time.monotonic() - start) * 1000),
            tokens_used=0,
            error=None,
            requires_approval=False, approval_prompt=None,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agents/test_cruz_mac_dispatch.py -v`
Expected: PASS — 6 tests.

Also run the full CRUZ test suite to confirm no regressions:

Run: `pytest tests/agents/test_cruz_agent.py tests/agents/test_cruz_stream.py tests/agents/test_cruz_tools_registry.py -v`
Expected: PASS — no regressions.

- [ ] **Step 5: Commit**

```bash
git add agents/cruz/cruz_agent.py tests/agents/test_cruz_mac_dispatch.py
git commit -m "feat(cruz): dispatch mac_* tools to MacControllerService

mac_* tools are services, not agents — bypass _TOOL_AGENT_MAP.
Screenshot returns metadata (bytes_len, mime_type) rather than raw
PNG to keep tool_result text size sane. Caller invokes
mac.screenshot() directly when bytes are needed."
```

---

### Task 9: Live-tier mac tests

**Files:**
- Create: `tests/services/test_mac_controller_live.py`

These tests run only on a real Mac when `CRUZ_LIVE_MAC_TESTS=1` is set. They are skipped in CI and on Linux dev machines.

- [ ] **Step 1: Write the file**

```python
# tests/services/test_mac_controller_live.py
"""Live-tier MacControllerService tests — real osascript / screencapture.

Run on the Mac Mini only:
    CRUZ_LIVE_MAC_TESTS=1 pytest tests/services/test_mac_controller_live.py -v

Skipped automatically on Linux / CI / when env var is unset.
"""

from __future__ import annotations

import asyncio
import io
import os
import platform
import sys

import pytest

from services.mac_controller import (
    MacControllerError,
    get_mac_controller_service,
)

LIVE = os.environ.get("CRUZ_LIVE_MAC_TESTS") == "1"
IS_MAC = platform.system() == "Darwin"

pytestmark = pytest.mark.skipif(
    not (LIVE and IS_MAC),
    reason="Live mac tests require CRUZ_LIVE_MAC_TESTS=1 on macOS",
)


@pytest.mark.asyncio
async def test_live_clipboard_round_trip() -> None:
    svc = get_mac_controller_service()
    sentinel = "CRUZ-test-clipboard-7f3a9c2e"
    original = ""
    try:
        original = await svc.clipboard_read()
    except MacControllerError:
        pass  # empty clipboard is fine

    await svc.clipboard_write(sentinel)
    read_back = await svc.clipboard_read()
    assert read_back == sentinel

    # Restore
    await svc.clipboard_write(original)


@pytest.mark.asyncio
async def test_live_notify_does_not_raise() -> None:
    svc = get_mac_controller_service()
    await svc.notify("CRUZ test", "If you see this, ignore — automated test.")


@pytest.mark.asyncio
async def test_live_open_app_textedit() -> None:
    svc = get_mac_controller_service()
    await svc.open_app("TextEdit")
    # Give it a moment to actually launch.
    await asyncio.sleep(1.0)
    # Confirm it's running via pgrep.
    proc = await asyncio.create_subprocess_exec(
        "pgrep", "-x", "TextEdit",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    assert proc.returncode == 0, "TextEdit should be running"

    # Cleanup — quit TextEdit politely.
    quit_proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", 'tell application "TextEdit" to quit',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await quit_proc.communicate()


@pytest.mark.asyncio
async def test_live_open_app_rejects_invalid_name() -> None:
    svc = get_mac_controller_service()
    with pytest.raises(MacControllerError, match="invalid app name"):
        await svc.open_app("TextEdit; do shell script")


@pytest.mark.asyncio
async def test_live_screenshot_returns_valid_png() -> None:
    svc = get_mac_controller_service()
    png = await svc.screenshot()
    assert png.startswith(b"\x89PNG\r\n\x1a\n"), "should be PNG magic"
    assert len(png) > 1000, "PNG should be more than 1 KB"

    # Optional richer parse if Pillow is installed.
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.size[0] > 0 and img.size[1] > 0


@pytest.mark.asyncio
async def test_live_screenshot_with_region() -> None:
    svc = get_mac_controller_service()
    png = await svc.screenshot(region=(0, 0, 200, 200))
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_live_open_app_unknown_raises() -> None:
    svc = get_mac_controller_service()
    with pytest.raises(MacControllerError):
        await svc.open_app("CRUZ-nonexistent-app-zzz")
```

- [ ] **Step 2: Verify the suite is correctly skipped on the dev machine (if not Mac Mini)**

Run: `pytest tests/services/test_mac_controller_live.py -v`
Expected: All tests SKIPPED with reason `Live mac tests require CRUZ_LIVE_MAC_TESTS=1 on macOS` (unless you're on a Mac with the env set).

- [ ] **Step 3: Run the live tier on the Mac Mini**

(Operator step — not part of automated CI.)

On the Mac Mini:

```bash
CRUZ_LIVE_MAC_TESTS=1 pytest tests/services/test_mac_controller_live.py -v
```

Expected: PASS — 7 tests. You will see:
- A clipboard sentinel briefly replace your clipboard contents (then restored)
- A "CRUZ test" notification banner
- TextEdit launches and quits within ~1 second

If `test_live_open_app_unknown_raises` does NOT raise, the AppleScript may be silently activating Finder — re-test with a clearly-invalid name.

- [ ] **Step 4: Commit**

```bash
git add tests/services/test_mac_controller_live.py
git commit -m "test(mac): live tier for mac_controller (env-gated, Mac-only)

Skipped unless CRUZ_LIVE_MAC_TESTS=1 on Darwin. Round-trips clipboard
with sentinel + restore, fires notification, launches/quits TextEdit,
captures real screenshot. Run manually on Mac Mini."
```

---

## Chunk 3: Google Calendar service + OAuth bootstrap

Spec §4 (auth subsection). Day 3 of build order.

### Task 10: Add Google API dependencies + env vars

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Add deps to `requirements.txt`**

Locate the alphabetical position (after `google-` other entries if present, otherwise after `gemini-` or alphabetical order). Add:

```
google-api-python-client==2.140.0
google-auth==2.34.0
google-auth-oauthlib==1.2.1
```

- [ ] **Step 2: Install and verify**

```bash
pip install -r requirements.txt
python -c "from googleapiclient.discovery import build; from google.oauth2.credentials import Credentials; print('ok')"
```
Expected: prints `ok`.

- [ ] **Step 3: Add env vars to `.env.example`**

Append:

```bash
# Google Calendar (SP3)
GCAL_CLIENT_ID=
GCAL_CLIENT_SECRET=
GCAL_TOKEN_PATH=~/.config/cruz/gcal-token.json
GCAL_DEFAULT_CALENDAR_ID=primary
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .env.example
git commit -m "chore(deps): add google-api-python-client + auth libs for SP3 Calendar"
```

---

### Task 11: `services/gcal.py` — Google Calendar wrapper

**Files:**
- Create: `services/gcal.py`
- Create: `tests/services/test_gcal.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_gcal.py
"""Unit tests for services.gcal — Google client mocked."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.gcal import (
    GCalAuthError,
    GCalError,
    GCalService,
    get_gcal_service,
)


# ── Singleton ─────────────────────────────────────────────────────────


def test_singleton(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"refresh_token": "x", "client_id": "y", "client_secret": "z", '
        '"token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(token_path))
    a = get_gcal_service()
    b = get_gcal_service()
    assert a is b


# ── Auth ──────────────────────────────────────────────────────────────


def test_load_credentials_missing_token_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(tmp_path / "missing.json"))
    svc = GCalService()
    with pytest.raises(GCalAuthError, match="token file not found"):
        svc._load_credentials()


def test_load_credentials_malformed_token_raises(tmp_path, monkeypatch) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json {{")
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(bad))
    svc = GCalService()
    with pytest.raises(GCalAuthError):
        svc._load_credentials()


# ── create_event ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_event_self_only(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"refresh_token": "x", "client_id": "y", "client_secret": "z", '
        '"token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("GCAL_DEFAULT_CALENDAR_ID", "primary")

    svc = GCalService()
    fake_event = {
        "id": "abc123",
        "htmlLink": "https://calendar.google.com/...",
        "summary": "Deep work",
    }
    mock_service = MagicMock()
    mock_service.events.return_value.insert.return_value.execute.return_value = fake_event

    with patch.object(svc, "_build_service", return_value=mock_service):
        result = await svc.create_event(
            title="Deep work",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T12:00:00",
        )

    assert result["id"] == "abc123"
    body = mock_service.events.return_value.insert.call_args.kwargs["body"]
    assert body["summary"] == "Deep work"
    assert body["start"]["dateTime"] == "2026-05-01T10:00:00"
    assert body["end"]["dateTime"] == "2026-05-01T12:00:00"
    assert "attendees" not in body  # self-only


@pytest.mark.asyncio
async def test_create_event_with_attendees(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"refresh_token": "x", "client_id": "y", "client_secret": "z", '
        '"token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(token_path))
    svc = GCalService()
    mock_service = MagicMock()
    mock_service.events.return_value.insert.return_value.execute.return_value = {"id": "x"}
    with patch.object(svc, "_build_service", return_value=mock_service):
        await svc.create_event(
            title="Sync",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T11:00:00",
            attendees=["a@x.com", "b@y.com"],
            description="agenda",
            location="Zoom",
        )
    body = mock_service.events.return_value.insert.call_args.kwargs["body"]
    assert body["attendees"] == [{"email": "a@x.com"}, {"email": "b@y.com"}]
    assert body["description"] == "agenda"
    assert body["location"] == "Zoom"


@pytest.mark.asyncio
async def test_create_event_http_error_raises_gcal_error(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"refresh_token": "x", "client_id": "y", "client_secret": "z", '
        '"token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(token_path))
    svc = GCalService()
    from googleapiclient.errors import HttpError
    mock_service = MagicMock()
    err = HttpError(resp=MagicMock(status=500, reason="Server Error"), content=b"boom")
    mock_service.events.return_value.insert.return_value.execute.side_effect = err
    with patch.object(svc, "_build_service", return_value=mock_service):
        with pytest.raises(GCalError, match="500"):
            await svc.create_event(
                title="x",
                start_iso="2026-05-01T10:00:00",
                end_iso="2026-05-01T11:00:00",
            )


# ── list_events ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_events(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"refresh_token": "x", "client_id": "y", "client_secret": "z", '
        '"token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(token_path))
    svc = GCalService()
    mock_service = MagicMock()
    mock_service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {"id": "e1", "summary": "A", "start": {"dateTime": "2026-05-01T10:00:00"}},
            {"id": "e2", "summary": "B", "start": {"dateTime": "2026-05-01T14:00:00"}},
        ],
    }
    with patch.object(svc, "_build_service", return_value=mock_service):
        events = await svc.list_events(
            start_iso="2026-05-01T00:00:00",
            end_iso="2026-05-02T00:00:00",
        )
    assert len(events) == 2
    assert events[0]["id"] == "e1"
    kwargs = mock_service.events.return_value.list.call_args.kwargs
    assert kwargs["timeMin"] == "2026-05-01T00:00:00Z"
    assert kwargs["timeMax"] == "2026-05-02T00:00:00Z"
    assert kwargs["singleEvents"] is True
    assert kwargs["orderBy"] == "startTime"


# ── delete_event ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_event(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"refresh_token": "x", "client_id": "y", "client_secret": "z", '
        '"token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(token_path))
    svc = GCalService()
    mock_service = MagicMock()
    mock_service.events.return_value.delete.return_value.execute.return_value = ""
    with patch.object(svc, "_build_service", return_value=mock_service):
        await svc.delete_event("abc123")
    mock_service.events.return_value.delete.assert_called_once_with(
        calendarId="primary", eventId="abc123"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_gcal.py -v`
Expected: FAIL — `services.gcal` not found.

- [ ] **Step 3: Implement `services/gcal.py`**

```python
# services/gcal.py
"""
GCalService — Google Calendar API wrapper for the Calendar agent.

OAuth 2.0 with stored refresh token. Token lives at GCAL_TOKEN_PATH
(default ~/.config/cruz/gcal-token.json) and is provisioned by
scripts/gcal_auth.py once per machine.

Public surface used by agents/calendar/calendar_agent.py:
  - create_event(title, start_iso, end_iso, attendees=None, **kw) -> dict
  - list_events(start_iso, end_iso, calendar_id=None) -> list[dict]
  - delete_event(event_id, calendar_id=None) -> None  (used by test cleanup)

Spec: docs/superpowers/specs/2026-04-26-sp3-mac-controller-design.md §4
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cruz.services.gcal")

_DEFAULT_TOKEN_PATH = "~/.config/cruz/gcal-token.json"
_DEFAULT_CALENDAR_ID = "primary"
_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class GCalError(RuntimeError):
    """Raised on Google Calendar API failures."""


class GCalAuthError(GCalError):
    """Raised when the OAuth token is missing, malformed, or refresh fails."""


_instance: Optional["GCalService"] = None


def get_gcal_service() -> "GCalService":
    global _instance
    if _instance is None:
        _instance = GCalService()
    return _instance


class GCalService:
    """Async wrapper around the synchronous google-api-python-client.

    The Google client is sync — we offload calls to a thread via asyncio.to_thread
    so we don't block the event loop.
    """

    def __init__(self) -> None:
        self._token_path = Path(
            os.path.expanduser(
                os.environ.get("GCAL_TOKEN_PATH", _DEFAULT_TOKEN_PATH)
            )
        )
        self._default_calendar_id = os.environ.get(
            "GCAL_DEFAULT_CALENDAR_ID", _DEFAULT_CALENDAR_ID
        )

    # ── Auth ───────────────────────────────────────────────────────────

    def _load_credentials(self):
        """Load Credentials from GCAL_TOKEN_PATH. Raise GCalAuthError on failure."""
        from google.oauth2.credentials import Credentials

        if not self._token_path.exists():
            raise GCalAuthError(f"token file not found at {self._token_path}")
        try:
            data = json.loads(self._token_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise GCalAuthError(f"failed to read token file: {exc}") from exc

        try:
            creds = Credentials(
                token=data.get("token"),
                refresh_token=data["refresh_token"],
                token_uri=data["token_uri"],
                client_id=data["client_id"],
                client_secret=data["client_secret"],
                scopes=data.get("scopes", _SCOPES),
            )
        except KeyError as exc:
            raise GCalAuthError(f"token file missing key: {exc}") from exc

        # Refresh if needed.
        if not creds.valid:
            from google.auth.transport.requests import Request
            try:
                creds.refresh(Request())
            except Exception as exc:
                raise GCalAuthError(f"token refresh failed: {exc}") from exc
            # Persist refreshed token back to disk.
            data["token"] = creds.token
            self._token_path.write_text(json.dumps(data, indent=2))

        return creds

    def _build_service(self):
        """Build a Google Calendar service object. Cached per call (cheap)."""
        from googleapiclient.discovery import build
        creds = self._load_credentials()
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    # ── create_event ──────────────────────────────────────────────────

    async def create_event(
        self,
        title: str,
        start_iso: str,
        end_iso: str,
        attendees: Optional[List[str]] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        calendar_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert one event. Returns Google's event resource on success."""
        cal = calendar_id or self._default_calendar_id
        body: Dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
        }
        if attendees:
            body["attendees"] = [{"email": e} for e in attendees]
        if description:
            body["description"] = description
        if location:
            body["location"] = location

        return await asyncio.to_thread(self._sync_create_event, cal, body)

    def _sync_create_event(self, cal: str, body: Dict[str, Any]) -> Dict[str, Any]:
        from googleapiclient.errors import HttpError
        try:
            return self._build_service().events().insert(
                calendarId=cal, body=body, sendUpdates="all" if "attendees" in body else "none",
            ).execute()
        except HttpError as exc:
            raise GCalError(f"Google API error {exc.resp.status}: {exc}") from exc

    # ── list_events ───────────────────────────────────────────────────

    async def list_events(
        self,
        start_iso: str,
        end_iso: str,
        calendar_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List events in [start, end). Returns a flat list of event resources."""
        cal = calendar_id or self._default_calendar_id
        return await asyncio.to_thread(
            self._sync_list_events, cal, _ensure_z(start_iso), _ensure_z(end_iso)
        )

    def _sync_list_events(self, cal: str, time_min: str, time_max: str) -> List[Dict[str, Any]]:
        from googleapiclient.errors import HttpError
        try:
            response = self._build_service().events().list(
                calendarId=cal,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=2500,
            ).execute()
            return response.get("items", [])
        except HttpError as exc:
            raise GCalError(f"Google API error {exc.resp.status}: {exc}") from exc

    # ── delete_event (test cleanup only) ──────────────────────────────

    async def delete_event(
        self,
        event_id: str,
        calendar_id: Optional[str] = None,
    ) -> None:
        cal = calendar_id or self._default_calendar_id
        await asyncio.to_thread(self._sync_delete_event, cal, event_id)

    def _sync_delete_event(self, cal: str, event_id: str) -> None:
        from googleapiclient.errors import HttpError
        try:
            self._build_service().events().delete(
                calendarId=cal, eventId=event_id
            ).execute()
        except HttpError as exc:
            raise GCalError(f"Google API error {exc.resp.status}: {exc}") from exc


def _ensure_z(iso: str) -> str:
    """Append 'Z' UTC marker if the ISO string has no offset."""
    if iso.endswith("Z") or "+" in iso[10:] or "-" in iso[10:]:
        return iso
    return iso + "Z"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_gcal.py -v`
Expected: PASS — 7 tests.

- [ ] **Step 5: Commit**

```bash
git add services/gcal.py tests/services/test_gcal.py
git commit -m "feat(gcal): Google Calendar OAuth wrapper

create_event / list_events / delete_event with token refresh.
Sync Google client offloaded to asyncio.to_thread. Token at
GCAL_TOKEN_PATH (default ~/.config/cruz/gcal-token.json),
provisioned by scripts/gcal_auth.py."
```

---

### Task 12: `scripts/gcal_auth.py` — one-time OAuth bootstrap

**Files:**
- Create: `scripts/gcal_auth.py`

This script runs once on the Mac Mini to provision the refresh token. It is NOT covered by automated tests (interactive browser flow).

- [ ] **Step 1: Write the script**

```python
# scripts/gcal_auth.py
"""
One-time Google Calendar OAuth bootstrap.

Run on the Mac Mini:
    python scripts/gcal_auth.py

Requires GCAL_CLIENT_ID + GCAL_CLIENT_SECRET in environment (or .env).

Opens a browser for consent, writes the refresh token to
GCAL_TOKEN_PATH (default ~/.config/cruz/gcal-token.json), then
prints the user's primary calendar to confirm.

Spec: docs/superpowers/specs/2026-04-26-sp3-mac-controller-design.md §4
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
DEFAULT_TOKEN_PATH = "~/.config/cruz/gcal-token.json"


def main() -> int:
    client_id = os.environ.get("GCAL_CLIENT_ID")
    client_secret = os.environ.get("GCAL_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("ERROR: GCAL_CLIENT_ID and GCAL_CLIENT_SECRET must be set in env.")
        print()
        print("Get them from https://console.cloud.google.com/apis/credentials")
        print("(create an OAuth 2.0 Client ID, type 'Desktop app').")
        return 1

    token_path = Path(
        os.path.expanduser(os.environ.get("GCAL_TOKEN_PATH", DEFAULT_TOKEN_PATH))
    )
    token_path.parent.mkdir(parents=True, exist_ok=True)

    if token_path.exists():
        resp = input(f"Token already exists at {token_path}. Overwrite? [y/N] ")
        if resp.strip().lower() != "y":
            print("Aborted. Existing token kept.")
            return 0

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    print("Opening browser for Google consent...")
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }
    token_path.write_text(json.dumps(payload, indent=2))
    token_path.chmod(0o600)
    print(f"\n✓ Refresh token written to {token_path} (mode 0600)")

    # Verify by listing the primary calendar.
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    cal = service.calendars().get(calendarId="primary").execute()
    print(f"✓ Authenticated as: {cal.get('summary')} ({cal.get('id')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke-test the script's argument-handling on a dev machine (not a Mac Mini run yet)**

```bash
unset GCAL_CLIENT_ID GCAL_CLIENT_SECRET
python scripts/gcal_auth.py
```
Expected: prints `ERROR: GCAL_CLIENT_ID and GCAL_CLIENT_SECRET must be set in env.` and exits 1.

```bash
echo $?  # should be 1
```

- [ ] **Step 3: (Mac Mini operator step) Run the real OAuth flow**

On the Mac Mini, with `GCAL_CLIENT_ID` + `GCAL_CLIENT_SECRET` set in `.env`:

```bash
source venv/bin/activate
export $(grep -v '^#' .env | xargs)
python scripts/gcal_auth.py
```
Expected:
- Browser opens, you grant consent.
- Script prints `✓ Refresh token written to /Users/<you>/.config/cruz/gcal-token.json (mode 0600)`.
- Script prints `✓ Authenticated as: Your Name (your.email@gmail.com)`.

- [ ] **Step 4: Commit**

```bash
git add scripts/gcal_auth.py
git commit -m "feat(gcal): one-time OAuth bootstrap script

scripts/gcal_auth.py runs the InstalledAppFlow once per machine,
writes refresh token to GCAL_TOKEN_PATH (mode 0600), confirms by
listing primary calendar."
```

---

## Chunk 4: Calendar agent

Spec §4 (full agent). Days 4–5 of build order.

### Task 13: Calendar package + agent skeleton with `find_free_slot`

**Files:**
- Create: `agents/calendar/__init__.py`
- Create: `agents/calendar/calendar_agent.py`
- Create: `tests/agents/test_calendar_agent.py`

`find_free_slot` is the simplest of the three operations (no Google write, no AppleScript, no LLM) — start there to lock the agent's shape.

- [ ] **Step 1: Create the package marker**

```python
# agents/calendar/__init__.py
"""Calendar agent — Google Calendar + Calendar.app dual-write."""
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/agents/test_calendar_agent.py
"""Unit tests for CalendarAgent."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.calendar.calendar_agent import CalendarAgent


def _input(task: str, **context):
    return {
        "task": task,
        "context": context,
        "trace_id": "trace-1",
        "conversation_id": "conv-1",
    }


# ── KNOWLEDGE_RINGS declared per Charter Rule 3 ───────────────────────


def test_knowledge_rings_declared() -> None:
    assert CalendarAgent.KNOWLEDGE_RINGS == [
        "cruz_activities",
        "cruz_user_patterns",
    ]


def test_agent_name() -> None:
    a = CalendarAgent()
    assert a.name == "CALENDAR"


# ── find_free_slot — pure algorithm ───────────────────────────────────


@pytest.mark.asyncio
async def test_find_free_slot_no_busy_returns_first_window() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.list_events = AsyncMock(return_value=[])

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        out = await agent.process(_input(
            task="find_free_slot",
            tool="calendar_find_free_slot",
            duration_minutes=60,
            earliest_iso="2026-05-01T09:00:00",
            latest_iso="2026-05-01T18:00:00",
        ))

    assert out["success"] is True
    assert out["result"]["start_iso"] == "2026-05-01T09:00:00"
    assert out["result"]["end_iso"] == "2026-05-01T10:00:00"


@pytest.mark.asyncio
async def test_find_free_slot_skips_busy_block() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.list_events = AsyncMock(return_value=[
        {"start": {"dateTime": "2026-05-01T09:00:00"},
         "end":   {"dateTime": "2026-05-01T10:30:00"}},
    ])

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        out = await agent.process(_input(
            task="find_free_slot",
            tool="calendar_find_free_slot",
            duration_minutes=60,
            earliest_iso="2026-05-01T09:00:00",
            latest_iso="2026-05-01T18:00:00",
        ))

    assert out["result"]["start_iso"] == "2026-05-01T10:30:00"
    assert out["result"]["end_iso"] == "2026-05-01T11:30:00"


@pytest.mark.asyncio
async def test_find_free_slot_no_gap_returns_failure() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    # One huge meeting fills the whole window.
    fake_gcal.list_events = AsyncMock(return_value=[
        {"start": {"dateTime": "2026-05-01T09:00:00"},
         "end":   {"dateTime": "2026-05-01T18:00:00"}},
    ])
    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        out = await agent.process(_input(
            task="find_free_slot",
            tool="calendar_find_free_slot",
            duration_minutes=60,
            earliest_iso="2026-05-01T09:00:00",
            latest_iso="2026-05-01T18:00:00",
        ))
    assert out["success"] is False
    assert "no free slot" in out["error"].lower()


@pytest.mark.asyncio
async def test_find_free_slot_kb_hooks_fire() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="## Your patterns\n- prefers mornings")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.list_events = AsyncMock(return_value=[])
    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        await agent.process(_input(
            task="find_free_slot for 60min tomorrow morning",
            tool="calendar_find_free_slot",
            duration_minutes=60,
            earliest_iso="2026-05-01T09:00:00",
            latest_iso="2026-05-01T18:00:00",
        ))
    fake_kb.build_agent_context.assert_awaited_once()
    fake_kb.record_agent_activity.assert_awaited_once()
    args = fake_kb.build_agent_context.await_args
    assert args.args[1] == ["cruz_activities", "cruz_user_patterns"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/agents/test_calendar_agent.py -v`
Expected: FAIL — `agents.calendar.calendar_agent` not found.

- [ ] **Step 4: Implement the agent skeleton + `find_free_slot`**

```python
# agents/calendar/calendar_agent.py
"""
CalendarAgent — Google Calendar (primary) + Calendar.app (mirror).

Three CRUZ-callable operations dispatched by the `tool` field in
context (set by CRUZ's _dispatch_tool when forwarding):

  - calendar_create_event   — dual-write: Google → AppleScript mirror
  - calendar_list_events    — read-only, Google only
  - calendar_find_free_slot — deterministic gap finder, no LLM

Per charter Rule 3: declares KNOWLEDGE_RINGS, calls build_agent_context
at the top of process() and record_agent_activity in finally.

Per charter Rule 4 + Override #1: self-only events auto-create;
events with attendees require context['send'] = True.

Spec: docs/superpowers/specs/2026-04-26-sp3-mac-controller-design.md §4
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.db import get_db_service
from services.gcal import GCalError, get_gcal_service
from services.knowledge_base import get_kb_service
from services.mac_controller import MacControllerError, get_mac_controller_service

logger = logging.getLogger("cruz.agents.CALENDAR")


class CalendarAgent(BaseAgent):
    """Single-shot dispatcher — no internal agentic loop."""

    KNOWLEDGE_RINGS: List[str] = ["cruz_activities", "cruz_user_patterns"]

    def __init__(self) -> None:
        super().__init__()
        self.name = "CALENDAR"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        output: Optional[AgentOutput] = None

        # ── KB context (fire-and-forget; never raises) ───────────────────
        kb = get_kb_service()
        try:
            await kb.build_agent_context(
                input["task"],
                self.KNOWLEDGE_RINGS,
                input["trace_id"],
                project_id=input["context"].get("project_id"),
            )
        except Exception as exc:
            logger.warning("[%s] build_agent_context failed: %s", input["trace_id"], exc)

        try:
            tool = input["context"].get("tool", "calendar_find_free_slot")
            if tool == "calendar_find_free_slot":
                output = await self._find_free_slot(input, start)
            elif tool == "calendar_list_events":
                output = await self._list_events(input, start)
            elif tool == "calendar_create_event":
                output = await self._create_event(input, start)
            else:
                output = AgentOutput(
                    success=False, result=None, agent=self.name,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    tokens_used=0,
                    error=f"Unknown calendar tool: {tool!r}",
                    requires_approval=False, approval_prompt=None,
                )
            return output

        except Exception as exc:
            output = self.handle_error(exc, input["trace_id"])
            return output

        finally:
            try:
                if output is not None:
                    await kb.record_agent_activity(
                        "calendar",
                        input["task"],
                        str(output.get("result", ""))[:200],
                        output["success"],
                        input["trace_id"],
                        project_id=input["context"].get("project_id"),
                        tokens_used=output.get("tokens_used"),
                    )
            except Exception:
                pass

    # ── find_free_slot ──────────────────────────────────────────────

    async def _find_free_slot(self, input: AgentInput, start: float) -> AgentOutput:
        ctx = input["context"]
        duration_minutes = int(ctx["duration_minutes"])
        earliest_iso = ctx["earliest_iso"]
        latest_iso = ctx["latest_iso"]

        gcal = get_gcal_service()
        try:
            events = await gcal.list_events(earliest_iso, latest_iso)
        except GCalError as exc:
            return _failure(self.name, start, f"Google list failed: {exc}")

        slot = _first_free_slot(
            earliest_iso, latest_iso, duration_minutes, events,
        )
        if slot is None:
            return _failure(
                self.name, start,
                f"No free slot of {duration_minutes}min in [{earliest_iso}, {latest_iso}].",
            )

        return AgentOutput(
            success=True,
            result={"start_iso": slot[0], "end_iso": slot[1]},
            agent=self.name,
            duration_ms=int((time.monotonic() - start) * 1000),
            tokens_used=0,
            error=None,
            requires_approval=False,
            approval_prompt=None,
        )

    # ── placeholders, filled by Tasks 14 + 15 ───────────────────────

    async def _list_events(self, input: AgentInput, start: float) -> AgentOutput:
        raise NotImplementedError("filled in Task 14")

    async def _create_event(self, input: AgentInput, start: float) -> AgentOutput:
        raise NotImplementedError("filled in Task 15")


# ─────────────────────────────────────────────────────────────────────
# Pure helpers (testable without mocks)
# ─────────────────────────────────────────────────────────────────────


def _failure(agent: str, start: float, msg: str) -> AgentOutput:
    return AgentOutput(
        success=False, result=None, agent=agent,
        duration_ms=int((time.monotonic() - start) * 1000),
        tokens_used=0, error=msg,
        requires_approval=False, approval_prompt=None,
    )


def _parse_iso(s: str) -> datetime:
    """Tolerate trailing Z or timezone offsets."""
    s = s.replace("Z", "")
    if "+" in s[10:]:
        s = s[: s.rindex("+")]
    return datetime.fromisoformat(s)


def _first_free_slot(
    earliest_iso: str,
    latest_iso: str,
    duration_minutes: int,
    busy_events: List[Dict[str, Any]],
) -> Optional[Tuple[str, str]]:
    """Return the first (start, end) gap of >= duration_minutes inside the window.

    Algorithm: build a sorted list of busy intervals, walk gaps, pick first fit.
    """
    window_start = _parse_iso(earliest_iso)
    window_end = _parse_iso(latest_iso)
    duration = timedelta(minutes=duration_minutes)

    busy: List[Tuple[datetime, datetime]] = []
    for ev in busy_events:
        s = ev.get("start", {}).get("dateTime")
        e = ev.get("end", {}).get("dateTime")
        if not s or not e:
            continue  # all-day events skipped
        bs = max(_parse_iso(s), window_start)
        be = min(_parse_iso(e), window_end)
        if be > bs:
            busy.append((bs, be))
    busy.sort()

    cursor = window_start
    for bs, be in busy:
        if bs - cursor >= duration:
            return (cursor.isoformat(timespec="seconds"),
                    (cursor + duration).isoformat(timespec="seconds"))
        cursor = max(cursor, be)

    if window_end - cursor >= duration:
        return (cursor.isoformat(timespec="seconds"),
                (cursor + duration).isoformat(timespec="seconds"))
    return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/agents/test_calendar_agent.py -v`
Expected: PASS — 6 tests (KNOWLEDGE_RINGS + name + 4 free-slot tests).

- [ ] **Step 6: Commit**

```bash
git add agents/calendar/__init__.py agents/calendar/calendar_agent.py tests/agents/test_calendar_agent.py
git commit -m "feat(calendar): CalendarAgent skeleton + find_free_slot

KNOWLEDGE_RINGS per Rule 3, dispatcher pattern by context['tool'].
find_free_slot is a pure deterministic gap-walker — no LLM, no
Google write, no AppleScript. _list_events and _create_event are
NotImplementedError placeholders for Tasks 14 + 15."
```

---

### Task 14: `_list_events` operation

**Files:**
- Modify: `agents/calendar/calendar_agent.py`
- Modify: `tests/agents/test_calendar_agent.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/agents/test_calendar_agent.py`:

```python
# ── list_events ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_events_returns_passthrough() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.list_events = AsyncMock(return_value=[
        {"id": "e1", "summary": "Standup"},
        {"id": "e2", "summary": "Client call"},
    ])
    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        out = await agent.process(_input(
            task="list events tomorrow",
            tool="calendar_list_events",
            start_iso="2026-05-01T00:00:00",
            end_iso="2026-05-02T00:00:00",
        ))
    assert out["success"] is True
    assert len(out["result"]) == 2
    assert out["result"][0]["id"] == "e1"
    assert out["requires_approval"] is False


@pytest.mark.asyncio
async def test_list_events_uses_calendar_id_override() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.list_events = AsyncMock(return_value=[])
    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        await agent.process(_input(
            task="list",
            tool="calendar_list_events",
            start_iso="2026-05-01T00:00:00",
            end_iso="2026-05-02T00:00:00",
            calendar_id="ama-shared@group.calendar.google.com",
        ))
    fake_gcal.list_events.assert_awaited_once_with(
        "2026-05-01T00:00:00",
        "2026-05-02T00:00:00",
        calendar_id="ama-shared@group.calendar.google.com",
    )


@pytest.mark.asyncio
async def test_list_events_propagates_gcal_error() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.list_events = AsyncMock(side_effect=GCalError("Google API error 401"))
    from services.gcal import GCalError as _GE
    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal):
        out = await agent.process(_input(
            task="list",
            tool="calendar_list_events",
            start_iso="2026-05-01T00:00:00",
            end_iso="2026-05-02T00:00:00",
        ))
    assert out["success"] is False
    assert "401" in out["error"]
```

Add the `from services.gcal import GCalError` import at the top of the test file (with the other `from agents...` imports).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agents/test_calendar_agent.py -k list_events -v`
Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement `_list_events`**

Replace the `_list_events` placeholder in `agents/calendar/calendar_agent.py`:

```python
    async def _list_events(self, input: AgentInput, start: float) -> AgentOutput:
        ctx = input["context"]
        start_iso = ctx["start_iso"]
        end_iso = ctx["end_iso"]
        calendar_id = ctx.get("calendar_id")

        gcal = get_gcal_service()
        try:
            kwargs = {"calendar_id": calendar_id} if calendar_id else {}
            events = await gcal.list_events(start_iso, end_iso, **kwargs)
        except GCalError as exc:
            return _failure(self.name, start, str(exc))

        return AgentOutput(
            success=True, result=events, agent=self.name,
            duration_ms=int((time.monotonic() - start) * 1000),
            tokens_used=0, error=None,
            requires_approval=False, approval_prompt=None,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agents/test_calendar_agent.py -v`
Expected: PASS — 9 tests.

- [ ] **Step 5: Commit**

```bash
git add agents/calendar/calendar_agent.py tests/agents/test_calendar_agent.py
git commit -m "feat(calendar): list_events operation (read-only passthrough)"
```

---

### Task 15: `_create_event` with dual-write + approval gate

**Files:**
- Modify: `agents/calendar/calendar_agent.py`
- Modify: `tests/agents/test_calendar_agent.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
# ── create_event — self-only auto-create ──────────────────────────────


@pytest.mark.asyncio
async def test_create_event_self_only_writes_google_and_mirrors() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_kb.observe_interaction = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.create_event = AsyncMock(return_value={
        "id": "ev1", "htmlLink": "https://...", "summary": "Deep work",
    })
    fake_mac = MagicMock()
    fake_mac._calendar_create_local = AsyncMock(return_value=None)

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal), \
         patch("agents.calendar.calendar_agent.get_mac_controller_service", return_value=fake_mac):
        out = await agent.process(_input(
            task="block 10am-12pm tomorrow for AMA",
            tool="calendar_create_event",
            title="Deep work",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T12:00:00",
        ))

    assert out["success"] is True
    assert out["requires_approval"] is False
    assert out["result"]["id"] == "ev1"
    fake_gcal.create_event.assert_awaited_once()
    fake_mac._calendar_create_local.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_event_self_only_observes_hour_pattern() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_kb.observe_interaction = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.create_event = AsyncMock(return_value={"id": "ev1"})
    fake_mac = MagicMock()
    fake_mac._calendar_create_local = AsyncMock()

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal), \
         patch("agents.calendar.calendar_agent.get_mac_controller_service", return_value=fake_mac):
        await agent.process(_input(
            task="block 10am-12pm",
            tool="calendar_create_event",
            title="x",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T12:00:00",
        ))

    fake_kb.observe_interaction.assert_awaited_once_with(
        "calendar", "preferred_block_hour", "10",
    )


@pytest.mark.asyncio
async def test_create_event_mirror_failure_is_non_fatal() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_kb.observe_interaction = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.create_event = AsyncMock(return_value={"id": "ev1"})
    fake_mac = MagicMock()
    fake_mac._calendar_create_local = AsyncMock(
        side_effect=MacControllerError("Calendar.app not running"),
    )

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal), \
         patch("agents.calendar.calendar_agent.get_mac_controller_service", return_value=fake_mac):
        out = await agent.process(_input(
            task="block",
            tool="calendar_create_event",
            title="x",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T11:00:00",
        ))

    assert out["success"] is True  # Google succeeded → call succeeds
    assert out["result"]["id"] == "ev1"
    assert out["result"].get("mirror_warning") is not None


@pytest.mark.asyncio
async def test_create_event_google_failure_is_fatal() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_kb.observe_interaction = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.create_event = AsyncMock(side_effect=GCalError("quota exceeded"))
    fake_mac = MagicMock()
    fake_mac._calendar_create_local = AsyncMock()

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal), \
         patch("agents.calendar.calendar_agent.get_mac_controller_service", return_value=fake_mac):
        out = await agent.process(_input(
            task="block",
            tool="calendar_create_event",
            title="x",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T11:00:00",
        ))

    assert out["success"] is False
    assert "quota" in out["error"]
    fake_mac._calendar_create_local.assert_not_awaited()


# ── create_event — attendees → approval gate ──────────────────────────


@pytest.mark.asyncio
async def test_create_event_with_attendees_requires_approval_by_default() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_kb.observe_interaction = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.create_event = AsyncMock()
    fake_mac = MagicMock()

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal), \
         patch("agents.calendar.calendar_agent.get_mac_controller_service", return_value=fake_mac):
        out = await agent.process(_input(
            task="set up sync with Acme",
            tool="calendar_create_event",
            title="Sync",
            start_iso="2026-05-01T15:00:00",
            end_iso="2026-05-01T15:30:00",
            attendees=["client@acme.com"],
        ))

    assert out["requires_approval"] is True
    assert out["success"] is True
    assert "client@acme.com" in out["approval_prompt"]
    fake_gcal.create_event.assert_not_awaited()  # nothing sent


@pytest.mark.asyncio
async def test_create_event_with_attendees_send_true_actually_sends() -> None:
    agent = CalendarAgent()
    fake_kb = MagicMock()
    fake_kb.build_agent_context = AsyncMock(return_value="")
    fake_kb.record_agent_activity = AsyncMock()
    fake_kb.observe_interaction = AsyncMock()
    fake_gcal = MagicMock()
    fake_gcal.create_event = AsyncMock(return_value={"id": "ev2"})
    fake_mac = MagicMock()
    fake_mac._calendar_create_local = AsyncMock()

    with patch("agents.calendar.calendar_agent.get_kb_service", return_value=fake_kb), \
         patch("agents.calendar.calendar_agent.get_gcal_service", return_value=fake_gcal), \
         patch("agents.calendar.calendar_agent.get_mac_controller_service", return_value=fake_mac):
        out = await agent.process(_input(
            task="confirmed — send the invite",
            tool="calendar_create_event",
            title="Sync",
            start_iso="2026-05-01T15:00:00",
            end_iso="2026-05-01T15:30:00",
            attendees=["client@acme.com"],
            send=True,
        ))

    assert out["requires_approval"] is False
    assert out["success"] is True
    fake_gcal.create_event.assert_awaited_once()
    body_kwargs = fake_gcal.create_event.await_args.kwargs
    assert body_kwargs["attendees"] == ["client@acme.com"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agents/test_calendar_agent.py -k create_event -v`
Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement `_create_event`**

Replace the `_create_event` placeholder:

```python
    async def _create_event(self, input: AgentInput, start: float) -> AgentOutput:
        ctx = input["context"]
        title = ctx["title"]
        start_iso = ctx["start_iso"]
        end_iso = ctx["end_iso"]
        attendees = ctx.get("attendees") or []
        description = ctx.get("description")
        location = ctx.get("location")
        send = bool(ctx.get("send", False))

        # Approval gate — Override #1: only when attendees present.
        if attendees and not send:
            preview = {
                "title": title,
                "start_iso": start_iso,
                "end_iso": end_iso,
                "attendees": attendees,
            }
            return AgentOutput(
                success=True,
                result=preview,
                agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0,
                error=None,
                requires_approval=True,
                approval_prompt=(
                    f"Send invite to {', '.join(attendees)}?\n"
                    f"  Title: {title}\n"
                    f"  When: {start_iso} – {end_iso}\n"
                    "Reply 'yes' to send or 'no' to discard."
                ),
            )

        # Step 1 — Google write (source of truth).
        gcal = get_gcal_service()
        try:
            event = await gcal.create_event(
                title=title,
                start_iso=start_iso,
                end_iso=end_iso,
                attendees=attendees if attendees else None,
                description=description,
                location=location,
                calendar_id=ctx.get("calendar_id"),
            )
        except GCalError as exc:
            return _failure(self.name, start, str(exc))

        # Step 2 — AppleScript mirror (best-effort).
        mirror_warning: Optional[str] = None
        try:
            mac = get_mac_controller_service()
            await mac._calendar_create_local(
                title=title,
                start_iso=start_iso,
                end_iso=end_iso,
            )
        except MacControllerError as exc:
            logger.warning(
                "[%s] Calendar.app mirror failed (non-fatal): %s",
                input["trace_id"], exc,
            )
            mirror_warning = str(exc)

        # Pattern observation — only on self-only successful creates.
        if not attendees:
            try:
                hour = _parse_iso(start_iso).hour
                await get_kb_service().observe_interaction(
                    "calendar", "preferred_block_hour", str(hour),
                )
            except Exception:
                pass

        result = dict(event)
        if mirror_warning is not None:
            result["mirror_warning"] = mirror_warning

        return AgentOutput(
            success=True, result=result, agent=self.name,
            duration_ms=int((time.monotonic() - start) * 1000),
            tokens_used=0, error=None,
            requires_approval=False, approval_prompt=None,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agents/test_calendar_agent.py -v`
Expected: PASS — full suite (15 tests).

- [ ] **Step 5: Commit**

```bash
git add agents/calendar/calendar_agent.py tests/agents/test_calendar_agent.py
git commit -m "feat(calendar): create_event with dual-write + approval gate

Google is source of truth; AppleScript mirror best-effort (failure
logged + surfaced as result.mirror_warning, not fatal). Self-only
events auto-create per Charter Override #1; attendees-present
requires context['send']=True. Self-only creates fire
observe_interaction('calendar', 'preferred_block_hour', H) for
KB pattern learning."
```

---

## Chunk 5: CRUZ Calendar tool registration + live tier

Spec §3 (CRUZ tool registration), §4 (live tier). Day 6 of build order.

### Task 16: Register 3 calendar tools in `CRUZ_TOOLS` + `_TOOL_AGENT_MAP`

**Files:**
- Modify: `agents/cruz/cruz_agent.py`
- Modify: `tests/agents/test_cruz_tools_registry.py`

Calendar IS an agent (passes Rule 1 with criteria b + c) — it goes into both `CRUZ_TOOLS` and `_TOOL_AGENT_MAP`. But unlike the existing agents, CRUZ has 3 different tool entries that all dispatch to the same agent class (with different `context["tool"]` values).

- [ ] **Step 1: Write the failing tests**

Append to `tests/agents/test_cruz_tools_registry.py`:

```python
def test_calendar_tools_present() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    names = {t["name"] for t in CRUZ_TOOLS}
    assert {"calendar_create_event", "calendar_list_events", "calendar_find_free_slot"} <= names


def test_calendar_create_event_schema() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    tool = next(t for t in CRUZ_TOOLS if t["name"] == "calendar_create_event")
    schema = tool["input_schema"]
    assert {"title", "start_iso", "end_iso"} <= set(schema["required"])
    assert "attendees" in schema["properties"]
    assert schema["properties"]["attendees"]["type"] == "array"


def test_calendar_find_free_slot_schema() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    tool = next(t for t in CRUZ_TOOLS if t["name"] == "calendar_find_free_slot")
    schema = tool["input_schema"]
    assert {"duration_minutes", "earliest_iso", "latest_iso"} <= set(schema["required"])


def test_calendar_in_tool_agent_map() -> None:
    from agents.cruz.cruz_agent import _TOOL_AGENT_MAP
    from agents.calendar.calendar_agent import CalendarAgent
    for tool in ("calendar_create_event", "calendar_list_events", "calendar_find_free_slot"):
        assert _TOOL_AGENT_MAP[tool] is CalendarAgent
```

Also add a test for `_dispatch_tool` forwarding the tool name into `context["tool"]`:

```python
# tests/agents/test_cruz_calendar_dispatch.py — NEW file
"""Verify _dispatch_tool forwards calendar tool names to CalendarAgent via context."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.cruz.cruz_agent import CruzAgent


@pytest.mark.asyncio
async def test_dispatch_calendar_create_event_passes_tool_name_in_context() -> None:
    cruz = CruzAgent()
    fake_agent = MagicMock()
    fake_agent.process = AsyncMock(return_value={
        "success": True, "result": {"id": "x"}, "agent": "CALENDAR",
        "duration_ms": 1, "tokens_used": 0, "error": None,
        "requires_approval": False, "approval_prompt": None,
    })
    with patch("agents.cruz.cruz_agent.CalendarAgent", return_value=fake_agent):
        await cruz._dispatch_tool(
            tool_name="calendar_create_event",
            tool_input={
                "title": "Block",
                "start_iso": "2026-05-01T10:00:00",
                "end_iso": "2026-05-01T12:00:00",
            },
            trace_id="t1",
            conversation_id="c1",
        )
    args = fake_agent.process.await_args.args[0]
    assert args["context"]["tool"] == "calendar_create_event"
    assert args["context"]["title"] == "Block"


@pytest.mark.asyncio
async def test_dispatch_calendar_find_free_slot_forwards_tool_name() -> None:
    cruz = CruzAgent()
    fake_agent = MagicMock()
    fake_agent.process = AsyncMock(return_value={
        "success": True, "result": {"start_iso": "...", "end_iso": "..."},
        "agent": "CALENDAR", "duration_ms": 1, "tokens_used": 0, "error": None,
        "requires_approval": False, "approval_prompt": None,
    })
    with patch("agents.cruz.cruz_agent.CalendarAgent", return_value=fake_agent):
        await cruz._dispatch_tool(
            tool_name="calendar_find_free_slot",
            tool_input={
                "duration_minutes": 60,
                "earliest_iso": "2026-05-01T09:00:00",
                "latest_iso": "2026-05-01T18:00:00",
            },
            trace_id="t1",
            conversation_id="c1",
        )
    args = fake_agent.process.await_args.args[0]
    assert args["context"]["tool"] == "calendar_find_free_slot"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agents/test_cruz_tools_registry.py tests/agents/test_cruz_calendar_dispatch.py -v`
Expected: FAIL — calendar tools not in registry.

- [ ] **Step 3: Add the 3 tool entries to `CRUZ_TOOLS`**

Insert immediately after the 5 mac entries (Task 7), still inside `CRUZ_TOOLS`, before the closing `]`:

```python
    # ── Calendar (Layer 2 — agents/calendar/calendar_agent.py) ────────
    {
        "name": "calendar_create_event",
        "description": (
            "Create a calendar event in Google Calendar (auto-mirrors to Calendar.app). "
            "Self-only events (no attendees) are created immediately. "
            "Events with attendees require user approval before sending invites."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title":       {"type": "string"},
                "start_iso":   {"type": "string",
                                "description": "ISO 8601 datetime, e.g. 2026-05-01T10:00:00"},
                "end_iso":     {"type": "string"},
                "attendees":   {"type": "array", "items": {"type": "string"},
                                "description": "Optional list of attendee email addresses."},
                "description": {"type": "string"},
                "location":    {"type": "string"},
                "calendar_id": {"type": "string",
                                "description": "Optional non-primary calendar ID."},
            },
            "required": ["title", "start_iso", "end_iso"],
        },
    },
    {
        "name": "calendar_list_events",
        "description": "List Google Calendar events in a time range. Read-only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_iso":   {"type": "string"},
                "end_iso":     {"type": "string"},
                "calendar_id": {"type": "string"},
            },
            "required": ["start_iso", "end_iso"],
        },
    },
    {
        "name": "calendar_find_free_slot",
        "description": (
            "Find the first free slot of `duration_minutes` in [earliest_iso, latest_iso]. "
            "Reads busy events from Google Calendar. Read-only — does not create anything."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_minutes": {"type": "integer", "minimum": 5},
                "earliest_iso":     {"type": "string"},
                "latest_iso":       {"type": "string"},
                "working_hours":    {"type": "array", "items": {"type": "integer"},
                                     "minItems": 2, "maxItems": 2,
                                     "description": "Optional [start_hour, end_hour], 24h."},
            },
            "required": ["duration_minutes", "earliest_iso", "latest_iso"],
        },
    },
```

- [ ] **Step 4: Register Calendar in `_TOOL_AGENT_MAP`**

Add the import at the top of the file:

```python
from agents.calendar.calendar_agent import CalendarAgent
```

In `_TOOL_AGENT_MAP`, add three entries (all pointing to the same class):

```python
    "calendar_create_event":   CalendarAgent,
    "calendar_list_events":    CalendarAgent,
    "calendar_find_free_slot": CalendarAgent,
```

- [ ] **Step 5: Forward tool name into context**

The current `_dispatch_tool` calls `agent_cls()` and passes `tool_input` as `context`. The Calendar agent reads `context["tool"]` to know which operation to run — we need to inject the tool name. In `_dispatch_tool`, modify the `agent_input` construction (around line 702):

Replace:

```python
        agent_input: AgentInput = {
            "task": tool_input.get("task", ""),
            "context": tool_input,
            "trace_id": trace_id,
            "conversation_id": conversation_id,
        }
```

With:

```python
        # Inject tool name into context so dispatcher-style agents (Calendar)
        # know which operation to run. Existing agents ignore the extra key.
        context: Dict[str, Any] = dict(tool_input)
        context["tool"] = tool_name
        agent_input: AgentInput = {
            "task": tool_input.get("task", ""),
            "context": context,
            "trace_id": trace_id,
            "conversation_id": conversation_id,
        }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/agents/test_cruz_tools_registry.py tests/agents/test_cruz_calendar_dispatch.py tests/agents/test_cruz_agent.py -v`
Expected: PASS — no regressions, calendar tests green.

Also run the full test suite to catch any unintended fallout:

Run: `pytest tests/ -x --ignore=tests/services/test_mac_controller_live.py --ignore=tests/agents/test_calendar_agent_live.py -q`
Expected: PASS — full suite (1,073+ tests + new SP3 tests).

- [ ] **Step 7: Commit**

```bash
git add agents/cruz/cruz_agent.py tests/agents/test_cruz_tools_registry.py tests/agents/test_cruz_calendar_dispatch.py
git commit -m "feat(cruz): register 3 calendar tools + dispatch via context['tool']

calendar_create_event, calendar_list_events, calendar_find_free_slot —
all map to CalendarAgent in _TOOL_AGENT_MAP. _dispatch_tool now forwards
the tool name into context['tool'] so dispatcher-style agents can route
by operation. Existing agents ignore the extra key."
```

---

### Task 17: Live-tier Calendar tests

**Files:**
- Create: `tests/agents/test_calendar_agent_live.py`

These hit a REAL Google Calendar account and create real events with the prefix `CRUZ TEST —`. Cleanup runs in a finalizer even on test failure.

- [ ] **Step 1: Write the file**

```python
# tests/agents/test_calendar_agent_live.py
"""Live-tier CalendarAgent tests — real Google Calendar API.

Run on the Mac Mini with a provisioned token:
    CRUZ_LIVE_MAC_TESTS=1 pytest tests/agents/test_calendar_agent_live.py -v

Skipped automatically when env var unset, on Linux, or when no token file exists.

Cleanup deletes ALL events with title prefix 'CRUZ TEST —' from the
last hour, even on failure (pytest finalizer).
"""

from __future__ import annotations

import asyncio
import os
import platform
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio

from agents.calendar.calendar_agent import CalendarAgent
from services.gcal import get_gcal_service

LIVE = os.environ.get("CRUZ_LIVE_MAC_TESTS") == "1"
IS_MAC = platform.system() == "Darwin"
TOKEN_PATH = Path(
    os.path.expanduser(os.environ.get("GCAL_TOKEN_PATH", "~/.config/cruz/gcal-token.json"))
)
HAS_TOKEN = TOKEN_PATH.exists()

pytestmark = pytest.mark.skipif(
    not (LIVE and IS_MAC and HAS_TOKEN),
    reason="Live calendar tests require CRUZ_LIVE_MAC_TESTS=1, macOS, and a provisioned gcal token",
)

PREFIX = "CRUZ TEST —"


def _input(**ctx):
    return {
        "task": "live calendar test",
        "context": ctx,
        "trace_id": "live-trace",
        "conversation_id": "live-conv",
    }


@pytest_asyncio.fixture
async def cleanup_test_events():
    """Delete all CRUZ TEST events created within the cleanup window, even on failure.

    Async fixture (not sync) — `asyncio.get_event_loop().run_until_complete()` from a
    sync fixture conflicts with pytest-asyncio's loop management. The yield-style
    finalizer still runs even if the wrapped test raises.
    """
    yield
    await _cleanup()


async def _cleanup():
    gcal = get_gcal_service()
    now = datetime.now(timezone.utc)
    # Window widened to +7d to catch any seeded events from future tests.
    events = await gcal.list_events(
        start_iso=(now - timedelta(hours=1)).isoformat(),
        end_iso=(now + timedelta(days=7)).isoformat(),
    )
    for ev in events:
        if (ev.get("summary", "")).startswith(PREFIX):
            try:
                await gcal.delete_event(ev["id"])
            except Exception as exc:
                print(f"cleanup failed for {ev.get('id')}: {exc}")


@pytest.mark.asyncio
async def test_live_create_self_only_event_round_trips_google_and_calendar_app(
    cleanup_test_events,
) -> None:
    agent = CalendarAgent()
    title = f"{PREFIX} self-only {uuid.uuid4().hex[:8]}"
    start = (datetime.now() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)

    out = await agent.process(_input(
        tool="calendar_create_event",
        title=title,
        start_iso=start.isoformat(timespec="seconds"),
        end_iso=end.isoformat(timespec="seconds"),
    ))

    assert out["success"] is True, f"create failed: {out.get('error')}"
    assert out["requires_approval"] is False
    event_id = out["result"]["id"]

    # Verify visible in Google API list
    gcal = get_gcal_service()
    events = await gcal.list_events(
        start.isoformat(timespec="seconds"),
        end.isoformat(timespec="seconds"),
    )
    assert any(e["id"] == event_id for e in events), "event not visible in Google list"

    # Verify visible in Calendar.app via osascript
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e",
        'tell application "Calendar" to return summary of (every event of every calendar '
        f'whose summary starts with "{PREFIX}")',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    # Calendar.app sync may take a few seconds; if mirror succeeded synchronously it should appear.
    out_text = stdout.decode("utf-8", errors="replace")
    if title not in out_text:
        # Mirror may have failed gracefully — verify warning surfaced.
        assert "mirror_warning" in out["result"], (
            f"event not in Calendar.app and no mirror_warning surfaced: {out_text}"
        )


@pytest.mark.asyncio
async def test_live_create_with_attendees_returns_approval_no_send(
    cleanup_test_events,
) -> None:
    agent = CalendarAgent()
    title = f"{PREFIX} attendees {uuid.uuid4().hex[:8]}"
    start = (datetime.now() + timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=30)

    out = await agent.process(_input(
        tool="calendar_create_event",
        title=title,
        start_iso=start.isoformat(timespec="seconds"),
        end_iso=end.isoformat(timespec="seconds"),
        attendees=["nonexistent-cruz-test@example.com"],
    ))

    assert out["requires_approval"] is True
    assert out["success"] is True
    assert "approval_prompt" in out and "nonexistent-cruz-test" in out["approval_prompt"]

    # Verify NO event was created in Google
    gcal = get_gcal_service()
    events = await gcal.list_events(
        start.isoformat(timespec="seconds"),
        end.isoformat(timespec="seconds"),
    )
    assert not any((e.get("summary", "")).startswith(title) for e in events), (
        "event was created despite no send=True"
    )


@pytest.mark.asyncio
async def test_live_list_events_returns_real_events(cleanup_test_events) -> None:
    agent = CalendarAgent()
    title = f"{PREFIX} list {uuid.uuid4().hex[:8]}"
    start = (datetime.now() + timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=30)

    # Seed an event
    create_out = await agent.process(_input(
        tool="calendar_create_event",
        title=title,
        start_iso=start.isoformat(timespec="seconds"),
        end_iso=end.isoformat(timespec="seconds"),
    ))
    assert create_out["success"]

    # List
    list_out = await agent.process(_input(
        tool="calendar_list_events",
        start_iso=start.isoformat(timespec="seconds"),
        end_iso=end.isoformat(timespec="seconds"),
    ))
    assert list_out["success"]
    assert any((e.get("summary", "")).startswith(title) for e in list_out["result"])


@pytest.mark.asyncio
async def test_live_find_free_slot_against_real_calendar(cleanup_test_events) -> None:
    agent = CalendarAgent()
    # 24h window starting tomorrow
    base = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    out = await agent.process(_input(
        tool="calendar_find_free_slot",
        duration_minutes=30,
        earliest_iso=base.replace(hour=9).isoformat(timespec="seconds"),
        latest_iso=base.replace(hour=18).isoformat(timespec="seconds"),
    ))
    # Should find SOMETHING in a 9-hour window for a 30-min slot.
    assert out["success"] is True, f"failed to find free slot: {out.get('error')}"
    assert "start_iso" in out["result"]
    assert "end_iso" in out["result"]
```

- [ ] **Step 2: Verify suite skips on dev machine (if not Mac Mini with token)**

Run: `pytest tests/agents/test_calendar_agent_live.py -v`
Expected: All tests SKIPPED with reason starting `Live calendar tests require ...`.

- [ ] **Step 3: Run on the Mac Mini**

(Operator step. Requires a provisioned `gcal-token.json` from Task 12.)

```bash
CRUZ_LIVE_MAC_TESTS=1 pytest tests/agents/test_calendar_agent_live.py -v -s
```
Expected: PASS — 4 tests. You will see test events briefly appear and disappear from your Google Calendar.

After the run, manually verify:
- Open https://calendar.google.com — no `CRUZ TEST —` events remain.
- Open Calendar.app — no `CRUZ TEST —` events remain (will sync within ~60s).

If the cleanup leaves stragglers, run:
```bash
python -c "
import asyncio
from tests.agents.test_calendar_agent_live import _cleanup
asyncio.run(_cleanup())
"
```

- [ ] **Step 4: Commit**

```bash
git add tests/agents/test_calendar_agent_live.py
git commit -m "test(calendar): live tier — real Google Calendar + Calendar.app

Skipped unless CRUZ_LIVE_MAC_TESTS=1 + macOS + provisioned token.
Cleans up all 'CRUZ TEST —' events in finalizer (even on failure).
Verifies dual-write (Google + Calendar.app), approval gate gates
Google write entirely, list_events sees seeded events, and
find_free_slot returns something in a 9h window."
```

---

## Chunk 6: Exit-gate documentation + sign-off

Spec §5 (exit-gate verification table). Day 7 of build order.

### Task 18: `docs/perf/sp3-exit-gate.md`

**Files:**
- Create: `docs/perf/sp3-exit-gate.md`

- [ ] **Step 1: Write the verification doc**

```markdown
# SP3 Exit-Gate Verification

> Manual checklist filled in once at SP3 sign-off. Maps directly to charter §5.1 SP3 (modified by spec Override #2 — Messenger criterion deferred).

**Run on:** Mac Mini, with PM2 stack live (PostgreSQL, Redis, Qdrant, Ollama, FastAPI).

**Spec:** [`../superpowers/specs/2026-04-26-sp3-mac-controller-design.md`](../superpowers/specs/2026-04-26-sp3-mac-controller-design.md)
**Charter:** [`../superpowers/specs/2026-04-20-v2-program-charter.md`](../superpowers/specs/2026-04-20-v2-program-charter.md) §5.1 SP3

---

## Pre-flight

- [ ] PM2 process `cruz-api` is running (`pm2 list`)
- [ ] `/health` is green: `curl -s http://localhost:3000/health | jq`
- [ ] `~/.config/cruz/gcal-token.json` exists, mode 0600, not expired
- [ ] Calendar.app is open and subscribed to the Google account `gcal-token.json` is authenticated against (System Settings → Internet Accounts → Google → Calendars enabled)
- [ ] All unit tests pass: `pytest tests/ --ignore=tests/services/test_mac_controller_live.py --ignore=tests/agents/test_calendar_agent_live.py -q`
- [ ] Live mac tests pass: `CRUZ_LIVE_MAC_TESTS=1 pytest tests/services/test_mac_controller_live.py -v`
- [ ] Live calendar tests pass: `CRUZ_LIVE_MAC_TESTS=1 pytest tests/agents/test_calendar_agent_live.py -v`

---

## Exit-gate criteria (charter §5.1 SP3 + Override #2)

### G1 — `mac_screenshot` from a CRUZ tool call

- [ ] `curl -X POST http://localhost:3000/command -H 'Content-Type: application/json' -d '{"message":"take a screenshot of the screen and tell me how big it is", "stream":false}'`
- [ ] CRUZ picks `mac_screenshot` (verify in `agent_logs` filtered by trace_id)
- [ ] CRUZ replies with the byte size and mime type
- [ ] Operator confirmation: did the response indicate a non-zero PNG was captured? **YES / NO**

### G2 — `mac_clipboard_read` from a CRUZ tool call

- [ ] Manually copy a known string: `pbcopy <<< "sentinel-7f3a"`
- [ ] `curl -X POST http://localhost:3000/command -H 'Content-Type: application/json' -d '{"message":"what is on my clipboard right now", "stream":false}'`
- [ ] CRUZ picks `mac_clipboard_read`
- [ ] CRUZ replies containing `sentinel-7f3a`. **YES / NO**

### G3 — `mac_clipboard_write` from a CRUZ tool call

- [ ] `curl -X POST http://localhost:3000/command -H 'Content-Type: application/json' -d '{"message":"copy this to my clipboard: hello-from-cruz", "stream":false}'`
- [ ] CRUZ picks `mac_clipboard_write`
- [ ] Manually paste in Notes / TextEdit: `pbpaste` returns `hello-from-cruz`. **YES / NO**

### G4 — `mac_open_app` from a CRUZ tool call

- [ ] `curl -X POST http://localhost:3000/command -H 'Content-Type: application/json' -d '{"message":"open TextEdit for me", "stream":false}'`
- [ ] CRUZ picks `mac_open_app`
- [ ] TextEdit launches and comes to the foreground. **YES / NO**
- [ ] Cleanup: quit TextEdit (`osascript -e 'tell application "TextEdit" to quit'`)

### G5 — `mac_notify` from a CRUZ tool call

- [ ] `curl -X POST http://localhost:3000/command -H 'Content-Type: application/json' -d '{"message":"send me a reminder notification: take a break", "stream":false}'`
- [ ] CRUZ picks `mac_notify`
- [ ] Notification banner appears in macOS Notification Center. **YES / NO**

### G6 — Calendar event in BOTH Google Calendar AND Calendar.app

- [ ] `curl -X POST http://localhost:3000/command -H 'Content-Type: application/json' -d '{"message":"block 14:00 to 14:30 tomorrow as deep work", "stream":false}'`
- [ ] CRUZ picks `calendar_create_event`
- [ ] Open https://calendar.google.com — event visible at 14:00 tomorrow with title "deep work" (or similar). **YES / NO**
- [ ] Open Calendar.app on the Mac Mini — same event visible. **YES / NO**
- [ ] Cleanup: delete the event from Google Calendar (Calendar.app will sync the deletion)

### G7 — Test calendar cleanup ran clean

- [ ] No `CRUZ TEST —` events remain in primary Google Calendar
- [ ] No `CRUZ TEST —` events remain in Calendar.app

---

## Sign-off

When all 7 gates above tick **YES**:

1. Append SP3 sign-off block to `docs/superpowers/PROGRESS.md`:

```markdown
## SP3 — Mac Controller (signed off YYYY-MM-DD)

- Mac Controller primitives (5 CRUZ tools) live and verified
- Calendar agent (3 CRUZ tools) live and verified
- Charter Override #1 (self-only auto-create) confirmed in production
- Charter Override #2 (Messenger deferred to v2.1) recorded in DEFERRED.md
- Exit gate: docs/perf/sp3-exit-gate.md ticked
- Live tests: docs/perf/sp3-exit-gate.md "Pre-flight" all green
```

2. Commit: `git commit -am "chore(sp3): sign-off — exit gate green"`

3. Notify Darshan; SP4 brainstorming may begin.
```

- [ ] **Step 2: Commit**

```bash
git add docs/perf/sp3-exit-gate.md
git commit -m "docs(sp3): exit-gate verification checklist

Maps each charter §5.1 SP3 criterion (modified by Override #2) to a
concrete curl + visual-check operator step. Sign-off appended to
PROGRESS.md only after all 7 gates tick YES."
```

---

### Task 19: Smoke-test the full plan in dev (skip live tests)

**Files:** none modified

- [ ] **Step 1: Run the full unit suite from clean state**

```bash
pytest tests/ \
  --ignore=tests/services/test_mac_controller_live.py \
  --ignore=tests/agents/test_calendar_agent_live.py \
  -q
```
Expected: PASS — full suite passes (1,073 SP2 tests + ~30 new SP3 tests). No regressions.

- [ ] **Step 2: Verify ruff + black pass on new files**

```bash
ruff check services/mac_controller.py services/gcal.py agents/calendar/ \
  scripts/gcal_auth.py tests/services/test_mac_controller.py \
  tests/services/test_gcal.py tests/agents/test_calendar_agent.py
black --check services/mac_controller.py services/gcal.py agents/calendar/ \
  scripts/gcal_auth.py
```
Expected: no warnings, no formatting drift.

- [ ] **Step 3: Open PR**

```bash
git push -u origin claude/cool-curran-6d761f
gh pr create --title "feat(sp3): Mac Controller + Calendar agent" --body "$(cat <<'EOF'
## Summary

Implements SP3 (Layer 2 — Mac Controller) per spec [docs/superpowers/specs/2026-04-26-sp3-mac-controller-design.md](docs/superpowers/specs/2026-04-26-sp3-mac-controller-design.md).

- `services/mac_controller.py` — 4 AppleScript primitives + 1 Calendar.app helper, exposed as 5 typed CRUZ tools (`mac_screenshot`, `mac_clipboard_read`, `mac_clipboard_write`, `mac_open_app`, `mac_notify`).
- `services/gcal.py` + `scripts/gcal_auth.py` — Google Calendar OAuth wrapper + one-time token bootstrap.
- `agents/calendar/calendar_agent.py` — 3 CRUZ tools (`calendar_create_event`, `calendar_list_events`, `calendar_find_free_slot`). Self-only events auto-create per Override #1; attendees-present requires `context['send']=True`. Dual-write: Google primary + Calendar.app mirror (best-effort). KB hooks per Rule 3.

Charter overrides documented in spec §2: (1) Rule 4 reads "externally visible" literally for self-only blocks; (2) Messenger/iMessage deferred to v2.1 per cut-list row 9.

## Test plan
- [x] Unit tier passes (~30 new tests + 1,073 existing) on Linux/CI
- [ ] Live mac tier passes on Mac Mini: `CRUZ_LIVE_MAC_TESTS=1 pytest tests/services/test_mac_controller_live.py`
- [ ] Live calendar tier passes on Mac Mini: `CRUZ_LIVE_MAC_TESTS=1 pytest tests/agents/test_calendar_agent_live.py`
- [ ] Exit gate ticked: `docs/perf/sp3-exit-gate.md` (7/7)
- [ ] PROGRESS.md SP3 sign-off appended
EOF
)"
```

Report the PR URL.

---

## Verification commands cheat sheet

| Goal | Command |
|---|---|
| Unit tests only | `pytest tests/ --ignore=tests/services/test_mac_controller_live.py --ignore=tests/agents/test_calendar_agent_live.py -q` |
| Live mac tests (Mac Mini) | `CRUZ_LIVE_MAC_TESTS=1 pytest tests/services/test_mac_controller_live.py -v` |
| Live calendar tests (Mac Mini) | `CRUZ_LIVE_MAC_TESTS=1 pytest tests/agents/test_calendar_agent_live.py -v` |
| Lint + format check | `ruff check services/mac_controller.py services/gcal.py agents/calendar/ && black --check services/mac_controller.py services/gcal.py agents/calendar/` |
| Health check | `curl -s http://localhost:3000/health \| jq` |
| Trace inspect | `psql -d cruz_db -c "SELECT agent, action, status, duration_ms FROM agent_logs WHERE trace_id = 'TRACE' ORDER BY created_at;"` |
