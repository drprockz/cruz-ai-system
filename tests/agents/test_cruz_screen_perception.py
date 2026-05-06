"""Integration tests: CRUZ ↔ screen_perception tool + runtime-context injection."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agents.cruz.cruz_agent import CRUZ_TOOLS, CruzAgent
from services.screen_perception import (
    ActiveWindow,
    ScreenAnalysis,
    ScreenPerceptionError,
)


def test_screen_perception_tool_registered() -> None:
    """CRUZ_TOOLS must contain a `screen_perception` entry with an
    optional `question` string parameter."""
    matches = [t for t in CRUZ_TOOLS if t["name"] == "screen_perception"]
    assert len(matches) == 1, "screen_perception not registered in CRUZ_TOOLS"
    tool = matches[0]
    assert "question" in tool["input_schema"]["properties"]
    assert tool["input_schema"]["properties"]["question"]["type"] == "string"
    # question is optional — not in required list
    assert "question" not in tool["input_schema"].get("required", [])


@pytest.mark.asyncio
async def test_dispatch_screen_perception_success() -> None:
    """Successful analyze() → AgentOutput.success=True, result is the
    sanitized answer string (NOT a dict)."""
    cruz = CruzAgent()
    aw = ActiveWindow(app="Code", window_title="x.py", captured_at=0.0)
    sa = ScreenAnalysis(
        answer="Editing x.py.",
        active_window=aw,
        image_bytes_len=512,
        duration_ms=200,
        tokens_used=120,
    )
    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp:
        mock_get_sp.return_value.analyze = AsyncMock(return_value=sa)
        out = await cruz._dispatch_screen_perception_tool(
            tool_input={}, trace_id="t1",
        )
    assert out["success"] is True
    assert out["result"] == "Editing x.py."   # plain string, not a dict
    assert out["agent"] == cruz.name
    assert out["error"] is None
    assert out["requires_approval"] is False


@pytest.mark.asyncio
async def test_dispatch_screen_perception_with_question() -> None:
    """`question` from tool_input is forwarded to analyze()."""
    cruz = CruzAgent()
    aw = ActiveWindow(app="Code", window_title=None, captured_at=0.0)
    sa = ScreenAnalysis(
        answer="A connection error.", active_window=aw,
        image_bytes_len=1, duration_ms=1, tokens_used=1,
    )
    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp:
        mock_get_sp.return_value.analyze = AsyncMock(return_value=sa)
        await cruz._dispatch_screen_perception_tool(
            tool_input={"question": "what's the error?"}, trace_id="t1",
        )
    mock_get_sp.return_value.analyze.assert_awaited_once_with(
        question="what's the error?"
    )


@pytest.mark.asyncio
async def test_dispatch_screen_perception_failure_returns_error_output() -> None:
    """ScreenPerceptionError → AgentOutput.success=False with error text."""
    cruz = CruzAgent()
    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp:
        mock_get_sp.return_value.analyze = AsyncMock(
            side_effect=ScreenPerceptionError("vision call failed: 503")
        )
        out = await cruz._dispatch_screen_perception_tool(
            tool_input={}, trace_id="t1",
        )
    assert out["success"] is False
    assert out["result"] is None
    assert "vision call failed: 503" in out["error"]
    assert out["requires_approval"] is False


@pytest.mark.asyncio
async def test_dispatch_tool_routes_screen_perception_correctly() -> None:
    """_dispatch_tool routes name='screen_perception' to the new method."""
    cruz = CruzAgent()
    with patch.object(
        cruz, "_dispatch_screen_perception_tool", new=AsyncMock(
            return_value={"success": True, "result": "x", "agent": "CRUZ",
                          "duration_ms": 0, "tokens_used": 0, "error": None,
                          "requires_approval": False, "approval_prompt": None},
        ),
    ) as mock_method:
        await cruz._dispatch_tool(
            tool_name="screen_perception",
            tool_input={"question": "q"},
            trace_id="t",
            conversation_id="c",
        )
    mock_method.assert_awaited_once_with({"question": "q"}, "t")


@pytest.mark.asyncio
async def test_process_runtime_context_includes_active_app() -> None:
    """process() injects an 'Active app:' line into the system prompt
    passed to llm.chat."""
    cruz = CruzAgent()
    aw = ActiveWindow(app="Code", window_title="x.py", captured_at=0.0)

    captured_system: dict = {}

    from types import SimpleNamespace

    async def fake_llm_chat(*, system, messages, tools, max_tokens, **_):
        captured_system["value"] = system
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    # Patch all the heavy collaborators so we exercise just the
    # runtime_context construction.
    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp, patch(
        "agents.cruz.cruz_agent.get_kb_service",
    ) as mock_kb, patch(
        "agents.cruz.cruz_agent.get_db_service",
    ) as mock_db, patch(
        "agents.cruz.cruz_agent.ConversationService",
    ) as mock_conv_cls, patch(
        "agents.cruz.cruz_agent.SemanticMemoryService",
    ) as mock_sem_cls, patch(
        "agents.cruz.cruz_agent.llm_chat",
        new=AsyncMock(side_effect=fake_llm_chat),
    ):
        mock_get_sp.return_value.get_active_window = AsyncMock(return_value=aw)
        mock_kb.return_value.build_agent_context = AsyncMock(return_value="")
        mock_kb.return_value.record_agent_activity = AsyncMock()
        mock_conv = mock_conv_cls.return_value
        mock_conv.get_or_create_conversation = AsyncMock()
        mock_conv.load_history = AsyncMock(return_value=[])
        mock_conv.save_exchange = AsyncMock()
        mock_sem = mock_sem_cls.return_value
        mock_sem.search_similar = AsyncMock(return_value=[])
        mock_sem.store = AsyncMock()

        await cruz.process({
            "task": "hi",
            "context": {},
            "trace_id": "t1",
            "conversation_id": "c1",
        })

    sys_prompt = captured_system["value"]
    assert "- Active app: Code — x.py" in sys_prompt


@pytest.mark.asyncio
async def test_process_runtime_context_omits_active_app_on_failure() -> None:
    """If get_active_window raises, the request still completes and the
    'Active app:' line is omitted from system prompt."""
    cruz = CruzAgent()

    captured_system: dict = {}

    from types import SimpleNamespace

    async def fake_llm_chat(*, system, messages, tools, max_tokens, **_):
        captured_system["value"] = system
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp, patch(
        "agents.cruz.cruz_agent.get_kb_service",
    ) as mock_kb, patch(
        "agents.cruz.cruz_agent.get_db_service",
    ), patch(
        "agents.cruz.cruz_agent.ConversationService",
    ) as mock_conv_cls, patch(
        "agents.cruz.cruz_agent.SemanticMemoryService",
    ) as mock_sem_cls, patch(
        "agents.cruz.cruz_agent.llm_chat",
        new=AsyncMock(side_effect=fake_llm_chat),
    ):
        mock_get_sp.return_value.get_active_window = AsyncMock(
            side_effect=RuntimeError("osascript missing")
        )
        mock_kb.return_value.build_agent_context = AsyncMock(return_value="")
        mock_kb.return_value.record_agent_activity = AsyncMock()
        mock_conv = mock_conv_cls.return_value
        mock_conv.get_or_create_conversation = AsyncMock()
        mock_conv.load_history = AsyncMock(return_value=[])
        mock_conv.save_exchange = AsyncMock()
        mock_sem = mock_sem_cls.return_value
        mock_sem.search_similar = AsyncMock(return_value=[])
        mock_sem.store = AsyncMock()

        out = await cruz.process({
            "task": "hi",
            "context": {},
            "trace_id": "t1",
            "conversation_id": "c1",
        })

    assert out["success"] is True
    assert "Active app:" not in captured_system["value"]


@pytest.mark.asyncio
async def test_process_runtime_context_omits_on_timeout() -> None:
    """If get_active_window hangs > 2s, wait_for cancels and the
    'Active app:' line is omitted. This is the load-bearing latency
    test for spec §5 (voice-mode ~3.6s SLO must not regress)."""
    cruz = CruzAgent()

    captured_system: dict = {}

    from types import SimpleNamespace

    async def fake_llm_chat(*, system, messages, tools, max_tokens, **_):
        captured_system["value"] = system
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp, patch(
        "agents.cruz.cruz_agent.get_kb_service",
    ) as mock_kb, patch(
        "agents.cruz.cruz_agent.get_db_service",
    ), patch(
        "agents.cruz.cruz_agent.ConversationService",
    ) as mock_conv_cls, patch(
        "agents.cruz.cruz_agent.SemanticMemoryService",
    ) as mock_sem_cls, patch(
        "agents.cruz.cruz_agent.llm_chat",
        new=AsyncMock(side_effect=fake_llm_chat),
    ), patch(
        # Patch wait_for to raise TimeoutError immediately. This is the
        # load-bearing assertion: when wait_for cancels the inner call,
        # the active-app line must be omitted and the request must still
        # complete. Patching avoids waiting 2 real seconds in the suite.
        "agents.cruz.cruz_agent.asyncio.wait_for",
        new=AsyncMock(side_effect=asyncio.TimeoutError()),
    ):
        # get_active_window is never actually awaited (wait_for raises
        # before reaching it), but it must be a callable that returns
        # an awaitable so the production code's call site type-checks.
        mock_get_sp.return_value.get_active_window = AsyncMock()
        mock_kb.return_value.build_agent_context = AsyncMock(return_value="")
        mock_kb.return_value.record_agent_activity = AsyncMock()
        mock_conv = mock_conv_cls.return_value
        mock_conv.get_or_create_conversation = AsyncMock()
        mock_conv.load_history = AsyncMock(return_value=[])
        mock_conv.save_exchange = AsyncMock()
        mock_sem = mock_sem_cls.return_value
        mock_sem.search_similar = AsyncMock(return_value=[])
        mock_sem.store = AsyncMock()

        out = await cruz.process({
            "task": "hi",
            "context": {},
            "trace_id": "t1",
            "conversation_id": "c1",
        })

    # Request still completes
    assert out["success"] is True
    # No active-app line in the system prompt
    assert "Active app:" not in captured_system["value"]


@pytest.mark.asyncio
async def test_process_runtime_context_omits_when_disabled_via_env(monkeypatch) -> None:
    """CRUZ_DISABLE_ACTIVE_APP=1 short-circuits the injection (used for
    Gate 2 control runs in the exit-gate test plan)."""
    monkeypatch.setenv("CRUZ_DISABLE_ACTIVE_APP", "1")

    cruz = CruzAgent()
    captured_system: dict = {}

    from types import SimpleNamespace

    async def fake_llm_chat(*, system, messages, tools, max_tokens, **_):
        captured_system["value"] = system
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    aw = ActiveWindow(app="Code", window_title="x.py", captured_at=0.0)

    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp, patch(
        "agents.cruz.cruz_agent.get_kb_service",
    ) as mock_kb, patch(
        "agents.cruz.cruz_agent.get_db_service",
    ), patch(
        "agents.cruz.cruz_agent.ConversationService",
    ) as mock_conv_cls, patch(
        "agents.cruz.cruz_agent.SemanticMemoryService",
    ) as mock_sem_cls, patch(
        "agents.cruz.cruz_agent.llm_chat",
        new=AsyncMock(side_effect=fake_llm_chat),
    ):
        get_aw = AsyncMock(return_value=aw)
        mock_get_sp.return_value.get_active_window = get_aw
        mock_kb.return_value.build_agent_context = AsyncMock(return_value="")
        mock_kb.return_value.record_agent_activity = AsyncMock()
        mock_conv = mock_conv_cls.return_value
        mock_conv.get_or_create_conversation = AsyncMock()
        mock_conv.load_history = AsyncMock(return_value=[])
        mock_conv.save_exchange = AsyncMock()
        mock_sem = mock_sem_cls.return_value
        mock_sem.search_similar = AsyncMock(return_value=[])
        mock_sem.store = AsyncMock()

        await cruz.process({
            "task": "hi",
            "context": {},
            "trace_id": "t1",
            "conversation_id": "c1",
        })

    # Disabled flag → service must not be called and prompt has no line
    get_aw.assert_not_called()
    assert "Active app:" not in captured_system["value"]


@pytest.mark.asyncio
async def test_stream_response_runtime_context_includes_active_app() -> None:
    """stream_response also injects active-app into runtime_context."""
    from types import SimpleNamespace
    from services.llm.stream_events import (
        TextDeltaEvent, DoneEvent as _LLMDone, UsageInfo,
    )

    cruz = CruzAgent()
    aw = ActiveWindow(app="Terminal", window_title=None, captured_at=0.0)

    captured_system: dict = {}

    async def fake_llm_chat_stream(*, system, messages, tools, max_tokens, **_):
        captured_system["value"] = system
        yield TextDeltaEvent(delta="ok")
        yield _LLMDone(stop_reason="end_turn",
                       usage=UsageInfo(input_tokens=1, output_tokens=1))

    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp, patch(
        "agents.cruz.cruz_agent.get_kb_service",
    ) as mock_kb, patch(
        "agents.cruz.cruz_agent.get_db_service",
    ), patch(
        "agents.cruz.cruz_agent.ConversationService",
    ) as mock_conv_cls, patch(
        "agents.cruz.cruz_agent.SemanticMemoryService",
    ) as mock_sem_cls, patch(
        "agents.cruz.cruz_agent.llm_chat_stream",
        new=fake_llm_chat_stream,
    ):
        mock_get_sp.return_value.get_active_window = AsyncMock(return_value=aw)
        mock_kb.return_value.build_agent_context = AsyncMock(return_value="")
        mock_kb.return_value.record_agent_activity = AsyncMock()
        mock_conv = mock_conv_cls.return_value
        mock_conv.get_or_create_conversation = AsyncMock()
        mock_conv.load_history = AsyncMock(return_value=[])
        mock_conv.save_exchange = AsyncMock()
        mock_sem = mock_sem_cls.return_value
        mock_sem.search_similar = AsyncMock(return_value=[])
        mock_sem.store = AsyncMock()

        # Drain the iterator
        async for _ in cruz.stream_response(
            task="hi", conversation_id="c1", trace_id="t1", device=None,
        ):
            pass

    assert "- Active app: Terminal" in captured_system["value"]


@pytest.mark.asyncio
async def test_stream_response_emits_tool_events_for_screen_perception() -> None:
    """When Claude calls screen_perception in streaming mode, the
    iterator emits ToolStart and ToolFinish events."""
    from types import SimpleNamespace
    from services.llm.stream_events import (
        TextDeltaEvent, ToolUseEvent, DoneEvent as _LLMDone, UsageInfo,
    )
    from agents.cruz.stream_events import ToolStart, ToolFinish

    cruz = CruzAgent()
    aw = ActiveWindow(app="Code", window_title=None, captured_at=0.0)
    sa = ScreenAnalysis(
        answer="Editing code.", active_window=aw,
        image_bytes_len=1, duration_ms=1, tokens_used=1,
    )

    # Two-pass stream: first call emits a tool_use; second call emits
    # plain text after the tool result is fed back.
    call_count = {"n": 0}

    async def fake_llm_chat_stream(*, system, messages, tools, max_tokens, **_):
        call_count["n"] += 1
        if call_count["n"] == 1:
            yield ToolUseEvent(
                tool_use_id="tu_1", name="screen_perception", input={},
            )
            yield _LLMDone(stop_reason="tool_use",
                           usage=UsageInfo(input_tokens=1, output_tokens=1))
        else:
            yield TextDeltaEvent(delta="Done.")
            yield _LLMDone(stop_reason="end_turn",
                           usage=UsageInfo(input_tokens=1, output_tokens=1))

    with patch(
        "agents.cruz.cruz_agent.get_screen_perception_service",
    ) as mock_get_sp, patch(
        "agents.cruz.cruz_agent.get_kb_service",
    ) as mock_kb, patch(
        "agents.cruz.cruz_agent.get_db_service",
    ), patch(
        "agents.cruz.cruz_agent.ConversationService",
    ) as mock_conv_cls, patch(
        "agents.cruz.cruz_agent.SemanticMemoryService",
    ) as mock_sem_cls, patch(
        "agents.cruz.cruz_agent.llm_chat_stream",
        new=fake_llm_chat_stream,
    ):
        mock_get_sp.return_value.get_active_window = AsyncMock(return_value=aw)
        mock_get_sp.return_value.analyze = AsyncMock(return_value=sa)
        mock_kb.return_value.build_agent_context = AsyncMock(return_value="")
        mock_kb.return_value.record_agent_activity = AsyncMock()
        mock_conv = mock_conv_cls.return_value
        mock_conv.get_or_create_conversation = AsyncMock()
        mock_conv.load_history = AsyncMock(return_value=[])
        mock_conv.save_exchange = AsyncMock()
        mock_sem = mock_sem_cls.return_value
        mock_sem.search_similar = AsyncMock(return_value=[])
        mock_sem.store = AsyncMock()

        events = []
        async for ev in cruz.stream_response(
            task="what am i working on?",
            conversation_id="c1", trace_id="t1", device=None,
        ):
            events.append(ev)

    starts = [e for e in events if isinstance(e, ToolStart)]
    finishes = [e for e in events if isinstance(e, ToolFinish)]
    assert any(s.agent == "screen_perception" for s in starts)
    assert any(f.agent == "screen_perception" for f in finishes)
    sp_finish = next(f for f in finishes if f.agent == "screen_perception")
    assert "Editing code." in sp_finish.result_preview
