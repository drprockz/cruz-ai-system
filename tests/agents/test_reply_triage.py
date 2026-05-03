"""ReplyTriageAgent — gate-determining agent for SP5 exit gate."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from typing import Any

import pytest

from agents.reply_triage.reply_triage_agent import ReplyTriageAgent
from services.proactive_engine import GateDecision


@pytest.fixture(autouse=True)
def _reset_proactive_engine_singleton():
    import services.proactive_engine as mod
    mod._instance = None
    yield
    mod._instance = None


@pytest.fixture
def agent():
    return ReplyTriageAgent()


def test_class_attrs_match_spec(agent):
    assert agent.KNOWLEDGE_RINGS == ["cruz_activities", "cruz_user_patterns"]
    assert "webhook.gmail.new_message" in agent.TRIGGERS
    assert "cron.5min.gmail_poll" in agent.TRIGGERS
    assert "client_email_unanswered_72h" in agent.CRITICAL_REASONS


@pytest.mark.asyncio
async def test_process_classifies_via_llm_and_caches_result(agent):
    """LLM returns a classification dict; agent stores it in state."""
    fake_msg = {
        "id": "msg-1", "subject": "AMA — production down",
        "from": "ateet@ama.com", "body": "the site is broken",
        "thread_id": "t1", "date": "2026-04-26T10:00:00Z",
    }
    fake_classification = {
        "label": "needs_reply", "urgency": "now",
        "client_match": "ama-uuid", "confidence": 0.9,
        "reason": "explicit production incident",
    }
    fake_state_set = AsyncMock()
    with patch("agents.reply_triage.reply_triage_agent.fetch_message",
               AsyncMock(return_value=fake_msg)), \
         patch("agents.reply_triage.reply_triage_agent._classify_email",
               AsyncMock(return_value=fake_classification)), \
         patch("agents.reply_triage.reply_triage_agent._resolve_client_match",
               AsyncMock(return_value="ama-uuid")), \
         patch("agents.reply_triage.reply_triage_agent._email_age_hours",
               return_value=80), \
         patch("agents.reply_triage.reply_triage_agent.get_state_service",
               return_value=AsyncMock(set=fake_state_set, get=AsyncMock(return_value=None))), \
         patch.object(agent, "emit",
                      AsyncMock(return_value=GateDecision.ALLOW)):
        result = await agent.process({
            "task": "event:webhook.gmail.new_message",
            "context": {"event": {"data": {"message_id": "msg-1"}}},
            "trace_id": "tr-1",
            "conversation_id": "",
        })
    assert result["success"] is True
    fake_state_set.assert_awaited()  # classification cached


@pytest.mark.asyncio
async def test_critical_only_when_all_four_conditions_hold(agent):
    """needs_reply + urgency now/today + client_match + age>72h → critical."""
    fake_msg = {"id": "m1", "subject": "x", "from": "ateet@ama.com",
                "body": "hi", "thread_id": "t", "date": ""}
    cases = [
        # (label, urgency, client_match, age_hours, expected_severity_arg)
        ("needs_reply", "now", "ama-uuid", 80, "critical"),
        ("needs_reply", "now", "ama-uuid", 50, "warn"),  # too young
        ("needs_reply", "now", None,        80, "warn"),  # no client
        ("needs_reply", "this_week", "ama-uuid", 80, "warn"),  # not urgent
        ("fyi",        "now", "ama-uuid", 80, "info"),  # not needs_reply
    ]
    for label, urgency, client, age, expected_sev in cases:
        emit_calls = []
        async def fake_emit(severity, reason, dedup_key, payload):
            emit_calls.append(severity)
            return GateDecision.ALLOW
        with patch("agents.reply_triage.reply_triage_agent.fetch_message",
                   AsyncMock(return_value=fake_msg)), \
             patch("agents.reply_triage.reply_triage_agent._classify_email",
                   AsyncMock(return_value={
                       "label": label, "urgency": urgency,
                       "client_match": client, "confidence": 0.9,
                       "reason": "test",
                   })), \
             patch("agents.reply_triage.reply_triage_agent._resolve_client_match",
                   AsyncMock(return_value=client)), \
             patch("agents.reply_triage.reply_triage_agent._email_age_hours",
                   return_value=age), \
             patch("agents.reply_triage.reply_triage_agent.get_state_service",
                   return_value=AsyncMock(set=AsyncMock(),
                                           get=AsyncMock(return_value=None))), \
             patch.object(agent, "emit", fake_emit):
            await agent.process({
                "task": "event:webhook.gmail.new_message",
                "context": {"event": {"data": {"message_id": "m1"}}},
                "trace_id": "tr", "conversation_id": "",
            })
        assert emit_calls == [expected_sev], (
            f"label={label} urgency={urgency} client={client} age={age}: "
            f"expected emit at {expected_sev!r}, got {emit_calls!r}"
        )


@pytest.mark.asyncio
async def test_dedup_key_uses_message_id(agent):
    fake_msg = {"id": "m-uniq", "subject": "x", "from": "x@y.com",
                "body": "", "thread_id": "t", "date": ""}
    captured_dedup = []
    async def fake_emit(severity, reason, dedup_key, payload):
        captured_dedup.append(dedup_key)
        return GateDecision.ALLOW
    with patch("agents.reply_triage.reply_triage_agent.fetch_message",
               AsyncMock(return_value=fake_msg)), \
         patch("agents.reply_triage.reply_triage_agent._classify_email",
               AsyncMock(return_value={"label": "fyi", "urgency": "later",
                                        "client_match": None, "confidence": 0.5,
                                        "reason": ""})), \
         patch("agents.reply_triage.reply_triage_agent._resolve_client_match",
               AsyncMock(return_value=None)), \
         patch("agents.reply_triage.reply_triage_agent._email_age_hours",
               return_value=10), \
         patch("agents.reply_triage.reply_triage_agent.get_state_service",
               return_value=AsyncMock(set=AsyncMock(),
                                       get=AsyncMock(return_value=None))), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({
            "task": "event", "context": {"event": {"data": {"message_id": "m-uniq"}}},
            "trace_id": "t", "conversation_id": "",
        })
    assert captured_dedup == ["email:m-uniq"]


@pytest.mark.asyncio
async def test_skips_if_already_classified(agent):
    """If state has a prior classification for this message, skip LLM call."""
    cached = {"label": "fyi", "urgency": "later", "client_match": None,
              "confidence": 0.5, "reason": "cached"}
    fake_msg = {"id": "m1", "subject": "x", "from": "x@y.com", "body": "",
                "thread_id": "t", "date": ""}
    classify_mock = AsyncMock()
    with patch("agents.reply_triage.reply_triage_agent.fetch_message",
               AsyncMock(return_value=fake_msg)), \
         patch("agents.reply_triage.reply_triage_agent._classify_email",
               classify_mock), \
         patch("agents.reply_triage.reply_triage_agent.get_state_service",
               return_value=AsyncMock(get=AsyncMock(return_value=cached),
                                       set=AsyncMock())), \
         patch.object(agent, "emit", AsyncMock(return_value=GateDecision.ALLOW)):
        await agent.process({
            "task": "event", "context": {"event": {"data": {"message_id": "m1"}}},
            "trace_id": "t", "conversation_id": "",
        })
    classify_mock.assert_not_awaited()
