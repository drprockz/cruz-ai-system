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
