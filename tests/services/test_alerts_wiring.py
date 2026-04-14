"""
Wiring tests: AlertService is invoked on CruzAgent unhandled exception,
TITAN deploy failure, and ARQ worker task failure.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_cruz_agent_alerts_on_unhandled_exception():
    from agents.cruz.cruz_agent import CruzAgent

    agent = CruzAgent()
    mock_alert = AsyncMock(return_value={"telegram": True, "sentry": False})

    with patch("agents.cruz.cruz_agent.get_alert_service") as gs, \
         patch("agents.cruz.cruz_agent.ConversationService",
               side_effect=RuntimeError("boom")), \
         patch.object(agent, "log", new=AsyncMock()):
        gs.return_value = MagicMock(notify=mock_alert)
        out = await agent.process({
            "task": "t", "context": {}, "trace_id": "trace-1", "conversation_id": "c1",
        })
    assert out["success"] is False
    mock_alert.assert_awaited()
    args, kwargs = mock_alert.await_args
    assert args[0] == "critical"
    assert "CRUZ" in args[1] or "cruz" in args[1].lower()


@pytest.mark.asyncio
async def test_titan_alerts_on_deploy_failure():
    from agents.titan.titan_agent import TitanAgent

    agent = TitanAgent()
    mock_alert = AsyncMock(return_value={"telegram": True, "sentry": False})

    with patch("agents.titan.titan_agent.get_alert_service") as gs, \
         patch.object(agent, "_deploy_vercel",
                      new=AsyncMock(return_value=({"target": "vercel", "error": "502"}, False))), \
         patch.object(agent, "_rollback", new=AsyncMock(return_value={"rolled_back": True})), \
         patch.object(agent, "log", new=AsyncMock()):
        gs.return_value = MagicMock(notify=mock_alert)
        out = await agent.process({
            "task": "deploy",
            "context": {"target": "vercel", "project": "ama",
                        "auto_rollback": True, "qt_passed": True},
            "trace_id": "trace-titan",
            "conversation_id": "c1",
        })
    assert out["success"] is False
    mock_alert.assert_awaited()
    args, _ = mock_alert.await_args
    assert args[0] in ("critical", "warning")
    assert "deploy" in args[1].lower() or "titan" in args[1].lower()


@pytest.mark.asyncio
async def test_worker_task_failure_triggers_alert():
    """The ARQ on_job_end hook should notify on failed jobs."""
    from workers.arq_worker import on_job_end

    mock_alert = AsyncMock(return_value={"telegram": True, "sentry": False})
    ctx = {
        "job_id": "j1",
        "function": "run_reach",
        "success": False,
        "exception": RuntimeError("kapow"),
    }
    with patch("workers.arq_worker.get_alert_service") as gs:
        gs.return_value = MagicMock(notify=mock_alert)
        await on_job_end(ctx)
    mock_alert.assert_awaited()
    args, _ = mock_alert.await_args
    assert args[0] == "critical"
    assert "run_reach" in args[2] or "run_reach" in args[1]


@pytest.mark.asyncio
async def test_worker_task_success_does_not_alert():
    from workers.arq_worker import on_job_end
    mock_alert = AsyncMock()
    ctx = {"job_id": "j2", "function": "run_pulse", "success": True}
    with patch("workers.arq_worker.get_alert_service") as gs:
        gs.return_value = MagicMock(notify=mock_alert)
        await on_job_end(ctx)
    mock_alert.assert_not_awaited()
