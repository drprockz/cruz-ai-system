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
APP_NAME_RE = re.compile(r"^[A-Za-z0-9 ._-]+$")
# Backward-compat alias.
_APP_NAME_RE = APP_NAME_RE


class MacControllerError(RuntimeError):
    """Raised when an osascript / screencapture call returns non-zero."""


def get_mac_controller_service() -> "MacControllerService":
    """Return the module-level MacControllerService singleton."""
    global _instance
    if _instance is None:
        _instance = MacControllerService()
    return _instance


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


def escape_applescript_string(raw: str) -> str:
    """Escape a Python string for safe inclusion inside an AppleScript double-quoted string.

    AppleScript string literals don't support \\n / \\t escapes — newlines and
    tabs are concatenated using `" & return & "` and `" & tab & "`.
    """
    if raw == "":
        return ""
    out = raw.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", '" & return & "').replace("\t", '" & tab & "')
    return out


# Backward-compat alias — internal callers may keep using the leading-underscore form.
_escape_applescript_string = escape_applescript_string


class MacControllerService:
    """All public methods are async. All raise MacControllerError on failure."""

    # ── Public primitives ─────────────────────────────────────────────

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

    async def clipboard_read(self) -> str:
        """Return the current clipboard contents as text. Empty clipboard → ''."""
        out = await self._run_osascript("the clipboard as text")
        return out.rstrip("\n")

    async def clipboard_write(self, text: str) -> None:
        """Replace the clipboard with the given text."""
        text_esc = escape_applescript_string(text)
        await self._run_osascript(f'set the clipboard to "{text_esc}"')

    async def open_app(self, name: str) -> None:
        """Activate (launch + foreground) a macOS app by name.

        App name is validated against APP_NAME_RE to defend against
        AppleScript injection through this primitive.
        """
        if not APP_NAME_RE.match(name):
            raise MacControllerError(f"invalid app name: {name!r}")
        await self._run_osascript(f'tell application "{name}" to activate')

    async def notify(self, title: str, body: str, sound: bool = False) -> None:
        """Fire a macOS Notification Center banner."""
        title_esc = escape_applescript_string(title)
        body_esc = escape_applescript_string(body)
        script = f'display notification "{body_esc}" with title "{title_esc}"'
        if sound:
            script += ' sound name "Submarine"'
        await self._run_osascript(script)

    # ── Internal Calendar helper ──────────────────────────────────────

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

        `calendar_name` always defaults to "Calendar" because there is no
        corresponding parameter on the `calendar_create_event` CRUZ tool —
        users with multiple local calendars and a desire to target a
        specific one would need a future tool-schema change. SP3 scope
        keeps this targeted at the default Calendar.app calendar only.

        start_iso / end_iso must be ISO 8601 with seconds (e.g. 2026-05-01T10:00:00).
        Calendar.app requires AppleScript date literals — we build them with
        `date "<MM/DD/YYYY HH:MM:SS>"` form which AppleScript parses unambiguously.
        """
        title_esc = escape_applescript_string(title)
        cal_esc = escape_applescript_string(calendar_name)
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
