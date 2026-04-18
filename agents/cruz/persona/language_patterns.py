"""
LanguagePatterns — post-processing applied to CRUZ's LLM output to keep the
voice consistent across turns.

Two operations:
  1. Vocabulary substitution — "do" → "handle", "okay" → "noted", etc.
     (Only substitutes whole words at safe positions to avoid mangling code.)
  2. Greeting injection — if the user hasn't been greeted this session and
     it's a new conversation, prepend a time-appropriate greeting.

These rules are explicit + deterministic because asking the LLM to change
vocabulary is unreliable; better to enforce post-hoc.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional


GREETING_PATTERNS: Dict[str, List[str]] = {
    "morning": [
        "Morning, {name}.",
        "Morning, {name} — ready to tackle the day?",
    ],
    "afternoon": [
        "Afternoon, {name}.",
    ],
    "evening": [
        "Evening, {name}.",
    ],
    "night": [
        "{name} — burning the midnight oil?",
        "{name}, still at it?",
    ],
}


ACKNOWLEDGMENTS: Dict[str, List[str]] = {
    "understood": ["Got it.", "Understood.", "On it."],
    "thinking": ["One moment…", "Let me check that…"],
    "completed": ["Done.", "Handled.", "Wrapped up."],
}


# Whole-word, case-preserving substitutions applied to the final reply.
# Deliberately conservative — won't touch code blocks or quoted strings.
_VOCAB_MAP: Dict[str, str] = {
    "okay": "noted",
    "ok": "noted",
    "alright": "understood",
}


def _time_bucket(dt: Optional[datetime] = None) -> str:
    """Return 'morning' / 'afternoon' / 'evening' / 'night'."""
    h = (dt or datetime.now()).hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "afternoon"
    if 17 <= h < 22:
        return "evening"
    return "night"


def greeting(name: str, dt: Optional[datetime] = None) -> str:
    bucket = _time_bucket(dt)
    # Deterministic pick: first option. Randomizing would break tests +
    # make the personality feel jittery.
    return GREETING_PATTERNS[bucket][0].format(name=name)


def apply_vocabulary(text: str) -> str:
    """
    Replace casual fillers with CRUZ's preferred vocabulary.

    Runs whole-word, case-preserving. Skips content inside fenced code
    blocks and inline backticks to avoid mangling code/examples.
    """
    if not text:
        return text

    # Split on fenced blocks so we only substitute in prose segments.
    parts = re.split(r"(```.*?```|`[^`]+`)", text, flags=re.DOTALL)
    out: List[str] = []
    for p in parts:
        if p.startswith("`"):
            out.append(p)  # leave code untouched
            continue
        segment = p
        for bad, good in _VOCAB_MAP.items():
            pattern = re.compile(rf"\b{re.escape(bad)}\b", flags=re.IGNORECASE)

            def _preserve_case(m: re.Match) -> str:
                word = m.group(0)
                if word.isupper():
                    return good.upper()
                if word[0].isupper():
                    return good.capitalize()
                return good

            segment = pattern.sub(_preserve_case, segment)
        out.append(segment)
    return "".join(out)


def acknowledgment(kind: str = "understood") -> str:
    """Return the first canonical acknowledgment phrase for a kind."""
    return ACKNOWLEDGMENTS.get(kind, ["Got it."])[0]
