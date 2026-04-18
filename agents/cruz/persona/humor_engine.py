"""
HumorEngine — decides whether humor is permitted for this turn and, if so,
which situational phrase bank to draw from.

Only SURFACES a permission + suggestion. The LLM is the actual author;
this module just gates when a dry one-liner is appropriate.

Rules (explicit, conservative):
  - Forbidden during stress / failure / production actions (always)
  - Permitted only in specific windows: late-night casual, post-success
  - Default: off. Humor must be explicitly unlocked.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


_SITUATIONAL: dict[str, list[str]] = {
    "late_night_casual": [
        "Burning the midnight oil again?",
        "At least one of us doesn't need coffee.",
    ],
    "successful_complex_task": [
        "Done. Surprisingly fun one.",
        "Handled. Tighter than expected.",
    ],
    "user_frustrated_with_tech": [
        "Technology. Great when it works.",
    ],
}


_STRESS_MARKERS = (
    "urgent",
    "asap",
    "prod",
    "broken",
    "down",
    "outage",
    "emergency",
)


@dataclass
class HumorPermission:
    allowed: bool
    reason: str
    bank: Optional[str] = None
    examples: Optional[List[str]] = None


def decide(
    *,
    now: Optional[datetime] = None,
    last_turn_errored: bool = False,
    last_user_message: str = "",
    touched_production: bool = False,
    task_completed_with_tools: int = 0,
) -> HumorPermission:
    """
    Return whether humor is permitted for this turn.

    Forbidden conditions take precedence over permitted ones.
    """
    dt = now or datetime.now().astimezone()
    lower = (last_user_message or "").lower()

    # Hard stops
    if last_turn_errored:
        return HumorPermission(False, "recent failure — stay serious")
    if touched_production:
        return HumorPermission(False, "production context — no humor")
    if any(m in lower for m in _STRESS_MARKERS):
        return HumorPermission(False, "user is stressed — be efficient")

    # Permitted windows
    h = dt.hour
    if (h >= 22 or h < 2) and lower:
        return HumorPermission(
            True,
            "late-night casual",
            bank="late_night_casual",
            examples=_SITUATIONAL["late_night_casual"],
        )
    if task_completed_with_tools >= 3:
        return HumorPermission(
            True,
            "just finished a multi-step task",
            bank="successful_complex_task",
            examples=_SITUATIONAL["successful_complex_task"],
        )

    return HumorPermission(False, "no trigger matched; default off")


def prompt_hint(perm: HumorPermission) -> str:
    """Snippet to append to the system prompt based on humor permission."""
    if not perm.allowed:
        return (
            "\n\n## Humor\nOff this turn — be direct and efficient. "
            "No jokes, no idioms that could read as flippant."
        )
    lines = "\n".join(f"  - {x}" for x in (perm.examples or []))
    return (
        f"\n\n## Humor\nLightly permitted — {perm.reason}. "
        f"If a dry one-liner fits *naturally*, examples of tone:\n{lines}\n"
        "Do NOT force a joke; skip if it doesn't land."
    )
