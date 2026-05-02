# tests/services/test_proactive_engine.py
"""ProactiveEngine gate — type contract tests come first."""

from __future__ import annotations

import pytest

from services.proactive_engine import GateDecision, GateRequest


def test_gate_decision_has_four_outcomes():
    assert {d.value for d in GateDecision} == {
        "allow", "suppress", "demote_warn", "demote_info"
    }


def test_gate_request_requires_severity():
    with pytest.raises(TypeError):
        GateRequest(agent="x", reason_code=None, dedup_key="k", payload={},
                    valid_critical_reasons=set())  # missing severity


def test_gate_request_accepts_valid_critical_reasons_set():
    req = GateRequest(
        agent="reply_triage",
        severity="critical",
        reason_code="client_email_unanswered_72h",
        dedup_key="email:abc",
        payload={"text": "..."},
        valid_critical_reasons={"client_email_unanswered_72h"},
    )
    assert req.severity == "critical"
    assert req.valid_critical_reasons == {"client_email_unanswered_72h"}


import time
from typing import Any
from services.proactive_engine import ProactiveEngine, get_proactive_engine


@pytest.fixture(autouse=True)
def _reset_proactive_engine_singleton():
    """Insulate tests from any code path that calls get_proactive_engine()
    against a real DB. Reset before AND after every test."""
    import services.proactive_engine as mod
    mod._instance = None
    yield
    mod._instance = None


class FakeStateService:
    """In-memory StateService for fast unit tests — no DB required."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], tuple[Any, float | None]] = {}

    async def get(self, agent: str, key: str, default: Any = None) -> Any:
        v = self.store.get((agent, key))
        if v is None:
            return default
        value, expires = v
        if expires is not None and expires <= time.time():
            return default
        return value

    async def set(self, agent: str, key: str, value: Any,
                  ttl_seconds: int | None = None) -> None:
        expires = time.time() + ttl_seconds if ttl_seconds else None
        self.store[(agent, key)] = (value, expires)

    async def delete(self, agent: str, key: str) -> None:
        self.store.pop((agent, key), None)


class FakeDB:
    """Records execute() calls so we can assert agent_logs writes happened."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    async def execute(self, sql: str, *args) -> str:
        self.calls.append((sql, args))
        return "INSERT 0 1"


@pytest.fixture
def fake_state():
    return FakeStateService()


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def gate(fake_state, fake_db):
    return ProactiveEngine(fake_state, fake_db)


# ── Whitelist tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_critical_without_reason_code_demotes_to_warn(gate):
    req = GateRequest(
        agent="x", severity="critical", reason_code=None,
        dedup_key="k1", payload={},
        valid_critical_reasons={"some_reason"},
    )
    decision = await gate.allow(req)
    assert decision == GateDecision.DEMOTE_TO_WARN


@pytest.mark.asyncio
async def test_critical_with_unwhitelisted_reason_demotes_to_warn(gate):
    req = GateRequest(
        agent="x", severity="critical", reason_code="invented_reason",
        dedup_key="k1", payload={},
        valid_critical_reasons={"only_this_one_is_valid"},
    )
    assert await gate.allow(req) == GateDecision.DEMOTE_TO_WARN


@pytest.mark.asyncio
async def test_critical_with_whitelisted_reason_allows(gate):
    req = GateRequest(
        agent="x", severity="critical", reason_code="valid_reason",
        dedup_key="k1", payload={},
        valid_critical_reasons={"valid_reason"},
    )
    assert await gate.allow(req) == GateDecision.ALLOW
