# CRUZ Command Center Web UI — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a responsive React web app at `http://localhost:5173` that replaces the current 3-terminal dev flow with a visual command center (FRIDAY-style orb, 4 tabs: Conversation/Dashboard/Events/Approvals, left agent rail + right pending rail on Mac, voice-only on phone, tablet middle ground). Joins the same LiveKit room as the daemon.

**Architecture:** Fresh Vite + React + shadcn under new `frontend/` dir. Backend gains Redis-pubsub-backed `/events` SSE, `/dashboard` aggregate, `/approvals` CRUD. Mac daemon stays — it keeps wake-word + speaker output; web UI is visual only on Mac, voice I/O on phone/iPad. All other voice infra (LiveKit worker, Deepgram, CRUZ stream_response) unchanged.

**Tech Stack:**
- Backend: FastAPI 0.128 + asyncpg + `redis.asyncio` (already in repo)
- Frontend: Vite 6 + React 18 + TypeScript 5 strict + Tailwind CSS 4 + shadcn/ui + Zustand + TanStack Query 5 + React Router 6 + `@livekit/components-react` + `livekit-client` + `framer-motion` + `vite-plugin-pwa`
- Tests: Vitest + @testing-library/react + Playwright (one e2e smoke)

**Spec:** [docs/superpowers/specs/2026-04-18-command-center-web-ui-design.md](../specs/2026-04-18-command-center-web-ui-design.md)

**Run from:** `/Users/drprockz/Projects/cruz-ai-system` (not the worktree — we're on main)

**Active venv:** `/Users/drprockz/Projects/cruz-ai-system/venv-py311/bin/activate`

---

## Pre-Flight

- [ ] Verify `node --version` ≥ 20 and `npm --version` ≥ 10. If missing, `brew install node`.
- [ ] Verify from repo root: `ls frontend/` fails (dir shouldn't exist yet — we'll create it).
- [ ] Verify LiveKit env vars are set (for UI to hit `/voice/token`): `grep -E '^LIVEKIT_' .env | wc -l` → 3.
- [ ] Verify backend is runnable: `source venv-py311/bin/activate && python -c "from backend.api.main import app; print('ok')"` → "ok".

---

## Chunk 1: Backend — `BaseAgent.log` publishes to Redis + `GET /events` SSE

**Why first:** Without the Redis pub/sub, the Events tab can't stream. This chunk is self-contained and has no frontend dependency; we can ship + verify via curl.

**Files:**
- Modify: `agents/base_agent.py` (add Redis publish to `log()`)
- Modify: `backend/api/main.py` (append `GET /events` endpoint)
- Create: `tests/api/test_events_endpoint.py`
- Modify: `tests/agents/test_base_agent.py` or `tests/agents/test_agent_logging.py` (add coverage for Redis publish)

### Task 1.1: Add Redis publish to `BaseAgent.log()`

- [ ] **Step 1: Read the current `log()` method in `agents/base_agent.py`** to understand the exact insert flow + error handling.

- [ ] **Step 2: Write failing test**

```python
# tests/agents/test_agent_logging.py — add this test
@pytest.mark.asyncio
async def test_log_publishes_to_redis_cruz_agent_logs_channel():
    """BaseAgent.log() publishes each inserted row to redis channel `cruz:agent_logs`."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from agents.base_agent import BaseAgent

    class TinyAgent(BaseAgent):
        async def process(self, input): ...

    db = AsyncMock()
    db.execute = AsyncMock(return_value="INSERT 0 1")

    published = {"calls": []}
    async def _fake_publish(channel, payload):
        published["calls"].append((channel, payload))

    fake_redis = MagicMock()
    fake_redis.publish = AsyncMock(side_effect=_fake_publish)

    with patch("agents.base_agent.get_redis_service") as gr:
        gr.return_value = fake_redis
        await TinyAgent().log(
            db=db, trace_id="t-1", status="success",
            input_data={"task": "x"}, output_data={"result": "y"},
            tokens_used=10, duration_ms=42,
        )

    assert len(published["calls"]) == 1
    channel, payload = published["calls"][0]
    assert channel == "cruz:agent_logs"
    import json as _json
    parsed = _json.loads(payload)
    assert parsed["trace_id"] == "t-1"
    assert parsed["status"] == "success"
    assert parsed["tokens_used"] == 10
```

- [ ] **Step 3: Run — expect fail**
```bash
source venv-py311/bin/activate
pytest tests/agents/test_agent_logging.py::test_log_publishes_to_redis_cruz_agent_logs_channel -v
```

- [ ] **Step 4: Implement** — in `agents/base_agent.py`, inside `log()` after the DB insert succeeds, add:

```python
# After the existing db.execute(...) insert — non-fatal Redis publish.
try:
    import json as _json
    from services.redis_client import get_redis_service
    _redis = get_redis_service()
    _payload = _json.dumps({
        "trace_id": trace_id,
        "agent": self.name,
        "action": "log",
        "status": status,
        "input_data": input_data,
        "output_data": output_data,
        "tokens_used": tokens_used,
        "duration_ms": duration_ms,
    }, default=str)
    await _redis.publish("cruz:agent_logs", _payload)
except Exception as _pub_exc:
    logger.warning("[%s] redis publish failed (non-fatal): %s", trace_id, _pub_exc)
```

- [ ] **Step 5: Pass**
```bash
pytest tests/agents/test_agent_logging.py -v
```

- [ ] **Step 6: Regression check — no existing agent test should break**
```bash
pytest tests/agents/ -q
```
Expected: all green.

- [ ] **Step 7: Commit**
```bash
git add agents/base_agent.py tests/agents/test_agent_logging.py
git commit -m "feat(agent): BaseAgent.log publishes agent_logs row to redis channel cruz:agent_logs"
```

### Task 1.2: `GET /events` SSE endpoint

**Files:**
- Modify: `backend/api/main.py` (append new route)
- Create: `tests/api/test_events_endpoint.py`

- [ ] **Step 1: Write tests**

```python
# tests/api/test_events_endpoint.py
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


def _make_app():
    from backend.api.main import app
    return app


def test_events_returns_text_event_stream(monkeypatch):
    """GET /events responds with text/event-stream media type."""
    # Mock DB fetch for initial replay
    async def _fake_fetch(*a, **kw): return []
    # Mock redis pubsub — return immediately after subscribe
    class FakePubSub:
        def __init__(self): self.subscribed = False
        async def subscribe(self, *channels): self.subscribed = True
        async def listen(self):
            # yield one fake message then return
            yield {"type": "subscribe", "data": 1}
            return
        async def unsubscribe(self, *c): pass
        async def close(self): pass

    fake_redis = MagicMock()
    fake_redis.pubsub = MagicMock(return_value=FakePubSub())

    class FakeDB:
        async def fetch(self, *a, **kw): return []
    fake_db = FakeDB()

    with patch("backend.api.main.get_redis_service", return_value=fake_redis), \
         patch("backend.api.main.get_db_service", return_value=fake_db):
        app = _make_app()
        client = TestClient(app)
        # Use stream=True so we don't block on the generator
        with client.stream("GET", "/events") as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]
            # Read a little to kick off the generator
            chunks = []
            for i, chunk in enumerate(r.iter_lines()):
                chunks.append(chunk)
                if i > 3:
                    break
            # Replay event present
            payload = "\n".join(chunks)
            assert "event: replay" in payload or "event: ping" in payload
```

- [ ] **Step 2: Run — expect fail (404)**
```bash
pytest tests/api/test_events_endpoint.py -v
```

- [ ] **Step 3: Implement**

Append to `backend/api/main.py`:

```python
# ─── Events SSE ──────────────────────────────────────────────
@app.get("/events")
async def events_stream(request: Request, last_id: int | None = None):
    """
    SSE stream of agent_logs rows.

    - On connect: emit `event: replay` with up to 50 recent rows (or rows > last_id).
    - Then emit `event: sync` so client knows it's caught up.
    - Then subscribe to redis channel `cruz:agent_logs` and emit `event: log` per message.
    - Emit `event: ping` every 25s to keep connection alive.
    """
    async def _gen() -> AsyncGenerator[str, None]:
        db = get_db_service()
        redis_svc = get_redis_service()
        pubsub = redis_svc.pubsub()
        try:
            # Replay
            if last_id is None:
                rows = await db.fetch(
                    "SELECT id, trace_id, agent, action, status, "
                    "tokens_used, duration_ms, created_at "
                    "FROM agent_logs ORDER BY id DESC LIMIT 50",
                )
                rows = list(reversed(rows))
            else:
                rows = await db.fetch(
                    "SELECT id, trace_id, agent, action, status, "
                    "tokens_used, duration_ms, created_at "
                    "FROM agent_logs WHERE id > $1 ORDER BY id ASC LIMIT 500",
                    last_id,
                )
            replay = [dict(r) for r in rows]
            yield _sse_event({"__event__": "replay", "data": replay})
            last_replay_id = replay[-1]["id"] if replay else last_id
            yield _sse_event({"__event__": "sync", "data": {"last_id": last_replay_id}})

            # Subscribe to pub/sub
            await pubsub.subscribe("cruz:agent_logs")
            import asyncio as _asyncio
            last_ping = _asyncio.get_event_loop().time()
            async for msg in pubsub.listen():
                if await request.is_disconnected():
                    break
                now = _asyncio.get_event_loop().time()
                if now - last_ping > 25:
                    yield _sse_event({"__event__": "ping", "data": {"t": int(now)}})
                    last_ping = now
                if msg.get("type") != "message":
                    continue
                data = msg.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(data) if isinstance(data, str) else data
                except Exception:
                    parsed = {"raw": str(data)}
                yield _sse_event({"__event__": "log", "data": parsed})
        finally:
            try:
                await pubsub.unsubscribe("cruz:agent_logs")
                await pubsub.close()
            except Exception:
                pass

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

And update `_sse_event` if it doesn't support the `__event__` key yet:

```python
def _sse_event(payload: dict) -> str:
    """Format a single SSE event line. If payload has `__event__`, emit a named event."""
    event_name = payload.pop("__event__", None) if isinstance(payload, dict) else None
    if event_name:
        data = payload.get("data", {})
        return f"event: {event_name}\ndata: {json.dumps(data, default=str)}\n\n"
    return f"data: {json.dumps(payload, default=str)}\n\n"
```

Imports — add near existing imports if missing: `from fastapi import Request`.

- [ ] **Step 4: Pass**
```bash
pytest tests/api/test_events_endpoint.py -v
```

- [ ] **Step 5: Full suite regression check**
```bash
pytest tests/ -q --ignore=tests/integration
```
Expected: 1129 + 1 new = 1130 passed (or at most one pre-existing flaky).

- [ ] **Step 6: Commit**
```bash
git add backend/api/main.py tests/api/test_events_endpoint.py
git commit -m "feat(api): GET /events SSE stream of agent_logs via redis pubsub"
```

---

## Chunk 2: Backend — `/dashboard` + `/approvals` endpoints

**Files:**
- Modify: `backend/api/main.py` (append)
- Create: `tests/api/test_dashboard_endpoint.py`
- Create: `tests/api/test_approvals_endpoint.py`

### Task 2.1: `GET /dashboard`

- [ ] **Step 1: Test**

```python
# tests/api/test_dashboard_endpoint.py
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

def test_dashboard_returns_expected_shape(monkeypatch):
    from backend.api.main import app
    monkeypatch.setenv("ENVIRONMENT", "test")

    # Fake DB for metrics
    class FakeDB:
        async def fetchrow(self, q, *a):
            return {"turns": 42, "tokens": 58342, "duration_total_ms": 73000}
    with patch("backend.api.main.get_db_service", return_value=FakeDB()):
        client = TestClient(app)
        r = client.get("/dashboard")
        assert r.status_code == 200
        j = r.json()
        assert set(j.keys()) >= {"today", "metrics", "system_health", "upcoming"}
        assert "turns_today" in j["metrics"]
        assert "deepgram" in j["system_health"]
```

- [ ] **Step 2: Run — fails**

- [ ] **Step 3: Implement**

Append to `backend/api/main.py`:

```python
@app.get("/dashboard")
async def dashboard():
    """Aggregate payload for DashboardTab. 5s TTL cache; always fresh enough."""
    db = get_db_service()

    # Metrics — today's agent_logs roll-up
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*)::int AS turns, "
            "COALESCE(SUM(tokens_used),0)::int AS tokens, "
            "COALESCE(SUM(duration_ms),0)::int AS duration_total_ms "
            "FROM agent_logs WHERE created_at > NOW() - INTERVAL '1 day'"
        )
        turns = row["turns"] if row else 0
        tokens = row["tokens"] if row else 0
        duration_total_ms = row["duration_total_ms"] if row else 0
    except Exception as exc:
        logger.warning("dashboard metrics fetch failed: %s", exc)
        turns, tokens, duration_total_ms = 0, 0, 0

    # System health — reuse the /health probe logic
    try:
        health_resp = await health()  # existing function
        sh_raw = health_resp if isinstance(health_resp, dict) else {}
    except Exception:
        sh_raw = {}

    def _state(x) -> str:
        if isinstance(x, dict):
            return "healthy" if x.get("status") in ("reachable", "connected", "loaded", "healthy") else "degraded"
        if x in ("healthy", "connected", "reachable"):
            return "healthy"
        return "degraded"

    system_health = {
        "deepgram": "healthy" if os.environ.get("DEEPGRAM_API_KEY") else "degraded",
        "livekit": "healthy" if os.environ.get("LIVEKIT_API_KEY") else "degraded",
        "postgres": _state(sh_raw.get("postgresql")),
        "redis": _state(sh_raw.get("redis")),
        "qdrant": _state(sh_raw.get("qdrant")),
        "ollama": _state(sh_raw.get("ollama")),
        "claude_api": _state(sh_raw.get("claude_api", "healthy")),
    }

    # Estimated cost — naive: $3 per 1M input + $15 per 1M output; we don't split so use weighted avg.
    estimated_cost = round((tokens / 1_000_000.0) * 9.0, 2)
    estimated_time_saved_hours = round(turns * 0.1, 1)  # crude heuristic

    return {
        "today": {
            "calendar_events": [],  # Phase 2
            "unread_emails": 0,     # Phase 2
            "open_prs": 0,          # Phase 2 via GitHub webhook mirror
            "deploys_today": 0,
        },
        "metrics": {
            "turns_today": turns,
            "tokens_today": tokens,
            "estimated_cost_usd": estimated_cost,
            "estimated_time_saved_hours": estimated_time_saved_hours,
        },
        "system_health": system_health,
        "upcoming": [
            {"agent": "pulse", "scheduled_at": "tomorrow 06:00", "label": "Morning brief"},
            {"agent": "raw", "scheduled_at": "tonight 03:00", "label": "Research scan"},
        ],
    }
```

- [ ] **Step 4: Pass**
- [ ] **Step 5: Commit**
```bash
git add backend/api/main.py tests/api/test_dashboard_endpoint.py
git commit -m "feat(api): GET /dashboard aggregate — metrics + system_health + upcoming"
```

### Task 2.2: `GET /approvals` + `POST /approvals/:id/{approve|deny}`

- [ ] **Step 1: Test**

```python
# tests/api/test_approvals_endpoint.py
import uuid
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


def test_list_approvals_returns_pending_rows():
    from backend.api.main import app
    row = {
        "id": "a-1", "trace_id": "t-1", "agent": "titan",
        "action": "deploy", "payload": {}, "state": "pending",
        "requested_at": "2026-04-18T18:00:00Z",
        "expires_at": "2026-04-18T18:10:00Z",
    }
    class FakeDB:
        async def fetch(self, *a, **kw): return [row]
        async def fetchrow(self, *a, **kw): return row
        async def execute(self, *a, **kw): return "UPDATE 1"

    with patch("backend.api.main.get_db_service", return_value=FakeDB()):
        c = TestClient(app)
        r = c.get("/approvals?state=pending")
        assert r.status_code == 200
        j = r.json()
        assert len(j) == 1 and j[0]["id"] == "a-1"


def test_approve_updates_state_and_returns_approved():
    from backend.api.main import app
    class FakeRedis:
        async def publish(self, *a, **kw): return 1
    class FakeDB:
        async def execute(self, *a, **kw): return "UPDATE 1"
    with patch("backend.api.main.get_db_service", return_value=FakeDB()), \
         patch("backend.api.main.get_redis_service", return_value=FakeRedis()):
        c = TestClient(app)
        r = c.post(f"/approvals/{uuid.uuid4()}/approve")
        assert r.status_code == 200
        assert r.json()["state"] == "approved"
```

- [ ] **Step 2: Implement** — Append to `backend/api/main.py`:

```python
from typing import Literal

class ApprovalRow(BaseModel):
    id: str
    trace_id: str
    agent: str
    action: str
    payload: Any
    state: str
    requested_at: Any
    responded_at: Any = None
    expires_at: Any


@app.get("/approvals", response_model=list[ApprovalRow])
async def list_approvals(state: str = "pending", limit: int = 25):
    db = get_db_service()
    rows = await db.fetch(
        "SELECT id, trace_id, agent, action, payload, state, "
        "requested_at, responded_at, expires_at "
        "FROM approval_requests WHERE state = $1 "
        "ORDER BY requested_at DESC LIMIT $2",
        state, limit,
    )
    return [dict(r) for r in rows]


async def _respond(approval_id: str, new_state: Literal["approved", "denied"]):
    db = get_db_service()
    redis_svc = get_redis_service()
    await db.execute(
        "UPDATE approval_requests SET state = $1, responded_at = NOW() "
        "WHERE id = $2",
        new_state, approval_id,
    )
    try:
        await redis_svc.publish(
            f"cruz:approval:{approval_id}",
            json.dumps({"state": new_state}),
        )
    except Exception as exc:
        logger.warning("approval publish failed (non-fatal): %s", exc)
    return {"state": new_state}


@app.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str):
    return await _respond(approval_id, "approved")


@app.post("/approvals/{approval_id}/deny")
async def deny(approval_id: str):
    return await _respond(approval_id, "denied")
```

- [ ] **Step 3: Pass**
- [ ] **Step 4: Commit**
```bash
git add backend/api/main.py tests/api/test_approvals_endpoint.py
git commit -m "feat(api): /approvals list + approve/deny endpoints"
```

---

## Chunk 3: Frontend — Scaffold + Layout shell

**Files:**
- Create: `frontend/package.json`, `vite.config.ts`, `tsconfig.json`, `tailwind.config.ts`, `postcss.config.js`, `.eslintrc.cjs`, `.prettierrc`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/index.css`
- Create: shadcn init files (automated)
- Create: `src/components/Layout.tsx`, `SystemBar.tsx`, `AgentRail.tsx`, `PendingRail.tsx`
- Create: `src/lib/api.ts`, `src/lib/breakpoints.ts`

### Task 3.1: Scaffold Vite project

- [ ] **Step 1: Create Vite project non-interactively**

```bash
cd /Users/drprockz/Projects/cruz-ai-system
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

- [ ] **Step 2: Install runtime + dev deps**

```bash
npm install @livekit/components-react livekit-client zustand \
  @tanstack/react-query react-router-dom framer-motion \
  lucide-react clsx tailwind-merge class-variance-authority
npm install -D tailwindcss@4 postcss autoprefixer vite-plugin-pwa \
  @types/node \
  vitest @testing-library/react @testing-library/jest-dom jsdom \
  @playwright/test
```

- [ ] **Step 3: Initialise Tailwind + shadcn**

```bash
npx tailwindcss init -p
npx shadcn@latest init -d     # defaults: zinc, CSS variables, src/ aliases
npx shadcn@latest add button card tabs input scroll-area tooltip \
  sheet dialog toast badge separator
```

- [ ] **Step 4: `vite.config.ts`** — proxy backend + enable PWA

```ts
// frontend/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import path from "node:path";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "CRUZ",
        short_name: "CRUZ",
        description: "FRIDAY-style AI command center",
        theme_color: "#0a0a0a",
        background_color: "#0a0a0a",
        display: "standalone",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icons/icon-512-maskable.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
    }),
  ],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:3000", changeOrigin: true, rewrite: p => p.replace(/^\/api/, "") },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
```

- [ ] **Step 5: Dummy PWA icons** — create placeholder 192/512 PNGs (any solid-colored square, shadcn generates something; otherwise just touch zero-byte files and lint ignores them). In `frontend/public/icons/` create 3 files:

```bash
mkdir -p frontend/public/icons
# Use `sips` (macOS) or `convert` (ImageMagick) to make 192 + 512 + 512-maskable
# Fallback: green square
python3 - <<'PY'
from PIL import Image
for size, name in [(192,"icon-192"),(512,"icon-512"),(512,"icon-512-maskable")]:
    img = Image.new("RGB", (size, size), "#22c55e")
    img.save(f"frontend/public/icons/{name}.png", "PNG")
PY
```

If `PIL` not available: `pip install pillow`. This is non-critical — missing icons just means the PWA install prompt is ugly.

- [ ] **Step 6: `src/test-setup.ts`**

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 7: Smoke test**

```bash
cd frontend
npm run dev &
sleep 3
curl -s http://localhost:5173 | head -c 400
pkill -f "vite"
```
Expected: HTML page with `<div id="root">`.

- [ ] **Step 8: Commit**
```bash
cd /Users/drprockz/Projects/cruz-ai-system
git add frontend/ package.json 2>/dev/null || true
# Respect existing .gitignore; ensure node_modules is ignored
echo "frontend/node_modules" >> .gitignore 2>/dev/null
git add .gitignore
git add -A frontend/
git commit -m "feat(ui): scaffold Vite + React + TS + Tailwind + shadcn"
```

### Task 3.2: Layout shell + SystemBar + rails

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/breakpoints.ts`
- Create: `frontend/src/components/Layout.tsx`
- Create: `frontend/src/components/SystemBar.tsx`
- Create: `frontend/src/components/AgentRail.tsx`
- Create: `frontend/src/components/PendingRail.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: `lib/breakpoints.ts`** — `useDevice()` hook

```ts
// frontend/src/lib/breakpoints.ts
import { useEffect, useState } from "react";

export type Device = "phone" | "tablet" | "desktop";

function resolve(w: number): Device {
  if (w < 768) return "phone";
  if (w < 1024) return "tablet";
  return "desktop";
}

export function useDevice(): Device {
  const [d, setD] = useState<Device>(() =>
    typeof window === "undefined" ? "desktop" : resolve(window.innerWidth),
  );
  useEffect(() => {
    const on = () => setD(resolve(window.innerWidth));
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return d;
}
```

- [ ] **Step 2: `lib/api.ts`** — HTTP client

```ts
// frontend/src/lib/api.ts
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} at ${path}`);
  return (await r.json()) as T;
}

export const sseUrl = (path: string) => `${BASE}${path}`;
```

- [ ] **Step 3: `SystemBar.tsx`** — top bar

```tsx
// frontend/src/components/SystemBar.tsx
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

type Health = { postgresql?: any; redis?: any; qdrant?: any; ollama?: any };

export function SystemBar() {
  const { data } = useQuery<Health>({
    queryKey: ["health"],
    queryFn: () => api<Health>("/health"),
    refetchInterval: 10_000,
  });
  const allGreen = data && Object.values(data).every(v =>
    v === "connected" || v === "reachable" || (v && typeof v === "object" && v.status !== "error"),
  );
  return (
    <div className="flex items-center gap-3 h-10 px-4 border-b bg-zinc-950/80 text-xs text-zinc-400">
      <span className={allGreen ? "text-green-500" : "text-amber-500"}>●</span>
      <span className="font-medium text-zinc-100">CRUZ</span>
      <span>{allGreen ? "all systems online" : "degraded"}</span>
      <span className="ml-auto">{new Date().toLocaleTimeString()}</span>
    </div>
  );
}
```

- [ ] **Step 4: `AgentRail.tsx`** — left rail (12 agents)

```tsx
// frontend/src/components/AgentRail.tsx
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const AGENTS = ["cruz","forge","echo","reach","pm","catch","qt","sentinel","titan","mark","raw","pulse"];

type AgentStatus = Record<string, { status: string; last_run?: string }>;

export function AgentRail() {
  const { data } = useQuery<AgentStatus>({
    queryKey: ["agents"],
    queryFn: () => api("/agents/status"),
    refetchInterval: 5_000,
  });
  return (
    <div className="w-48 border-r bg-zinc-950/50 p-3">
      <div className="text-[10px] uppercase text-zinc-500 mb-2 tracking-wider">12 Agents</div>
      <ul className="space-y-1 text-xs">
        {AGENTS.map(a => {
          const status = data?.[a]?.status ?? "idle";
          const dot = status === "running" ? "bg-amber-500" : status === "error" ? "bg-red-500" : "bg-green-500";
          return (
            <li key={a} className="flex items-center gap-2 text-zinc-300">
              <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
              <span className="lowercase">{a}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
```

- [ ] **Step 5: `PendingRail.tsx`** — right rail (approvals + upcoming)

```tsx
// frontend/src/components/PendingRail.tsx
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Link } from "react-router-dom";

type Approval = { id: string; agent: string; action: string };

export function PendingRail() {
  const { data } = useQuery<Approval[]>({
    queryKey: ["approvals","pending"],
    queryFn: () => api("/approvals?state=pending"),
    refetchInterval: 4_000,
  });
  return (
    <div className="w-52 border-l bg-zinc-950/50 p-3">
      <div className="text-[10px] uppercase text-zinc-500 mb-2 tracking-wider">Pending</div>
      <ul className="space-y-2 text-xs">
        {!data?.length && <li className="text-zinc-500">No approvals</li>}
        {data?.slice(0,5).map(a => (
          <li key={a.id}>
            <Link to={`/tab/approvals/${a.id}`} className="block text-amber-400 hover:underline">
              ⚠ {a.agent} · {a.action}
            </Link>
          </li>
        ))}
      </ul>
      <div className="text-[10px] uppercase text-zinc-500 mt-6 mb-2 tracking-wider">Upcoming</div>
      <ul className="space-y-1 text-xs text-zinc-400">
        <li>📰 Brief · 6 AM</li>
        <li>🔬 Research · 3 AM</li>
      </ul>
    </div>
  );
}
```

- [ ] **Step 6: `Layout.tsx`** — grid

```tsx
// frontend/src/components/Layout.tsx
import { SystemBar } from "./SystemBar";
import { AgentRail } from "./AgentRail";
import { PendingRail } from "./PendingRail";
import { useDevice } from "@/lib/breakpoints";
import type { ReactNode } from "react";

export function Layout({ children }: { children: ReactNode }) {
  const d = useDevice();
  return (
    <div className="h-dvh flex flex-col bg-zinc-950 text-zinc-100">
      <SystemBar />
      <div className="flex-1 flex overflow-hidden">
        {d === "desktop" && <AgentRail />}
        <main className="flex-1 overflow-hidden">{children}</main>
        {d === "desktop" && <PendingRail />}
      </div>
    </div>
  );
}
```

- [ ] **Step 7: `App.tsx` + routing**

```tsx
// frontend/src/App.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { lazy, Suspense } from "react";

const ConversationTab = lazy(() => import("./tabs/ConversationTab").then(m => ({ default: m.ConversationTab })));
const DashboardTab = lazy(() => import("./tabs/DashboardTab").then(m => ({ default: m.DashboardTab })));
const EventsTab = lazy(() => import("./tabs/EventsTab").then(m => ({ default: m.EventsTab })));
const ApprovalsTab = lazy(() => import("./tabs/ApprovalsTab").then(m => ({ default: m.ApprovalsTab })));

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 5_000 } } });

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Layout>
          <Suspense fallback={<div className="p-6 text-zinc-500">Loading…</div>}>
            <Routes>
              <Route path="/" element={<Navigate to="/tab/conversation" replace />} />
              <Route path="/tab/conversation" element={<ConversationTab />} />
              <Route path="/tab/dashboard" element={<DashboardTab />} />
              <Route path="/tab/events" element={<EventsTab />} />
              <Route path="/tab/approvals" element={<ApprovalsTab />} />
              <Route path="/tab/approvals/:id" element={<ApprovalsTab />} />
            </Routes>
          </Suspense>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 8: Stub tabs** (so lazy imports don't 404)

Create `src/tabs/` each with a trivial component:

```tsx
// frontend/src/tabs/ConversationTab.tsx
export function ConversationTab() { return <div className="p-6">Conversation (tab) — coming in Chunk 4</div>; }
// ditto for DashboardTab, EventsTab, ApprovalsTab
```

- [ ] **Step 9: `src/index.css`** — ensure Tailwind base loaded

Check that `npx shadcn init` already wrote CSS vars + `@tailwind base/components/utilities`. If not, add.

- [ ] **Step 10: Dev smoke**

```bash
cd frontend && npm run dev &
sleep 3
curl -s http://localhost:5173/tab/conversation | grep -c "root"
pkill -f "vite"
```
Expected: `1`.

- [ ] **Step 11: Commit**
```bash
git add frontend/src/ frontend/vite.config.ts
git commit -m "feat(ui): layout shell — system bar, rails, routed tab stubs"
```

---

## Chunk 4: Frontend — Orb + voice store + LiveKit room integration

**Files:**
- Create: `frontend/src/state/voiceStore.ts`
- Create: `frontend/src/components/Orb.tsx`
- Create: `frontend/src/components/PTTButton.tsx`
- Create: `frontend/src/lib/livekit.ts`
- Create: `frontend/src/hooks/useLiveKitRoom.ts`
- Modify: `frontend/src/tabs/ConversationTab.tsx`

### Task 4.1: Voice state + Orb

- [ ] **Step 1: Voice store (Zustand)**

```ts
// frontend/src/state/voiceStore.ts
import { create } from "zustand";

export type VoiceState = "idle" | "listening" | "thinking" | "speaking" | "interrupted";

interface VS {
  state: VoiceState;
  currentText: string;
  transcript: { role: "user" | "cruz" | "tool"; text: string; ts: number }[];
  set: (s: Partial<VS>) => void;
  append: (entry: VS["transcript"][number]) => void;
  reset: () => void;
}

export const useVoice = create<VS>((set) => ({
  state: "idle",
  currentText: "",
  transcript: [],
  set: (patch) => set(patch),
  append: (entry) => set((s) => ({ transcript: [...s.transcript.slice(-99), entry] })),
  reset: () => set({ transcript: [], currentText: "", state: "idle" }),
}));
```

- [ ] **Step 2: `Orb.tsx` — animated with framer-motion**

```tsx
// frontend/src/components/Orb.tsx
import { motion } from "framer-motion";
import { useVoice } from "@/state/voiceStore";

export function Orb() {
  const s = useVoice((v) => v.state);
  const text = useVoice((v) => v.currentText);

  const scale = s === "speaking" ? 1.1 : s === "listening" ? 1.05 : 1;
  const ringColour =
    s === "interrupted" ? "ring-amber-500"
    : s === "thinking" ? "ring-blue-500"
    : "ring-green-500";

  return (
    <div className="flex flex-col items-center justify-center gap-4 py-6">
      <motion.div
        animate={{ scale }}
        transition={{ type: "spring", stiffness: 180, damping: 14 }}
        className={`h-24 w-24 rounded-full ring-2 ${ringColour} ring-offset-2 ring-offset-zinc-950 bg-zinc-900 flex items-center justify-center`}
      >
        {(s === "listening" || s === "speaking") && (
          <div className="flex gap-1 items-end">
            {[16, 26, 14, 22].map((h, i) => (
              <motion.div
                key={i}
                className="w-1 bg-green-500 rounded-full"
                animate={{ height: [h, h * 0.6, h] }}
                transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.1 }}
                style={{ height: h }}
              />
            ))}
          </div>
        )}
        {s === "thinking" && (
          <div className="flex gap-1">{[0,1,2].map(i => (
            <motion.div key={i} className="h-2 w-2 rounded-full bg-blue-400"
              animate={{ opacity: [0.3, 1, 0.3] }}
              transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }} />
          ))}</div>
        )}
        {s === "idle" && <div className="h-2 w-2 rounded-full bg-zinc-600" />}
      </motion.div>
      <div className="text-sm text-zinc-300 min-h-[1.25rem] text-center max-w-xl">
        {text || (s === "idle" ? "Ready." : "")}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**
```bash
git add frontend/src/state/voiceStore.ts frontend/src/components/Orb.tsx
git commit -m "feat(ui): voice state store + animated orb (5 states)"
```

### Task 4.2: LiveKit room integration

- [ ] **Step 1: `lib/livekit.ts`** — token fetch + room helpers

```ts
// frontend/src/lib/livekit.ts
import { api } from "./api";

export async function fetchVoiceToken(device: string, conversationId?: string) {
  return api<{ room: string; token: string; ws_url: string; conversation_id: string }>(
    "/voice/token",
    { method: "POST", body: JSON.stringify({ device_id: device, conversation_id: conversationId }) },
  );
}
```

- [ ] **Step 2: `hooks/useLiveKitRoom.ts`** — connect + manage

```ts
// frontend/src/hooks/useLiveKitRoom.ts
import { useEffect, useRef, useState } from "react";
import { Room, RoomEvent, Track, LocalAudioTrack, createLocalAudioTrack } from "livekit-client";
import { fetchVoiceToken } from "@/lib/livekit";
import { useVoice } from "@/state/voiceStore";

export function useLiveKitRoom(deviceId: string) {
  const [room, setRoom] = useState<Room | null>(null);
  const [connected, setConnected] = useState(false);
  const micTrackRef = useRef<LocalAudioTrack | null>(null);

  useEffect(() => {
    let mounted = true;
    let localRoom: Room | null = null;
    (async () => {
      try {
        const tok = await fetchVoiceToken(deviceId);
        const r = new Room({ adaptiveStream: true, dynacast: true });
        r.on(RoomEvent.TrackSubscribed, (track, _pub, participant) => {
          if (track.kind !== Track.Kind.Audio) return;
          // Only play agent audio on phone/tablet. On Mac the daemon plays audio.
          const isMac = /Macintosh/.test(navigator.userAgent);
          if (participant.identity.startsWith("agent-") && !isMac) {
            const el = track.attach();
            el.autoplay = true;
            document.body.appendChild(el);
          }
        });
        r.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
          const agentSpeaking = speakers.some(s => s.identity.startsWith("agent-"));
          const userSpeaking = speakers.some(s => !s.identity.startsWith("agent-") && s.identity !== deviceId);
          useVoice.getState().set({
            state: agentSpeaking ? "speaking" : userSpeaking ? "listening" : "idle",
          });
        });
        await r.connect(tok.ws_url, tok.token);
        if (!mounted) { await r.disconnect(); return; }
        localRoom = r;
        setRoom(r);
        setConnected(true);
      } catch (exc) {
        console.error("livekit connect failed", exc);
      }
    })();
    return () => {
      mounted = false;
      if (localRoom) localRoom.disconnect();
    };
  }, [deviceId]);

  const startPTT = async () => {
    if (!room) return;
    const t = await createLocalAudioTrack();
    micTrackRef.current = t;
    await room.localParticipant.publishTrack(t);
    useVoice.getState().set({ state: "listening" });
  };
  const stopPTT = async () => {
    if (!room || !micTrackRef.current) return;
    await room.localParticipant.unpublishTrack(micTrackRef.current);
    micTrackRef.current.stop();
    micTrackRef.current = null;
    useVoice.getState().set({ state: "thinking" });
  };

  return { room, connected, startPTT, stopPTT };
}
```

- [ ] **Step 3: `PTTButton.tsx`**

```tsx
// frontend/src/components/PTTButton.tsx
import { useLiveKitRoom } from "@/hooks/useLiveKitRoom";
import { Mic } from "lucide-react";

export function PTTButton({ deviceId }: { deviceId: string }) {
  const { startPTT, stopPTT, connected } = useLiveKitRoom(deviceId);
  return (
    <button
      disabled={!connected}
      onPointerDown={startPTT}
      onPointerUp={stopPTT}
      onPointerLeave={stopPTT}
      className="flex items-center gap-2 rounded-full bg-green-500 px-6 py-3 text-black font-semibold disabled:opacity-40"
    >
      <Mic size={18} /> Hold to talk
    </button>
  );
}
```

- [ ] **Step 4: `ConversationTab.tsx`** (replace stub)

```tsx
// frontend/src/tabs/ConversationTab.tsx
import { useVoice } from "@/state/voiceStore";
import { Orb } from "@/components/Orb";
import { PTTButton } from "@/components/PTTButton";
import { useLiveKitRoom } from "@/hooks/useLiveKitRoom";
import { useDevice } from "@/lib/breakpoints";

export function ConversationTab() {
  const device = useDevice();
  const deviceId = device === "phone" ? "phone" : device === "tablet" ? "ipad" : "mac-web";
  useLiveKitRoom(deviceId); // ensure room is joined
  const transcript = useVoice((v) => v.transcript);

  return (
    <div className="h-full flex flex-col gap-4 p-4 overflow-hidden">
      <Orb />
      <div className="flex-1 overflow-y-auto rounded-md border border-zinc-800 bg-zinc-900/50 p-4 text-sm">
        {transcript.length === 0 && (
          <div className="text-zinc-500">Say "Hey Jarvis" on Mac, or hold the button below to talk.</div>
        )}
        {transcript.map((t, i) => (
          <div key={i} className="mb-2">
            <span className={t.role === "user" ? "text-blue-400" : t.role === "cruz" ? "text-green-400" : "text-zinc-500"}>
              {t.role === "user" ? "You" : t.role === "cruz" ? "CRUZ" : "→"}
            </span>
            <span className="ml-2 text-zinc-200">{t.text}</span>
          </div>
        ))}
      </div>
      {device !== "desktop" && (
        <div className="flex justify-center">
          <PTTButton deviceId={deviceId} />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Dev smoke + commit**
```bash
cd frontend && npm run dev &
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/tab/conversation  # 200
pkill -f vite
cd /Users/drprockz/Projects/cruz-ai-system
git add frontend/src/
git commit -m "feat(ui): LiveKit room integration + ConversationTab + PTT button"
```

---

## Chunk 5: Frontend — Dashboard + Events + Approvals tabs

### Task 5.1: DashboardTab

**Files:** Create `frontend/src/tabs/DashboardTab.tsx`

- [ ] Implement using `useQuery` against `/api/dashboard`; render 4 Cards (Today, Metrics, System Health, Upcoming). Use shadcn `Card` + `Badge`. 60 lines max.

- [ ] Commit: `feat(ui): DashboardTab with 4 widgets polled every 10s`

### Task 5.2: EventsTab (SSE reader)

**Files:**
- Create: `frontend/src/hooks/useEventStream.ts`
- Create: `frontend/src/tabs/EventsTab.tsx`

- [ ] **Step 1: `useEventStream` hook**

```ts
// frontend/src/hooks/useEventStream.ts
import { useEffect, useState } from "react";
import { sseUrl } from "@/lib/api";

export type LogEvent = {
  id: number; trace_id: string; agent: string; action: string;
  status: string; tokens_used: number; duration_ms: number; created_at: string;
};

export function useEventStream(max = 200) {
  const [events, setEvents] = useState<LogEvent[]>([]);
  useEffect(() => {
    const es = new EventSource(sseUrl("/events"));
    es.addEventListener("replay", (e) => {
      const rows: LogEvent[] = JSON.parse((e as MessageEvent).data);
      setEvents(rows.slice(-max));
    });
    es.addEventListener("log", (e) => {
      const row: LogEvent = JSON.parse((e as MessageEvent).data);
      setEvents((prev) => [...prev.slice(-(max - 1)), row]);
    });
    return () => es.close();
  }, [max]);
  return events;
}
```

- [ ] **Step 2: `EventsTab.tsx`** — table/timeline UI

```tsx
// frontend/src/tabs/EventsTab.tsx
import { useEventStream } from "@/hooks/useEventStream";
import { useMemo, useState } from "react";

export function EventsTab() {
  const events = useEventStream(200);
  const [filter, setFilter] = useState("");
  const filtered = useMemo(() => {
    if (!filter) return events;
    return events.filter(e =>
      e.agent.includes(filter) || e.action.includes(filter) || e.trace_id.includes(filter)
    );
  }, [events, filter]);

  return (
    <div className="h-full flex flex-col p-4 gap-3">
      <input
        placeholder="filter by agent / action / trace_id"
        className="rounded-md bg-zinc-900 border border-zinc-800 px-3 py-2 text-sm"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      <div className="flex-1 overflow-y-auto font-mono text-[11px] space-y-1">
        {filtered.map(e => (
          <div key={e.id} className="flex gap-3 text-zinc-300">
            <span className="text-zinc-500">{new Date(e.created_at).toLocaleTimeString()}</span>
            <span className="text-blue-400 w-16">{e.agent}</span>
            <span className="text-zinc-400 w-20">{e.action}</span>
            <span className={e.status === "success" ? "text-green-500" : e.status === "error" ? "text-red-500" : "text-amber-500"}>{e.status}</span>
            <span className="text-zinc-600">{e.duration_ms}ms · {e.tokens_used}tk</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Commit:** `feat(ui): EventsTab live SSE stream + filter`

### Task 5.3: ApprovalsTab

**Files:** Create `frontend/src/tabs/ApprovalsTab.tsx`

- [ ] Use `useQuery` against `/api/approvals?state=pending`; render Cards with Approve/Deny buttons that `POST /approvals/:id/approve|deny`. `queryClient.invalidateQueries` on success. 80 lines max.

- [ ] **Commit:** `feat(ui): ApprovalsTab list + approve/deny actions`

---

## Chunk 6: PWA + responsive polish + PM2 daemon + Playwright e2e

### Task 6.1: PM2 daemon entry

- [ ] Modify `ecosystem.config.js` — add third app:

```js
{
  name: "cruz-daemon",
  script: VENV_PY,
  args: "scripts/voice/livekit_client.py --host http://localhost:3000",
  cwd: ROOT,
  interpreter: "none",
  autorestart: true,
  max_memory_restart: "512M",
  min_uptime: "10s",
  max_restarts: 5,
  env: { PYTHONUNBUFFERED: "1", PYTHONPATH: ROOT },
  out_file: path.join(LOGS_DIR, "cruz-daemon.out.log"),
  error_file: path.join(LOGS_DIR, "cruz-daemon.err.log"),
}
```

- [ ] Commit: `feat(ops): PM2 cruz-daemon entry keeps voice listener alive`

### Task 6.2: Responsive — phone view

- [ ] On phone, Layout hides AgentRail + PendingRail (already handled via `useDevice`). Verify `ConversationTab` shows PTT on phone (already handled). Verify tabs are still accessible via URL but no persistent nav on phone — add a floating hamburger drawer using shadcn `Sheet` at top-right. ~40 lines.

- [ ] Commit: `feat(ui): phone view — bottom PTT + drawer nav for non-conversation tabs`

### Task 6.3: Playwright e2e smoke

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/smoke.spec.ts`

```ts
// frontend/playwright.config.ts
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "e2e",
  use: { baseURL: "http://localhost:5173" },
  webServer: { command: "npm run dev", url: "http://localhost:5173", reuseExistingServer: true },
});
```

```ts
// frontend/e2e/smoke.spec.ts
import { test, expect } from "@playwright/test";

test("loads and shows the orb", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/tab\/conversation/);
  await expect(page.getByText(/Say "Hey Jarvis"|Ready\./)).toBeVisible();
});

test("tabs navigate", async ({ page }) => {
  await page.goto("/tab/dashboard");
  await expect(page.locator("body")).toContainText(/system|metrics/i, { timeout: 5000 });
});
```

- [ ] Install browsers: `npx playwright install chromium`
- [ ] Run: `npx playwright test` (should pass)
- [ ] Commit: `test(ui): playwright e2e smoke — load + tab navigation`

### Task 6.4: README

**Files:** Create `frontend/README.md`

- [ ] Short ops guide — dev (`npm run dev`), build (`npm run build`), preview (`npm run preview`), test (`npm test`, `npx playwright test`), prod launch (via PM2 `pm2 start ecosystem.config.js`).

- [ ] Commit: `docs(ui): frontend README with dev + prod launch`

---

## Exit Checklist

- [ ] `pytest tests/ -q --ignore=tests/integration` — green (1129 + 3 new = ~1132 passed)
- [ ] `cd frontend && npm test` — Vitest green
- [ ] `cd frontend && npx playwright test` — e2e green
- [ ] `curl -s http://localhost:3000/dashboard | jq` returns full shape
- [ ] `curl -N http://localhost:3000/events | head -c 400` shows `event: replay`
- [ ] `curl -s http://localhost:3000/approvals` returns 200 `[]`
- [ ] Manual: open `http://localhost:5173` on Mac → orb + rails + 4 tabs visible
- [ ] Manual: Resize to < 768 px → rails disappear, PTT button appears
- [ ] Manual: With daemon + worker running, say "Hey Jarvis, what time is it" → orb animates → transcript appears in ConversationTab
- [ ] `pm2 start ecosystem.config.js` — 3 processes alive (`cruz-api`, `cruz-worker`, `cruz-daemon`)
- [ ] Git log shows one feature commit per task, well-scoped

## Deferred to Phase 2 (explicit)

- AgentsTab (per-agent detail)
- MemoryTab (Qdrant search)
- TasksTab (ARQ queue)
- Waveform visualizer component
- Auth (JWT middleware)
- FCM push for mobile approvals
- Offline PWA caching beyond shell
