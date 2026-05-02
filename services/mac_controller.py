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
        text_esc = _escape_applescript_string(text)
        await self._run_osascript(f'set the clipboard to "{text_esc}"')

    async def open_app(self, name: str) -> None:
        """Activate (launch + foreground) a macOS app by name.

        App name is validated against _APP_NAME_RE to defend against
        AppleScript injection through this primitive.
        """
        if not _APP_NAME_RE.match(name):
            raise MacControllerError(f"invalid app name: {name!r}")
        await self._run_osascript(f'tell application "{name}" to activate')

    async def notify(self, title: str, body: str, sound: bool = False) -> None:
        """Fire a macOS Notification Center banner."""
        title_esc = _escape_applescript_string(title)
        body_esc = _escape_applescript_string(body)
        script = f'display notification "{body_esc}" with title "{title_esc}"'
        if sound:
            script += ' sound name "Submarine"'
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
