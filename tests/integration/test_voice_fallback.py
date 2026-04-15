"""
Fallback matrix: verify worker falls back to VoicePipeline when Deepgram errors.
Marked `voice` but should not need a real DEEPGRAM_API_KEY — the failing TTS is
injected.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import patch

pytestmark = pytest.mark.voice


@pytest.mark.asyncio
async def test_tts_falls_back_to_inworld_when_deepgram_errors():
    """
    _speak_with_fallback catches DeepgramTTS errors and invokes VoicePipeline.
    We mock ffmpeg via subprocess patch since the test container may lack it.
    """
    from workers.voice_agent.worker import _speak_with_fallback

    class BoomTTS:
        sample_rate = 24000

        async def synthesize(self, text: str):
            raise RuntimeError("deepgram down")
            yield b""  # never reached; satisfies async-gen shape

    class FakeSource:
        def __init__(self):
            self.captured = []

        async def capture_frame(self, frame):
            self.captured.append(frame)

    source = FakeSource()
    cancel = asyncio.Event()

    from services.voice import VoicePipeline
    # subprocess is imported locally inside _speak_with_fallback, so we patch
    # the module-level subprocess.check_output directly.
    with patch.object(VoicePipeline, "speak", return_value=b"\x00\x01" * 100), \
         patch("subprocess.check_output", return_value=b"\xff\x00" * 200):
        await _speak_with_fallback("hi", BoomTTS(), source, cancel)

    assert len(source.captured) == 1
    frame = source.captured[0]
    # frame.data holds the fake PCM from the mocked ffmpeg
    assert bytes(frame.data) == b"\xff\x00" * 200
