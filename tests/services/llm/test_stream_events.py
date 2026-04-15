from services.llm.stream_events import (
    TextDeltaEvent, ToolUseEvent, ToolResultEvent, DoneEvent, UsageInfo,
)


def test_events_are_dataclasses():
    e = TextDeltaEvent(delta="hi")
    assert e.delta == "hi"
    t = ToolUseEvent(tool_use_id="tu_1", name="forge", input={"task": "x"})
    assert t.name == "forge"
    r = ToolResultEvent(tool_use_id="tu_1", content="ok", is_error=False)
    assert r.content == "ok"
    d = DoneEvent(stop_reason="end_turn", usage=UsageInfo(input_tokens=10, output_tokens=5))
    assert d.usage.input_tokens == 10
