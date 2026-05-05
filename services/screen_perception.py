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
