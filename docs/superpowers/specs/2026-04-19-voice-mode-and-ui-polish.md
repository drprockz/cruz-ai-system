# Voice Mode + UI Polish — Design Spec

**Author:** CRUZ (autonomous AFK session)
**Date:** 2026-04-19
**Status:** Executing

## Context

After the Persona v1 ship, the remaining gap to a "Claude voice mode / ChatGPT voice" experience is (a) continuous duplex voice instead of tap-to-toggle, and (b) surface polish on the existing Command Center. The backend voice pipeline (LiveKit + Deepgram STT + Claude streaming + Deepgram TTS) already works end-to-end; the gap is in the UI layer.

## Non-goals (explicit)

- Full rewrite to Electron / React Native (Capacitor stays deferred; already discussed).
- Wake-word tuning (openWakeWord) — needs user-present mic testing.
- New third-party services (cost constraint from user: "stop if higher costs than anticipated").
- Touching persona layer, cruz_agent core, or backend agent plumbing.
- Matching GPT-4o Realtime latency — that needs a different backend stack entirely.

## Iteration log

I drafted this plan, then critiqued it three times before locking. Summary of what changed across iterations:

**v0 (brain dump):** Dedicated full-screen `/voice` route, audio-reactive orb, interim transcripts via LiveKit data channels, full Tailwind theme rewrite, command palette, skeleton shimmer, micro-interactions everywhere.

**v1 (critique: too much):** Command palette is a nice-to-have, not production-critical. Tailwind theme rewrite risks breaking every component — scoped to design tokens + targeted surface fixes instead. Skeleton shimmer only where first-paint is >300ms (Dashboard, Events).

**v2 (critique: voice mode complexity):** Canvas-based orb is correct (SVG can't do 60fps amplitude-reactive rendering cleanly), but I was going to build the analyser graph from scratch — LiveKit already exposes `Track.mediaStreamTrack` which plugs straight into `AudioContext.createMediaStreamSource`. Simpler than I thought. Also: the "thinking" state needs a real signal, not a timer. The worker's `Done` event on the data channel is the truth source.

**v3 (critique: failure modes):** What happens if the data channel message arrives before the audio track? Order the orb state off the `RoomEvent.ActiveSpeakersChanged` (always-correct) and use data channel only for transcript text. What if user double-clicks End? Idempotent disconnect. What if the LiveKit token expires mid-session (15 min TTL)? Add auto-refresh with a 30s margin. What if the mic permission was granted once but Chrome's audio settings changed? Catch `NotAllowedError` specifically and show a user-facing message, not a console warning.

**Locked plan below reflects v3.**

## Architecture

```
┌───────────────────────────────────────────────────┐
│ /voice (full-screen route)                        │
│ ┌───────────────────────────────────────────────┐ │
│ │ VoiceOrb (canvas)                             │ │
│ │   ← Web Audio AnalyserNode on:                │ │
│ │      • local mic track (listening state)      │ │
│ │      • remote agent track (speaking state)    │ │
│ │   ← state from useVoiceSession                │ │
│ └───────────────────────────────────────────────┘ │
│ ┌───────────────────────────────────────────────┐ │
│ │ LiveTranscript                                │ │
│ │   • interim (gray, italic)                    │ │
│ │   • final (white, locked)                     │ │
│ │   • reply (green, streaming)                  │ │
│ │   ← from LiveKit data channel                 │ │
│ └───────────────────────────────────────────────┘ │
│ [End call]                                        │
└───────────────────────────────────────────────────┘
```

State machine in `useVoiceSession`:
- `idle` — room not connected yet
- `listening` — mic is hot, user speaking (activeSpeakers includes local)
- `thinking` — final transcript received, no agent audio yet
- `speaking` — activeSpeakers includes agent
- `error` — unrecoverable (shown as orb in red)

Transitions are driven by:
- `RoomEvent.ActiveSpeakersChanged` (authoritative for listening↔speaking)
- Data channel messages for transcript text (never for state)
- Errors for transition to `error`

## Files touched

### Voice mode (new or modified)

| File | Action | Notes |
|---|---|---|
| `frontend/src/routes/VoiceMode.tsx` | NEW | Full-screen route |
| `frontend/src/hooks/useVoiceSession.ts` | NEW | Continuous duplex + state machine + data channel handlers |
| `frontend/src/components/voice/VoiceOrb.tsx` | NEW | Canvas-based audio-reactive orb |
| `frontend/src/components/voice/LiveTranscript.tsx` | NEW | Interim + final + reply rendering |
| `frontend/src/App.tsx` | MODIFY | Add `/voice` route |
| `frontend/src/components/SystemBar.tsx` | MODIFY | "Voice mode" button in top bar |
| `workers/voice_agent/worker.py` | MODIFY | Publish transcript + reply chunks on LiveKit data channel |
| `services/realtime_voice.py` | MODIFY | Expose interim transcripts via async generator (currently only yields finals) |

### UI polish (surgical — no global rewrite)

| File | Action | Notes |
|---|---|---|
| `frontend/src/index.css` | MODIFY | Tailwind v4 `@theme` with semantic tokens (surface, accent, muted) |
| `frontend/src/components/SystemBar.tsx` | MODIFY | Degraded reason as chip; spacing refinement |
| `frontend/src/tabs/ConversationTab.tsx` | MODIFY | Proper message bubbles + empty state illustration |
| `frontend/src/tabs/DashboardTab.tsx` | MODIFY | Skeleton shimmer on first paint |
| `frontend/src/tabs/EventsTab.tsx` | MODIFY | Empty state ("No events yet. CRUZ will log here when agents run.") |
| `frontend/src/tabs/ApprovalsTab.tsx` | MODIFY | Framer entrance on new approvals |
| `frontend/src/lib/keymap.ts` | NEW | Global hotkeys: `v` → voice mode, `1-4` → tab nav, `Esc` → exit voice |
| `frontend/src/components/Layout.tsx` | MODIFY | Register keymap; thin top border separator |

## Contracts

### LiveKit data channel payloads (worker → browser)

```ts
type CruzVoiceMsg =
  | { type: "stt_interim"; text: string }
  | { type: "stt_final"; text: string }
  | { type: "reply_chunk"; text: string; trace_id: string }
  | { type: "reply_done"; trace_id: string };
```

Published from worker with `reliable=True` for finals/done, `reliable=False` for interims (latency > correctness there).

### useVoiceSession return shape

```ts
{
  state: "idle" | "listening" | "thinking" | "speaking" | "error";
  error: string | null;
  interim: string;            // current partial user speech
  final: string[];             // locked-in user turns
  replies: Array<{ trace_id: string; text: string; streaming: boolean }>;
  enter(): Promise<void>;      // activate voice mode
  exit(): Promise<void>;       // deactivate, back to idle
}
```

## Failure modes + mitigations

| Failure | Mitigation |
|---|---|
| Mic permission denied | Catch `NotAllowedError`, show in-orb message with "Enable in browser settings" link |
| LiveKit token expires mid-session | Auto-refresh 30s before expiry; re-use same room name |
| Data channel messages arrive before audio track | State machine ignores data-channel for state; only uses `ActiveSpeakersChanged` |
| User spam-taps End | Idempotent `exit()`; guarded by `busy` flag |
| Agent audio buffer underrun (slow network) | LiveKit handles via adaptiveStream; nothing on our side |
| Double-publish races on mic track | Already solved in `useLiveKitRoom` via module-scoped singleton + serialize |
| Browser tab backgrounded | LiveKit auto-reduces bitrate; orb pauses canvas render via `document.visibilityState === "hidden"` |
| Worker crashes mid-turn | Watchdog in worker already exits after 90s audio idle; client sees disconnect → state = error |

## Cost impact

- **No new services.**
- **No new npm deps** (framer-motion and livekit-client already in package.json).
- **No backend cost change** — same Deepgram STT, same Claude, same Deepgram TTS.
- Data channel messages are free on LiveKit Cloud (same as audio).

## Execution order

1. Spec doc (this file) → commit
2. Worker: add data channel publishing → commit
3. Voice service: expose interim transcripts → commit (may be tiny/empty)
4. Frontend: voice mode route + hook + orb + transcript → single commit
5. Frontend: design tokens (CSS only) → commit
6. Frontend: polish surface (tabs, bars, empty states) → commit
7. Frontend: keymap + voice mode entry point → commit
8. Final smoke test via PM2 + browser → document results → commit

Each step stops and reports back if something breaks. No destructive changes without verification.

## What I will NOT do autonomously

- Install new packages
- Modify backend agent logic (anything in `agents/` except reads)
- Change persona layer
- Touch database migrations
- Publish to production infra
- Commit secrets or touch `.env`
- Force-push or rewrite git history
