"""
PersonaLayer — single facade over the 7 persona modules.

Used from CruzAgent.process() and CruzAgent.stream_response() at two hooks:

  BEFORE LLM call:
    system_prompt = persona.augment_system_prompt(
        base=_SYSTEM_PROMPT, task=task, device=device, now=now, profile=profile,
        last_turn_errored=bool, tool_calls_this_turn=int,
    )

  AFTER LLM reply:
    text = persona.post_process(text)              # vocab + greeting
    safe = persona.sanitize_for_memory(text)       # PII redact before Qdrant

Everything is optional — if persona fails for any reason, CruzAgent falls
back to raw behaviour (see the try/except wrap in integration).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from agents.cruz.persona.behavior_engine import decide as _decide_style, style_hint as _style_hint
from agents.cruz.persona.humor_engine import decide as _decide_humor, prompt_hint as _humor_hint
from agents.cruz.persona.identity_loader import IdentityLoader
from agents.cruz.persona.language_patterns import apply_vocabulary
from agents.cruz.persona.privacy_engine import sanitize
from agents.cruz.persona.relationship_memory import UserPersonaProfile


class PersonaLayer:
    _instance: Optional["PersonaLayer"] = None

    @classmethod
    def get(cls) -> "PersonaLayer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def augment_system_prompt(
        self,
        *,
        base: str,
        task: str,
        device: Optional[str],
        now: Optional[datetime] = None,
        profile: Optional[UserPersonaProfile] = None,
        last_turn_errored: bool = False,
        tool_calls_this_turn: int = 0,
        touched_production: bool = False,
    ) -> str:
        dt = now or datetime.now().astimezone()
        identity = IdentityLoader.system_prompt_snippet()
        style = _decide_style(task=task, device=device, now=dt)
        hstyle = _style_hint(style)
        humor_perm = _decide_humor(
            now=dt,
            last_turn_errored=last_turn_errored,
            last_user_message=task,
            touched_production=touched_production,
            task_completed_with_tools=tool_calls_this_turn,
        )
        hhumor = _humor_hint(humor_perm)

        profile_block = ""
        if profile and profile.total_turns:
            profile_block = (
                f"\n\n## User context (last 30 days)\n"
                f"{profile.summary_line()}"
            )

        return f"{identity}\n\n{base}{profile_block}{hstyle}{hhumor}"

    def post_process(self, text: str) -> str:
        """Apply vocabulary rules to the LLM output."""
        if not text:
            return text
        return apply_vocabulary(text)

    def sanitize_for_memory(self, text: str) -> str:
        """Redact PII before text goes to Qdrant / long-term storage."""
        return sanitize(text)


__all__ = ["PersonaLayer", "UserPersonaProfile"]
