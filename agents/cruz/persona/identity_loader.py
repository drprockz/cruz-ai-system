"""
IdentityLoader — reads core_identity.yaml into a cached dict, serves a
short system-prompt snippet to prepend to CRUZ's existing prompt.

Zero runtime cost after first load; reload() re-reads the file.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml  # PyYAML already in backend requirements

_IDENTITY_PATH = Path(__file__).parent / "core_identity.yaml"


class IdentityLoader:
    _cached: Optional[Dict[str, Any]] = None

    @classmethod
    def load(cls) -> Dict[str, Any]:
        if cls._cached is None:
            with open(_IDENTITY_PATH, "r", encoding="utf-8") as f:
                cls._cached = yaml.safe_load(f)
        return cls._cached

    @classmethod
    def reload(cls) -> Dict[str, Any]:
        cls._cached = None
        return cls.load()

    @classmethod
    def system_prompt_snippet(cls) -> str:
        """Short persona block to prepend to CRUZ's base system prompt."""
        d = cls.load()
        pm = d.get("personality_matrix", {})
        user = d.get("user", {})
        traits = "\n".join(f"  - {t}" for t in d.get("core_traits", []))
        clients = ", ".join(user.get("clients", []))
        return f"""## Identity

You are **{d.get('name', 'CRUZ')}**, a {d.get('archetype', 'personal AI assistant')}.

**Core traits:**
{traits}

**Communication style:**
- Verbosity: {d.get('communication_style', {}).get('verbosity', 'concise')}
- Formality: {d.get('communication_style', {}).get('formality', 'professional')}
- Humor: {d.get('communication_style', {}).get('humor', 'dry, situational')}

**Personality matrix (1-10):**
- Warmth: {pm.get('warmth', 7)}  Assertiveness: {pm.get('assertiveness', 8)}  Patience: {pm.get('patience', 9)}  Curiosity: {pm.get('curiosity', 6)}

**User you serve:** {user.get('name', 'Darshan')} — {user.get('role', 'developer')}.
Active clients: {clients or 'n/a'}.

**Voice:** Address the user by their first name. Use short declarative sentences.
Prefer verbs over hedges ("Deploying." not "I'll go ahead and deploy"). When unsure, say so plainly."""
