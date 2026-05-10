# SP7 — Multi-modal Polish (Layer 6)

**Date:** 2026-05-10
**Status:** Draft for user review
**Sub-project of:** CRUZ v2 Program Charter (`docs/superpowers/specs/2026-04-20-v2-program-charter.md`)
**Inherits:** All charter Section 3 rules. Exit gate from charter Section 5.1 (SP7 row).
**Depends on:** SP1 (operational deployment), SP2 (knowledge base), SP3 (Mac controller), SP4 (browser automation), SP5 (event loop), SP6 (screen perception) — all merged on `main` per user confirmation 2026-05-10.
**Enables:** v2 code-completion. After SP7 merges, the remaining v2 work is operator-side burn-in and Firebase setup (tracked in `docs/superpowers/v2-burn-in-checklist.md`).

---

## 1. Goal and scope

**Goal.** Make the existing multi-modal infrastructure (voice daemon, voice worker, PWA shell) production-grade for 24/7 always-on operation across the user's four devices: Mac Mini (voice + dashboard), Nothing Phone 2 (PWA), iPad (PWA), ThinkPad (PWA + dashboard). Add device push notifications so any agent can reach the user wherever they are.

**One-line description.** Voice daemon hardening (echo cancellation + reconnect + memory watchdog + 24h burn-in) + custom "Hey CRUZ" wake word + PWA offline polish + FCM push to all registered devices.

### In scope

- **Voice daemon hardening** (`scripts/voice/livekit_client.py`, `workers/voice_agent/worker.py`):
  - Wake-word suppression during TTS playback (echo cancellation)
  - LiveKit reconnect-with-backoff (capped at 60s)
  - sounddevice mic-stream restart on PortAudioError
  - psutil RSS memory watchdog with Telegram warning at 80% of PM2 cap
  - Defensive Deepgram queue bounds (drop oldest interim if backlog > 1000)
  - 24-hour burn-in protocol with synthetic round-trip every 30 minutes
- **Custom wake word** (`scripts/wakeword/`):
  - openWakeWord training pipeline (Docker-wrapped, no Picovoice dependency)
  - Synthetic-sample training script + ROC table generation
  - Trained `hey_cruz.onnx` committed to repo (~250 KB)
  - `WakeWordDetector` ONNX-path branch in `services/voice.py`
  - Fallback on load failure: fail loud (no silent revert to `hey_jarvis`)
- **PWA offline polish** (`frontend/`):
  - Flip `vite.config.ts:VitePWA` `selfDestroying: true` → `false`
  - Workbox runtime caching: app shell (StaleWhileRevalidate), assets (CacheFirst), `GET /conversations*` (NetworkFirst with 3s timeout), `POST /command` (Background Sync queue)
  - IndexedDB conversation cache via `idb` — last 50 messages per conversation
  - Outbox UI component for queued offline commands
  - Generate missing PWA icons (`/icons/icon-192.png`, `/icons/icon-512.png`, `/icons/icon-512-maskable.png`)
- **FCM push notifications**:
  - New `device_tokens` table (Alembic migration)
  - `POST /devices/register` endpoint (JWT-authed)
  - `services/push.py` — `PushService.send_to_user(user_id, payload)` callable from any agent
  - Frontend `firebase-messaging-sw.js` SW handler at public root
  - `EnableNotifications` component for permission UI
  - Three immediate consumers wired: PULSE morning briefing, CATCH meeting summary, approval-gate prompts
  - Token cleanup on `UnregisteredError` / `InvalidArgumentError` / `SenderIdMismatchError`

### Out of scope (cuts taken from charter §6)

- **Cut #4 — React Native shell.** PWA-only ship. Phone install via "Add to Home Screen" on Android Chrome and iOS Safari (≥ 16.4).
- **Cut #5 — macOS menu bar app.** No menu bar status icon, no global keyboard shortcut. Ops visibility via `pm2 status`, `/agents/status`, and Telegram alerts.

### Out of scope (deferred — not part of any charter cut)

- Real-sample wake-word fine-tuning (post-burn-in polish, lives in `v2-burn-in-checklist.md`)
- iOS Safari PWA testing on a fresh-install device beyond the user's iPad
- Push notification preference UI (per-agent mute, quiet hours) — hard-coded defaults for v2
- Push notification history / inbox view in PWA
- Firebase Crashlytics for the PWA — observability adequate via Sentry already-wired
- React Native shell (cut #4 — defer to v2.1 if ever revisited)
- Menu bar app (cut #5 — defer indefinitely; not on v2.1 list)

### Charter overrides — none

This sub-spec adheres to all charter §3 rules without override. No new agents (Rule 1 N/A — only services), no new LLM-calling code paths (Rule 2 N/A — voice daemon hits existing `/command`), no destructive actions added beyond approval-gate-already-wired (Rule 4 unchanged), no new logging tables (Rule 5 — `device_tokens` is a domain table, push dispatches log to existing `agent_logs` via `services/push.py`).

---

## 2. Architecture

### 2.1 Process topology (unchanged from current state)

```
┌────────────────────── Mac Mini (PM2-managed) ──────────────────────┐
│                                                                    │
│   cruz-daemon  ──mic→ LiveKit room ←mic── cruz-voice-worker        │
│   (sp7: + AEC)                            (sp7: + watchdog)        │
│                                                                    │
│   cruz-api ──→ POST /devices/register ──→ device_tokens (sp7)      │
│            ←─ services/push.send_to_user ←─ any agent (sp7)        │
│                                                                    │
│   cruz-ui (Vite PWA) ──→ Workbox SW (sp7: enabled, with caching)   │
│                       ├→ firebase-messaging-sw.js (sp7: new)       │
│                       └→ IndexedDB conversation-cache (sp7: new)   │
│                                                                    │
│   cruz-worker (ARQ) — unchanged                                    │
└────────────────────────────────────────────────────────────────────┘
                                   │
                            FCM (Firebase Spark)
                                   │
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
          Nothing Phone 2     iPad (PWA)       ThinkPad (PWA)
            (PWA install)
```

### 2.2 Module-level changes

| File | Type | Change |
|---|---|---|
| `scripts/voice/livekit_client.py` | modify | AEC pause flag, reconnect loop, mic-stream restart, memory watchdog |
| `workers/voice_agent/worker.py` | modify | Bounded Deepgram queue, raise-on-disconnect, TTS speaking flag tightened |
| `services/voice.py` | modify | `WakeWordDetector` ONNX-path branch + fail-loud on load error |
| `scripts/wakeword/` | new | Training pipeline + Dockerfile + collect_real_samples.py + models/hey_cruz.onnx |
| `scripts/uptime/voice_burn_in.py` | new | 24h burn-in harness, synthetic round-trip every 30min |
| `backend/migrations/versions/0XX_device_tokens.py` | new | Alembic migration |
| `services/push.py` | new | PushService singleton with send_to_user fan-out |
| `backend/api/main.py` | modify | `POST /devices/register`, lifespan inits PushService |
| `frontend/vite.config.ts` | modify | Flip selfDestroying, configure workbox runtimeCaching |
| `frontend/public/firebase-messaging-sw.js` | new | FCM background handler |
| `frontend/public/icons/icon-{192,512,512-maskable}.png` | new | PWA install icons |
| `frontend/src/lib/conversation-cache.ts` | new | IndexedDB last-50-messages cache |
| `frontend/src/state/outbox.ts` | new | Zustand slice for offline-queued commands |
| `frontend/src/components/EnableNotifications.tsx` | new | Permission prompt + token registration |
| `agents/pulse/pulse_agent.py` | modify | Call push on briefing-ready |
| `agents/catch/catch_agent.py` | modify | Call push on summary-ready |
| `agents/cruz/cruz_agent.py` | modify | Call push when `requires_approval=True` returned |
| `docs/superpowers/v2-burn-in-checklist.md` | new | Aggregated post-merge operator items |

---

## 3. Voice daemon hardening

### 3.1 Echo cancellation (mic suppression during TTS)

**Problem.** The daemon publishes mic to a LiveKit room and plays the worker's TTS audio out of the local speakers. Without suppression, the mic re-captures the speaker output, causing wake-word false re-trigger and Deepgram pollution on the next turn.

**Fix.** A shared `threading.Event` flag in the daemon (`playback_active`). Two integration points:

1. **Set the flag** when the worker's audio track starts streaming. Clear it ~300ms after the stream ends (configurable via `TTS_TAIL_MS` env, default `300`). The tail covers BT/AirPods codec latency.
2. **In the mic callback** (`_audio_cb`):
   - If `playback_active` is set, skip wake-word detection entirely on this frame.
   - Capture an int16-zeros frame to LiveKit instead of real mic audio, so the voice-worker's Deepgram WS never receives the speaker echo.

**Belt-and-suspenders.** The voice-worker also tightens its existing `speaking["active"]` flag — within 200ms of TTS-frame publish, ignore Deepgram interim results. Protects against clock skew between daemon and worker processes.

### 3.2 LiveKit reconnect with backoff

Wrap `_join_and_run` in a backoff loop. Schedule: `[1, 2, 4, 8, 16, 30, 60, 60, 60]` seconds, capped at 60s. Reset attempt counter on clean disconnect (returned normally from `_run_session`). Emit a Telegram alert on attempt ≥ 3 — frequent reconnects indicate LiveKit-server-side or network issues worth surfacing.

Mirror in `cruz-voice-worker`: livekit-agents already restarts the entrypoint on exit. Change current "log and continue" on Deepgram WS disconnect to `raise` — let the harness rejoin cleanly. The livekit-agents harness catches the raised exception, logs it, and dispatches a fresh entrypoint job for the same room — no PM2 restart, no cascading crash.

### 3.3 Mic-stream restart on device-disconnect

`sounddevice.InputStream` raises `PortAudioError` on USB unplug/replug or BT disconnect. Currently this kills the daemon. Wrap the `with sd.InputStream(...)` block in its own try-loop using the same backoff schedule as 3.2. Telegram alert on every restart — frequent restarts are a hardware/driver smell.

### 3.4 Memory watchdog

Inside the daemon, a 60-second async loop logs `psutil.Process().memory_info().rss` to Loki. PM2 `max_memory_restart` is the hard ceiling (`512M` for daemon, `1G` for voice-worker). At 80% of cap, emit a Telegram warning so the operator sees the leak before PM2 force-restarts.

In the voice-worker, add `if stt._queue.qsize() > 1000: drop oldest interim`. Most likely leak vector — if `_process_turns` falls behind (long CRUZ turn under load), the Deepgram queue grows unbounded. The drop is safe because interim transcripts are superseded by their successor anyway.

### 3.5 24-hour burn-in protocol

`scripts/uptime/voice_burn_in.py` (new). Every 60 seconds asserts:
- `pm2 jlist | jq '.[] | select(.name=="cruz-daemon") | .pm2_env.status'` == `"online"`
- Same for `cruz-voice-worker`
- Restart count delta over the run ≤ 3 per process (allows transient hiccups but flags genuine instability)
- RSS for both processes < their PM2 cap
- `/health` reports `livekit: connected` and `deepgram: reachable`

Every 30 minutes a **synthetic round-trip**:
- Spawn a side daemon process with `SKIP_WAKE_WORD=1` so the mic stays unmuted
- Publish a known WAV utterance ("CRUZ status check") via the LiveKit data-channel injection path
- Assert the corresponding final transcript appears in `agent_logs` within 10s
- Tear down the side daemon

Burn-in writes JSONL to `docs/perf/sp7-voice-burn-in.jsonl` and emits a final summary block. Pass = 24h elapsed, all assertions green, ≤ 6 total PM2 restarts across both processes, ≥ 95% synthetic round-trip success rate.

---

## 4. Custom "Hey CRUZ" wake-word

### 4.1 Training pipeline

openWakeWord ships a Piper-TTS-based synthetic-sample generator + `synth_train.py` toolchain. Pipeline lives in `scripts/wakeword/`:

```
scripts/wakeword/
├── README.md                 # how to retrain locally
├── Dockerfile                # PyTorch + openWakeWord + Piper, isolated from venv
├── train_hey_cruz.sh         # one-command trainer
├── collect_real_samples.py   # records 30 utterances into samples/positive/
├── samples/                  # gitignored — your voice
│   ├── positive/             # 30 × ~1.5s "hey cruz" recordings
│   └── negative/             # 30 × ~3s ambient/conversation clips
└── models/
    └── hey_cruz.onnx         # COMMITTED — daemon loads this at boot
```

**Why commit the ONNX.** The trained model is ~250 KB and deterministic given a fixed seed. Mac Mini install becomes `git pull` instead of a 20-minute retrain. Source samples (your voice) stay gitignored for privacy — voice samples are biometric data.

**Why Docker-wrap.** PyTorch + CUDA-build wheels would pollute the Python venv. Mac Mini already runs Docker for Qdrant; reuse.

### 4.2 Threshold tuning

Training script also produces `docs/perf/sp7-wake-word-roc.md`:
- Score histogram on 100 held-out positive clips
- Score histogram on 1000 held-out negative clips (Common Voice random sentences)
- Recommended threshold = 95th percentile of negatives (target ~5% FP, < 1 false trigger / 24h ambient)

Default threshold becomes that recommendation. `WAKE_WORD_THRESHOLD` env var continues to override.

### 4.3 Daemon integration

`services/voice.py:WakeWordDetector._init_openwakeword` accepts `keyword` as either a pretrained name (existing) or a path-like string ending in `.onnx` (new). openWakeWord's `Model(wakeword_models=[…])` accepts both forms — the only change is a small validator + clear logging.

`livekit_client.py`:
```python
keyword = os.environ.get(
    "WAKE_WORD_MODEL_PATH",
    "scripts/wakeword/models/hey_cruz.onnx",
)
detector = WakeWordDetector(keyword=keyword, threshold=wake_threshold)
```

Operator can override for A/B testing or fall back to `hey_jarvis` by setting `WAKE_WORD_MODEL_PATH=hey_jarvis`.

### 4.4 Fail-loud on load error

If the ONNX model fails to load (corrupt, openWakeWord version mismatch), raise `RuntimeError` with a remediation message. **No silent fallback to `hey_jarvis`** — that would mask the problem and cause the user to assume their custom wake word is working when it's actually responding to "Hey Jarvis."

### 4.5 Real-sample collection during burn-in

The burn-in script's synthetic round-trip extends to also dump 5 seconds of pre-trigger audio when a real wake word fires. Clips are written to `scripts/wakeword/samples/positive/burnin-<timestamp>.wav`, which is gitignored (per §4.1 directory layout) — these are biometric data and must never be committed (R12). Over 24h this yields enough natural-condition positive clips for a follow-up retrain. Real-sample retraining is **post-burn-in polish**, not part of the SP7 exit gate. Listed in `v2-burn-in-checklist.md`.

---

## 5. PWA offline polish

### 5.1 Workbox configuration

`frontend/vite.config.ts` change (key fields only):

```typescript
VitePWA({
  registerType: "autoUpdate",
  selfDestroying: false,                  // was true
  workbox: {
    skipWaiting: true,
    clientsClaim: true,
    navigateFallback: "/index.html",      // SPA fallback for offline open
    runtimeCaching: [
      { /* shell: HTML/CSS/JS/font  → StaleWhileRevalidate */ },
      { /* assets: image           → CacheFirst, 50 entries, 30d */ },
      { /* GET /conversations*     → NetworkFirst, 3s timeout */ },
      { /* POST /command           → NetworkOnly + Background Sync */ },
    ],
  },
  manifest: { /* unchanged */ },
}),
```

Workbox's `backgroundSync` plugin auto-registers an IndexedDB-backed queue. Failed POSTs land in the queue and replay on `sync` event when the device reconnects. No custom code needed for the SW side.

### 5.2 IndexedDB conversation cache

`frontend/src/lib/conversation-cache.ts` (new). Uses the `idb` library (~3 KB). Object store keyed on `[conversation_id, id]`. API:

```typescript
rememberMessages(conversationId, messages: Message[]): Promise<void>  // keeps last 50
recallMessages(conversationId): Promise<Message[]>
```

The conversation-view component calls `rememberMessages` on every successful TanStack Query `onSuccess`. On mount, `useQuery` falls through to `recallMessages` as `placeholderData` so the cached transcript shows instantly even when offline.

Storage cap: 50 messages × ~2 KB × 100 conversations ≈ 10 MB, well under iOS Safari's ~50 MB IndexedDB cap.

### 5.3 Outbox UI

When `POST /command` fails offline, Workbox queues silently. UX needs visible state.

`frontend/src/state/outbox.ts` (Zustand slice):
- `addPending(localId, message)` — optimistically renders user message with "queued (offline)" pill
- Listens for `navigator.onLine` events and SW message channel for replay confirmation
- On replay success: swap pill for assistant reply and remove from outbox

If the queue still has items 60 seconds after `online` event fires, surface a "tap to retry" button. Mitigates iOS Safari's ~30s Background Sync window.

### 5.4 PWA icons

Generate three icons via `pwa-asset-generator` from a 1024×1024 source:
- `/icons/icon-192.png` (192×192)
- `/icons/icon-512.png` (512×512)
- `/icons/icon-512-maskable.png` (512×512, maskable purpose)

If no source logo exists, create a simple "C" wordmark white-on-`#0a0a0a` (matching the manifest `theme_color`). One-shot Figma export or a single AI-art generation.

### 5.5 Service-worker update strategy

`registerType: "autoUpdate"` + `skipWaiting: true` + `clientsClaim: true` means new SW versions take over immediately on next page load. Trade-off: faster shipping vs. risk of pushing a buggy SW to all clients instantly.

Mitigation: every PR that touches frontend bumps a `SW_VERSION` constant in `frontend/src/sw-version.ts` (imported by `main.tsx` registration code, logged on `activate`). PR description includes a manual phone-side QA check (install, swipe-refresh, confirm version logged).

### 5.6 Migration from current self-destroying SW

The existing `selfDestroying: true` SW unregisters itself on install. The new SW with `autoUpdate` will replace it cleanly within one page-load cycle on installed PWAs. No user action needed.

### 5.7 Charter gate verification (manual procedure)

1. Phone: open `https://cruz.simpleinc.cloud` → "Add to Home Screen"
2. Open the installed PWA → home view loads
3. Toggle airplane mode ON → close PWA → reopen → home view still loads, last conversation visible
4. Type a command while offline → "queued (offline)" pill appears
5. Toggle airplane mode OFF → wait <10s → command replays, response streams in
6. Repeat steps 1–5 on iPad and ThinkPad
7. Screenshots into `docs/perf/sp7-exit-gate.md`

---

## 6. FCM push notifications

### 6.1 Firebase project setup (operator-side, one-time)

Tracked in `v2-burn-in-checklist.md`:
1. Create Firebase project `cruz-personal` (Spark / free plan)
2. Enable Cloud Messaging API
3. Generate service-account JSON → save to `~/.config/cruz/fcm-sa.json` on Mac Mini, mode `0600`
4. Project Settings → Cloud Messaging → "Web Push certificates" → generate VAPID key pair
5. New env vars in `.env`:
   ```
   FCM_SA_PATH=/Users/darshan/.config/cruz/fcm-sa.json
   FCM_VAPID_PUBLIC_KEY=B...
   FCM_PROJECT_ID=cruz-personal
   VITE_FCM_VAPID_PUBLIC_KEY=...           # Vite-prefix for frontend
   ```
6. Backup the service-account JSON as a Bitwarden secure-note attachment.

Free-plan limits: unlimited messages, 6000 concurrent connections — never going to hit it.

### 6.2 Schema

```sql
CREATE TABLE device_tokens (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fcm_token     TEXT NOT NULL UNIQUE,
    device_label  VARCHAR(50),                 -- 'phone', 'ipad', 'thinkpad', 'mac-mini'
    user_agent    TEXT,
    last_seen_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_device_tokens_user ON device_tokens(user_id);
```

`UNIQUE(fcm_token)` enables idempotent upsert: `INSERT ... ON CONFLICT (fcm_token) DO UPDATE SET last_seen_at = NOW()`.

### 6.3 Backend — registration endpoint

`POST /devices/register` (auth: existing JWT). Body: `{fcm_token, device_label, user_agent}`. Returns `{registered: true, device_id}`. Upserts on conflict.

### 6.4 Backend — `services/push.py`

Singleton service, ~100 LOC. Public API:

```python
@dataclass
class PushPayload:
    title: str
    body: str
    url: str | None = None
    trace_id: str | None = None

@dataclass
class SendResult:
    token: str
    ok: bool
    msg_id: str | None = None
    reason: str | None = None

class PushService:
    def __init__(self, sa_path: str, project_id: str): ...

    async def send_to_user(
        self, user_id: int, payload: PushPayload,
    ) -> list[SendResult]:
        """Fan out to all of user's registered devices.
        Auto-prunes UNREGISTERED / Invalid / SenderIdMismatch tokens.
        Logs the dispatch to agent_logs."""
```

Implementation detail: `firebase-admin` is sync. Wrap `messaging.send` calls in `asyncio.to_thread`. With 3 devices × ~5ms overhead each = 15ms total — well under the 5s exit gate.

### 6.5 Backend — DI and lifespan

`get_push_service()` is a singleton like `get_db_service()`. Initialised in `lifespan()`:
- Read `FCM_SA_PATH`. If unset → `PushService` is `None`, log a warning, dispatchers no-op gracefully (degraded mode).
- If set but unreadable → `RuntimeError`, fail-fast at startup. Don't degrade silently — operator should know.

### 6.6 Backend — wired consumers (SP7 scope)

Three immediate callers:

| Caller | Trigger | Title | Body |
|---|---|---|---|
| `agents/pulse/pulse_agent.py` | 6 AM cron, briefing complete | "Morning briefing ready" | "{N} items + {M} client alerts" |
| `agents/catch/catch_agent.py` | Post-transcription complete | "{Meeting title} captured" | "{N} action items extracted" |
| `agents/cruz/cruz_agent.py` | `AgentOutput.requires_approval=True` | "{Agent} needs approval" | `approval_prompt` (truncated 100 chars) |

Three follow-ups documented but not wired in SP7:
- SENTINEL post-review notification
- TITAN deploy/rollback notification
- `services/alerts.py` adds `push` as a sink alongside Telegram

### 6.7 Frontend — service worker

`frontend/public/firebase-messaging-sw.js` (must live at the public root — FCM requirement). Loads `firebase-app-compat` + `firebase-messaging-compat` from gstatic CDN. Handles `onBackgroundMessage` (showNotification) and `notificationclick` (open the URL from `payload.data.url`).

Workbox SW (Vite-PWA-generated) and `firebase-messaging-sw.js` are **separate** service workers. Both register at `/` scope and coexist — Workbox handles `fetch`/cache, Firebase handles `push` and `notificationclick`. Per FCM convention, the Firebase SW owns push-event handling; the Workbox SW does not register for push. Click handling lives in `firebase-messaging-sw.js` (see §6.7 snippet). This pattern is documented in vite-plugin-pwa.

### 6.8 Frontend — permission UI

`frontend/src/components/EnableNotifications.tsx` (new). Renders only if:
- `Notification.permission === "default"` (never asked)
- AND user hasn't dismissed (LocalStorage flag)

Subtle banner in chat header: "Get notified when CRUZ has news for you. [Enable]". On click:
1. `Notification.requestPermission()`
2. On granted: `getToken({vapidKey: import.meta.env.VITE_FCM_VAPID_PUBLIC_KEY})`
3. `POST /devices/register` with token + device label

If denied: show one-line "Notifications off — enable in browser settings" footnote. Never re-prompt.

### 6.9 Token cleanup

Three Firebase error types prune tokens on dispatch:
- `UnregisteredError` (uninstalled / cleared site data)
- `InvalidArgumentError` (token never valid)
- `SenderIdMismatchError` (token from different Firebase project)

Anything else (network, 5xx) keeps the token, retries on next dispatch. Background cleanup not needed — dead tokens prune themselves on first failed send. If a device never receives another push, its dead token sits inertly in the table; on next page-load the live device re-upserts.

### 6.10 Charter gate verification (manual procedure)

1. Phone PWA: tap "Enable notifications" → grant → verify `device_tokens` row in Postgres
2. iPad PWA: same → second row
3. ThinkPad PWA: same → third row
4. From Mac Mini terminal: `python -c "..."` invoking `send_to_user(user_id=1, payload=...)`
5. Stopwatch: notification appears on **all three** devices within 5 seconds
6. Tap notification on phone → PWA opens to specified URL
7. Screenshots into `docs/perf/sp7-exit-gate.md`

---

## 7. Testing strategy (TDD per superpowers)

### 7.1 Unit tests (mocked) — same day as code

| Module | Coverage | Test count |
|---|---|---|
| `services/push.py` | success, UnregisteredError → delete, InvalidArgumentError → delete, network exception keeps, fan-out across N tokens, partial failure mid-fanout, **degraded-mode no-op when PushService is None (FCM_SA_PATH unset)** | ~13 |
| `services/voice.py:WakeWordDetector` (ONNX path) | path string detection, fail-loud on load error | ~3 |
| `frontend/src/lib/conversation-cache.ts` | rememberMessages keeps last 50, recall by id, eviction (Vitest + fake-indexeddb) | ~6 |
| `frontend/src/state/outbox.ts` | optimistic add, replay confirmation, retry button | ~5 |
| `POST /devices/register` | auth required, upsert-on-conflict, validation | ~6 |
| Daemon AEC pause flag | toggles suppress wake detection, tail timing | ~4 |
| Daemon reconnect loop | backoff schedule, attempt counter resets on clean disconnect | ~3 |
| Daemon mic-stream restart | PortAudioError triggers restart, alert fires | ~2 |
| Daemon memory watchdog | warning at 80%, log structure | ~2 |
| Voice-worker queue bound | drop oldest interim at >1000 | ~1 |
| `agents/pulse|catch|cruz` push integration | calls send_to_user with right payload | ~3 |
| Alembic migration shape | column types, index, FK | 1 |

Total ~48 unit tests added.

### 7.2 Integration tests (opt-in)

- `tests/integration/test_voice_burn_in_smoke.py` — 60-second mini burn-in. Skipped unless `VOICE_BURN_IN=1`.
- `tests/integration/test_fcm_dispatch.py` — real Firebase Admin against test project. Skipped unless `FCM_TEST_SA_PATH` set.

### 7.3 E2E (manual exit gate)

- 24-hour burn-in (§3.5)
- PWA install + offline on phone, iPad, ThinkPad (§5.7)
- 3-device push delivery within 5s (§6.10)

Walked manually with screenshots into `docs/perf/sp7-exit-gate.md`. Not automated — these are inherently device-physical tests.

### 7.4 Wake-word quality

Training script produces `docs/perf/sp7-wake-word-roc.md` with score histograms. Daemon hardening tests cover the *integration* (loads ONNX, threshold lookup) — not the model quality itself. Quality measured by the ROC table.

---

## 8. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | LiveKit reconnect storm under flaky network | Medium | Daemon hammers Cloud — ban risk | Backoff capped at 60s; alert on attempt ≥ 3 |
| R2 | AEC tail too short → wake-word false re-trigger | Medium | User annoyance, possible loop | `TTS_TAIL_MS` tunable (default 300ms), tuning procedure documented |
| R3 | Synthetic-only "hey cruz" model has high FN rate | Medium | "Had to say it twice" UX | Real-sample retrain post-burn-in; threshold tunable |
| R4 | iOS Safari Background Sync 30s window misses replays | Medium | Queued offline command silently drops | Outbox UI shows "tap to retry" after 60s |
| R5 | Workbox `skipWaiting` deploys buggy SW instantly | Low | All clients get broken UI | `SW_VERSION` bump + manual phone QA per release |
| R6 | Firebase service-account JSON leaks via git | Low | Push key compromise — rotatable | `.gitignore` includes `*-sa.json`; pre-commit hook scans for it |
| R7 | 24h burn-in catches a leak — no fix window | Medium | SP7 misses charter gate | K2 fix-window applies (≤25% = +3 days); else shelve voice daemon to v2.1, ship PWA + FCM only |
| R8 | Memory RSS growth slow but trending under cap | Low | Burn-in passes, prod fails later | Loki dashboard shows trend; revisit post-ship |
| R9 | Three devices register the same FCM token | Low | Push fires once instead of three times | UNIQUE upsert acceptable; rare collision |
| R10 | Firebase rate-limit during burn-in synthetic round-trips | Very low | Test flake | 48 calls / 24h — well under any free-plan limit |
| R11 | iOS PWA storage eviction after 7 days inactivity | Low | First-open shows empty cache | Acceptable; refills from network; documented |
| R12 | Privacy of voice samples committed accidentally | Low | Biometric leak | `samples/` in `.gitignore`; pre-commit scan |

**R7 is the watch-item.** If 24h burn-in fails, charter K2 rule applies: fix-window ≤ 25% of original estimate (1–2 weeks → 3 days max). Past that, voice daemon ships as v2.1; PWA + FCM still ship as SP7 and v2 is "code-complete" minus voice always-on.

---

## 9. Sequencing — Approach 2 (risk-front-loaded, parallel during burn-in)

```
Day 1   AM:  branch claude/<random>-sp7 from main
             Alembic migration 0XX_device_tokens
             services/push.py with mocked tests (TDD)
             POST /devices/register endpoint + tests
        PM:  daemon hardening: AEC pause flag + tests
             daemon reconnect loop + tests
             daemon memory watchdog + tests

Day 2   AM:  daemon mic-stream restart + tests
             scripts/uptime/voice_burn_in.py
             smoke-run burn-in for 30 min (catch obvious bugs)
        PM:  fix anything smoke caught
             KICK OFF 24H BURN-IN at ~16:00 IST
             (concludes ~16:00 Day 3)

Day 3   AM:  PWA: flip selfDestroying, runtime caching, IndexedDB cache
             outbox UI + tests
             generate icons
        PM:  Firebase project setup (operator side, ~1h)
             firebase-messaging-sw.js
             EnableNotifications component + tests
             VAPID env wiring
             16:00: burn-in result review

Day 4   AM:  wake-word retrain pipeline
             scripts/wakeword/* + Dockerfile
             synthetic train run (~20 min)
             commit hey_cruz.onnx + ROC table
        PM:  daemon swap to hey_cruz.onnx
             1-hour mini burn-in to verify FP/FN rate
             fix threshold if needed

Day 5   AM:  Manual exit-gate walkthrough (PWA install + offline + push)
             Screenshots → docs/perf/sp7-exit-gate.md
        PM:  PR open, review loop, merge
             Append SP7 sign-off block to PROGRESS.md
             Write docs/superpowers/v2-burn-in-checklist.md
```

5-day plan with 24h of "free" calendar absorbed into the burn-in. Within charter's 1–2 week budget. K2 trips at 7.5 days; ~2.5 days of slack.

---

## 10. Charter exit gate (verbatim from §5.1)

| Gate | Criterion | How verified |
|---|---|---|
| 1 | Wake-word + voice daemon operates 24 hours continuously | `docs/perf/sp7-voice-burn-in.jsonl` summary block; ≤ 6 PM2 restarts; RSS bounded; ≥ 95% synthetic round-trip success |
| 2 | PWA installed on phone with offline support confirmed | Manual procedure §5.7, screenshots in `docs/perf/sp7-exit-gate.md` |
| 3 | FCM push delivers to all registered devices within 5 seconds | Manual procedure §6.10, stopwatch + screenshots in `docs/perf/sp7-exit-gate.md` |

A single failed gate triggers a bounded fix window (≤ 25% of 1–2 weeks → +3 days). If the fix window closes still failing, K2 fires and the failing piece shelves to v2.1.

---

## 11. Cut-triggers (charter §6 ownership)

| Charter row | Trigger condition for SP7 | Status |
|---|---|---|
| #4 React Native shell | "SP7 start" — pre-committed by user 2026-05-10 | **TAKEN** |
| #5 Menu bar app | "SP7 mid-build" — pre-committed by user 2026-05-10 | **TAKEN** |
| (none lower) | n/a — all other rows touch earlier sub-projects |

Pre-committing both cuts at start saves ~5 days vs. taking them mid-build.

---

## 12. Hand-off

After SP7 merges:

1. Append SP7 sign-off block to `PROGRESS.md` (template-mirrored from SP1/SP2/SP3/SP4 blocks).
2. Author `docs/superpowers/v2-burn-in-checklist.md` aggregating:
   - Open SP1/SP2 operator items from `docs/superpowers/DEFERRED.md`
   - Firebase project + service-account setup
   - Wake-word real-sample retraining (post-burn-in polish)
   - LiveKit Cloud usage monitoring
   - iOS Safari fresh-device PWA test
3. v2 is "code-complete." v2 is "operational" only after the burn-in checklist clears. Charter §5.3 ("pause means operationally") aligns: v1 keeps running throughout.

---

## Appendix A — Decisions locked during brainstorming (2026-05-10)

| # | Decision | Alternatives considered | Chosen |
|---|---|---|---|
| 1 | React Native vs PWA-only | Both / PWA-only | PWA-only (charter cut #4) |
| 2 | Menu bar app vs keyboard shortcut vs neither | Menu bar / shortcut / neither | Neither (charter cut #5) |
| 3 | LiveKit hosting | Cloud / self-hosted / pending | Already running (Cloud or Mac Mini Docker) |
| 4 | FCM token storage | New table / users.preferences JSONB | New `device_tokens` table |
| 5 | Wake-word phrase | hey_jarvis / Picovoice .ppn / openWakeWord retrain | openWakeWord retrain to "hey cruz" |
| 6 | Echo cancellation | Pause wake-word during TTS / software AEC | Pause (simpler) |
| 7 | Sequencing | Sequential / parallel-during-burn-in / 3-track sub-agent | Approach 2 (parallel during burn-in) |

## Appendix B — Known v1/v2 reality to inherit

- LiveKit voice daemon (`scripts/voice/livekit_client.py`) and voice-worker (`workers/voice_agent/worker.py`) are already live, PM2-managed, on `main`. SP7 hardens them; doesn't replace them.
- `services/voice.py:WakeWordDetector` already supports both openWakeWord and Picovoice backends. SP7 only extends the openWakeWord path.
- `frontend/vite.config.ts` already has `vite-plugin-pwa` configured but in `selfDestroying: true` mode. SP7 flips it.
- `services/alerts.py` (Telegram + Sentry) already exists and is wired into CRUZ + TITAN + ARQ. SP7 reuses it for daemon alerts.
- Persona layer (`agents/cruz/persona/`) wraps CRUZ responses server-side. SP7 voice daemon does NOT bypass it — daemon is just an audio I/O wrapper around `POST /command`.
- All charter §3 rules are already wired into existing agents. SP7 adds no new agent and overrides no rule.
