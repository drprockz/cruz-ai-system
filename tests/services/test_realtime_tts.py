import pytest
import respx
import httpx

from services.realtime_voice import DeepgramTTS


@pytest.mark.asyncio
@respx.mock
async def test_tts_streams_pcm_chunks(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    monkeypatch.setenv("DEEPGRAM_TTS_MODEL", "aura-2-orion-en")

    respx.post("https://api.deepgram.com/v1/speak").mock(
        return_value=httpx.Response(200, content=b"\x00\x01" * 4800)
    )

    tts = DeepgramTTS()
    chunks = [c async for c in tts.synthesize("deployment complete.")]
    assert b"".join(chunks) == b"\x00\x01" * 4800


@pytest.mark.asyncio
@respx.mock
async def test_tts_raises_on_non_2xx(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    respx.post("https://api.deepgram.com/v1/speak").mock(
        return_value=httpx.Response(401, content=b"unauthorized")
    )
    tts = DeepgramTTS()
    with pytest.raises(RuntimeError, match="HTTP 401"):
        async for _ in tts.synthesize("hi"):
            pass


def test_tts_defaults_from_env(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_TTS_MODEL", "aura-2-draco-en")
    tts = DeepgramTTS()
    assert tts._model == "aura-2-draco-en"
    assert tts.sample_rate == 24000


def test_tts_model_override(monkeypatch):
    monkeypatch.delenv("DEEPGRAM_TTS_MODEL", raising=False)
    tts = DeepgramTTS()
    assert tts._model == "aura-2-orion-en"  # default
    tts2 = DeepgramTTS(model="aura-2-atlas-en")
    assert tts2._model == "aura-2-atlas-en"
