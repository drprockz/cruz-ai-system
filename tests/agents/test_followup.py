import time
from unittest.mock import AsyncMock, patch
import pytest
from agents.followup.followup_agent import FollowupAgent
from services.proactive_engine import GateDecision


@pytest.fixture(autouse=True)
def _reset_proactive_engine_singleton():
    import services.proactive_engine as mod
    mod._instance = None
    yield
    mod._instance = None


@pytest.fixture
def agent():
    return FollowupAgent()


@pytest.mark.asyncio
async def test_outbound_event_appends_to_queue(agent):
    set_calls = []
    async def fake_set(*args, **kwargs):
        set_calls.append(args)
    state = AsyncMock(get=AsyncMock(return_value=[]), set=fake_set)
    with patch("agents.followup.followup_agent.get_state_service",
               return_value=state):
        await agent.process({
            "task": "event:webhook.gmail.outbound_sent",
            "context": {"event": {"trigger": "webhook.gmail.outbound_sent",
                                  "data": {"thread_id": "t1",
                                           "to": "ateet@ama.com"}}},
            "trace_id": "tr", "conversation_id": "",
        })
    # set called with new queue entry appended
    assert set_calls
    queue = set_calls[-1][2]  # 3rd positional arg is value
    assert any(e["thread_id"] == "t1" for e in queue)


@pytest.mark.asyncio
async def test_cron_emits_critical_for_5d_unanswered_client_email(agent):
    six_days_ago = time.time() - 6 * 86400
    queue = [{"thread_id": "t1", "client_email": "ateet@ama.com",
              "sent_at_ts": six_days_ago, "project_id": "ama-uuid",
              "due_date_iso": None}]
    state = AsyncMock(get=AsyncMock(return_value=queue), set=AsyncMock())
    emit_calls = []
    async def fake_emit(severity, reason, dedup_key, payload):
        emit_calls.append((severity, reason))
        return GateDecision.ALLOW
    with patch("agents.followup.followup_agent.get_state_service",
               return_value=state), \
         patch("agents.followup.followup_agent.fetch_thread_replied",
               AsyncMock(return_value=False)), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({
            "task": "event:cron.daily.10:00",
            "context": {"event": {"trigger": "cron.daily.10:00", "data": {}}},
            "trace_id": "tr", "conversation_id": "",
        })
    assert ("critical", "followup_due_5d") in emit_calls


@pytest.mark.asyncio
async def test_cron_skips_already_replied_threads(agent):
    six_days_ago = time.time() - 6 * 86400
    queue = [{"thread_id": "t1", "client_email": "x@y.com",
              "sent_at_ts": six_days_ago, "project_id": "p1"}]
    state = AsyncMock(get=AsyncMock(return_value=queue), set=AsyncMock())
    emit_calls = []
    async def fake_emit(*a, **k): emit_calls.append(a)
    with patch("agents.followup.followup_agent.get_state_service",
               return_value=state), \
         patch("agents.followup.followup_agent.fetch_thread_replied",
               AsyncMock(return_value=True)), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({
            "task": "event", "context": {"event": {"trigger": "cron.daily.10:00", "data": {}}},
            "trace_id": "tr", "conversation_id": "",
        })
    assert emit_calls == []


@pytest.mark.asyncio
async def test_dedup_key_is_per_thread(agent):
    six_days_ago = time.time() - 6 * 86400
    queue = [{"thread_id": "t-X", "client_email": "x@y.com",
              "sent_at_ts": six_days_ago, "project_id": "p1"}]
    state = AsyncMock(get=AsyncMock(return_value=queue), set=AsyncMock())
    captured = []
    async def fake_emit(severity, reason, dedup_key, payload):
        captured.append(dedup_key)
        return GateDecision.ALLOW
    with patch("agents.followup.followup_agent.get_state_service",
               return_value=state), \
         patch("agents.followup.followup_agent.fetch_thread_replied",
               AsyncMock(return_value=False)), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({
            "task": "event", "context": {"event": {"trigger": "cron.daily.10:00", "data": {}}},
            "trace_id": "tr", "conversation_id": "",
        })
    assert captured == ["thread:t-X"]
