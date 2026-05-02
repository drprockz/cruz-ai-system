"""dispatch_event_to_agent — ARQ task that runs an EventDrivenAgent
in response to a registered trigger event."""

from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest

from workers.tasks.dispatch import dispatch_event_to_agent


@pytest.mark.asyncio
async def test_dispatch_imports_class_and_calls_process():
    """dispatch_event_to_agent dynamically imports the agent class,
    instantiates it, and calls process() with the event payload."""
    fake_process = AsyncMock(return_value={
        "success": True, "result": "did-thing", "agent": "F",
        "duration_ms": 10, "tokens_used": 0, "error": None,
        "requires_approval": False, "approval_prompt": None,
    })
    fake_class = type("F", (), {})
    fake_instance = type("FI", (), {"process": fake_process})()

    with patch("workers.tasks.dispatch._import_class",
               return_value=lambda: fake_instance):
        result = await dispatch_event_to_agent(
            ctx={},
            module_path="agents.fake.fake_agent",
            class_name="FakeAgent",
            event={"trigger": "cron.x", "data": {"y": 1}},
        )
    fake_process.assert_awaited_once()
    call_args = fake_process.await_args.args[0]
    assert call_args["context"]["event"] == {"trigger": "cron.x", "data": {"y": 1}}
    assert call_args["task"].startswith("event:")
    assert "trace_id" in call_args
    assert result["success"] is True


@pytest.mark.asyncio
async def test_dispatch_swallows_agent_errors_returns_failure_dict():
    """Agent exceptions become a failure dict — never raised. ARQ retries
    are surfaced via the after_job_end hook in arq_worker.py."""
    fake_instance = type("X", (), {
        "process": AsyncMock(side_effect=RuntimeError("oops")),
    })()
    with patch("workers.tasks.dispatch._import_class",
               return_value=lambda: fake_instance):
        result = await dispatch_event_to_agent(
            ctx={},
            module_path="agents.fake.fake_agent",
            class_name="FakeAgent",
            event={"trigger": "x", "data": {}},
        )
    assert result["success"] is False
    assert "oops" in result["error"]


@pytest.mark.asyncio
async def test_dispatch_propagates_trace_id_when_present():
    """If event carries a trace_id (from a webhook), reuse it."""
    fake_instance = type("X", (), {
        "process": AsyncMock(return_value={
            "success": True, "result": "ok", "agent": "X", "duration_ms": 0,
            "tokens_used": 0, "error": None, "requires_approval": False,
            "approval_prompt": None,
        }),
    })()
    with patch("workers.tasks.dispatch._import_class",
               return_value=lambda: fake_instance):
        await dispatch_event_to_agent(
            ctx={},
            module_path="m", class_name="C",
            event={"trigger": "t", "trace_id": "given-trace-7", "data": {}},
        )
    call_args = fake_instance.process.await_args.args[0]
    assert call_args["trace_id"] == "given-trace-7"
