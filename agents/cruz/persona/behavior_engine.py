"""
BehaviorEngine — decides HOW detailed/brief CRUZ should be for a given turn.

No LLM calls, no emotional guessing. Just hard rules based on signals we
actually have: time of day, device, query length.

Emits a single string "style hint" that's appended to the system prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional


DepthT = Literal["ultra_brief", "brief", "normal", "detailed"]


@dataclass
class ResponseStyle:
    depth: DepthT
    reason: str
    time_context: str


# Device → baseline depth (matches existing voice-mode brevity at cruz_agent.py)
_DEPTH_BY_DEVICE = {
    "phone": "ultra_brief",
    "mac_mini": "brief",
    "ipad": "brief",
    "mac_web": "normal",
    "thinkpad": "normal",
    None: "normal",
}


def _time_context(dt: datetime) -> str:
    h = dt.hour
    if 22 <= h or h < 5:
        return "late_night"
    if 5 <= h < 9:
        return "early_morning"
    if 9 <= h < 12:
        return "morning_focus"
    if 12 <= h < 14:
        return "midday"
    if 14 <= h < 18:
        return "afternoon_work"
    return "evening_wind_down"


def _complexity(task: str) -> int:
    """Crude but useful: 0 = simple, 1 = moderate, 2 = complex."""
    t = (task or "").lower().strip()
    words = len(t.split())
    if words <= 4:
        return 0
    if any(k in t for k in ("deploy", "refactor", "plan", "architecture", "review")):
        return 2
    if words > 25:
        return 2
    if words > 12:
        return 1
    return 0


def decide(
    *,
    task: str,
    device: Optional[str] = None,
    now: Optional[datetime] = None,
) -> ResponseStyle:
    """Return the response style for this turn."""
    dt = now or datetime.now().astimezone()
    ctx = _time_context(dt)
    base = _DEPTH_BY_DEVICE.get(device, "normal")
    comp = _complexity(task)

    # Start from device baseline, then apply complexity adjustments.
    depth: DepthT = base  # type: ignore[assignment]
    reason = "default by device"

    if comp == 2 and base == "normal":
        depth = "detailed"
        reason = "complex task on desk device — detail warranted"
    elif comp == 0 and base == "normal":
        depth = "brief"
        reason = "simple question"

    # Late-night override — ALWAYS caps at brief regardless of complexity,
    # because 11pm isn't the time for a 5-section breakdown.
    if ctx == "late_night" and depth in ("detailed", "normal"):
        depth = "brief"
        reason = "late night — trimming verbosity"

    return ResponseStyle(depth=depth, reason=reason, time_context=ctx)


def style_hint(style: ResponseStyle) -> str:
    """Prose snippet to append to the system prompt."""
    depth_map = {
        "ultra_brief": "Reply in ONE sentence. No markdown, no lists, under 20 words.",
        "brief": "Reply in 1-2 sentences, under 40 words. No lists.",
        "normal": "Reply in a tight paragraph. Bullet lists OK for 3+ items.",
        "detailed": "Reply with sections + bullets where appropriate, but omit filler.",
    }
    return (
        f"\n\n## Response style for this turn\n"
        f"- Depth: **{style.depth}** ({style.reason})\n"
        f"- Time context: {style.time_context}\n"
        f"- Style rule: {depth_map[style.depth]}"
    )
