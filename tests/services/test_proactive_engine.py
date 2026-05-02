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


# ── Dedup tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_first_warn_allows_then_dedup_suppresses(gate, fake_state):
    req = GateRequest(
        agent="x", severity="warn", reason_code=None,
        dedup_key="dup-1", payload={},
        valid_critical_reasons=set(),
    )
    assert await gate.allow(req) == GateDecision.ALLOW
    # Same dedup_key, second call → SUPPRESS
    assert await gate.allow(req) == GateDecision.SUPPRESS


@pytest.mark.asyncio
async def test_different_dedup_keys_both_allow(gate):
    # Different agents to avoid the per-agent cooldown
    req1 = GateRequest(agent="a", severity="warn", reason_code=None,
                       dedup_key="k1", payload={}, valid_critical_reasons=set())
    req2 = GateRequest(agent="b", severity="warn", reason_code=None,
                       dedup_key="k2", payload={}, valid_critical_reasons=set())
    assert await gate.allow(req1) == GateDecision.ALLOW
    assert await gate.allow(req2) == GateDecision.ALLOW


@pytest.mark.asyncio
async def test_dedup_expires_after_window(gate, fake_state):
    req = GateRequest(agent="x", severity="warn", reason_code=None,
                      dedup_key="exp", payload={}, valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.ALLOW
    # Manually expire dedup + cooldown
    fake_state.store.pop(("_gate", "dedup:x:exp"), None)
    fake_state.store.pop(("_gate", "cooldown:x:any"), None)
    assert await gate.allow(req) == GateDecision.ALLOW


# ── Cooldown tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_warn_after_cooldown_demotes_to_info(gate, fake_state):
    r1 = GateRequest(agent="x", severity="warn", reason_code=None,
                     dedup_key="k1", payload={}, valid_critical_reasons=set())
    r2 = GateRequest(agent="x", severity="warn", reason_code=None,
                     dedup_key="k2", payload={}, valid_critical_reasons=set())
    assert await gate.allow(r1) == GateDecision.ALLOW
    # Same agent, different dedup, within 1h → DEMOTE_TO_INFO
    assert await gate.allow(r2) == GateDecision.DEMOTE_TO_INFO


@pytest.mark.asyncio
async def test_info_within_cooldown_still_allows(gate):
    """Info isn't rate-limited at agent level."""
    r1 = GateRequest(agent="x", severity="info", reason_code=None,
                     dedup_key="k1", payload={}, valid_critical_reasons=set())
    r2 = GateRequest(agent="x", severity="info", reason_code=None,
                     dedup_key="k2", payload={}, valid_critical_reasons=set())
    assert await gate.allow(r1) == GateDecision.ALLOW
    assert await gate.allow(r2) == GateDecision.ALLOW


@pytest.mark.asyncio
async def test_critical_cooldown_suppresses_second_critical(gate):
    """Two criticals within 24h from same agent → second SUPPRESS."""
    valid = {"reason_a"}
    r1 = GateRequest(agent="x", severity="critical", reason_code="reason_a",
                     dedup_key="k1", payload={}, valid_critical_reasons=valid)
    r2 = GateRequest(agent="x", severity="critical", reason_code="reason_a",
                     dedup_key="k2", payload={}, valid_critical_reasons=valid)
    assert await gate.allow(r1) == GateDecision.ALLOW
    assert await gate.allow(r2) == GateDecision.SUPPRESS


# ── Global rate limit ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_global_daily_rate_limit_suppresses_warn(gate, fake_state):
    """8 non-info pings allowed, 9th SUPPRESSED."""
    today = ProactiveEngine._today()
    fake_state.store[("_global", f"daily_count:{today}")] = (8, None)
    req = GateRequest(agent="fresh_agent", severity="warn", reason_code=None,
                      dedup_key="k_overflow", payload={},
                      valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.SUPPRESS


@pytest.mark.asyncio
async def test_global_rate_limit_does_not_suppress_info(gate, fake_state):
    today = ProactiveEngine._today()
    fake_state.store[("_global", f"daily_count:{today}")] = (100, None)
    req = GateRequest(agent="fresh", severity="info", reason_code=None,
                      dedup_key="k_info", payload={},
                      valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.ALLOW


# ── Per-agent info safety cap ───────────────────────────────────

@pytest.mark.asyncio
async def test_info_cap_suppresses_after_20_per_agent_per_day(gate, fake_state):
    today = ProactiveEngine._today()
    fake_state.store[
        ("_global", f"info_count_per_agent:noisy:{today}")] = (20, None)
    req = GateRequest(agent="noisy", severity="info", reason_code=None,
                      dedup_key="k_cap", payload={},
                      valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.SUPPRESS


@pytest.mark.asyncio
async def test_info_cap_does_not_affect_other_agents(gate, fake_state):
    today = ProactiveEngine._today()
    fake_state.store[
        ("_global", f"info_count_per_agent:noisy:{today}")] = (50, None)
    req = GateRequest(agent="quiet", severity="info", reason_code=None,
                      dedup_key="k", payload={},
                      valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.ALLOW


# ── Counter increments ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_allow_increments_global_daily_count(gate, fake_state):
    req = GateRequest(agent="x", severity="warn", reason_code=None,
                      dedup_key="k1", payload={}, valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.ALLOW
    today = ProactiveEngine._today()
    cnt, _ = fake_state.store[("_global", f"daily_count:{today}")]
    assert cnt == 1


@pytest.mark.asyncio
async def test_demote_to_info_increments_info_counter_not_global(gate, fake_state):
    """The EFFECTIVE severity drives the counter."""
    fake_state.store[("_gate", "cooldown:x:any")] = (time.time(), None)
    req = GateRequest(agent="x", severity="warn", reason_code=None,
                      dedup_key="k1", payload={}, valid_critical_reasons=set())
    decision = await gate.allow(req)
    assert decision == GateDecision.DEMOTE_TO_INFO
    today = ProactiveEngine._today()
    info_cnt, _ = fake_state.store.get(
        ("_global", f"info_count_per_agent:x:{today}"), (0, None))
    assert info_cnt == 1
    assert ("_global", f"daily_count:{today}") not in fake_state.store


@pytest.mark.asyncio
async def test_suppress_increments_no_counter(gate, fake_state):
    today = ProactiveEngine._today()
    fake_state.store[("_global", f"daily_count:{today}")] = (8, None)
    req = GateRequest(agent="x", severity="warn", reason_code=None,
                      dedup_key="k", payload={}, valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.SUPPRESS
    cnt_after, _ = fake_state.store[("_global", f"daily_count:{today}")]
    assert cnt_after == 8  # unchanged


# ── Logging ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_every_decision_writes_to_agent_logs(gate, fake_db):
    req = GateRequest(agent="x", severity="info", reason_code=None,
                      dedup_key="k1",
                      payload={"trace_id": "trace-1"},
                      valid_critical_reasons=set())
    await gate.allow(req)
    # one INSERT row, action='gate_decision'
    assert len(fake_db.calls) == 1
    sql, args = fake_db.calls[0]
    assert "INSERT INTO agent_logs" in sql
    assert args[0] == "trace-1"
    assert args[1] == "x"
    assert args[2] == "allow"  # decision


@pytest.mark.asyncio
async def test_cached_get_called_for_cooldown_and_dedup(monkeypatch, gate):
    """`_decide` reads dedup + cooldown:any through the cache wrapper."""
    from typing import Any
    calls: list[tuple[str, str]] = []
    original = gate._cached_get
    async def spy(agent: str, key: str, default: Any = None) -> Any:
        calls.append((agent, key))
        return await original(agent, key, default)
    monkeypatch.setattr(gate, "_cached_get", spy)

    req = GateRequest(agent="x", severity="warn", reason_code=None,
                      dedup_key="hot1", payload={},
                      valid_critical_reasons=set())
    await gate.allow(req)
    keys_read = {k for _, k in calls}
    assert "dedup:x:hot1" in keys_read
    assert "cooldown:x:any" in keys_read


@pytest.mark.asyncio
async def test_counter_reads_bypass_cache(monkeypatch, gate):
    """Counter read-modify-write paths MUST stay on uncached state.get
    to avoid 60s-stale cache losing increments."""
    from typing import Any
    cached_calls: list[str] = []
    state_calls: list[str] = []
    orig_cached = gate._cached_get
    orig_state = gate._state.get

    async def cached_spy(agent, key, default=None):
        cached_calls.append(key)
        return await orig_cached(agent, key, default)

    async def state_spy(agent, key, default=None):
        state_calls.append(key)
        return await orig_state(agent, key, default)

    monkeypatch.setattr(gate, "_cached_get", cached_spy)
    monkeypatch.setattr(gate._state, "get", state_spy)

    today = ProactiveEngine._today()
    req = GateRequest(agent="x", severity="warn", reason_code=None,
                      dedup_key="k_cnt", payload={},
                      valid_critical_reasons=set())
    await gate.allow(req)

    daily_key = f"daily_count:{today}"
    assert daily_key in state_calls, "counter read must bypass cache"
    assert daily_key not in cached_calls, "counter must NOT be cached"


@pytest.mark.asyncio
async def test_cache_invalidate_called_after_each_set(monkeypatch, gate):
    invalidated: list[tuple[str, str]] = []
    orig = gate._cache_invalidate
    async def spy(agent, key):
        invalidated.append((agent, key))
        await orig(agent, key)
    monkeypatch.setattr(gate, "_cache_invalidate", spy)

    req = GateRequest(agent="x", severity="critical", reason_code="r1",
                      dedup_key="k_inv", payload={},
                      valid_critical_reasons={"r1"})
    await gate.allow(req)
    invalidated_keys = {k for _, k in invalidated}
    assert "cooldown:x:any" in invalidated_keys
    assert "cooldown:x:critical" in invalidated_keys
    assert "dedup:x:k_inv" in invalidated_keys
