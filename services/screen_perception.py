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

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from typing import Optional

from services.llm import chat as llm_chat
from services.mac_controller import (
    APP_NAME_RE,
    MacControllerError,
    escape_applescript_string,
    get_mac_controller_service,
)

logger = logging.getLogger("cruz.services.screen_perception")

# Per-step osascript timeout. Total wall-clock budget enforced by
# asyncio.wait_for in the runtime-context injection path (2s).
_STEP_TIMEOUT_S = 1.0

# Vision call configuration (analyze path).
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


def _extract_text(content) -> str:
    """Extract plain text from an Anthropic content-block list. Returns
    '' if no text block present."""
    if not content:
        return ""
    for block in content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
    return ""


class ScreenPerceptionService:
    """Two public async methods. See module docstring."""

    async def _run_osascript_for_step1(self) -> str:
        """Run step-1 (frontmost app) AppleScript. Internal — mocked by tests.

        Exists as a separate method (not inlined) so tests can mock at this
        boundary via patch.object(svc, ...) instead of reaching through the
        mac_controller singleton.

        Returns stripped stdout. Raises MacControllerError on failure.
        """
        mac = get_mac_controller_service()
        out = await mac.run_osascript(_STEP1_SCRIPT, timeout=_STEP_TIMEOUT_S)
        return out.strip()

    async def _run_osascript_for_step2(self, app_name: str) -> str:
        """Run step-2 (window title) AppleScript.

        Internal — mocked by tests; see step1 docstring for rationale.
        """
        mac = get_mac_controller_service()
        out = await mac.run_osascript(
            _step2_script(app_name), timeout=_STEP_TIMEOUT_S
        )
        return out.strip()

    async def get_active_window(self) -> ActiveWindow:
        captured_at = time.monotonic()  # monotonic — duration anchor only, not wall-clock

        # Step 1 — frontmost process name. Never raises out of this method.
        try:
            app_name = await self._run_osascript_for_step1()
        except (MacControllerError, asyncio.TimeoutError) as exc:
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
        except (MacControllerError, asyncio.TimeoutError) as exc:
            logger.warning("get_active_window step-2 failed for %r: %s", app_name, exc)
            return ActiveWindow(app=app_name, window_title=None, captured_at=captured_at)

        return ActiveWindow(
            app=app_name,
            window_title=title or None,   # empty string → None
            captured_at=captured_at,
        )

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
        except Exception as exc:  # broad: SDK exception surface (anthropic/httpx/pydantic) is unstable; wrap uniformly
            raise ScreenPerceptionError(f"vision call failed: {exc}") from exc

        # 4. Extract text + sanitize
        raw_answer = _extract_text(response.content)
        try:
            # Imported lazily to avoid a services/ → agents/ import-time coupling.
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
