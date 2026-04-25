"""Tests for the CRUZ persona v1 modules."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from agents.cruz.persona.behavior_engine import decide, style_hint
from agents.cruz.persona.explainability import build_explanation
from agents.cruz.persona.humor_engine import decide as humor_decide
from agents.cruz.persona.identity_loader import IdentityLoader
from agents.cruz.persona.language_patterns import apply_vocabulary, greeting
from agents.cruz.persona.privacy_engine import sanitize, find
from agents.cruz.persona.relationship_memory import RelationshipMemory


# ───── identity_loader ─────

def test_identity_loader_returns_name_cruz():
    snippet = IdentityLoader.system_prompt_snippet()
    assert "CRUZ" in snippet
    assert "Darshan" in snippet
    assert "Warmth:" in snippet


def test_identity_loader_credits_creator_darshan_drprockz():
    """System prompt must pin the creator so the model doesn't hallucinate
    that Anthropic/OpenAI built CRUZ when the user asks who made it."""
    snippet = IdentityLoader.system_prompt_snippet()
    assert "Darshan Parmar" in snippet
    assert "drprockz" in snippet
    # Explicit guard against the model crediting the wrong entity.
    assert "Anthropic" in snippet  # …named only to instruct *not* to credit it
    assert "who created you" in snippet or "created you" in snippet.lower()


def test_identity_reload_bypasses_cache():
    d1 = IdentityLoader.load()
    d2 = IdentityLoader.reload()
    assert d1["name"] == d2["name"] == "CRUZ"


# ───── language_patterns ─────

def test_apply_vocabulary_replaces_okay():
    assert apply_vocabulary("okay, done") == "noted, done"
    assert apply_vocabulary("Okay.") == "Noted."
    assert apply_vocabulary("OKAY") == "NOTED"


def test_apply_vocabulary_skips_code_blocks():
    src = "Here's how: ```python\nokay = 1\n```\nAnd okay for prose."
    out = apply_vocabulary(src)
    assert "okay = 1" in out  # code untouched
    assert "noted for prose" in out


def test_greeting_picks_by_hour():
    morning = datetime(2026, 4, 18, 9, 0)
    night = datetime(2026, 4, 18, 23, 0)
    assert "Morning" in greeting("Darshan", morning)
    assert "Darshan" in greeting("Darshan", night)


# ───── behavior_engine ─────

def test_behavior_late_night_trims_to_brief():
    style = decide(
        task="explain the architecture of the voice pipeline",
        device="mac_web",
        now=datetime(2026, 4, 18, 23, 30),
    )
    assert style.depth == "brief"
    assert "late night" in style.reason


def test_behavior_complex_task_on_desk_goes_detailed():
    style = decide(
        task="refactor the worker's audio pipeline to handle barge-in better",
        device="mac_web",
        now=datetime(2026, 4, 18, 14, 0),
    )
    assert style.depth == "detailed"


def test_behavior_phone_always_ultra_brief():
    style = decide(
        task="what time is it",
        device="phone",
        now=datetime(2026, 4, 18, 14, 0),
    )
    assert style.depth == "ultra_brief"


def test_behavior_style_hint_mentions_depth():
    style = decide(task="hi", device="mac_web", now=datetime(2026, 4, 18, 14, 0))
    hint = style_hint(style)
    assert style.depth in hint


# ───── privacy_engine ─────

def test_privacy_redacts_api_keys():
    text = "my key is sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
    out = sanitize(text)
    assert "sk-ant" not in out
    assert "[REDACTED_API_KEY]" in out


def test_privacy_redacts_private_key_block():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
    out = sanitize(text)
    assert "MIIEpAIBAAKCAQEA" not in out
    assert "[REDACTED_PRIVATE_KEY]" in out


def test_privacy_redacts_url_password():
    out = sanitize("connect to postgres://cruz:Drp%40100@localhost/db")
    assert "Drp%40100" not in out
    assert "[REDACTED_PW]" in out


def test_privacy_find_returns_labels():
    hits = find("key sk-ant-123456789012345678901234567890")
    assert any(label == "API_KEY" for label, _ in hits)


def test_privacy_sanitize_empty_safe():
    assert sanitize("") == ""
    assert sanitize(None) is None  # type: ignore[arg-type]


# ───── humor_engine ─────

def test_humor_forbidden_during_production():
    perm = humor_decide(
        now=datetime(2026, 4, 18, 23, 0),
        touched_production=True,
        last_user_message="deploy ama",
    )
    assert perm.allowed is False
    assert "production" in perm.reason


def test_humor_forbidden_after_error():
    perm = humor_decide(
        now=datetime(2026, 4, 18, 23, 0),
        last_turn_errored=True,
        last_user_message="hi",
    )
    assert perm.allowed is False


def test_humor_allowed_late_night():
    perm = humor_decide(
        now=datetime(2026, 4, 18, 23, 30),
        last_user_message="still here",
    )
    assert perm.allowed is True
    assert perm.bank == "late_night_casual"


def test_humor_allowed_after_successful_multi_step():
    perm = humor_decide(
        now=datetime(2026, 4, 18, 14, 0),
        last_user_message="that worked",
        task_completed_with_tools=4,
    )
    assert perm.allowed is True


# ───── relationship_memory ─────

@pytest.mark.asyncio
async def test_relationship_profile_handles_db_errors_gracefully():
    class BadDB:
        async def fetchrow(self, *a, **kw):
            raise RuntimeError("db down")
        async def fetch(self, *a, **kw):
            raise RuntimeError("db down")

    mem = RelationshipMemory()
    profile = await mem.build_user_profile(BadDB(), user_id="darshan", force=True)
    assert profile.user_id == "darshan"
    # Should return a zeroed profile, not throw
    assert profile.total_turns == 0


@pytest.mark.asyncio
async def test_relationship_profile_uses_db_aggregates():
    class FakeDB:
        async def fetchrow(self, query, *a):
            if "COUNT(*)::int AS n" in query and "agent_logs" in query:
                return {"n": 42}
            if "COUNT(*)::int AS total, SUM" in query and "error" in query.lower():
                return {"total": 100, "errs": 5}
            if "voice_session_id IS NOT NULL" in query:
                return {"total": 10, "voice": 6}
            if "approval_requests" in query:
                return {"a": 18, "decided": 20}
            return None
        async def fetch(self, query, *a):
            if "agent, COUNT" in query:
                return [{"agent": "forge", "n": 15}, {"agent": "qt", "n": 10}]
            if "EXTRACT(hour" in query:
                return [{"h": 9, "n": 5}, {"h": 14, "n": 10}, {"h": 22, "n": 3}]
            return []

    mem = RelationshipMemory()
    profile = await mem.build_user_profile(FakeDB(), user_id="darshan", force=True)
    assert profile.total_turns == 42
    assert profile.top_agents == ["forge", "qt"]
    assert profile.error_rate_7d == 0.05
    assert profile.voice_fraction == 0.6
    assert profile.approval_rate == 0.9


# ───── explainability ─────

@pytest.mark.asyncio
async def test_explainability_returns_none_for_unknown_trace():
    class FakeDB:
        async def fetch(self, *a, **kw): return []
    ex = await build_explanation(FakeDB(), "does-not-exist")
    assert ex is None


@pytest.mark.asyncio
async def test_explainability_builds_chain():
    class FakeDB:
        async def fetch(self, *a, **kw):
            return [
                {
                    "agent": "CRUZ", "action": "process", "status": "success",
                    "duration_ms": 1200, "tokens_used": 900,
                    "input_data": {"task": "deploy ama"},
                    "output_data": {"result": "tests pass, deploying"},
                    "created_at": "2026-04-18T10:00:00Z",
                },
                {
                    "agent": "qt", "action": "test", "status": "success",
                    "duration_ms": 3200, "tokens_used": 0,
                    "input_data": {"task": "run pytest"},
                    "output_data": {"result": "12/12 pass"},
                    "created_at": "2026-04-18T10:00:03Z",
                },
            ]
    ex = await build_explanation(FakeDB(), "trace-1")
    assert ex is not None
    assert ex.trace_id == "trace-1"
    assert ex.final_status == "success"
    assert ex.total_tokens == 900
    assert ex.total_duration_ms == 4400
    assert len(ex.steps) == 2
    d = ex.to_dict()
    assert "headline" in d
    assert "steps" in d
