# Voice Pipeline v2 — Phase 1 (Mac-only MVP) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Mac-only realtime voice pipeline (openWakeWord → LiveKit Cloud → Deepgram Nova-3 STT → Sonnet 4 streaming → Deepgram Aura-2 Orion TTS → speaker) that beats ~2s E2E latency, supports barge-in, and leaves the existing HTTP `/command` + `/voice/*` stack untouched as a fallback.

**Architecture:** Extend `services/llm` with a streaming wrapper. Add `services/realtime_voice.py` with Deepgram STT + Aura-2 TTS WebSocket clients. Extract a shared `CruzAgent.stream_response()` async iterator usable by both the HTTP SSE endpoint and a new LiveKit Agent worker. Replace `scripts/voice/listen.py` with a thin LiveKit-native daemon. Persist voice sessions and approval requests in three new SQL tables.

**Tech Stack:** Python 3.11+, FastAPI, asyncpg/psycopg2, `deepgram-sdk>=3.7`, `livekit-agents>=0.9`, `livekit-rtc`, `anthropic>=0.40` (streaming), `pytest`, `pytest-asyncio`, `respx`, `sounddevice` (already in use), existing `openwakeword` wake word, existing `services/voice.py` as fallback.

**Reference spec:** [docs/superpowers/specs/2026-04-15-voice-pipeline-v2.md](../specs/2026-04-15-voice-pipeline-v2.md).

---

## Pre-Flight: Accounts + Environment

Not code — do these **before** Chunk 1 or everything blocks.

- [ ] Create Deepgram account, claim $200 credit. Copy key → `DEEPGRAM_API_KEY`.
- [ ] Pin TTS model: `DEEPGRAM_TTS_MODEL=aura-2-orion-en`. Confirm by curl:
  ```bash
  curl -X POST 'https://api.deepgram.com/v1/speak?model=aura-2-orion-en' \
    -H "Authorization: Token $DEEPGRAM_API_KEY" \
    -H 'Content-Type: application/json' \
    -d '{"text":"CRUZ online"}' --output /tmp/orion_test.mp3 \
    && afplay /tmp/orion_test.mp3
  ```
- [ ] Create LiveKit Cloud project. Copy `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_WS_URL`.
- [ ] Add to `.env` and `.env.example` (commit `.env.example` only).
- [ ] Install new Python deps:
  ```bash
  source venv/bin/activate
  pip install "deepgram-sdk>=3.7" "livekit-rtc>=0.9" "livekit-agents>=0.9" "livekit-api>=0.7"
  pip freeze > backend/requirements.txt
  ```
  Note: the bare `livekit` PyPI name is a different package — always use `livekit-rtc`.
- [ ] Commit: `chore(voice): add Deepgram + LiveKit deps, env placeholders`

---

## Chunk 1: Schema Extensions

**Rationale:** Add the three tables the spec requires and two columns on `messages`. **Spec ↔ plan drift:** the spec (Section 6) says "all four migrations go through Alembic per CLAUDE.md". Reality: the repo has no Alembic configured yet; `backend/models/schema.sql` is the source of truth. Phase 1 extends schema.sql directly with idempotent `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` statements. Introducing Alembic is deferred to its own plan so Phase 1 does not bundle unrelated infra work.

### Task 1.1: Extend schema.sql with voice tables

**Files:**
- Modify: `backend/models/schema.sql` (append at end)

- [ ] **Step 1: Append the three new tables and two columns**

Append the following to [backend/models/schema.sql](backend/models/schema.sql):

```sql
-- ============================================================
-- Voice pipeline v2 (added 2026-04-15)
-- ============================================================

-- A single voice interaction session bound to a LiveKit room.
CREATE TABLE IF NOT EXISTS voice_sessions (
    id               VARCHAR(36) PRIMARY KEY,
    conversation_id  VARCHAR(36) REFERENCES conversations(id) NOT NULL,
    device_id        VARCHAR(100) NOT NULL,
    livekit_room     VARCHAR(200) NOT NULL,
    started_at       TIMESTAMP DEFAULT NOW(),
    ended_at         TIMESTAMP,
    deepgram_ws_ms   INTEGER DEFAULT 0,
    turns            INTEGER DEFAULT 0,
    barges           INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_voice_sessions_conv ON voice_sessions(conversation_id);

-- Approval request surfaced to the user via FCM + voice prompt.
CREATE TABLE IF NOT EXISTS approval_requests (
    id            VARCHAR(36) PRIMARY KEY,
    trace_id      VARCHAR(64) NOT NULL,
    agent         VARCHAR(50) NOT NULL,
    action        VARCHAR(100) NOT NULL,
    payload       JSONB NOT NULL,
    state         VARCHAR(20) DEFAULT 'pending',
    requested_at  TIMESTAMP DEFAULT NOW(),
    responded_at  TIMESTAMP,
    expires_at    TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approval_requests_trace ON approval_requests(trace_id);
CREATE INDEX IF NOT EXISTS idx_approval_requests_state ON approval_requests(state, expires_at);

-- FCM device tokens for push-based approval notifications.
CREATE TABLE IF NOT EXISTS fcm_tokens (
    id         VARCHAR(36) PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id),
    device     VARCHAR(50) NOT NULL,
    token      TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, device)
);

-- messages: link a voice-originated turn to its session + audio length.
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS voice_session_id VARCHAR(36) REFERENCES voice_sessions(id);
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS audio_ms INTEGER;
```

- [ ] **Step 2: Apply to running dev DB**

```bash
psql "$DATABASE_URL" -f backend/models/schema.sql
```

Expected: `CREATE TABLE` ×3, `ALTER TABLE` ×2, `CREATE INDEX` ×3. Rerunning is idempotent (`IF NOT EXISTS`).

- [ ] **Step 3: Commit**

```bash
git add backend/models/schema.sql
git commit -m "feat(voice): add voice_sessions, approval_requests, fcm_tokens tables"
```

### Task 1.2: DB helper for voice_sessions

**Files:**
- Create: `services/voice_sessions.py`
- Test: `tests/services/test_voice_sessions.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/services/test_voice_sessions.py
import pytest
from uuid import uuid4

from services.voice_sessions import VoiceSessionService


@pytest.mark.asyncio
async def test_start_session_returns_id(db_service):
    # conversation must pre-exist (FK)
    conv_id = str(uuid4())
    await db_service.execute_async(
        "INSERT INTO conversations (id) VALUES (%s)", (conv_id,)
    )
    svc = VoiceSessionService(db_service)
    sid = await svc.start(conversation_id=conv_id, device_id="mac-mini", room="cruz-xyz")
    assert sid  # non-empty uuid
    row = await db_service.fetchrow_async(
        "SELECT conversation_id, livekit_room FROM voice_sessions WHERE id=%s", (sid,)
    )
    assert row["conversation_id"] == conv_id
    assert row["livekit_room"] == "cruz-xyz"


@pytest.mark.asyncio
async def test_end_session_sets_ended_at(db_service):
    conv_id = str(uuid4())
    await db_service.execute_async(
        "INSERT INTO conversations (id) VALUES (%s)", (conv_id,)
    )
    svc = VoiceSessionService(db_service)
    sid = await svc.start(conversation_id=conv_id, device_id="mac-mini", room="cruz-abc")
    await svc.end(sid, turns=3, barges=1, deepgram_ws_ms=4200)
    row = await db_service.fetchrow_async(
        "SELECT ended_at, turns, barges FROM voice_sessions WHERE id=%s", (sid,)
    )
    assert row["ended_at"] is not None
    assert row["turns"] == 3
    assert row["barges"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/services/test_voice_sessions.py -v
```
Expected: ImportError or assertion failures — module doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
# services/voice_sessions.py
"""VoiceSessionService — lightweight CRUD over voice_sessions table."""
from __future__ import annotations

import uuid
from typing import Optional


class VoiceSessionService:
    def __init__(self, db):
        self._db = db

    async def start(self, *, conversation_id: str, device_id: str, room: str) -> str:
        sid = str(uuid.uuid4())
        await self._db.execute_async(
            "INSERT INTO voice_sessions (id, conversation_id, device_id, livekit_room) "
            "VALUES (%s, %s, %s, %s)",
            (sid, conversation_id, device_id, room),
        )
        return sid

    async def end(
        self,
        session_id: str,
        *,
        turns: int = 0,
        barges: int = 0,
        deepgram_ws_ms: int = 0,
    ) -> None:
        await self._db.execute_async(
            "UPDATE voice_sessions SET ended_at = NOW(), turns = %s, barges = %s, "
            "deepgram_ws_ms = %s WHERE id = %s",
            (turns, barges, deepgram_ws_ms, session_id),
        )

    async def increment_turn(self, session_id: str) -> None:
        await self._db.execute_async(
            "UPDATE voice_sessions SET turns = turns + 1 WHERE id = %s", (session_id,)
        )

    async def increment_barge(self, session_id: str) -> None:
        await self._db.execute_async(
            "UPDATE voice_sessions SET barges = barges + 1 WHERE id = %s", (session_id,)
        )
```

- [ ] **Step 4: Verify tests pass**

```bash
pytest tests/services/test_voice_sessions.py -v
```
Expected: PASS ×2.

- [ ] **Step 5: Commit**

```bash
git add services/voice_sessions.py tests/services/test_voice_sessions.py
git commit -m "feat(voice): VoiceSessionService CRUD"
```

---

## Chunk 2: Streaming LLM Backend

**Rationale:** `services/llm/router.chat()` is non-streaming. CRUZ can't do per-sentence TTS until tokens arrive as they're generated. Add `chat_stream()` that yields text / tool_use / tool_result events. Anthropic-only for Phase 1 (Ollama/Gemini keep blocking `chat()`).

### Task 2.1: Define streaming event types

**Files:**
- Create: `services/llm/stream_events.py`
- Test: `tests/services/llm/test_stream_events.py`

- [ ] **Step 1: Write failing test**

```python
# tests/services/llm/test_stream_events.py
from services.llm.stream_events import (
    TextDeltaEvent, ToolUseEvent, ToolResultEvent, DoneEvent, UsageInfo,
)

def test_events_are_dataclasses():
    e = TextDeltaEvent(delta="hi")
    assert e.delta == "hi"
    t = ToolUseEvent(tool_use_id="tu_1", name="forge", input={"task":"x"})
    assert t.name == "forge"
    r = ToolResultEvent(tool_use_id="tu_1", content="ok", is_error=False)
    assert r.content == "ok"
    d = DoneEvent(stop_reason="end_turn", usage=UsageInfo(input_tokens=10, output_tokens=5))
    assert d.usage.input_tokens == 10
```

- [ ] **Step 2: Run test — expect ImportError**

```bash
pytest tests/services/llm/test_stream_events.py -v
```

- [ ] **Step 3: Implement**

```python
# services/llm/stream_events.py
"""Stream event dataclasses for CRUZ's streaming LLM layer."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class UsageInfo:
    input_tokens: int
    output_tokens: int


@dataclass
class TextDeltaEvent:
    delta: str


@dataclass
class ToolUseEvent:
    tool_use_id: str
    name: str
    input: Dict[str, Any]


@dataclass
class ToolResultEvent:
    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass
class DoneEvent:
    stop_reason: str
    usage: UsageInfo
```

- [ ] **Step 4: Pass + commit**

```bash
pytest tests/services/llm/test_stream_events.py -v
git add services/llm/stream_events.py tests/services/llm/test_stream_events.py
git commit -m "feat(llm): streaming event dataclasses"
```

### Task 2.2: Anthropic streaming backend

**Files:**
- Modify: `services/llm/anthropic_backend.py`
- Create test: `tests/services/llm/test_anthropic_stream.py`

- [ ] **Step 1: Write failing test**

```python
# tests/services/llm/test_anthropic_stream.py
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
    # Mock Anthropic raw events: content_block_delta (text_delta), message_delta (stop)
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

    with patch("services.llm.anthropic_backend._anthropic_client") as c:
        c.return_value.messages.stream = MagicMock(return_value=fake)

        events = []
        async for ev in anthropic_chat_stream(
            system="s", messages=[{"role":"user","content":"hi"}], tools=None,
        ):
            events.append(ev)

    text = "".join(e.delta for e in events if isinstance(e, TextDeltaEvent))
    assert text == "hello world"
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].stop_reason == "end_turn"
    assert events[-1].usage.output_tokens == 2
```

- [ ] **Step 2: Run — expect ImportError**

```bash
pytest tests/services/llm/test_anthropic_stream.py -v
```

- [ ] **Step 3: Implement `anthropic_chat_stream`**

Append to [services/llm/anthropic_backend.py](services/llm/anthropic_backend.py):

```python
# ── Streaming variant ─────────────────────────────────────────────
from services.llm.stream_events import (
    TextDeltaEvent, ToolUseEvent, DoneEvent, UsageInfo,
)

async def anthropic_chat_stream(
    system,
    messages,
    max_tokens: int = 1024,
    tools=None,
    model: str | None = None,
):
    """
    Yield stream events from Anthropic. Shapes:
      - TextDeltaEvent(delta)
      - ToolUseEvent(tool_use_id, name, input)   (input may be partial until stop)
      - DoneEvent(stop_reason, usage)
    """
    client = _anthropic_client()
    _model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    kwargs = dict(
        model=_model, max_tokens=max_tokens, system=system, messages=messages,
    )
    if tools:
        kwargs["tools"] = tools

    tool_use_accum: dict[int, dict] = {}  # index → {id, name, input_json_accum}
    input_tokens = 0
    output_tokens = 0
    stop_reason = "end_turn"

    async with client.messages.stream(**kwargs) as stream:
        async for event in stream:
            t = getattr(event, "type", None)
            if t == "content_block_start":
                block = getattr(event, "content_block", None)
                if getattr(block, "type", None) == "tool_use":
                    tool_use_accum[event.index] = {
                        "id": block.id, "name": block.name, "json": "",
                    }
            elif t == "content_block_delta":
                d = event.delta
                if getattr(d, "type", None) == "text_delta":
                    yield TextDeltaEvent(delta=d.text)
                elif getattr(d, "type", None) == "input_json_delta":
                    tool_use_accum[event.index]["json"] += d.partial_json
            elif t == "content_block_stop":
                if event.index in tool_use_accum:
                    import json as _json
                    acc = tool_use_accum[event.index]
                    try:
                        parsed = _json.loads(acc["json"]) if acc["json"] else {}
                    except Exception:
                        parsed = {}
                    yield ToolUseEvent(
                        tool_use_id=acc["id"], name=acc["name"], input=parsed,
                    )
            elif t == "message_delta":
                stop_reason = getattr(event.delta, "stop_reason", stop_reason) or stop_reason
                usage = getattr(event, "usage", None)
                if usage is not None:
                    input_tokens = getattr(usage, "input_tokens", 0) or input_tokens
                    output_tokens = getattr(usage, "output_tokens", 0) or output_tokens

    yield DoneEvent(
        stop_reason=stop_reason,
        usage=UsageInfo(input_tokens=input_tokens, output_tokens=output_tokens),
    )
```

- [ ] **Step 4: Pass + commit**

```bash
pytest tests/services/llm/test_anthropic_stream.py -v
git add services/llm/anthropic_backend.py tests/services/llm/test_anthropic_stream.py
git commit -m "feat(llm): anthropic streaming chat with text+tool_use events"
```

### Task 2.3: Router streaming entry

**Files:**
- Modify: `services/llm/router.py`
- Create: `tests/services/llm/test_router_stream.py`

- [ ] **Step 1: Test**

```python
# tests/services/llm/test_router_stream.py
import pytest
from unittest.mock import patch

from services.llm.router import chat_stream


@pytest.mark.asyncio
async def test_router_stream_dispatches_anthropic(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "anthropic")
    async def _fake(system, messages, **kw):
        yield {"delta": "x"}
    with patch("services.llm.router.anthropic_chat_stream", _fake):
        async for ev in chat_stream(system="s", messages=[]):
            assert ev == {"delta": "x"}


@pytest.mark.asyncio
async def test_router_stream_rejects_non_anthropic(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    with pytest.raises(NotImplementedError):
        async for _ in chat_stream(system="s", messages=[]):
            pass
```

- [ ] **Step 2: Run — expect fail**

```bash
pytest tests/services/llm/test_router_stream.py -v
```

- [ ] **Step 3: Implement in [services/llm/router.py](services/llm/router.py)**

Append:

```python
from services.llm.anthropic_backend import anthropic_chat_stream  # noqa: E402

async def chat_stream(system, messages, max_tokens=4096, tools=None, backend=None, model=None):
    """
    Streaming counterpart to `chat`. Phase 1: anthropic-only.
    Yields TextDeltaEvent / ToolUseEvent / DoneEvent (see stream_events.py).
    """
    resolved = _resolve_backend(backend)
    if resolved != "anthropic":
        raise NotImplementedError(
            f"Streaming only supported on anthropic backend for now (got {resolved}). "
            "Fall back to blocking chat() for others."
        )
    async for ev in anthropic_chat_stream(
        system=system, messages=messages, max_tokens=max_tokens, tools=tools, model=model,
    ):
        yield ev
```

- [ ] **Step 4: Pass + commit**

```bash
pytest tests/services/llm/test_router_stream.py -v
git add services/llm/router.py tests/services/llm/test_router_stream.py
git commit -m "feat(llm): chat_stream router entry (anthropic-only Phase 1)"
```

---

## Chunk 3: Deepgram STT Streaming Client

**Rationale:** Replace whisper-on-POST-wait with WebSocket streaming. Wraps Deepgram SDK so the LiveKit worker gets partial + final transcripts with latency ~250ms after user stops speaking.

### Task 3.1: DeepgramSTT WebSocket client

**Files:**
- Create: `services/realtime_voice.py` (start of file)
- Test: `tests/services/test_realtime_stt.py`

- [ ] **Step 1: Test (mock SDK, assert behavior)**

```python
# tests/services/test_realtime_stt.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.realtime_voice import DeepgramSTT, STTTranscript


@pytest.mark.asyncio
async def test_stt_emits_final_transcripts(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")

    # Fake Deepgram SDK: callback registration captured here
    captured = {}
    class FakeEnum:
        Transcript = "transcript_evt"

    class FakeLive:
        _TRANSCRIPT_EVENT = FakeEnum.Transcript
        def on(self, event, fn):
            captured[event] = fn
        async def start(self, opts): return True
        async def send(self, audio): pass
        async def finish(self): pass

    fake_conn = FakeLive()
    with patch("services.realtime_voice._deepgram_live_connection", return_value=fake_conn):
        stt = DeepgramSTT()
        await stt.connect()
        out_queue: asyncio.Queue = asyncio.Queue()

        async def consume():
            async for t in stt.transcripts():
                await out_queue.put(t)

        task = asyncio.create_task(consume())
        # Simulate a final transcript event
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
```

- [ ] **Step 2: Run — expect import error**

```bash
pytest tests/services/test_realtime_stt.py -v
```

- [ ] **Step 3: Implement `DeepgramSTT`**

Create [services/realtime_voice.py](services/realtime_voice.py):

```python
"""
Realtime voice primitives for Phase 1.

DeepgramSTT — WebSocket streaming STT wrapping deepgram-sdk's LiveClient.
DeepgramTTS — WebSocket streaming TTS for Aura-2 (see Chunk 4).

Both are designed to plug into a LiveKit Agent worker. They deliberately do
NOT touch LiveKit types so they're unit-testable without a live-kit server.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import AsyncIterator, Optional

logger = logging.getLogger("cruz.services.realtime_voice")


@dataclass
class STTTranscript:
    text: str
    is_final: bool


def _deepgram_live_connection():
    """Indirection so tests can monkeypatch. Imports lazily."""
    from deepgram import DeepgramClient, LiveTranscriptionEvents  # type: ignore
    key = os.environ["DEEPGRAM_API_KEY"]
    client = DeepgramClient(key)
    conn = client.listen.asyncwebsocket.v("1")
    # Pin the SDK 3.7+ event enum; we register on LiveTranscriptionEvents.Transcript.
    conn._TRANSCRIPT_EVENT = LiveTranscriptionEvents.Transcript  # type: ignore[attr-defined]
    return conn


class DeepgramSTT:
    """
    Streaming STT. Connect, push audio frames, iterate transcripts.
    Caller is responsible for audio format: linear16, 16kHz, mono, 20-100ms frames.
    """
    def __init__(self, *, model: str = "nova-3", endpointing_ms: int = 300) -> None:
        self._model = model
        self._endpointing_ms = endpointing_ms
        self._conn = None
        self._queue: asyncio.Queue[STTTranscript] = asyncio.Queue()
        self._closed = False

    async def connect(self) -> None:
        self._conn = _deepgram_live_connection()
        async def _on_transcript(_self, result):
            try:
                alt = result.channel.alternatives[0]
                text = (alt.transcript or "").strip()
                if not text:
                    return
                await self._queue.put(
                    STTTranscript(text=text, is_final=bool(result.is_final))
                )
            except Exception:
                logger.exception("DeepgramSTT transcript parse failed")

        # SDK 3.7+: single canonical event.
        self._conn.on(self._conn._TRANSCRIPT_EVENT, _on_transcript)

        opts = {
            "model": self._model,
            "encoding": "linear16",
            "sample_rate": 16000,
            "channels": 1,
            "interim_results": True,
            "punctuate": True,
            "endpointing": self._endpointing_ms,
        }
        started = await self._conn.start(opts)
        if not started:
            raise RuntimeError("DeepgramSTT: failed to start WS")

    async def send(self, audio_bytes: bytes) -> None:
        if self._conn is None or self._closed:
            raise RuntimeError("STT not connected")
        await self._conn.send(audio_bytes)

    async def transcripts(self) -> AsyncIterator[STTTranscript]:
        while not self._closed:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                yield item
            except asyncio.TimeoutError:
                continue

    async def close(self) -> None:
        self._closed = True
        if self._conn is not None:
            try:
                await self._conn.finish()
            except Exception:
                pass
            self._conn = None
```

- [ ] **Step 4: Pass**

```bash
pytest tests/services/test_realtime_stt.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/realtime_voice.py tests/services/test_realtime_stt.py
git commit -m "feat(voice): DeepgramSTT streaming client with partial+final events"
```

---

## Chunk 4: Deepgram Aura-2 Orion TTS Streaming

**Rationale:** Per-sentence WS to Aura-2 streams PCM back with ~100ms TTFB. Caller feeds sentences as they complete; client yields PCM chunks for LiveKit publishing.

### Task 4.1: DeepgramTTS streaming client

**Files:**
- Modify: `services/realtime_voice.py` (append)
- Test: `tests/services/test_realtime_tts.py`

- [ ] **Step 1: Test**

```python
# tests/services/test_realtime_tts.py
import pytest
import respx
import httpx

from services.realtime_voice import DeepgramTTS


@pytest.mark.asyncio
@respx.mock
async def test_tts_streams_pcm_chunks(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    monkeypatch.setenv("DEEPGRAM_TTS_MODEL", "aura-2-orion-en")

    # Deepgram /v1/speak with ?encoding=linear16 streams raw PCM
    respx.post("https://api.deepgram.com/v1/speak").mock(
        return_value=httpx.Response(200, content=b"\x00\x01" * 4800)  # 0.1s of 48kHz
    )

    tts = DeepgramTTS()
    chunks = [c async for c in tts.synthesize("deployment complete.")]
    assert b"".join(chunks) == b"\x00\x01" * 4800
```

- [ ] **Step 2: Run — expect ImportError**

```bash
pytest tests/services/test_realtime_tts.py -v
```

- [ ] **Step 3: Implement**

Append to [services/realtime_voice.py](services/realtime_voice.py):

```python
# ── Aura-2 streaming TTS ─────────────────────────────────────────
import httpx


class DeepgramTTS:
    """
    HTTP-streaming TTS (Aura-2). Deepgram's /v1/speak endpoint returns
    audio progressively — we yield chunks as they arrive so the caller
    can start playback before the whole sentence synthesises.

    Note: Deepgram does offer a WebSocket TTS variant. HTTP streaming is
    sufficient for Phase 1 (~100ms TTFB in practice) and simpler to wrap.
    If observed TTFB exceeds SLO in Phase 3 benchmarks, swap to WS.
    """
    def __init__(
        self,
        *,
        model: Optional[str] = None,
        encoding: str = "linear16",
        sample_rate: int = 24000,
    ) -> None:
        self._model = model or os.environ.get(
            "DEEPGRAM_TTS_MODEL", "aura-2-orion-en"
        )
        self._encoding = encoding
        self._sample_rate = sample_rate

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        api_key = os.environ["DEEPGRAM_API_KEY"]
        params = {
            "model": self._model,
            "encoding": self._encoding,
            "sample_rate": str(self._sample_rate),
            "container": "none",
        }
        headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        }
        payload = {"text": text}

        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                "https://api.deepgram.com/v1/speak",
                params=params, headers=headers, json=payload,
            ) as resp:
                if resp.status_code >= 300:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"DeepgramTTS HTTP {resp.status_code}: {body[:200]!r}"
                    )
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk

    @property
    def sample_rate(self) -> int:
        return self._sample_rate
```

- [ ] **Step 4: Pass + commit**

```bash
pytest tests/services/test_realtime_tts.py -v
git add services/realtime_voice.py tests/services/test_realtime_tts.py
git commit -m "feat(voice): DeepgramTTS streaming client (Aura-2 Orion)"
```

---

## Chunk 5: Sentence Segmenter + CruzAgent.stream_response()

**Rationale:** Turn token-level text deltas into whole sentences for TTS. Then build the shared `stream_response` async iterator that both the SSE endpoint and the LiveKit worker consume.

### Task 5.1: Sentence segmenter

**Files:**
- Create: `services/sentence_stream.py`
- Test: `tests/services/test_sentence_stream.py`

- [ ] **Step 1: Failing test**

```python
# tests/services/test_sentence_stream.py
import asyncio
import pytest

from services.sentence_stream import sentence_stream


async def _iter(tokens):
    for t in tokens:
        yield t
        await asyncio.sleep(0)  # hand control back to loop


@pytest.mark.asyncio
async def test_splits_on_sentence_terminators():
    tokens = ["Hello", " world", ".", " How", " are", " you", "?", " Fine", "."]
    out = [s async for s in sentence_stream(_iter(tokens))]
    assert out == ["Hello world.", "How are you?", "Fine."]


@pytest.mark.asyncio
async def test_flushes_trailing_fragment_without_terminator():
    tokens = ["incomplete", " fragment"]
    out = [s async for s in sentence_stream(_iter(tokens))]
    assert out == ["incomplete fragment"]


@pytest.mark.asyncio
async def test_handles_empty_stream():
    out = [s async for s in sentence_stream(_iter([]))]
    assert out == []
```

- [ ] **Step 2: Run — fails**

```bash
pytest tests/services/test_sentence_stream.py -v
```

- [ ] **Step 3: Implement**

```python
# services/sentence_stream.py
"""
Token → sentence adaptor. Buffers deltas until a sentence terminator
(`.`, `!`, `?`) followed by whitespace or EOF. Trailing non-terminated
text is flushed on stream close.

Known limitation: treats decimals and common abbreviations (Mr., e.g.)
as sentence breaks. Acceptable for voice output where a short pause
after "Mr." is natural. Revisit if artefact rate > 10%.
"""
from __future__ import annotations
import re
from typing import AsyncIterator

_SENTENCE_END = re.compile(r'[.!?](?:\s|$)')


async def sentence_stream(token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """
    Implementation note: during streaming, `$` in the regex matches the
    current buffer end (not true end-of-input). To avoid prematurely cutting
    on ambiguous punctuation like "Mr." mid-sentence, we only accept a
    sentence boundary when followed by actual whitespace. The trailing-
    fragment flush at the end handles genuine EOF.
    """
    # Same regex tuned: require whitespace or end-of-buffer-after-newline.
    buf = ""
    async for tok in token_stream:
        buf += tok
        while True:
            m = re.search(r'[.!?]\s', buf)
            if not m:
                break
            cut = m.end()
            sentence = buf[:cut].strip()
            if sentence:
                yield sentence
            buf = buf[cut:]
    if buf.strip():
        yield buf.strip()
```

- [ ] **Step 4: Pass + commit**

```bash
pytest tests/services/test_sentence_stream.py -v
git add services/sentence_stream.py tests/services/test_sentence_stream.py
git commit -m "feat(voice): sentence_stream token→sentence adaptor"
```

### Task 5.2: CruzAgent.stream_response()

**Files:**
- Modify: `agents/cruz/cruz_agent.py`
- Test: `tests/agents/test_cruz_stream.py`

- [ ] **Step 1: Event contract + failing test**

Stream events produced by `stream_response`:

```python
# agents/cruz/stream_events.py  (create)
from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class Text:
    content: str           # a full sentence ready for TTS

@dataclass
class ToolStart:
    agent: str
    summary: str            # short human-readable, e.g. "Running tests..."

@dataclass
class ToolFinish:
    agent: str
    result_preview: str

@dataclass
class ApprovalRequired:
    agent: str
    prompt: str
    payload: Dict[str, Any]

@dataclass
class Done:
    tokens_used: int
    duration_ms: int
```

Test:

```python
# tests/agents/test_cruz_stream.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agents.cruz.cruz_agent import CruzAgent
from agents.cruz.stream_events import Text, Done
from services.llm.stream_events import TextDeltaEvent, DoneEvent, UsageInfo


@pytest.mark.asyncio
async def test_stream_response_yields_sentences_then_done(monkeypatch):
    async def _fake_stream(**kw):
        yield TextDeltaEvent(delta="Deployment ")
        yield TextDeltaEvent(delta="complete. ")
        yield TextDeltaEvent(delta="All good.")
        yield DoneEvent(stop_reason="end_turn", usage=UsageInfo(5, 3))

    with patch("agents.cruz.cruz_agent.llm_chat_stream", _fake_stream), \
         patch("agents.cruz.cruz_agent.ConversationService") as conv_cls, \
         patch("agents.cruz.cruz_agent.SemanticMemoryService") as sem_cls, \
         patch("agents.cruz.cruz_agent.get_db_service"), \
         patch("agents.cruz.cruz_agent.get_qdrant_service"), \
         patch("agents.cruz.cruz_agent.get_embedding_service"):
        conv_cls.return_value.get_or_create_conversation = AsyncMock()
        conv_cls.return_value.load_history = AsyncMock(return_value=[])
        conv_cls.return_value.save_exchange = AsyncMock()
        sem_cls.return_value.search_similar = AsyncMock(return_value=[])
        sem_cls.return_value.store = AsyncMock()

        agent = CruzAgent()
        events = []
        async for ev in agent.stream_response(
            task="deploy ama",
            conversation_id="conv-1",
            trace_id="t-1",
            device="mac_mini",
        ):
            events.append(ev)

    texts = [e.content for e in events if isinstance(e, Text)]
    assert texts == ["Deployment complete.", "All good."]
    assert isinstance(events[-1], Done)
    assert events[-1].tokens_used == 8
```

- [ ] **Step 2: Run — fails**

```bash
pytest tests/agents/test_cruz_stream.py -v
```

- [ ] **Step 3: Add module-level imports to [agents/cruz/cruz_agent.py](agents/cruz/cruz_agent.py) (after existing imports, ~line 49)**

```python
from services.llm.router import chat_stream as llm_chat_stream
from services.sentence_stream import sentence_stream as _sentence_stream
from services.llm.stream_events import (
    TextDeltaEvent, ToolUseEvent, DoneEvent as _LLMDone,
)
from agents.cruz.stream_events import (
    Text, ToolStart, ToolFinish, ApprovalRequired, Done,
)

# Human-friendly "I'm working on it" phrasing per tool.
_TOOL_INTRO = {
    "forge": "Let me write that code.",
    "echo": "Drafting the message.",
    "reach": "Finding leads now.",
    "pm": "Updating tasks.",
    "catch": "Transcribing that for you.",
    "qt": "Running tests.",
    "sentinel": "Reviewing the code.",
    "titan": "Starting the deploy.",
    "mark": "Generating the docs.",
    "raw": "Researching.",
    "pulse": "Gathering your briefing.",
}
```

- [ ] **Step 4: Add `stream_response` as a method on the existing `CruzAgent` class**

Use `Edit` to insert it **inside** the class body, right after the `_dispatch_tool` method (around [cruz_agent.py:559](agents/cruz/cruz_agent.py:559)). **Do not** subclass `CruzAgent`.

```python
    async def stream_response(
        self,
        *,
        task: str,
        conversation_id: str,
        trace_id: str,
        device: Optional[str] = None,
    ):
        """
        Async iterator for voice + SSE paths. Yields:
          Text / ToolStart / ToolFinish / ApprovalRequired / Done
        Persists conversation + semantic memory identically to process().
        """
        import time as _time
        import uuid as _uuid
        start = _time.monotonic()
        total_tokens = 0

        db = get_db_service()
        conv_service = ConversationService(db)
        await conv_service.get_or_create_conversation(conversation_id)
        history = await conv_service.load_history(conversation_id)

        sem_service = SemanticMemoryService(
            get_qdrant_service(), get_embedding_service()
        )
        semantic_hits = await sem_service.search_similar(task, limit=10)

        messages: List[Dict[str, Any]] = [
            *semantic_hits, *history, {"role": "user", "content": task},
        ]

        tools = CRUZ_TOOLS
        hint = classify(task)
        if hint:
            f = [t for t in CRUZ_TOOLS if t["name"] == hint]
            if f:
                tools = f

        system_prompt = _SYSTEM_PROMPT
        max_reply_tokens = 512 if device in ("mac_mini", "phone", "ipad") else 4096
        if device in ("mac_mini", "phone", "ipad"):
            system_prompt += (
                "\n\nIMPORTANT: Voice mode — reply in 1-2 plain sentences under 40 words. "
                "No markdown, no lists."
            )

        # Buffer every spoken token across the whole turn. Used for persistence
        # AND for faithfully reconstructing the assistant message in history
        # when CRUZ mixes text with tool_use (must include text block alongside
        # tool_use blocks, per Anthropic message format).
        final_text_parts: list[str] = []

        while True:
            pending_tools: list[ToolUseEvent] = []
            turn_text_parts: list[str] = []

            async def _text_token_stream():
                nonlocal total_tokens
                async for ev in llm_chat_stream(
                    system=system_prompt, messages=messages,
                    tools=tools, max_tokens=max_reply_tokens,
                ):
                    if isinstance(ev, TextDeltaEvent):
                        turn_text_parts.append(ev.delta)
                        yield ev.delta
                    elif isinstance(ev, ToolUseEvent):
                        pending_tools.append(ev)
                    elif isinstance(ev, _LLMDone):
                        total_tokens += ev.usage.input_tokens + ev.usage.output_tokens

            async for sentence in _sentence_stream(_text_token_stream()):
                final_text_parts.append(sentence)
                yield Text(content=sentence)

            if not pending_tools:
                break

            # Dispatch tools
            tool_result_blocks = []
            for tu in pending_tools:
                yield ToolStart(
                    agent=tu.name,
                    summary=_TOOL_INTRO.get(tu.name, f"Running {tu.name}."),
                )
                out = await self._dispatch_tool(
                    tool_name=tu.name, tool_input=tu.input,
                    trace_id=trace_id, conversation_id=conversation_id,
                )
                if out.get("requires_approval"):
                    yield ApprovalRequired(
                        agent=tu.name,
                        prompt=out.get("approval_prompt") or "",
                        payload=tu.input,
                    )
                    yield Done(
                        tokens_used=total_tokens,
                        duration_ms=int((_time.monotonic() - start) * 1000),
                    )
                    return
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tu.tool_use_id,
                    "content": str(out.get("result", "")),
                })
                yield ToolFinish(
                    agent=tu.name,
                    result_preview=str(out.get("result", ""))[:200],
                )

            # Reconstruct assistant turn for history. Include any text that
            # came BEFORE the tool_use blocks — Anthropic rejects histories
            # that drop emitted content.
            assistant_content: list[dict] = []
            joined_turn_text = "".join(turn_text_parts).strip()
            if joined_turn_text:
                assistant_content.append({"type": "text", "text": joined_turn_text})
            for tu in pending_tools:
                assistant_content.append({
                    "type": "tool_use", "id": tu.tool_use_id,
                    "name": tu.name, "input": tu.input,
                })
            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_result_blocks})

        # Persist — matches process() parity at cruz_agent.py:400-417
        final_text = " ".join(final_text_parts).strip()
        if final_text:
            await conv_service.save_exchange(
                conversation_id=conversation_id,
                user_task=task,
                assistant_result=final_text,
            )
            await sem_service.store(
                id=str(_uuid.uuid4()), role="user",
                content=task, conversation_id=conversation_id,
            )
            await sem_service.store(
                id=str(_uuid.uuid4()), role="assistant",
                content=final_text, conversation_id=conversation_id,
            )

        yield Done(
            tokens_used=total_tokens,
            duration_ms=int((_time.monotonic() - start) * 1000),
        )
```

- [ ] **Step 5: Pass + commit**

```bash
pytest tests/agents/test_cruz_stream.py tests/agents/test_cruz_agent.py -v
git add agents/cruz/cruz_agent.py agents/cruz/stream_events.py tests/agents/test_cruz_stream.py
git commit -m "feat(cruz): stream_response() async iterator for voice + SSE paths"
```

### Task 5.3: Wire SSE endpoint to use stream_response

**Files:**
- Modify: `backend/api/main.py:363-397` (replace `_sse_stream`)
- Modify: `tests/api/test_streaming.py` (update expectations)

- [ ] **Step 1: Update test**

Add:

```python
# tests/api/test_streaming.py — append
@pytest.mark.asyncio
async def test_sse_emits_text_events_per_sentence(client, monkeypatch):
    from agents.cruz.stream_events import Text, Done
    async def _fake_stream(self, *, task, conversation_id, trace_id, device=None):
        yield Text(content="Deploying AMA now.")
        yield Text(content="Tests passing.")
        yield Done(tokens_used=42, duration_ms=900)
    monkeypatch.setattr("agents.cruz.cruz_agent.CruzAgent.stream_response", _fake_stream)

    r = await client.post("/command", json={
        "command": "deploy", "stream": True, "device": "mac_mini",
    })
    body = r.text
    assert 'data: {"type": "text", "content": "Deploying AMA now."}' in body
    assert 'data: {"type": "text", "content": "Tests passing."}' in body
    assert '"type": "done"' in body
```

- [ ] **Step 2: Run — fails**

```bash
pytest tests/api/test_streaming.py::test_sse_emits_text_events_per_sentence -v
```

- [ ] **Step 3: Rewrite `_sse_stream`**

Replace the body of `_sse_stream` in [backend/api/main.py:363](backend/api/main.py:363):

```python
async def _sse_stream(
    agent: CruzAgent,
    agent_input: AgentInput,
    trace_id: str,
    conversation_id: str,
) -> AsyncGenerator[str, None]:
    from agents.cruz.stream_events import (
        Text, ToolStart, ToolFinish, ApprovalRequired, Done,
    )
    try:
        async for ev in agent.stream_response(
            task=agent_input["task"],
            conversation_id=conversation_id,
            trace_id=trace_id,
            device=agent_input["context"].get("device"),
        ):
            if isinstance(ev, Text):
                yield _sse_event({"type": "text", "content": ev.content})
            elif isinstance(ev, ToolStart):
                yield _sse_event({"type": "tool_start", "agent": ev.agent, "summary": ev.summary})
            elif isinstance(ev, ToolFinish):
                yield _sse_event({"type": "tool_finish", "agent": ev.agent, "result": ev.result_preview})
            elif isinstance(ev, ApprovalRequired):
                yield _sse_event({
                    "type": "approval_required", "agent": ev.agent,
                    "approval_prompt": ev.prompt,
                })
            elif isinstance(ev, Done):
                yield _sse_event({
                    "type": "done", "trace_id": trace_id,
                    "conversation_id": conversation_id,
                    "tokens_used": ev.tokens_used,
                })
    except Exception as exc:
        yield _sse_event({"type": "error", "error": str(exc)})
        yield _sse_event({"type": "done", "trace_id": trace_id,
                          "conversation_id": conversation_id})
```

- [ ] **Step 4: Pass + commit**

```bash
pytest tests/api/test_streaming.py -v
git add backend/api/main.py tests/api/test_streaming.py
git commit -m "feat(api): SSE uses CruzAgent.stream_response for per-sentence events"
```

---

## Chunk 6: LiveKit Token Endpoint + Agent Worker

**Rationale:** Client (Mac daemon / future mobile) needs a JWT to join the LiveKit room. Worker runs on Mac Mini and bridges room audio ↔ Deepgram ↔ CRUZ.

### Task 6.1: LiveKit token minting endpoint

**Files:**
- Modify: `backend/api/main.py` (new route)
- Test: `tests/api/test_voice_token.py`

- [ ] **Step 1: Test**

```python
# tests/api/test_voice_token.py
import pytest

@pytest.mark.asyncio
async def test_voice_token_returns_jwt(client, monkeypatch):
    monkeypatch.setenv("LIVEKIT_API_KEY", "key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "s" * 32)
    monkeypatch.setenv("LIVEKIT_WS_URL", "wss://x.livekit.cloud")

    r = await client.post("/voice/token", json={"device_id": "mac-mini"})
    assert r.status_code == 200
    j = r.json()
    assert j["room"].startswith("cruz-")
    assert j["ws_url"] == "wss://x.livekit.cloud"
    assert len(j["token"].split(".")) == 3  # JWT
```

- [ ] **Step 2: Run — fails (404)**

```bash
pytest tests/api/test_voice_token.py -v
```

- [ ] **Step 3: Implement**

Append to [backend/api/main.py](backend/api/main.py) (near `/command`):

```python
class VoiceTokenRequest(BaseModel):
    device_id: str
    conversation_id: Optional[str] = None


@app.post("/voice/token")
async def voice_token(req: VoiceTokenRequest):
    """Mint a short-lived LiveKit JWT for a voice session."""
    import datetime
    from livekit import api as lkapi  # lazy import

    api_key = os.environ.get("LIVEKIT_API_KEY", "")
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "")
    ws_url = os.environ.get("LIVEKIT_WS_URL", "")
    if not (api_key and api_secret and ws_url):
        raise HTTPException(500, "LiveKit not configured")

    conversation_id = req.conversation_id or str(uuid.uuid4())
    room = f"cruz-{conversation_id}-{req.device_id}"

    token = (
        lkapi.AccessToken(api_key, api_secret)
        .with_identity(req.device_id)
        .with_name(req.device_id)
        .with_grants(lkapi.VideoGrants(
            room_join=True, room=room,
            can_publish=True, can_subscribe=True,
        ))
        .with_ttl(datetime.timedelta(minutes=15))
        .to_jwt()
    )
    return {"room": room, "token": token, "ws_url": ws_url,
            "conversation_id": conversation_id}
```

- [ ] **Step 4: Pass + commit**

```bash
pytest tests/api/test_voice_token.py -v
git add backend/api/main.py tests/api/test_voice_token.py
git commit -m "feat(api): /voice/token — mint LiveKit JWTs"
```

### Task 6.2: LiveKit Agent worker entrypoint

**Files:**
- Create: `workers/voice_agent/worker.py`
- Create: `workers/voice_agent/__init__.py`
- Test: `tests/workers/test_voice_agent_smoke.py` (unit, no live LiveKit)

- [ ] **Step 1: Skeleton test**

```python
# tests/workers/test_voice_agent_smoke.py
import pytest
from workers.voice_agent.worker import VoiceAgentConfig


def test_config_defaults_from_env(monkeypatch):
    monkeypatch.setenv("LIVEKIT_WS_URL", "wss://x")
    monkeypatch.setenv("LIVEKIT_API_KEY", "k")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "s" * 32)
    cfg = VoiceAgentConfig.from_env()
    assert cfg.ws_url == "wss://x"
    assert cfg.api_key == "k"
```

- [ ] **Step 2: Run — fails**

```bash
pytest tests/workers/test_voice_agent_smoke.py -v
```

- [ ] **Step 3: Implement**

```python
# workers/voice_agent/worker.py
"""
LiveKit Agent worker. Runs on the Mac Mini; listens to rooms named
cruz-<conversation_id>-<device_id>.

Per room, it:
  1. Subscribes to the participant's audio track
  2. Feeds frames to DeepgramSTT
  3. On each final transcript: calls CruzAgent.stream_response()
  4. Pipes sentence events to DeepgramTTS
  5. Publishes the synthesised audio back to the room
  6. Barge-in: when user speaks while CRUZ is speaking, cancel current TTS

Run locally:
    python -m workers.voice_agent.worker
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Optional

from livekit import rtc, agents  # type: ignore
from livekit.agents import JobContext, WorkerOptions, cli  # type: ignore

from agents.cruz.cruz_agent import CruzAgent
from agents.cruz.stream_events import Text, ToolStart, Done
from services.realtime_voice import DeepgramSTT, DeepgramTTS
from services.voice_sessions import VoiceSessionService
from services.db import get_db_service

logger = logging.getLogger("cruz.workers.voice_agent")


@dataclass
class VoiceAgentConfig:
    ws_url: str
    api_key: str
    api_secret: str

    @classmethod
    def from_env(cls) -> "VoiceAgentConfig":
        return cls(
            ws_url=os.environ["LIVEKIT_WS_URL"],
            api_key=os.environ["LIVEKIT_API_KEY"],
            api_secret=os.environ["LIVEKIT_API_SECRET"],
        )


async def entrypoint(ctx: JobContext) -> None:
    """Called by the LiveKit agent harness for each new room."""
    await ctx.connect()
    room = ctx.room
    logger.info("voice_agent joined room=%s", room.name)

    # room name format: cruz-<conversation_id>-<device_id>
    parts = room.name.split("-", 2)
    conversation_id = parts[1] if len(parts) > 1 else str(uuid.uuid4())
    device_id = parts[2] if len(parts) > 2 else "unknown"

    session_svc = VoiceSessionService(get_db_service())
    session_id = await session_svc.start(
        conversation_id=conversation_id,
        device_id=device_id,
        room=room.name,
    )

    stt = DeepgramSTT()
    tts = DeepgramTTS()
    await stt.connect()

    cruz = CruzAgent()
    tts_cancel = asyncio.Event()
    # `speaking` is flipped True while _speak is running — the barge-in detector
    # uses this instead of any LiveKit AudioSource internal state.
    speaking = {"active": False}
    audio_source = rtc.AudioSource(sample_rate=tts.sample_rate, num_channels=1)
    track = rtc.LocalAudioTrack.create_audio_track("cruz-voice", audio_source)
    await room.local_participant.publish_track(track)

    turns = 0
    barges = 0

    async def _pump_audio_into_stt():
        async for participant in _iter_remote_participants(room):
            async for frame in _iter_audio_frames(room, participant):
                # Barge-in: user speech while CRUZ is speaking → cancel TTS.
                if speaking["active"] and _is_speech(frame) and not tts_cancel.is_set():
                    tts_cancel.set()
                await stt.send(bytes(frame.data))

    async def _process_turns():
        nonlocal turns, barges
        async for t in stt.transcripts():
            if not t.is_final or not t.text.strip():
                continue
            turns += 1
            await session_svc.increment_turn(session_id)
            tts_cancel.clear()
            async for ev in cruz.stream_response(
                task=t.text,
                conversation_id=conversation_id,
                trace_id=str(uuid.uuid4()),
                device="mac_mini",
            ):
                if isinstance(ev, (Text, ToolStart)):
                    text = ev.content if isinstance(ev, Text) else ev.summary
                    speaking["active"] = True
                    try:
                        await _speak_with_fallback(text, tts, audio_source, tts_cancel)
                    finally:
                        speaking["active"] = False
                    if tts_cancel.is_set():
                        barges += 1
                        await session_svc.increment_barge(session_id)
                        break
                elif isinstance(ev, Done):
                    logger.info("turn done tokens=%d ms=%d",
                                ev.tokens_used, ev.duration_ms)

    try:
        await asyncio.gather(_pump_audio_into_stt(), _process_turns())
    finally:
        await stt.close()
        await session_svc.end(session_id, turns=turns, barges=barges)


async def _speak(text, tts, source, cancel_evt):
    async for pcm_chunk in tts.synthesize(text):
        if cancel_evt.is_set():
            return
        frame = rtc.AudioFrame(
            data=pcm_chunk, sample_rate=tts.sample_rate,
            num_channels=1, samples_per_channel=len(pcm_chunk) // 2,
        )
        await source.capture_frame(frame)


def _is_speech(frame) -> bool:
    import struct
    samples = struct.unpack(f"{len(frame.data)//2}h", bytes(frame.data))
    if not samples:
        return False
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
    return rms > 600


async def _iter_remote_participants(room):
    """Async generator of each remote participant as they join."""
    # (skeleton — fill in with actual LiveKit event subscriptions during impl)
    for p in list(room.remote_participants.values()):
        yield p
    # Also subscribe to `participant_connected` future events; see LiveKit docs.


async def _iter_audio_frames(room, participant):
    """Async generator of AudioFrames for the participant's first audio track."""
    # Implement using rtc.TrackSource / AudioStream
    raise NotImplementedError("wire up rtc.AudioStream in Phase 1 step 6.3")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
```

- [ ] **Step 4: Pass the smoke test**

```bash
pytest tests/workers/test_voice_agent_smoke.py -v
git add workers/voice_agent/ tests/workers/test_voice_agent_smoke.py
git commit -m "feat(voice): LiveKit agent worker skeleton (entrypoint + config)"
```

### Task 6.3: Wire participant/track iteration

The skeleton left `_iter_remote_participants` and `_iter_audio_frames` unfinished because they require live LiveKit state. Finish them using `rtc.RoomEvent.TrackSubscribed` and `rtc.AudioStream`:

- [ ] **Step 1: Implement `_iter_audio_frames` using `rtc.AudioStream`:**

```python
async def _iter_audio_frames(room, participant):
    async def _wait_for_audio_track():
        fut = asyncio.get_running_loop().create_future()
        def _on_sub(track, pub, p):
            if p.identity == participant.identity and track.kind == rtc.TrackKind.KIND_AUDIO:
                if not fut.done():
                    fut.set_result(track)
        room.on("track_subscribed", _on_sub)
        # Already-present track?
        for pub in participant.track_publications.values():
            if pub.kind == rtc.TrackKind.KIND_AUDIO and pub.track:
                return pub.track
        return await fut

    track = await _wait_for_audio_track()
    stream = rtc.AudioStream(track)
    async for event in stream:
        yield event.frame
```

- [ ] **Step 2: Implement `_iter_remote_participants`:**

```python
async def _iter_remote_participants(room):
    queue: asyncio.Queue = asyncio.Queue()
    for p in room.remote_participants.values():
        queue.put_nowait(p)
    def _on_conn(p): queue.put_nowait(p)
    room.on("participant_connected", _on_conn)
    while True:
        p = await queue.get()
        yield p
```

- [ ] **Step 3: Manual smoke test**

In one terminal run `python -m workers.voice_agent.worker dev`, in another run a LiveKit sample client against the same key/room. Speak "hello". Confirm CRUZ responds.

- [ ] **Step 4: Commit**

```bash
git add workers/voice_agent/worker.py
git commit -m "feat(voice): wire LiveKit AudioStream + participant subscription"
```

---

## Chunk 7: Mac Daemon — `livekit_client.py`

**Rationale:** Replace the HTTP-polling listener with a LiveKit-native client that: (a) runs openWakeWord, (b) joins the room via a token from `/voice/token`, (c) publishes mic audio when unmuted, (d) plays back received audio.

### Task 7.1: New Mac daemon

**Files:**
- Create: `scripts/voice/livekit_client.py`
- Keep (do not delete): `scripts/voice/listen.py` (fallback)

- [ ] **Step 1: Write the daemon**

```python
#!/usr/bin/env python3
"""
CRUZ Mac voice daemon (Phase 1).

- openWakeWord listens on a local mic stream
- On wake, POST /voice/token → LiveKit room JWT
- Join room, unmute mic track, publish audio
- Subscribe to agent's audio track, play to speakers
- After N seconds of silence, mute mic (gated STT — agent closes Deepgram WS)

Run:
    python scripts/voice/livekit_client.py --host http://localhost:3000
"""
from __future__ import annotations
import argparse, asyncio, os, sys, logging, httpx, uuid

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _ROOT not in sys.path: sys.path.insert(0, _ROOT)

from services.voice import WakeWordDetector  # existing
from livekit import rtc  # type: ignore
import sounddevice as sd  # type: ignore
import numpy as np

logger = logging.getLogger("cruz.voice.daemon")

SAMPLE_RATE = 16000
SILENCE_SECONDS_TO_MUTE = 15
WAKE_WORD_FRAME = 1280  # openWakeWord default (80ms @16k)


async def _fetch_token(host: str, device_id: str, conversation_id: str | None):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{host}/voice/token",
                         json={"device_id": device_id,
                               "conversation_id": conversation_id})
        r.raise_for_status()
        return r.json()


async def _join_and_run(tok_info, conversation_id):
    room = rtc.Room()
    await room.connect(tok_info["ws_url"], tok_info["token"])
    logger.info("joined %s", room.name)

    # Mic track
    mic_source = rtc.AudioSource(sample_rate=SAMPLE_RATE, num_channels=1)
    mic_track = rtc.LocalAudioTrack.create_audio_track("mic", mic_source)
    await room.local_participant.publish_track(mic_track)

    # Start muted; wake_loop unmutes on detection
    mic_track.mute()

    loop = asyncio.get_running_loop()

    # Output stream for CRUZ's voice — opened once, written to per frame.
    # `RawOutputStream` is non-blocking; sd.play() is not safe from async.
    playback_stream: dict[str, Optional[sd.RawOutputStream]] = {"s": None}

    def on_track_sub(track, pub, participant):
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        async def _play():
            stream = rtc.AudioStream(track)
            async for ev in stream:
                if playback_stream["s"] is None:
                    playback_stream["s"] = sd.RawOutputStream(
                        samplerate=ev.frame.sample_rate,
                        channels=1, dtype="int16", blocksize=0,
                    )
                    playback_stream["s"].start()
                playback_stream["s"].write(bytes(ev.frame.data))
        asyncio.create_task(_play())
    room.on("track_subscribed", on_track_sub)

    detector = WakeWordDetector(keyword="hey_jarvis")
    last_unmute = 0.0

    def _audio_cb(indata, frames, time_, status):
        nonlocal last_unmute
        # openWakeWord
        if mic_track.muted:
            if detector.detect(indata[:, 0]):
                mic_track.unmute()
                last_unmute = loop.time()
        # Publish frame either way (muted flag stops it server-side)
        frame = rtc.AudioFrame(
            data=indata.tobytes(), sample_rate=SAMPLE_RATE,
            num_channels=1, samples_per_channel=frames,
        )
        loop.call_soon_threadsafe(
            asyncio.create_task, mic_source.capture_frame(frame))

    with sd.InputStream(
        channels=1, samplerate=SAMPLE_RATE, dtype="int16",
        blocksize=WAKE_WORD_FRAME, callback=_audio_cb,
    ):
        while True:
            await asyncio.sleep(1)
            if not mic_track.muted and loop.time() - last_unmute > SILENCE_SECONDS_TO_MUTE:
                mic_track.mute()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:3000")
    ap.add_argument("--conversation-id", default=None)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)
    conv_id = args.conversation_id or str(uuid.uuid4())
    tok = await _fetch_token(args.host, device_id="mac-mini", conversation_id=conv_id)
    await _join_and_run(tok, conv_id)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Manual run**

Start backend + worker in two terminals, then:

```bash
python scripts/voice/livekit_client.py --host http://localhost:3000
```

Say "Hey Jarvis, what's the weather". Confirm Mac speakers play Orion voice. Expect <2s E2E.

- [ ] **Step 3: Commit**

```bash
git add scripts/voice/livekit_client.py
git commit -m "feat(voice): Mac LiveKit daemon — openWakeWord gated mic, audio playback"
```

---

## Chunk 8: E2E Integration Test + Fallback Verification

**Rationale:** Phase 1 exit criterion is "<2s E2E, barge-in works, Mac wake-word reliable". Need one test that exercises the whole loop with real-ish services, plus explicit fallback proof.

### Task 8.1: Latency harness

**Files:**
- Create: `tests/integration/test_voice_latency.py`
- Create fixture: `tests/integration/fixtures/hello_cruz.wav` (record or use a TTS clip)

- [ ] **Step 1: Add fixture — 1s clip of "hello cruz" at 16kHz mono**

```bash
say -v Daniel "Hello Cruz, what time is it" -o /tmp/hc.aiff
ffmpeg -y -i /tmp/hc.aiff -ar 16000 -ac 1 -acodec pcm_s16le \
  tests/integration/fixtures/hello_cruz.wav
```

- [ ] **Step 2: Integration test (marked, opt-in)**

```python
# tests/integration/test_voice_latency.py
import os, time, asyncio, pytest, pathlib

pytestmark = pytest.mark.voice

@pytest.mark.asyncio
async def test_e2e_under_2s():
    if not os.environ.get("DEEPGRAM_API_KEY"):
        pytest.skip("no DEEPGRAM_API_KEY; integration test skipped")
    from services.realtime_voice import DeepgramSTT, DeepgramTTS

    audio = pathlib.Path("tests/integration/fixtures/hello_cruz.wav").read_bytes()
    t0 = time.monotonic()
    stt = DeepgramSTT(); await stt.connect()
    await stt.send(audio[44:])  # strip WAV header, send PCM
    final_text = None
    async for t in stt.transcripts():
        if t.is_final:
            final_text = t.text
            break
    t_stt = time.monotonic()
    assert final_text and "cruz" in final_text.lower()

    tts = DeepgramTTS()
    t_first_byte = None
    async for _chunk in tts.synthesize("That's 3 PM."):
        if t_first_byte is None:
            t_first_byte = time.monotonic()
        break
    await stt.close()

    stt_ms = int((t_stt - t0) * 1000)
    tts_ms = int((t_first_byte - t_stt) * 1000)
    total = int((t_first_byte - t0) * 1000)
    print(f"STT={stt_ms}ms TTS_TTFB={tts_ms}ms STT+TTS={total}ms")
    # Network-only ceiling: STT+TTS alone must stay under 1.2s; real E2E
    # adds Sonnet TTFT (measured in the full_e2e test below).
    assert total < 1200


@pytest.mark.asyncio
async def test_full_e2e_includes_sonnet_first_sentence():
    """
    True E2E: audio in → first TTS byte via CruzAgent.stream_response.
    This covers Sonnet TTFT, which is the largest hop (per spec Section 4).
    Phase 1 exit SLO: first TTS byte within 2000ms of STT-final.
    """
    if not (os.environ.get("DEEPGRAM_API_KEY") and os.environ.get("ANTHROPIC_API_KEY")):
        pytest.skip("needs DEEPGRAM_API_KEY + ANTHROPIC_API_KEY")
    from agents.cruz.cruz_agent import CruzAgent
    from agents.cruz.stream_events import Text
    from services.realtime_voice import DeepgramSTT, DeepgramTTS

    audio = pathlib.Path("tests/integration/fixtures/hello_cruz.wav").read_bytes()
    stt = DeepgramSTT(); await stt.connect()
    await stt.send(audio[44:])
    final = None
    async for t in stt.transcripts():
        if t.is_final:
            final = t.text; break
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

    e2e_ms = int((first_audio_byte_at - t_final) * 1000)
    print(f"STT-final → first TTS byte = {e2e_ms}ms")
    assert e2e_ms < 2000, f"Phase 1 SLO breach: {e2e_ms}ms > 2000ms"
```

- [ ] **Step 3: Run**

```bash
DEEPGRAM_API_KEY=... pytest tests/integration/test_voice_latency.py -v -m voice -s
```

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_voice_latency.py tests/integration/fixtures/hello_cruz.wav
git commit -m "test(voice): E2E latency harness — asserts < 2s from audio-in to TTS first byte"
```

### Task 8.2: Fallback matrix test

**Files:**
- Create: `tests/integration/test_voice_fallback.py`

- [ ] **Step 1: Test — each primary fails, verify fallback**

```python
# tests/integration/test_voice_fallback.py
import pytest
from unittest.mock import patch

pytestmark = pytest.mark.voice


@pytest.mark.asyncio
async def test_tts_falls_back_to_inworld_when_deepgram_errors(monkeypatch):
    """
    LiveKit worker's _speak should fall back to services.voice.VoicePipeline.speak
    when DeepgramTTS raises. This test drives that path directly.
    """
    from workers.voice_agent.worker import _speak_with_fallback

    class BoomTTS:
        sample_rate = 24000
        async def synthesize(self, text):
            raise RuntimeError("deepgram down")
            yield b""

    class FakeSource:
        captured = []
        async def capture_frame(self, frame):
            self.captured.append(frame)

    import asyncio
    from services.voice import VoicePipeline
    cancel = asyncio.Event()
    with patch.object(VoicePipeline, "speak", return_value=b"\x00\x01" * 100):
        await _speak_with_fallback("hi", BoomTTS(), FakeSource(), cancel)

    # Test passes if no exception raised; fallback path covered by mock
```

- [ ] **Step 2: Add `_speak_with_fallback` to worker**

In [workers/voice_agent/worker.py](workers/voice_agent/worker.py) add:

```python
async def _speak_with_fallback(text, tts, source, cancel):
    """Try DeepgramTTS; fall back to Inworld (services.voice.VoicePipeline)."""
    try:
        await _speak(text, tts, source, cancel)
        return
    except Exception as exc:
        logger.warning("DeepgramTTS failed, falling back to Inworld: %s", exc)
    from services.voice import VoicePipeline
    audio = await VoicePipeline().speak(text)
    # Inworld returns MP3 — decode to PCM for LiveKit. Lean on system tool:
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3:
        mp3.write(audio); mp3_path = mp3.name
    pcm = subprocess.check_output([
        "ffmpeg", "-i", mp3_path, "-f", "s16le",
        "-ar", str(tts.sample_rate), "-ac", "1", "-loglevel", "error", "pipe:1"
    ])
    frame = rtc.AudioFrame(
        data=pcm, sample_rate=tts.sample_rate, num_channels=1,
        samples_per_channel=len(pcm)//2,
    )
    await source.capture_frame(frame)
```

And replace calls to `_speak(...)` in `_process_turns` with `_speak_with_fallback(...)`.

- [ ] **Step 3: Pass + commit**

```bash
pytest tests/integration/test_voice_fallback.py -v -m voice
git add workers/voice_agent/worker.py tests/integration/test_voice_fallback.py
git commit -m "feat(voice): TTS fallback to Inworld when Deepgram Aura-2 fails"
```

### Task 8.3: Docs — runbook

**Files:**
- Create: `docs/voice/phase1-runbook.md`

- [ ] **Step 1: Write ops runbook**

```markdown
# Voice Phase 1 — Runbook

## Start dev stack

    brew services start postgresql@16 redis
    docker compose up -d qdrant
    # apply schema additions
    psql "$DATABASE_URL" -f backend/models/schema.sql

## Run backend + worker + daemon (3 terminals)

    # terminal 1 — API
    source venv/bin/activate && python backend/api/main.py

    # terminal 2 — LiveKit voice agent worker
    source venv/bin/activate && python -m workers.voice_agent.worker dev

    # terminal 3 — Mac mic daemon
    source venv/bin/activate && python scripts/voice/livekit_client.py

## Verify

- Say "Hey Jarvis, what time is it" — Orion voice should respond in <2s
- Speak over CRUZ mid-reply — TTS should cut within ~300ms (barge-in)
- Kill Deepgram API key mid-session — reply should still complete via Inworld fallback
- `SELECT * FROM voice_sessions ORDER BY started_at DESC LIMIT 5;` — new row with turns>=1

## Troubleshooting

- No Orion voice: check `DEEPGRAM_API_KEY` and `DEEPGRAM_TTS_MODEL=aura-2-orion-en`
- Wake word doesn't trigger: `openwakeword.utils.download_models()` may need first-run
- Agent worker won't connect: verify `LIVEKIT_WS_URL` matches `/voice/token` response
```

- [ ] **Step 2: Commit**

```bash
git add docs/voice/phase1-runbook.md
git commit -m "docs(voice): Phase 1 runbook + troubleshooting"
```

---

## Exit Checklist (Phase 1 Done)

- [ ] `pytest tests/ -v` — all green (non-voice tests)
- [ ] `pytest tests/ -m voice -v` — all green with DEEPGRAM_API_KEY + LIVEKIT creds
- [ ] Manual: wake word → transcript → streamed Orion voice reply < 2s on Mac
- [ ] Manual: barge-in stops TTS within 500ms
- [ ] Manual: `services/realtime_voice.py` disabled → `scripts/voice/listen.py` still works end-to-end (HTTP fallback intact)
- [ ] `voice_sessions` row created per conversation with turn/barge counts
- [ ] No regressions in `pytest tests/api/test_command_endpoint.py tests/api/test_streaming.py`

---

## Out of Scope (handed to Phase 2+)

- Mobile PTT button + React Native integration
- FCM push + approval gate endpoints
- Progress narration during long tool calls (currently just the intro phrase)
- LiveKit self-host migration
- Multi-device handoff beyond same-device continuity
- Ollama/Gemini streaming (only anthropic supports it in Phase 1)

Each of these gets its own plan under `docs/superpowers/plans/`.
