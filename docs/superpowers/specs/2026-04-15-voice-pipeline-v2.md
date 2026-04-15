# Voice Pipeline v2 — "FRIDAY-quality" Realtime Voice

**Author:** Darshan Parmar
**Date:** 2026-04-15
**Status:** Spec — decisions locked, awaiting implementation plan
**Supersedes:** Voice section of [CLAUDE.md](../../../CLAUDE.md) (Whisper + Inworld HTTP)

---

## 1. Goals

1. **E2E latency to first audio ≤ 1.8s** (target 1.5s) — vs current ~3.1–3.6s.
2. **Full-duplex streaming** — user can interrupt CRUZ mid-reply (barge-in).
3. **Progress narration** during long tool calls — CRUZ speaks as FORGE/QT/TITAN work.
4. **Cross-device conversation continuity** — same `conversation_id`, any device.
5. **FRIDAY-grade voice persona** — cloned JARVIS voice, British accent, calm authority.
6. **No regressions** — existing HTTP `/voice/transcribe` + `/voice/speak` remain as fallback.

## 2. Non-Goals (v1)

- Wake word on mobile (mobile = push-to-talk only).
- Multi-participant rooms (one human per room).
- On-device STT/TTS on phone (cloud only).
- Real-time translation (Whisper-based fallback handles multilingual later).

---

## 3. Architecture

### 3.1 Component diagram

```
┌───────────────────────── Client ──────────────────────────┐
│                                                            │
│  Mac / iPad: openWakeWord ──► unmute STT                  │
│  Phone:      PTT button    ──► unmute STT                 │
│                                                            │
│           LiveKit React Native / Web SDK                   │
│                    │ WebRTC (opus)                         │
└────────────────────┼───────────────────────────────────────┘
                     ▼
       ┌──── LiveKit Cloud (Phase 1) ─── Self-hosted (Phase 3) ────┐
       │  Room: cruz-session-<conversation_id>-<device_id>           │
       └──────────────┬──────────────────────────────────────────────┘
                      ▼
    ┌──────── LiveKit Agent Worker (Python, on Mac Mini) ────────────┐
    │                                                                  │
    │  ┌─ Silero VAD ─► Deepgram Nova-3 WS ─► partial + final texts ─┐│
    │  │                                                               ││
    │  │                           ▼                                   ││
    │  │  CRUZ Agent (Sonnet 4.6, streaming tool_use)                ││
    │  │                                                               ││
    │  │  ┌── Sentence Segmenter ──► Deepgram Aura-2 WS ──┐           ││
    │  │  │  (punctuation-based)    (streaming TTS)        │           ││
    │  │  └────────────────────────────────────────────────┘           ││
    │  │                           │                                   ││
    │  │                           ▼                                   ││
    │  │              Opus encode ──► LiveKit publish                 ││
    │  │                                                               ││
    │  │  Concurrent side effects:                                    ││
    │  │   - Persist messages / agent_logs (shared w/ HTTP endpoint)  ││
    │  │   - Fire FCM push on approval-required events                ││
    │  │   - Emit progress narration during long tool calls           ││
    │  └───────────────────────────────────────────────────────────────┘│
    └──────────────────────────────────────────────────────────────────┘
```

### 3.2 Resolved decisions

| Area | Decision |
|---|---|
| Wake word | openWakeWord on Mac, push-to-talk on mobile |
| Session lifecycle | Persistent room, gated STT (WS opens on wake / PTT press) |
| Interruption policy | Cancel TTS; let tool calls finish; store result in `messages` for next turn |
| Long tool-call UX | Progress narration streamed from each agent |
| Approval gates | FCM push with Approve/Deny; voice says "check your phone" |
| Multi-device | Same `conversation_id`, separate LiveKit rooms per device |
| LiveKit hosting | LiveKit Cloud for first 2 months, self-host after |
| TTS | Deepgram **Aura-2 Orion** (`model=aura-2-orion-en`, American accent, 101ms TTFB) |
| Fallback | Full existing stack stays intact as secondary path |

---

## 4. Latency Budget (SLO)

| Hop | p50 | p95 | SLO |
|---|---|---|---|
| Wake word → STT gate open | 150ms | 300ms | 400ms |
| User stops speaking → Deepgram final | 250ms | 500ms | 600ms |
| Deepgram final → Sonnet TTFT | 700ms | 1200ms | 1500ms |
| Sonnet first sentence → Aura TTFB | 200ms | 400ms | 500ms |
| Aura TTFB → speaker audio | 100ms | 250ms | 300ms |
| **E2E to first audio** | **1.4s** | **2.65s** | **3.0s** |
| Barge-in → TTS stops | <150ms | <300ms | 500ms |

SLO breach triggers Sentry alert. Metric source: `agent_logs.duration_ms` with per-hop sub-spans.

---

## 5. Component Design

### 5.1 Wake word (unchanged on Mac)

- Reuses [services/voice.py:278 `WakeWordDetector`](../../../services/voice.py) — openWakeWord default.
- Runs in a thin `scripts/voice/livekit_client.py` daemon replacing current `listen.py`.
- On detection: publish `wake-detected` event to LiveKit data channel, unmute audio track.

### 5.2 Gated STT

- LiveKit room stays connected 24/7 when daemon is running.
- Audio track is **muted by default**.
- Deepgram WebSocket is **closed by default** (zero cost idle).
- Wake word / PTT press → unmute track → agent worker opens Deepgram WS.
- 30s of silence post-turn → close WS, mute track, return to idle.
- Endpointing: Deepgram `endpointing=300` (ms silence = turn end). Tune in Phase 2.

### 5.3 CRUZ Agent streaming loop

New method `CruzAgent.stream_response(user_text, conversation_id)` that:

1. Loads last 50 messages + top-10 Qdrant retrieval.
2. Calls `client.messages.stream()` with full tool registry.
3. Emits three event types:
   - `text_delta` — token chunk
   - `tool_use` — tool invoked (agent name, inputs)
   - `tool_result` — tool finished (result summary)
4. A **sentence segmenter** buffers `text_delta` events until `. ! ?` or 200ms idle, then flushes to TTS.
5. Tool calls run async; their results are fed back into the stream. Progress narration is a prefab short sentence ("Running tests…") emitted by the agent wrapper **before** the tool call blocks.

Shared contract — the **same** `stream_response` function is called by both the HTTP `/command` SSE endpoint and the LiveKit Agent worker. No code duplication.

### 5.4 Sentence segmenter

```python
async def sentence_stream(token_stream) -> AsyncIterator[str]:
    buf = ""
    async for tok in token_stream:
        buf += tok
        while (m := _SENTENCE_END.search(buf)):
            yield buf[:m.end()].strip()
            buf = buf[m.end():]
    if buf.strip():
        yield buf.strip()
```

Regex: `r'[.!?](?:\s|$)'` — simple, handles 95% of cases. Known edge: decimals, abbreviations. Accept 5% mis-splits for v1.

### 5.5 Deepgram Aura-2 TTS streaming

- One WS per sentence (Aura-2's streaming model). Connection overhead ~50ms — acceptable.
- Model: `aura-2-orion-en` (American, deep-warm, 101ms TTFB). Overridable via `DEEPGRAM_TTS_MODEL` env.
- Encoding: linear16 @ 24kHz → opus-encode in worker → publish to LiveKit.
- Fallback: if Deepgram WS fails to open within 300ms, fall back to Inworld REST ([services/voice.py:200](../../../services/voice.py)).

### 5.6 Barge-in handling

- LiveKit Agent worker subscribes to user audio track.
- Silero VAD frame > threshold **while CRUZ is speaking** → `TTS.cancel()` + close Aura WS.
- Current tool call continues running — its result writes to `messages` table with `role='tool'` and `metadata.superseded=true`. CRUZ sees this on next turn and may reference it.
- **Never** cancels a tool call mid-flight (too expensive to re-run FORGE code gen).

### 5.7 Approval gates via FCM

- Existing `AgentOutput.requires_approval=True` path unchanged.
- New: when in voice context, CRUZ does two things simultaneously:
  1. Speaks: "Ready to deploy AMA to prod. Check your phone to confirm."
  2. POSTs to `/approval/request` → FCM push to registered device tokens.
- FCM payload includes `action_id`, action summary, Approve/Deny deep links.
- 30s timeout → cancel. 2min timeout → escalate to Slack DM fallback.
- Approval response hits `/approval/respond` → resumes the tool call.

### 5.8 Progress narration

- Each long-running agent (FORGE, QT, TITAN, REACH) emits `progress` events on an asyncio Queue every time it crosses a meaningful milestone.
- CRUZ's streaming loop multiplexes these into the text stream between tool calls.
- Example: TITAN emits `{"progress": "deploying to vercel preview"}` → appears as a filler sentence between the plan narration and the final confirmation.
- Cap: max 1 progress narration every 4s to avoid babbling.

---

## 6. Data Model Changes

### 6.1 New table: `voice_sessions`

```sql
CREATE TABLE voice_sessions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID REFERENCES conversations(id),
    device_id        VARCHAR(100) NOT NULL,   -- e.g. "mac-mini", "phone-nothing-2"
    livekit_room     VARCHAR(200) NOT NULL,
    started_at       TIMESTAMP DEFAULT NOW(),
    ended_at         TIMESTAMP,
    deepgram_ws_ms   INTEGER DEFAULT 0,       -- cumulative WS open time (cost tracking)
    turns            INTEGER DEFAULT 0,
    barges           INTEGER DEFAULT 0
);
CREATE INDEX idx_voice_sessions_conv ON voice_sessions(conversation_id);
```

### 6.2 New columns on `messages`

```sql
ALTER TABLE messages ADD COLUMN voice_session_id UUID REFERENCES voice_sessions(id);
ALTER TABLE messages ADD COLUMN audio_ms INTEGER;  -- length of spoken turn
```

### 6.3 New table: `approval_requests`

```sql
CREATE TABLE approval_requests (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id     UUID NOT NULL,
    agent        VARCHAR(50) NOT NULL,
    action       VARCHAR(100) NOT NULL,
    payload      JSONB NOT NULL,              -- what will execute if approved
    state        VARCHAR(20) DEFAULT 'pending', -- pending|approved|denied|timeout
    requested_at TIMESTAMP DEFAULT NOW(),
    responded_at TIMESTAMP,
    expires_at   TIMESTAMP NOT NULL
);
```

### 6.4 New table: `fcm_tokens`

```sql
CREATE TABLE fcm_tokens (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    INTEGER REFERENCES users(id),
    device     VARCHAR(50) NOT NULL,
    token      TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, device)
);
```

All four migrations go through Alembic per CLAUDE.md.

---

## 7. API Changes

### 7.1 New endpoints

```
POST /voice/token
  Body: {"conversation_id"?: uuid, "device_id": str}
  Returns: {"room": str, "token": str (JWT for LiveKit), "ws_url": str}
  - Mints a short-lived (15min) LiveKit room token.

POST /approval/request
  (internal; called by agent worker when requires_approval=True)
  Body: {"trace_id", "agent", "action", "payload", "expires_in_seconds"}
  Returns: {"approval_id": uuid}
  Side effect: sends FCM push to all user's devices.

POST /approval/respond
  Body: {"approval_id": uuid, "decision": "approve"|"deny"}
  Returns: {"state": str}
  Side effect: unblocks the waiting tool call.

POST /fcm/register
  Body: {"device": str, "token": str}
  Registers a device for push notifications.

GET /voice/session/:id
  Returns voice_session record + aggregate stats.
```

### 7.2 Unchanged (still works, used as fallback)

- `POST /voice/transcribe` — Whisper local
- `POST /voice/speak` — Inworld + macOS `say`
- `POST /command` — SSE streaming CRUZ

---

## 8. Fallback Matrix

| Primary fails | Fallback |
|---|---|
| Deepgram STT WS | faster-whisper via `/voice/transcribe` (HTTP) |
| Sonnet 4 | Haiku 4.5, then queue with 60s retry |
| Deepgram Aura-2 | Inworld TTS 1.5 Max REST |
| Inworld REST | macOS `say` (Mac only) |
| LiveKit Cloud | HTTP `/command` + `/voice/transcribe` + `/voice/speak` round-trip |
| FCM push | Slack DM → SMS (Twilio, future) |
| openWakeWord | Picovoice (already implemented) |

`services/voice.py` stays; becomes the **fallback layer**. New code in `services/realtime_voice.py`.

---

## 9. Cost Model

Assumptions: 300 conversation minutes/month, avg 12 turns each, 8s user + 6s CRUZ per turn.

| Component | Unit cost | Monthly usage | Monthly cost |
|---|---|---|---|
| Deepgram Nova-3 STT | $0.0077 / min | ~300 min | $2.31 |
| Deepgram Aura-2 Orion | $0.030 / 1k chars | ~225k chars | $6.75 |
| Claude Sonnet 4 | $3 in / $15 out per MTok | ~450k in / 120k out | $3.15 |
| LiveKit Cloud | Free tier 10k min | ~300 min | $0 |
| FCM push | Free | unlimited | $0 |
| Qdrant / Postgres / Redis | Self-hosted | — | $0 |
| **New voice stack total** | | | **$8.84 (~₹735)** |
| Retained: Inworld (fallback only) | | | ₹71 |
| **Grand total** | | | **~₹800/mo** |

Deepgram $200 free credit covers first ~24 months. Actual paid cost starts mid-2028.

Per CLAUDE.md overall budget: voice was ₹71 → now ₹800. Net add: ~₹730/mo. Offset by removing Inworld primary, reducing to ₹600/mo net delta. Absorbed within FRIDAY-quality goal.

---

## 10. Phased Rollout

### Phase 1 — Mac-only MVP (Week 1–2)
- LiveKit Cloud account + JARVIS voice clone validated
- `services/realtime_voice.py` with Deepgram STT + Aura-2 TTS streaming
- `scripts/voice/livekit_client.py` Mac daemon (replaces `listen.py`)
- LiveKit Agent worker on Mac Mini
- Shared `CruzAgent.stream_response()` used by both HTTP and LiveKit paths
- DB migrations for `voice_sessions`, `approval_requests`, `fcm_tokens`
- **Exit criterion:** <2s E2E, barge-in works, Mac wake-word reliable

### Phase 2 — Mobile + approvals (Week 3–4)
- React Native LiveKit SDK integration
- PTT button on mobile
- FCM push + `/approval/request` + `/approval/respond`
- Approve/Deny deep links
- **Exit criterion:** deploy AMA from phone with voice + FCM confirm

### Phase 3 — Self-host LiveKit (Month 3)
- Docker LiveKit server on Mac Mini
- coturn TURN server
- Migrate from LiveKit Cloud
- Sentry + Grafana Loki dashboards for voice latency SLOs
- **Exit criterion:** ₹0/mo LiveKit, SLO dashboards green for 7 days

### Phase 4 — Polish (Month 4+)
- Progress narration for all agents
- Multi-language Whisper fallback when Deepgram confidence low
- iPad secondary support
- Voice analytics: turn length, barge rate, approval latency

---

## 11. Test Strategy

| Layer | Approach |
|---|---|
| `services/realtime_voice.py` unit | Mock Deepgram + Aura WS with recorded transcripts/audio |
| Sentence segmenter | Property-based tests (Hypothesis) over token streams |
| CRUZ streaming loop | Fake tool registry, assert event order |
| LiveKit Agent worker | LiveKit's `AgentSession` test harness |
| FCM push + approval roundtrip | Stub FCM, full Postgres |
| E2E latency | Canned 6 audio fixtures (short/long, interrupt/no-interrupt, tool-call/direct); runs in CI with real Deepgram free-tier key; asserts p95 < 2s |
| Fallback matrix | Integration test that kills each primary in turn and verifies fallback path completes |

Written same day as code per CLAUDE.md standard. All voice tests tagged `@pytest.mark.voice` so the default `pytest` run skips them (they hit external APIs).

---

## 12. Known Risks

| Risk | Mitigation |
|---|---|
| Deepgram voice cloning gated / delayed | Fall back to ElevenLabs Flash v2.5 ($5/mo, same latency) |
| LiveKit Cloud latency from India | Measure in Phase 1. If >200ms, move to self-host earlier |
| Sonnet 4 TTFT > 700ms p50 | Prompt cache warm-up; pre-emit "let me check…" filler |
| Mobile PTT discoverability | Big button, haptic feedback; fallback SMS command via Telegram |
| FCM delivery >5s | Parallel Slack DM + in-app websocket notification |
| openWakeWord false positives waking Mac at night | `QUIET_HOURS` env var mutes STT between 23:00–07:00 |
| Barge-in triggered by background noise | Require 300ms of sustained user audio before TTS cancel |

---

## 13. Open Items Deferred to Implementation

- Exact opus encoder (pyogg vs livekit built-in) — decide in Phase 1
- JARVIS voice ID format (Deepgram vs ElevenLabs) — pending user provisioning
- Quiet hours schedule — user preference, default 23:00–07:00 IST
- iPad: LiveKit PWA vs RN — decide in Phase 4

---

## 14. Success Metrics (30 days post-launch)

- p50 E2E latency < 1.5s, p95 < 2.5s
- Barge-in rate 15–30% (sanity check: users comfortable interrupting)
- Approval roundtrip p95 < 10s
- 99% voice session completion (no crashes / dropped WS mid-turn)
- Monthly voice cost < ₹1000
- Zero regressions in HTTP `/command` path

---

**Next step:** implementation plan via `superpowers:writing-plans`, broken into the 4 phases above. Phase 1 blocks everything else — start there.
