"""EventDrivenAgent — base class for SP5 event-driven agents.

Verifies:
  - Class-level TRIGGERS, CRITICAL_REASONS, KNOWLEDGE_RINGS declarations
  - emit() builds GateRequest from class declarations and routes via gate
  - emit() consults gate decision and routes to NotificationRouter accordingly
  - SUPPRESS does not route
  - DEMOTE_TO_WARN routes at warn severity
  - DEMOTE_TO_INFO routes at info severity
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from agents.event_driven_agent import EventDrivenAgent
from services.proactive_engine import GateDecision, GateRequest


class _FixtureAgent(EventDrivenAgent):
    """Minimal subclass used only by these tests."""

    KNOWLEDGE_RINGS = ["cruz_activities"]
    TRIGGERS = ["cron.test.hourly"]
    CRITICAL_REASONS = {
        "test_critical_reason": "for tests",
    }

    async def process(self, input: AgentInput) -> AgentOutput:
        return AgentOutput(
            success=True, result="ok", agent=self.name,
            duration_ms=0, tokens_used=0, error=None,
            requires_approval=False, approval_prompt=None,
        )


@pytest.fixture
def agent():
    return _FixtureAgent()


def test_subclass_inherits_event_driven_attributes(agent):
    assert agent.KNOWLEDGE_RINGS == ["cruz_activities"]
    assert agent.TRIGGERS == ["cron.test.hourly"]
    assert agent.CRITICAL_REASONS == {"test_critical_reason": "for tests"}


def test_default_class_attributes_are_empty():
    class Empty(EventDrivenAgent):
        async def process(self, input):
            return None
    e = Empty()
    assert e.KNOWLEDGE_RINGS == []
    assert e.TRIGGERS == []
    assert e.CRITICAL_REASONS == {}


@pytest.mark.asyncio
async def test_emit_builds_gate_request_from_class_attrs(agent):
    """emit() passes self.CRITICAL_REASONS.keys() into GateRequest."""
    captured: list[GateRequest] = []
    async def fake_allow(req: GateRequest) -> GateDecision:
        captured.append(req)
        return GateDecision.ALLOW

    fake_router = AsyncMock()

    with patch("agents.event_driven_agent.get_proactive_engine") as eng, \
         patch("agents.event_driven_agent.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=fake_allow)
        router.return_value = fake_router
        await agent.emit("critical", "test_critical_reason",
                         "k1", {"text": "hi"})

    assert len(captured) == 1
    req = captured[0]
    assert req.agent == "_FixtureAgent"
    assert req.severity == "critical"
    assert req.reason_code == "test_critical_reason"
    assert req.dedup_key == "k1"
    assert req.payload == {"text": "hi", "agent": "_FixtureAgent", "dedup_key": "k1"}
    assert req.valid_critical_reasons == {"test_critical_reason"}
    fake_router.route.assert_awaited_once_with(
        "critical",
        {"text": "hi", "agent": "_FixtureAgent", "dedup_key": "k1"},
    )


@pytest.mark.asyncio
async def test_emit_allow_routes_at_requested_severity(agent):
    fake_router = AsyncMock()
    with patch("agents.event_driven_agent.get_proactive_engine") as eng, \
         patch("agents.event_driven_agent.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=AsyncMock(return_value=GateDecision.ALLOW))
        router.return_value = fake_router
        decision = await agent.emit("warn", None, "k", {"text": "x"})
    assert decision == GateDecision.ALLOW
    fake_router.route.assert_awaited_once_with(
        "warn", {"text": "x", "agent": "_FixtureAgent", "dedup_key": "k"}
    )


@pytest.mark.asyncio
async def test_emit_demote_to_warn_routes_at_warn(agent):
    fake_router = AsyncMock()
    with patch("agents.event_driven_agent.get_proactive_engine") as eng, \
         patch("agents.event_driven_agent.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=AsyncMock(return_value=GateDecision.DEMOTE_TO_WARN))
        router.return_value = fake_router
        await agent.emit("critical", "wrong_code", "k", {"text": "x"})
    fake_router.route.assert_awaited_once_with(
        "warn", {"text": "x", "agent": "_FixtureAgent", "dedup_key": "k"}
    )


@pytest.mark.asyncio
async def test_emit_demote_to_info_routes_at_info(agent):
    fake_router = AsyncMock()
    with patch("agents.event_driven_agent.get_proactive_engine") as eng, \
         patch("agents.event_driven_agent.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=AsyncMock(return_value=GateDecision.DEMOTE_TO_INFO))
        router.return_value = fake_router
        await agent.emit("warn", None, "k", {"text": "x"})
    fake_router.route.assert_awaited_once_with(
        "info", {"text": "x", "agent": "_FixtureAgent", "dedup_key": "k"}
    )


@pytest.mark.asyncio
async def test_emit_suppress_does_not_route(agent):
    fake_router = AsyncMock()
    with patch("agents.event_driven_agent.get_proactive_engine") as eng, \
         patch("agents.event_driven_agent.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=AsyncMock(return_value=GateDecision.SUPPRESS))
        router.return_value = fake_router
        decision = await agent.emit("warn", None, "k", {"text": "x"})
    assert decision == GateDecision.SUPPRESS
    fake_router.route.assert_not_awaited()


@pytest.mark.asyncio
async def test_emit_payload_carries_agent_and_dedup_key_for_telegram_button(agent):
    """TelegramChannel reads payload['agent'] and payload['dedup_key']
    to build the False-alarm callback. emit() must inject these."""
    captured: list[dict] = []
    async def fake_route(severity, payload):
        captured.append(payload)

    with patch("agents.event_driven_agent.get_proactive_engine") as eng, \
         patch("agents.event_driven_agent.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=AsyncMock(return_value=GateDecision.ALLOW))
        router.return_value = AsyncMock(route=fake_route)
        await agent.emit("critical", "test_critical_reason",
                         "email:abc", {"text": "URGENT"})
    p = captured[0]
    assert p["agent"] == "_FixtureAgent"
    assert p["dedup_key"] == "email:abc"
    assert p["text"] == "URGENT"
