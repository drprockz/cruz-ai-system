"""
E2E latency harness — opt-in, runs only when DEEPGRAM_API_KEY is set.

Phase 1 exit SLO: STT final → first TTS byte < 2000ms.
"""
from __future__ import annotations

import os
import pathlib
import time

import pytest

pytestmark = pytest.mark.voice


@pytest.mark.asyncio
async def test_stt_and_tts_under_1_2s():
    if not os.environ.get("DEEPGRAM_API_KEY"):
        pytest.skip("no DEEPGRAM_API_KEY; integration test skipped")
    from services.realtime_voice import DeepgramSTT, DeepgramTTS

    audio = pathlib.Path("tests/integration/fixtures/hello_cruz.wav").read_bytes()

    t0 = time.monotonic()
    stt = DeepgramSTT()
    await stt.connect()
    await stt.send(audio[44:])  # strip WAV header, send raw PCM
    final_text = None
    async for t in stt.transcripts():
        if t.is_final:
            final_text = t.text
            break
    t_stt = time.monotonic()
    assert final_text, "Deepgram returned no final transcript"

    tts = DeepgramTTS()
    t_first_byte = None
    async for _chunk in tts.synthesize("That's 3 PM."):
        if t_first_byte is None:
            t_first_byte = time.monotonic()
            break
    await stt.close()
    assert t_first_byte, "DeepgramTTS did not stream any bytes"

    stt_ms = int((t_stt - t0) * 1000)
    tts_ms = int((t_first_byte - t_stt) * 1000)
    total = int((t_first_byte - t0) * 1000)
    print(f"STT={stt_ms}ms TTS_TTFB={tts_ms}ms STT+TTS={total}ms")
    # Network-only ceiling (no LLM): STT + TTS must stay under 1.2s
    assert total < 1200, f"STT+TTS SLO breach: {total}ms"


@pytest.mark.asyncio
async def test_full_e2e_includes_sonnet_first_sentence():
    """
    True E2E: audio in → first TTS byte via CruzAgent.stream_response.
    Covers Sonnet TTFT, the largest hop in the pipeline.
    Phase 1 exit SLO: first TTS byte within 2000ms of STT-final.
    """
    if not (
        os.environ.get("DEEPGRAM_API_KEY")
        and os.environ.get("ANTHROPIC_API_KEY")
    ):
        pytest.skip("needs DEEPGRAM_API_KEY + ANTHROPIC_API_KEY")
    from agents.cruz.cruz_agent import CruzAgent
    from agents.cruz.stream_events import Text
    from services.realtime_voice import DeepgramSTT, DeepgramTTS

    audio = pathlib.Path("tests/integration/fixtures/hello_cruz.wav").read_bytes()
    stt = DeepgramSTT()
    await stt.connect()
    await stt.send(audio[44:])
    final = None
    async for t in stt.transcripts():
        if t.is_final:
            final = t.text
            break
    await stt.close()
    assert final

    cruz = CruzAgent()
    tts = DeepgramTTS()
    t_final = time.monotonic()
    first_audio_byte_at = None
    async for ev in cruz.stream_response(
        task=final, conversation_id="e2e-test",
        trace_id="e2e", device="mac_mini",
    ):
        if isinstance(ev, Text):
            async for _chunk in tts.synthesize(ev.content):
                first_audio_byte_at = time.monotonic()
                break
            break

    assert first_audio_byte_at is not None
    e2e_ms = int((first_audio_byte_at - t_final) * 1000)
    print(f"STT-final → first TTS byte = {e2e_ms}ms")
    assert e2e_ms < 2000, f"Phase 1 SLO breach: {e2e_ms}ms > 2000ms"
