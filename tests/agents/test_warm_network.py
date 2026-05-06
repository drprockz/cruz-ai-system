"""WarmNetworkAgent — SP5 §4.5 + §1.2.

Stub-mode pre-SP4: returns success+stub, no state writes, no router calls,
no external I/O. The real LinkedIn-driven ranking lands when SP4 ships
its headless-browser service.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.warm_network.warm_network_agent import WarmNetworkAgent


@pytest.fixture
def agent():
    return WarmNetworkAgent()


def _input(trace_id: str = "trace-warm-1") -> dict:
    return {
        "task": "weekly warm-network nudge",
        "context": {},
        "trace_id": trace_id,
        "conversation_id": "conv-warm-1",
    }


def test_class_attrs_match_spec(agent):
    assert agent.KNOWLEDGE_RINGS == ["cruz_activities", "cruz_user_patterns"]
    assert agent.TRIGGERS == ["cron.weekly.monday.09:00"]
    assert agent.CRITICAL_REASONS == {}


@pytest.mark.asyncio
async def test_stub_mode_returns_success_no_emit(agent):
    """Pre-SP4 path: services.browser doesn't exist, so the probe returns
    False and process() returns success+stub without ever calling emit()."""
    with patch.object(WarmNetworkAgent, "emit", new=AsyncMock()) as mock_emit:
        out = await agent.process(_input())

    assert out["success"] is True
    assert out["result"] == "stub"
    assert out["agent"] == agent.name
    assert out["duration_ms"] == 0
    assert out["tokens_used"] == 0
    assert out["error"] is None
    assert out["requires_approval"] is False
    assert out["approval_prompt"] is None
    mock_emit.assert_not_called()


@pytest.mark.asyncio
async def test_stub_mode_does_not_call_state_or_router(agent):
    """Pre-SP4 stub must touch zero shared services — no state writes, no
    notification routing, no proactive-engine gate calls."""
    with patch(
        "agents.warm_network.warm_network_agent._sp4_browser_available",
        return_value=False,
    ), patch(
        "services.agent_state.get_state_service"
    ) as mock_state, patch(
        "services.notification_router.get_notification_router"
    ) as mock_router, patch(
        "services.proactive_engine.get_proactive_engine"
    ) as mock_engine:
        out = await agent.process(_input())

    assert out["success"] is True
    assert out["result"] == "stub"
    mock_state.assert_not_called()
    mock_router.assert_not_called()
    mock_engine.assert_not_called()


@pytest.mark.skip(reason="SP4 not yet shipped")
@pytest.mark.asyncio
async def test_post_sp4_path_marker(agent):
    """Placeholder for the real ranking flow once SP4's browser lands.

    TODO(SP4): exercise the post-SP4 branch end-to-end:
      - patch services.browser.get_browser_service so _sp4_browser_available()
        returns True;
      - feed a fixture set of LinkedIn contacts + Gmail thread recencies;
      - assert WarmNetworkAgent emits one "warn" per top-ranked contact
        with dedup_key=f"last_nudge:{contact_id}";
      - assert no critical emits (CRITICAL_REASONS == {}).
    """
    pass
