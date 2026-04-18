# CRUZ Command Center Web UI — Design Spec

**Date:** 2026-04-18
**Author:** Darshan (brainstormed with CRUZ)
**Status:** Approved by user (brainstorm 2026-04-18, user went AFK authorizing autonomous completion)
**Supersedes:** No prior UI spec.
**Related:** [voice-pipeline-v2 spec](2026-04-15-voice-pipeline-v2.md), [voice Phase 1 plan](../plans/2026-04-15-voice-pipeline-phase1.md)

---

## 1. Problem

Running CRUZ today requires 3 terminals on the Mac Mini (API, LiveKit worker, daemon). There is no visual surface — no waveform, no transcript, no agent activity, no system health at a glance. Phone and iPad cannot use CRUZ at all; all the brain is there but no way to reach it without SSH-ing in.

## 2. Goal

Ship a single responsive web app at `http://localhost:5173` (dev) / `https://cruz.simpleinc.cloud` (prod via Cloudflare tunnel) that:

1. Replaces Terminal 3 with a visual **command center** on Mac — orb animation, live transcript, agent rail, system health, pending approvals.
2. Works on Nothing Phone 2 and iPad Safari as a PWA — PTT voice + core panels — without a separate codebase.
3. **Keeps the existing daemon alive** as the headless wake-word service on Mac. The web UI is a visual peer in the same LiveKit room, not a replacement for the audio pipeline.

## 3. Non-goals (v1)

- Native iOS / Android apps
- Electron / Tauri wrapping
- Always-listening wake word in the browser tab
- Voice-only approval flows (those ship in voice-pipeline Phase 2 via FCM)
- User authentication with multi-tenant (single user: `darshan`; auth is Phase 2)
- **Mobile approval gate UX** — Phase 1 phone shows a "check Mac to approve" message. Real approval UX on phone requires FCM, deferred to voice-pipeline Phase 2.
- AgentsTab, MemoryTab, TasksTab — deferred to Phase 2 to keep bundle small and scope realistic for one sprint.

## 4. Architecture

```
                ┌─────────────────────────────────────────────────┐
                │  Mac Mini M4                                    │
                │                                                 │
                │  ┌──────────────┐  ┌──────────────────────┐   │
                │  │ backend/api  │  │ workers/voice_agent  │   │
                │  │ FastAPI 3000 │  │ LiveKit agent worker │   │
                │  └──────────────┘  └──────────────────────┘   │
                │       ▲                    ▲                   │
                │       │                    │                   │
                │  ┌──────────────┐          │                   │
                │  │ Mac daemon   │──────────┘                   │
                │  │ wake-word +  │    (LiveKit room)            │
                │  │ mic/speaker  │                              │
                │  └──────────────┘                              │
                └───────────┼─────────────────────────────────────┘
                            │ LiveKit room (same as daemon)
                            │ HTTP to backend/api:3000
                            │ SSE from /events
                            ▼
              ┌──────────────────────────────────┐
              │   Web UI (Vite, PWA)             │  ← NEW
              │                                  │
              │   Mac Chrome    iPad Safari      │
              │   Phone Chrome  (PWA-installed)  │
              └──────────────────────────────────┘
```

**Key properties:**

- The web UI is a **third participant** in the LiveKit room (after daemon + agent worker). It subscribes to the agent's audio track to play CRUZ's voice back to the browser; it can publish its own mic track for in-browser PTT.
- Wake word remains the daemon's job on Mac. On phone/iPad there is no daemon; the PTT button in the UI unmutes/publishes mic.
- The UI reads everything else over HTTP + SSE from `backend/api`. It does not re-implement any backend logic.

## 5. Tech Stack

Per CLAUDE.md's declared stack plus voice-specific additions:

- **Framework:** Vite 6 + React 18 + TypeScript 5
- **Styling:** Tailwind CSS 4 + shadcn/ui + `lucide-react` icons
- **State:** Zustand (tiny; LiveKit state managed by `@livekit/components-react` hooks)
- **Routing:** React Router 6 (for tab deeplinking; URL = source of truth)
- **Data fetching:** TanStack Query 5 for polled endpoints (`/agents/status`, `/tasks`, etc.) + native `EventSource` for `/events` SSE
- **LiveKit:** `@livekit/components-react` + `livekit-client` (cherry-pick waveform visualizer + track subscription helper from LiveKit Playground as reference, write our own)
- **PWA:** `vite-plugin-pwa` for installable + offline-shell
- **Testing:** Vitest + @testing-library/react + Playwright for one e2e smoke
- **Linting:** ESLint + Prettier + TS strict mode

**Deliberately rejecting:** Next.js (CLAUDE.md says Vite), Electron/Tauri (web-only per §3), MUI (we chose shadcn).

## 6. File structure

```
frontend/                              # NEW top-level dir
├── index.html
├── package.json
├── vite.config.ts                     # PWA, proxy /api → :3000, /voice/* → :3000
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.js
├── .eslintrc.cjs
├── public/
│   ├── icons/                         # PWA icons (CRUZ orb, 192/512/maskable)
│   └── manifest.webmanifest           # generated by vite-plugin-pwa
├── src/
│   ├── main.tsx                       # React root + Router
│   ├── App.tsx                        # top-level layout: SystemBar + Layout + Rails
│   ├── index.css                      # Tailwind directives + CSS vars
│   ├── env.d.ts
│   │
│   ├── lib/
│   │   ├── api.ts                     # HTTP client (baseURL, JSON helpers)
│   │   ├── sse.ts                     # typed EventSource wrapper
│   │   ├── livekit.ts                 # token fetch + Room wiring helpers
│   │   └── breakpoints.ts             # `useDevice()` hook: 'phone'|'tablet'|'desktop'
│   │
│   ├── state/
│   │   ├── conversationStore.ts       # Zustand: current transcript, messages
│   │   ├── voiceStore.ts              # Zustand: orb state (idle|listening|speaking)
│   │   └── systemStore.ts             # Zustand: health, agent statuses
│   │
│   ├── components/
│   │   ├── ui/                        # shadcn generated components (button, tabs, card, etc.)
│   │   ├── Layout.tsx                 # grid template: top bar, left rail, center, right rail
│   │   ├── SystemBar.tsx              # top bar: status, time, device list
│   │   ├── AgentRail.tsx              # left rail: 12 agents with live status dots
│   │   ├── PendingRail.tsx            # right rail: approvals + scheduled tasks
│   │   ├── Orb.tsx                    # animated orb (listening / speaking / idle / barge-in)
│   │   ├── Waveform.tsx               # audio track visualizer
│   │   └── PTTButton.tsx              # push-to-talk button (mobile + desktop)
│   │
│   ├── tabs/
│   │   ├── ConversationTab.tsx        # transcript + manual text input
│   │   ├── DashboardTab.tsx           # widget grid: Today, Metrics, Health, Upcoming
│   │   ├── EventsTab.tsx              # live timestamped event stream
│   │   ├── AgentsTab.tsx              # per-agent detail + recent calls
│   │   ├── ApprovalsTab.tsx           # pending approval gates
│   │   ├── MemoryTab.tsx              # semantic memory search
│   │   └── TasksTab.tsx               # ARQ queue + Plane mirror
│   │
│   └── __tests__/                     # component + hook tests
│
└── README.md                          # how to run dev + build
```

**Why this structure:** Each file has one responsibility. Tabs are lazy-loaded so phone bundle stays small. State is split by domain so re-renders stay scoped.

### Changes outside `frontend/`

- **`backend/api/main.py`** — add **three new endpoints** (detailed in §8):
  - `GET /events` — SSE stream of agent_logs rows (read from DB + listen on Redis pubsub)
  - `GET /dashboard` — aggregated one-call payload for the Dashboard tab
  - `GET /approvals` — list pending `approval_requests` rows
- **`ecosystem.config.js`** — add a `cruz-ui` process that runs `npm run preview` on port 5173 (prod); dev is just `npm run dev`.

## 7. Design decisions (locked in brainstorm)

| Decision | Choice | Why |
|---|---|---|
| Layout | Orb center + left agent rail + right pending rail + top system bar | Most "FRIDAY"; chosen in option C from layout screen |
| Center zone | Tabs (one panel at a time, full-width) | Chosen option B from center-zone-combo screen; avoids cramming on any device |
| Tab set | 7 planned. Phase 1 ships 4: Conversation (default), Dashboard, Events, Approvals. Phase 2: Agents, Memory, Tasks (scope cut per spec-review feedback on bundle size + timeline) | User picked all 7 in brainstorm; Phase 1 cut is pragmatic, all 7 in Phase 2 |
| Phone view | Voice-only minimal: orb + transcript + PTT + FCM for approvals | Phone is glance-and-talk; tabs would be overkill on 6" |
| iPad view | Side rail with 5 tabs: Conversation, Dashboard, Events, Agents, Approvals | iPad is a work surface; Memory + Tasks deferred to Mac |
| Mac view | Full: top bar + left agent rail + right pending rail + 7 tabs | Desk use, 24" monitor, maximum info density |
| Visual theme | Modern ShadCN: `zinc-900` base, single green accent (`green-500`), SF Pro / system-ui | Clean, timeless, no fatigue; user rejected JARVIS cyan + FRIDAY amber |
| Tech stack | Fresh Vite + React + shadcn (no fork); cherry-pick 2-3 components from LiveKit Playground as reference | Matches CLAUDE.md; forking Next.js Playground adds tech debt |
| Wake word location | Stays in Mac daemon (headless background service) | Browser can't do always-on listening; daemon already works |
| Web app role | Visual peer in the same LiveKit room — subscribes to agent audio, publishes mic on PTT | Zero new audio plumbing; reuse Phase 1 voice infra |
| Routing | Tab = URL segment (`/tab/conversation`, `/tab/events/:traceId`) | Deep-linkable; shareable; browser back button works |

## 8. Backend API changes

### 8.1 `GET /events` — SSE stream

Live feed of every `agent_logs` row as it's inserted. Used by `EventsTab`.

Events emitted (server → client):

```
event: replay
data: [{"id":1234, ...}, {"id":1235, ...}, ...]    // up to last 50, newest-last, on initial connect

event: log
data: {"id":1236, "trace_id":"...", "agent":"qt", "action":"test", "status":"success",
       "duration_ms":3214, "tokens_used":0, "created_at":"2026-04-18T18:47:06Z"}

event: sync
data: {"last_id": 1235}    // after replay flushes, signals client is caught up

event: ping
data: {"t": 1776518147}      // every 25s to keep connection alive
```

**Reconnect**: client sends `?last_id=1235` query — server emits only logs newer than that, then `event: sync`.

**Implementation** — Redis pub/sub channel `cruz:agent_logs`:
1. **Modify `agents/base_agent.py::BaseAgent.log()`** — after the DB insert succeeds, publish the same row (as JSON) to Redis channel `cruz:agent_logs`. Non-fatal on publish failure (just log a warning). This is an invasive change to a widely-used method; must land in the same PR as the `/events` endpoint.
2. **`GET /events`** endpoint creates a FastAPI `StreamingResponse` that:
   - Reads `last_id` from query (default: fetch last 50 from DB)
   - Emits `event: replay` with those logs
   - Subscribes to `cruz:agent_logs` channel via `redis.asyncio`
   - Yields each message as `event: log`, emits `event: ping` every 25s
   - Closes cleanly on client disconnect
3. Verify `FastAPI.StreamingResponse` + `redis.asyncio.pubsub` compose without blocking the event loop — this repo already uses `StreamingResponse` for `/command` SSE at `backend/api/main.py` lines 373–420, so the pattern is known-good.

### 8.2 `GET /dashboard` — aggregated Dashboard payload

One call, short TTL cache (5s). Returns everything the Dashboard tab needs:

```json
{
  "today": {
    "calendar_events": [],      // populated when GCal integration lands
    "unread_emails": 0,         // populated when Gmail read lands
    "open_prs": 2,              // from GitHub webhook + cache
    "deploys_today": 1
  },
  "metrics": {
    "turns_today": 42,
    "tokens_today": 58342,
    "estimated_cost_usd": 0.73,
    "estimated_time_saved_hours": 4.2
  },
  "system_health": {
    "deepgram": "healthy",
    "livekit": "healthy",
    "postgres": "healthy",
    "redis": "healthy",
    "qdrant": "degraded",      // mirrors /health output
    "ollama": "healthy",
    "claude_api": "healthy"
  },
  "upcoming": [
    {"agent": "pulse", "scheduled_at": "2026-04-19T06:00:00Z", "label": "Morning brief"},
    {"agent": "raw", "scheduled_at": "2026-04-19T03:00:00Z", "label": "Research update"}
  ]
}
```

### 8.3 `GET /approvals` and `POST /approvals/:id/{approve|deny}`

Used by `ApprovalsTab` and the Pending rail.

```
GET /approvals?state=pending&limit=25
→ [{ id, trace_id, agent, action, payload, requested_at, expires_at }, ...]

POST /approvals/:id/approve
POST /approvals/:id/deny
→ 200 { state: "approved"|"denied" }
→ writes approval_requests.state + responded_at
→ publishes Redis `cruz:approval:<id>` so the waiting tool-call unblocks
```

### 8.4 Reused existing endpoints (no changes)

- `GET /health` — system health for SystemBar + DashboardTab
- `GET /agents/status` — agent rail live state (already exists in `main.py`)
- `POST /command` + SSE — fallback when LiveKit is unavailable
- `POST /voice/token` — LiveKit JWT minting (already exists)
- `GET /conversations/:id/messages` — transcript history on load
- `GET /logs/:trace_id` — drill-in from EventsTab
- `GET /tasks` — (available, deferred to Phase 2 TasksTab)

## 9. Voice flow in the web app

### 9.1 Mac (wake word still via daemon)

**Prerequisite:** the Mac daemon (`scripts/voice/livekit_client.py`) must be running. Today it's started manually. **Phase 1 adds a `cruz-daemon` process to `ecosystem.config.js`** so PM2 keeps it alive alongside `cruz-api` and `cruz-worker`.

1. Daemon hears "Hey Jarvis" → unmutes mic → streams to worker via LiveKit room.
2. Web UI is already in the same room (joined on page load). It subscribes to the daemon's audio track and displays a waveform when the user is talking.
3. Worker transcribes → runs CRUZ → streams sentences back. UI receives the agent audio track.

**Audio policy (simplified per spec review):**
- The **daemon owns audio output** on Mac (it's the always-on service with the speakers).
- The web UI is **visual only** on Mac — subscribes to the agent's audio track for waveform visualization but does not play it through browser speakers. A "Mute daemon" toggle in Settings lets power users flip the policy if they work headless.
- This eliminates any double-audio race. Phone/iPad don't have a daemon, so the web UI plays audio directly.

### 9.2 Phone / iPad (PTT)

1. User taps/holds the PTT button → browser `getUserMedia()` → LiveKit publishes the mic track.
2. Worker transcribes and replies; UI plays reply audio through browser speakers.
3. Release PTT → mic track stops publishing → Deepgram WS on worker closes for this device.

### 9.3 State-machine (Zustand `voiceStore`)

```ts
type VoiceState =
  | 'idle'           // nothing happening
  | 'listening'      // user mic active (via daemon wake or PTT)
  | 'thinking'       // transcript final, Sonnet running, no audio yet
  | 'speaking'       // agent audio streaming
  | 'interrupted';   // user spoke over agent; tts cancelled, tool still running
```

Orb colour / animation maps to state:
- `idle`: slow breath, low opacity
- `listening`: pulsing ring, green
- `thinking`: spinner dots inside orb
- `speaking`: bigger ring, gentle bounce synced to audio
- `interrupted`: brief amber flash, then back to `listening`

State is driven by events from the LiveKit room (track mute/unmute events) and from the SSE `/events` stream (tool_start / tool_finish / done).

## 10. Error handling and fallbacks

| Failure | UI behavior |
|---|---|
| LiveKit room join fails | Show toast "Voice unavailable — using HTTP mode". Fallback to `POST /command` with stream=true SSE; orb pulses but no audio IO |
| Daemon is offline | Mac UI: status bar shows "Daemon offline — PTT only". On-screen PTT button appears. Wake word gone but UI still works. |
| Backend `/api` unreachable | Show full-screen "CRUZ offline" overlay with retry button. Queue user's last command client-side; send on reconnect. |
| SSE `/events` drops | Auto-reconnect with exponential backoff + replay last-50 on reconnect. |
| Deepgram returns empty transcript | UI shows "Didn't catch that" in transcript for 3s; user retries. |
| Approval gate shown but user goes offline | Timeout on backend at `expires_at`; row auto-denies. UI shows "Expired" badge. |

## 11. Security & auth (v1 scope)

- **v1**: localhost-only / home-LAN only. No auth. Relies on Tailscale + Cloudflare Tunnel for remote access (already configured in your repo).
- **Phase 2**: add JWT + user table auth middleware (separate spec).

All voice tokens are already short-lived (15 min per the voice v2 spec), so no added risk from unauthenticated UI in v1.

## 12. Responsive breakpoints

| Width | Device | Layout |
|---|---|---|
| < 768 px | phone | Orb + transcript + PTT; no rails; bottom tab bar hidden (drawer "⋯") |
| 768 – 1023 px | tablet | Orb + tabs (5: Conversation, Dashboard, Events, Agents, Approvals) + side rail with agent list |
| ≥ 1024 px | desktop | Full: top bar + left rail + center (orb + 7 tabs) + right rail |

Breakpoints via `useDevice()` hook (`window.matchMedia`), not Tailwind `md:` alone — some components need to unmount entirely on phone.

## 13. Testing strategy

- **Unit:** Vitest + RTL for components (Orb, AgentRail, PTTButton) and hooks (`useDevice`, `useLiveKitRoom`).
- **State:** Zustand stores tested independently.
- **Integration:** one Playwright e2e: load page → join LiveKit room (mock server) → see orb → click PTT → assert audio track publishes → mock transcript event → assert orb transitions states.
- **Backend:** 3 new endpoints get pytest tests in `tests/api/` following existing pattern (mock DB, assert shape + status codes).
- **No visual regression tests** v1 — they're high maintenance for a fast-evolving UI.

## 14. Performance budget

- First-load JS bundle **(app shell + critical path)**: ≤ 300 KB gzip. `livekit-client` is ~200 KB gzip on its own, so lazy-loading non-critical tabs is mandatory.
- Each tab **lazy-imported** via `React.lazy()` — only Conversation loads on first paint. Dashboard / Events / Approvals load on first tab switch.
- Time to Interactive on Mac localhost: ≤ 1.5 s
- Orb state-change → visual update: ≤ 50 ms
- SSE event → EventsTab render: ≤ 100 ms
- PTT press → LiveKit publishing: ≤ 150 ms
- **Contingency**: if shell exceeds 300 KB gzip, also lazy-load `@livekit/components-react` behind the Conversation tab so phone bundle drops to ~100 KB.

## 15. Rollout plan

### Phase 1 (this sprint — 4–6 days of autonomous implementation)

**Must ship (MVP):**
1. `frontend/` project scaffold (Vite + React + TS + Tailwind + shadcn)
2. Layout + SystemBar + AgentRail + PendingRail
3. Orb with 5 states + animations (Framer Motion)
4. LiveKit room join via `/voice/token`, subscribe to agent audio track
5. ConversationTab: live transcript from SSE `/events` + text input fallback
6. DashboardTab: `/dashboard` payload → 4 widgets (Today stub, Metrics, System health, Upcoming)
7. EventsTab: SSE stream reader with filter + `last_id` reconnect
8. ApprovalsTab: list + Approve/Deny actions (Mac primary; phone shows "check Mac")
9. Backend: `BaseAgent.log()` publishes to Redis channel `cruz:agent_logs` (invasive change — tests updated)
10. Backend: `GET /events`, `GET /dashboard`, `GET /approvals`, `POST /approvals/:id/{approve|deny}` endpoints + pytest
11. PWA config + manifest + install icons
12. Responsive breakpoints: phone + tablet + desktop verified
13. PM2 config gains `cruz-daemon` entry; README docs dev + prod launch
14. One Playwright e2e smoke

**Deferred to Phase 2 (next sprint):**
- AgentsTab (per-agent detail view)
- MemoryTab (Qdrant search UI)
- TasksTab (ARQ + Plane mirror)
- Waveform component (use orb alone v1)
- PWA offline cache beyond shell
- Auth + JWT middleware
- FCM push for mobile approvals

### Phase 2 (next sprint)

- Remaining tabs (Agents detail, Memory, Tasks)
- Auth + JWT middleware
- FCM push for mobile approval gates (covered in voice-pipeline Phase 2 spec)
- Theme toggle (optional amber / terminal modes)

## 16. Success criteria

The MVP is done when:

- [ ] User can open `http://localhost:5173` on Mac → see orb + 7 tabs + rails
- [ ] Saying "Hey Jarvis, what time is it" (via the existing daemon) → orb animates → transcript appears → CRUZ voice replies within 3 s
- [ ] Opening the same URL on iPad (over Tailscale) → side rail with 5 tabs appears
- [ ] Opening same URL on phone → voice-only view appears
- [ ] Pressing PTT on phone → speaks → CRUZ replies
- [ ] EventsTab shows agent_logs rows in real time as CRUZ runs
- [ ] DashboardTab shows system_health matching `/health`
- [ ] ApprovalsTab shows any pending rows; Approve/Deny unblock TITAN-style gates
- [ ] `pytest tests/api/` — all new endpoint tests green
- [ ] `vitest` + one Playwright e2e — all green
- [ ] `pytest tests/` full suite — no regressions

## 17. Open questions (deliberately left for implementation)

- Orb animation implementation: Framer Motion? CSS-only? Canvas? Decide at build time — Framer Motion probably, since we already need animations for state transitions.
- SSE on mobile: iOS Safari closes SSE after ~30s of tab background. Handle via reconnect; accept occasional gaps on phone.
- Bundle splitting: each tab a dynamic import or all eager? Likely dynamic to keep phone bundle small.

## 18. Cost impact

- **Ops:** zero. No new external services. LiveKit participant minutes slightly up (UI joins the room = 2nd participant), but still well under 10k free tier.
- **Build dependencies:** npm install adds ~500 MB to `frontend/node_modules`. No runtime cost.

---

**End of spec. Implementation plan follows in `docs/superpowers/plans/2026-04-18-command-center-web-ui-phase1.md`.**
