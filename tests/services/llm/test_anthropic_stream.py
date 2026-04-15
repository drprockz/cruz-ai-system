import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.llm.anthropic_backend import anthropic_chat_stream
from services.llm.stream_events import TextDeltaEvent, DoneEvent


class FakeStream:
    """Mimics anthropic's async streaming context manager + iterator."""
    def __init__(self, events):
        self._events = events
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return None
    def __aiter__(self):
        self._iter = iter(self._events)
        return self
    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


@pytest.mark.asyncio
async def test_stream_yields_text_deltas_then_done():
    class Delta:
        type = "content_block_delta"
        delta = MagicMock(type="text_delta", text="hello ")
        index = 0
    class Delta2:
        type = "content_block_delta"
        delta = MagicMock(type="text_delta", text="world")
        index = 0
    class Stop:
        type = "message_delta"
        delta = MagicMock(stop_reason="end_turn")
        usage = MagicMock(input_tokens=10, output_tokens=2)
    fake = FakeStream([Delta, Delta2, Stop])

    with patch("services.llm.anthropic_backend.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(return_value=fake)
        events = []
        async for ev in anthropic_chat_stream(
            system="s", messages=[{"role": "user", "content": "hi"}], tools=None,
        ):
            events.append(ev)

    text = "".join(e.delta for e in events if isinstance(e, TextDeltaEvent))
    assert text == "hello world"
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].stop_reason == "end_turn"
    assert events[-1].usage.output_tokens == 2
