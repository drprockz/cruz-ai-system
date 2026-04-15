from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock, patch

from services.realtime_voice import DeepgramSTT, STTTranscript


@pytest.mark.asyncio
async def test_stt_emits_final_transcripts(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")

    captured = {}

    class FakeEnum:
        Transcript = "transcript_evt"

    class FakeLive:
        _TRANSCRIPT_EVENT = FakeEnum.Transcript

        def on(self, event, fn):
            captured[event] = fn

        async def start(self, opts):
            return True

        async def send(self, audio):
            pass

        async def finish(self):
            pass

    fake_conn = FakeLive()
    with patch("services.realtime_voice._deepgram_live_connection", return_value=fake_conn):
        stt = DeepgramSTT()
        await stt.connect()
        out_queue: asyncio.Queue = asyncio.Queue()

        async def consume():
            async for t in stt.transcripts():
                await out_queue.put(t)

        task = asyncio.create_task(consume())
        evt = MagicMock(
            is_final=True,
            channel=MagicMock(alternatives=[MagicMock(transcript="deploy ama to prod")]),
        )
        await captured[FakeEnum.Transcript](None, evt)
        await asyncio.sleep(0.05)
        await stt.close()
        task.cancel()

        got: STTTranscript = out_queue.get_nowait()
        assert got.text == "deploy ama to prod"
        assert got.is_final is True
