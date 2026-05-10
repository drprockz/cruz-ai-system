# CRUZ AI System — Project Bible

> **FRIDAY from Iron Man. Built for a freelance developer.**
> You talk to CRUZ. CRUZ handles everything else.

---

## Vision

CRUZ is a personal AI command center that runs 24/7 on a Mac Mini M4, accessible from any device — phone on the train, iPad between calls, ThinkPad at the office. You speak or type in natural language. CRUZ understands context, remembers your work, breaks complex goals into steps, delegates to specialized agents, and replies in a natural voice.

**The goal**: Reclaim 8-15 hours/week from repetitive dev work — client emails, meeting notes, deployments, lead gen, code review, documentation — so you can take on more clients or just breathe.

**Target user**: Darshan Parmar — freelance full-stack developer managing AMA Solutions, Shooterista, SuiteAdvisors, Asia Capital, and building MIDAR.

---

## The FRIDAY Mental Model

```
Tony Stark didn't talk to "the routing subsystem."
He talked to FRIDAY.

You don't talk to RELAY or FORGE.
You talk to CRUZ.
```

```
You (on phone / iPad / ThinkPad / voice)
          │
          ▼  "Hey CRUZ, the AMA site is broken in prod"
     ┌────────────────────────────────────────┐
     │               CRUZ                     │
     │  • Loads conversation history           │
     │  • Understands context + intent         │
     │  • Decides: act directly OR delegate   │
     │  • Orchestrates via native tool_use     │
     │  • Streams response back to you        │
     │  • Remembers outcome for next time     │
     └────────────────────────────────────────┘
          │  (invisible to you)
          ├──► SENTINEL reviews recent commits
          ├──► FORGE patches the bug
          ├──► QT runs smoke tests
          └──► TITAN deploys the fix
          │
          ▼
     "Fixed. It was a null check on line 84 of api/orders.js.
      Deployed to prod. Tests passing. Client notified."
```

---

## Hardware & Infrastructure

### Command Center
| Component | Spec | Purpose |
|-----------|------|---------|
| Mac Mini M4 | 24GB unified RAM, 256GB SSD, 10-core CPU/GPU | Runs all CRUZ services 24/7 |
| UPS (1000VA) | APC/Luminous | 30-60 min power backup |
| External HDD | 2TB (Seagate/WD) | Weekly full backups |
| Network | 200 Mbps fiber | API calls, webhooks |
| Power cost | 35W average | ₹202/month |

### Client Devices
| Device | OS | How CRUZ is accessed |
|--------|----|--------------------|
| Nothing Phone 2 | Android 14 | React Native app + voice |
| iPad | iPadOS 17 | Web dashboard / React Native |
| ThinkPad | Windows (32GB i7) | Web dashboard + SSH |
| Mac Mini | macOS Sequoia | Direct terminal + web |

### Network Architecture
```
Home WiFi (192.168.1.100:3000)     → Direct LAN access
Tailscale VPN (100.x.x.x:3000)    → Secure cross-device anywhere
Cloudflare Tunnel (https://cruz.simpleinc.cloud) → Webhooks + public access
```

---

## Production Architecture

### Why This Architecture (vs what others do)

Most multi-agent systems route through a dedicated "router" LLM call before delegating. This was necessary pre-2023. Today it is an anti-pattern.

| Old pattern (routing agent) | CRUZ approach (tool_use) |
|---|---|
| 2+ LLM calls per request | 1 LLM call per request |
| 600-1000ms routing overhead | 0ms routing overhead |
| JSON prompt parsing (fragile) | Schema-validated tool selection |
| Sequential agent execution | Parallel tool calls possible |
| Extra tokens every request | Zero extra tokens for routing |

**CRUZ uses Claude's native `tool_use`.** CRUZ's system prompt defines all agent capabilities as tools. Claude decides which to call — routing IS tool selection.

### Core Flow

```
POST /command  {message, conversation_id, stream: true}
       │
       ▼
CRUZ Agent (agents/cruz/cruz_agent.py)
  ├── loads conversation history from PostgreSQL
  ├── retrieves relevant context from Qdrant (Week 3+)
  ├── single Claude call with ALL tools defined
  │     Claude decides: call tools? reply directly? ask human?
  ├── executes tool(s) — in parallel where independent
  ├── observes results → continue loop or finalize
  ├── streams response token by token (SSE)
  ├── saves exchange to conversations + messages tables
  └── logs trace to agent_logs with trace_id
       │
       ▼
You get a streamed natural language response
```

### Agentic Loop (for complex goals)

```
"Build a contact form, test it, and email the client it's ready"
         │
         ▼
Plan: [FORGE: create form] → [QT: test it] → [ECHO: draft email]
         │
[FORGE runs]──► result ──► [QT runs]──► pass ──► [ECHO drafts]
                                │
                              fail ──► [FORGE fixes]──► [QT re-runs]
         │
[CRUZ: "Done. Form built, 12/12 tests passing. Draft email ready for your review."]
```

This is how Devin, LangGraph, and Claude Agents work. Single-shot response is only used for simple queries.

### RELAY's Role (Clarified)

RELAY is **not a brain**. It is a **lightweight keyword classifier** — a fast, deterministic Python function that:
- Detects explicit agent keywords in a message (`"FORGE, ..."`, `"deploy to prod"`)
- Pre-filters the tool list for efficiency on long registries
- Adds zero LLM calls

When no keyword match exists, Claude's native tool_use handles routing. RELAY is an optimization, not an orchestrator.

### Human Approval Gates

Before any irreversible action, CRUZ pauses:

```
TITAN:    "Ready to deploy to production (AMA website). Confirm?"
ECHO:     "Ready to send email to ateet@ama.com. Send now? [Preview]"
SENTINEL: "Found 2 SQL injection risks. Apply suggested fixes? [Show diff]"
REACH:    "Ready to send 5 outreach emails. Review before sending?"
```

No agent executes a destructive or externally visible action without your explicit OK. This matches how LangGraph `interrupt_before` and OpenAI human-in-the-loop work.

---

## Agent Registry

### CRUZ (Main Assistant)
**You always talk to CRUZ. You never talk to other agents directly.**

| Property | Value |
|---|---|
| Model | Claude Sonnet 4 |
| File | `agents/cruz/cruz_agent.py` |
| Role | Conversational interface, memory, orchestration, response formatting |
| Memory | Full conversation history + Qdrant semantic retrieval |
| Personality | Concise, direct, proactive — surfaces relevant context before you ask |

### RELAY (Internal Router)
**Called by CRUZ. Never by you.**

| Property | Value |
|---|---|
| Model | None (deterministic keyword matching) |
| File | `agents/relay/relay_agent.py` |
| Role | Keyword-to-tool mapping for efficiency; falls back to Claude tool_use |

### GENERAL (Catch-All)
| Property | Value |
|---|---|
| Model | Claude Sonnet 4 |
| File | `agents/general/general_agent.py` |
| Role | Handles tasks that don't fit any specialist |

### Specialized Agents

| Agent | Model | What CRUZ delegates | Autonomous? | Key integrations |
|-------|-------|---------------------|-------------|-----------------|
| **FORGE** ⚒️ | Claude Sonnet 4 | Code gen, components, APIs, bug fixes, refactoring | On-demand | GitHub, VS Code |
| **ECHO** 💬 | Qwen 2.5 Coder 14B | Email drafts, proposals, Slack messages | On-demand (with approval to send) | Gmail API, SendGrid, Notion |
| **REACH** 📨 | Gemini Flash 2.5 (discovery) + Qwen 14B (personalization) | Lead research, outreach email drafting | 2 AM daily (with approval to send) | Apollo.io, Hunter.io, Notion |
| **CATCH** 📝 | Whisper Large v3 | Meeting transcription, action items, summaries | Auto on calendar trigger | Teams/Meet/Zoom, Notion, Linear |
| **PM** ⏱️ | Qwen 2.5 Coder 14B | Sprint planning, task breakdown, estimation | Monday 9 AM sprint review | Linear/JIRA, Notion, GitHub |
| **TITAN** 🏗️ | Qwen 2.5 Coder 14B | Deployments, CI/CD, infra, rollbacks | On deploy webhook (approval gate) | Vercel, Railway, Hostinger SSH |
| **MARK** 🖊️ | Qwen 2.5 Coder 14B | API docs, README, changelogs, JSDoc | Post-commit auto | GitHub, Notion, Swagger |
| **QT** 🛡️ | Qwen 2.5 Coder 14B | Test generation, e2e, security scans, Lighthouse | Pre-deploy gate (blocks TITAN) | Pytest, Playwright, npm audit |
| **SENTINEL** 👁️ | Claude Sonnet 4 | Code review, security audit, PR analysis | On PR open | GitHub, Linear, Slack |
| **RAW** 🔬 | Llama 3.1 8B | Tech research, dependency updates, web scraping | 3 AM daily | Qdrant, Notion, npm/pip |
| **PULSE** 📰 | Llama 3.1 8B | Daily briefings, news, market intelligence | 6 AM daily (ready when you wake) | RSS feeds, Hacker News, Reddit, Notion |

### BaseAgent (Foundation for All)

Every agent extends `BaseAgent`. Non-negotiable.

```python
class BaseAgent:
    """All agents extend this. Provides: logging, error handling,
    model routing, trace propagation, structured I/O."""

    trace_id: str          # propagated from originating CRUZ request
    model: str             # from config, never hardcoded
    agent_name: str        # for logging

    async def process(self, input: AgentInput) -> AgentOutput: ...
    async def log(self, action, input, output, duration_ms): ...
    async def call_claude(self, messages, tools=None): ...
    async def call_ollama(self, model, messages): ...
    def handle_error(self, e: Exception) -> AgentOutput: ...
```

---

## Voice Pipeline

### Full Stack
```
"Hey CRUZ" → [Porcupine] → wake word detected
           → [Microphone capture] → audio stream
           → [Whisper Large v3] → text (500ms, local)
           → [CRUZ] → processes, orchestrates
           → [Inworld TTS 1.5 Max] → audio stream (250ms)
           → [Speaker] → natural voice response
```

### Components

| Component | Provider | Why | Cost |
|---|---|---|---|
| Wake word | Porcupine 3.x (Picovoice) | On-device, <1% CPU, custom "Hey CRUZ" | ₹0 |
| STT | Whisper Large v3 (local) | 99 languages, >98% accuracy, offline, zero latency cost | ₹0 |
| STT fallback | Deepgram nova-3 | 150ms cloud backup when accuracy critical | Free (200 hrs/mo) |
| TTS | Inworld TTS 1.5 Max | #1 quality (ELO 1,217), WebSocket streaming, voice cloning | ₹187→₹71/mo |
| Voice persona | JARVIS-style British accent | Cloned from 5-15s audio sample via Inworld | Included |

### Latency Budget
| Step | Time |
|---|---|
| Wake word detection | 150ms |
| User speaks (avg) | 2,000ms |
| Whisper STT | 500ms |
| CRUZ processing + agent | 700ms |
| Inworld TTS (streaming start) | 250ms |
| **Total to first audio** | **~3.6s** |
| **Optimized (caching + parallel)** | **~3.1s** |

### Streaming Architecture

CRUZ streams token-by-token via SSE. TTS begins on the first sentence while Claude is still generating the second. This is how Alexa and Google Assistant achieve perceived sub-second latency despite multi-second processing.

```
Claude generating: "The deployment to production... [streaming]
                   ...completed successfully. Tests—"
                                   ↑
                     TTS starts here, before Claude finishes
```

### Two voice entry points

| Component | Use case | Stack |
|---|---|---|
| `workers/voice_daemon.py` (SP7) | Mac Mini's physical mic & speakers — always-on FRIDAY-style listener | OpenWakeWord/Porcupine → faster-whisper → POST /command → Inworld TTS → sounddevice |
| `workers/voice_agent/` | Web-client browsers in LiveKit rooms | LiveKit + Deepgram STT/TTS |

The voice daemon talks to CRUZ over plain HTTP (`POST /command`) so it survives the API process restarting. Conversation ID stays stable for the daemon's lifetime — every spoken turn shares context. SIGINT/SIGTERM trigger clean shutdown.

---

## Memory Architecture

**Without memory, CRUZ is a chatbot. With it, CRUZ is FRIDAY.**

| Layer | What it stores | Implementation | Available |
|---|---|---|---|
| **Working memory** | Current conversation turn | Claude context window (200k tokens) | Always |
| **Session memory** | Full conversation history | PostgreSQL: conversations + messages | Phase 1 |
| **Semantic memory** | Past work, decisions, solutions, retrieved by meaning | Qdrant + sentence-transformers/all-MiniLM-L6-v2 | Phase 3 |
| **Procedural memory** | Learned preferences, client styles, code patterns | PostgreSQL: user_preferences JSONB | Phase 4 |

### Context Strategy
- **Active context**: Last 50 messages from current conversation
- **Semantic retrieval**: Top 10 most relevant past exchanges via vector similarity
- **Context timeout**: 30 minutes inactivity → new conversation
- **Cross-device**: Conversation persists by `conversation_id` — pick up on any device

### Why 4 Layers (Production Pattern)

ChatGPT Projects, Claude Projects, and Cursor all implement multi-layer memory. Single-layer systems (just context window) lose everything between sessions. Vector-only systems lose structured recent history. Both are needed.

---

## Tech Stack

### Backend
| Component | Choice | Why (vs alternatives) |
|---|---|---|
| Language | Python 3.11+ | Best AI/ML ecosystem, async-native |
| Framework | FastAPI 0.110+ | Async, ASGI, streaming SSE native |
| Server | Uvicorn | ASGI, HTTP/2, WebSocket |
| ORM | SQLAlchemy 2.x | Async support, production standard |
| Migrations | **Alembic** | Versioned schema. Raw SQL doesn't scale past 3 devs or 5 schema changes |
| Task queue | **ARQ** (Python + Redis) | Async Python-native. BullMQ is Node.js — wrong runtime for a Python backend |
| Process manager | PM2 | 24/7 uptime, auto-restart, log rotation |

### Databases
| DB | Purpose | Self-hosted | Cost |
|---|---|---|---|
| PostgreSQL 16 | Conversations, tasks, logs, users, preferences | Homebrew | ₹0 |
| Redis 7 | Sessions, ARQ queue, pub/sub, cache | Homebrew | ₹0 |
| Qdrant (Docker) | Semantic memory, vector search | Docker + named volume | ₹0 |

### AI/ML
| Component | Choice | Agents |
|---|---|---|
| Cloud LLM | Claude Sonnet 4 | CRUZ, FORGE, SENTINEL, GENERAL |
| Local (code) | Qwen 2.5 Coder 14B (Ollama) | ECHO, REACH, PM, TITAN, MARK, QT |
| Local (general) | Llama 3.1 8B (Ollama) | RAW, PULSE |
| Research augment | Gemini Flash 2.5 (free) | REACH (discovery phase) |
| STT | Whisper Large v3 (local) | CATCH, voice input |
| TTS | Inworld TTS 1.5 Max | All voice output |
| Wake word | Porcupine 3.x | All devices |
| Embeddings | all-MiniLM-L6-v2 (local) | Qdrant vector generation |

### Model Fallback Chain
```
Primary (Claude API down?) → Best available Ollama model
Ollama model down?         → Queue task, retry in 60s
Inworld TTS down?          → macOS 'say' command (emergency)
Whisper fails?             → Deepgram nova-3 API
```

### Frontend (Phase 2)
React 18 + TypeScript 5, Vite 6, Tailwind CSS 4, Zustand, shadcn/ui, React Router 6, TanStack Query 5, Socket.io client

### Mobile (Phase 3)
- **Primary**: PWA via Vite PWA plugin (installable, offline, push notifications via FCM)
- **Full native**: React Native 0.73+ (iOS + Android)
- **Quick access**: Telegram Bot (@CRUZBot) — text commands from anywhere, no app needed

---

## Data Model

```sql
-- Every request gets a trace_id that links ALL logs
-- conversations.id → messages → agent_logs (via trace_id)

CREATE TABLE conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     INTEGER REFERENCES users(id),
    device      VARCHAR(50),          -- 'phone', 'ipad', 'thinkpad'
    title       TEXT,
    context     JSONB,                -- project context, active client
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE messages (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID REFERENCES conversations(id),
    role             VARCHAR(20) NOT NULL,  -- 'user' | 'assistant' | 'tool'
    content          TEXT NOT NULL,
    metadata         JSONB,                  -- token counts, model used
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE TABLE agent_logs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id     UUID NOT NULL,       -- links to originating request
    agent        VARCHAR(50) NOT NULL,
    action       VARCHAR(100) NOT NULL,
    status       VARCHAR(20),         -- 'success' | 'error' | 'pending'
    input_data   JSONB,
    output_data  JSONB,
    tokens_used  INTEGER,             -- track Claude API costs
    duration_ms  INTEGER,
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE tasks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id     UUID,
    agent        VARCHAR(50) NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT,
    status       VARCHAR(20) DEFAULT 'pending',
    priority     INTEGER DEFAULT 3,   -- 1=critical, 3=normal, 5=background
    metadata     JSONB,
    created_at   TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE TABLE users (
    id           SERIAL PRIMARY KEY,
    email        VARCHAR(255) UNIQUE NOT NULL,
    name         VARCHAR(255),
    preferences  JSONB,               -- learned patterns, client styles
    created_at   TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_agent_logs_trace ON agent_logs(trace_id);
CREATE INDEX idx_agent_logs_agent ON agent_logs(agent, created_at DESC);
CREATE INDEX idx_tasks_status ON tasks(status, priority);
```

---

## API Design

### Primary Endpoint
```
POST /command
{
  "message":         "Deploy the AMA website to production",
  "conversation_id": "uuid",     // omit to start new conversation
  "device":          "ipad",     // for context
  "stream":          true        // always true for voice; false for tests
}

Response (SSE stream):
data: {"type": "text", "content": "Checking latest build..."}
data: {"type": "text", "content": " Running QT tests first."}
data: {"type": "tool_call", "agent": "QT", "status": "running"}
data: {"type": "tool_result", "agent": "QT", "status": "12/12 pass"}
data: {"type": "approval_required", "action": "deploy_production", "preview": {...}}
data: {"type": "done", "conversation_id": "uuid", "trace_id": "uuid"}
```

### Supporting Endpoints
```
GET  /health                        — server + all dependency health
POST /conversations                 — start new conversation
GET  /conversations/:id/messages    — load history for device handoff
GET  /agents/status                 — each agent's health + last run
GET  /tasks?status=pending          — queued background tasks
GET  /logs/:trace_id                — full execution trace for debugging
POST /voice/transcribe              — audio → text (Whisper)
GET  /metrics                       — Prometheus-format metrics
```

---

## External Integrations

| Category | Service | Agent | Auth | Free limit |
|---|---|---|---|---|
| Email | Gmail API | ECHO, REACH | OAuth 2.0 | Unlimited send |
| Email delivery | SendGrid | ECHO, REACH | API key | 100/day |
| Calendar | Google Calendar API | PULSE, CATCH | OAuth 2.0 | Unlimited read |
| Code hosting | GitHub | All code agents | PAT | Unlimited private |
| PM | Plane.so | PM | API token | Unlimited personal |
| Knowledge | Notion | CATCH, MARK, ECHO, RAW, PULSE | API token | Unlimited pages |
| Leads | Apollo.io | REACH | API key | 50 credits/mo |
| Email verify | Hunter.io | REACH | API key | 50 searches/mo |
| AI research | Gemini Flash 2.5 | REACH | API key | 250 req/day |
| Deployment | Vercel API | TITAN | API token | Free tier |
| Deployment | Railway API | TITAN | API token | $5 credit/mo |
| VPS | Hostinger SSH | TITAN | SSH key | Existing |
| Chat | Slack API | SENTINEL, ECHO, PM | Bot token | Free tier |
| Mobile | Telegram Bot API | CRUD (all) | Bot token | Unlimited |
| DNS/CDN | Cloudflare | TITAN | API token | Free tier |
| Network | Tailscale | Infrastructure | Auth key | 100 devices |
| Backup | Google Drive | Infrastructure | OAuth 2.0 | 100GB/₹130mo |

---

## Observability

### Monitoring Stack

```
Uptime Kuma (port 3001)     → service health checks, Slack/Telegram alerts
Grafana Loki (port 3100)    → centralized logs from all agents + PM2
Grafana (port 3002)         → log visualization + dashboards
Sentry (free tier)          → error grouping, stack traces (Python + JS)
PostgreSQL views            → agent performance analytics
```

### Health Check Hierarchy
```
GET /health returns:
{
  "api": "healthy",
  "postgresql": "connected",
  "redis": "connected",
  "qdrant": "connected",
  "ollama": {
    "qwen2.5-coder:14b": "loaded",
    "llama3.1:8b": "loaded"
  },
  "claude_api": "reachable",
  "agents": {
    "forge": "ready",
    "echo": "ready",
    ...
  }
}
```

### Trace-Based Debugging
Every request generates a `trace_id`. Query the full chain:
```sql
SELECT agent, action, status, duration_ms, created_at
FROM agent_logs
WHERE trace_id = 'uuid'
ORDER BY created_at;
```

### Cost Monitoring
`agent_logs.tokens_used` tracks every Claude API call. Query daily:
```sql
SELECT agent, SUM(tokens_used), COUNT(*) FROM agent_logs
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY agent;
```

---

## Security

| Layer | Implementation |
|---|---|
| Secrets | Bitwarden (API keys, SSH keys, DB passwords) — nothing in Git |
| Disk | macOS FileVault (AES-XTS 256-bit) |
| Network | Tailscale mesh (WireGuard), Cloudflare DDoS |
| API auth | JWT (15min access token, 7-day refresh), Redis session store |
| Rate limiting | slowapi — 100 req/min per IP, 1000/hr per user |
| CORS | Locked to localhost:5173 (dev) + cruz.simpleinc.cloud (prod) |
| Code exec | FORGE-generated code runs in sandboxed subprocess with timeout |
| Prompt injection | Input sanitization before agent calls |
| Approval gates | All destructive/external actions require explicit confirmation |

---

## Cost Model

### Monthly Operating Costs

| Category | Service | Monthly |
|---|---|---|
| Infrastructure | Mac Mini power (35W × 24/7) | ₹202 |
| Infrastructure | UPS amortized (₹6k/36mo) | ₹167 |
| Infrastructure | Domain (simpleinc.cloud) | ₹42 |
| AI — Cloud | Claude Max (CRUZ, FORGE, SENTINEL unlimited) | ₹1,660 |
| AI — Cloud | Claude API (FORGE heavy tasks, SENTINEL) | ₹900 |
| AI — Cloud | Gemini Flash 2.5 (REACH discovery) | ₹0 |
| AI — Local | Qwen 14B + Llama 8B + Whisper (Ollama) | ₹0 |
| Voice | Inworld TTS 1.5 Max (300 min/mo) | ₹187 → ₹71 |
| Backup | Google Drive 100GB | ₹130 |
| Everything else | 35+ services on free tiers | ₹0 |
| **TOTAL** | | **₹3,288 → ₹3,172** |

### One-Time
- UPS: ₹6,000 | HDD: ₹3,000 | **Total: ₹9,000**

### ROI
- Time saved: 12 hrs/week = ₹60,000/mo value (at ₹1,250/hr)
- Additional client capacity: +₹25,000/mo revenue
- Tool cost savings vs SaaS alternatives: ₹5,000-8,000/mo
- **Net benefit: ~₹88,000/mo vs ₹3,200 cost**

### vs Production Alternatives
| Alternative | Monthly Cost | What you get |
|---|---|---|
| Virtual Assistant | ₹15,000-25,000 | Limited hours, basic tasks |
| SaaS Tool Stack | ₹8,000-12,000 | Zapier + Linear + Notion + others |
| GitHub Copilot + ChatGPT Team | ₹10,000+ | Code only, no agents |
| Managed AI Agency | ₹50,000-1,00,000 | Full service, no control |
| **CRUZ** | **₹3,288** | **12 agents, 24/7, cross-device, voice, full control** |

---

## Project Structure

```
cruz-ai-system/
│
├── backend/
│   ├── api/
│   │   └── main.py              # FastAPI app, all routes, SSE streaming
│   ├── models/
│   │   └── schema.sql           # Source of truth schema
│   └── migrations/              # Alembic versioned migrations
│       ├── env.py
│       └── versions/
│
├── agents/
│   ├── base_agent.py            # BaseAgent — mandatory parent for all agents
│   ├── cruz/
│   │   └── cruz_agent.py        # Main assistant — ONLY entry point
│   ├── relay/
│   │   └── relay_agent.py       # Keyword classifier (no LLM call)
│   ├── general/
│   │   └── general_agent.py     # Catch-all sub-agent
│   ├── forge/
│   ├── echo/
│   ├── reach/
│   ├── catch/
│   ├── pm/
│   ├── titan/
│   ├── mark/
│   ├── qt/
│   ├── sentinel/
│   ├── raw/
│   └── pulse/
│
├── services/                    # Shared infrastructure (singletons)
│   ├── db.py                    # PostgreSQL async connection pool
│   ├── redis.py                 # Redis async client
│   ├── qdrant.py                # Qdrant vector DB client
│   ├── ollama.py                # Ollama local model client
│   └── voice.py                 # Whisper STT + Inworld TTS pipeline
│
├── workers/                     # ARQ background task workers + always-on daemons
│   ├── arq_worker.py            # ARQ worker entrypoint
│   ├── voice_daemon.py          # Always-on local mic/speaker loop (SP7)
│   ├── voice_agent/             # LiveKit web-client bridge (separate from voice_daemon)
│   ├── handlers/                # SP5 handler modules (workers/handlers/<name>.py)
│   └── tasks/
│       ├── pulse_tasks.py       # 6 AM daily briefing
│       ├── raw_tasks.py         # 3 AM research update
│       ├── reach_tasks.py       # 2 AM lead generation
│       ├── mark_tasks.py        # Post-commit documentation
│       └── webhook_tasks.py     # GitHub/Vercel/GCal dispatch (SP5)
│
├── tests/
│   ├── agents/                  # One file per agent (written same day)
│   │   ├── test_cruz.py
│   │   ├── test_forge.py
│   │   └── ...
│   ├── api/
│   │   └── test_endpoints.py
│   └── conftest.py              # Shared fixtures, test DB setup
│
├── frontend/                    # React 18 + TypeScript dashboard
├── mobile/                      # React Native app
│
├── scripts/
│   ├── setup.sh                 # One-command dev setup
│   └── migrate.sh               # Run Alembic migrations
│
├── docs/
│   └── superpowers/specs/       # Design documents + implementation plans
│
├── ecosystem.config.js          # PM2 process config
├── docker-compose.yml           # Qdrant + optional Redis/PG
├── .env                         # Never committed
├── alembic.ini                  # Migration config
└── CLAUDE.md                    # This file
```

---

## Development Standards

### Python
- Formatter: Black (88 chars)
- Linter: Ruff
- Type hints: Required on all functions
- Docstrings: Required on all classes and public methods
- Async: All I/O must be `async/await` — zero blocking calls on event loop
- Structured output: Always use Claude `tool_use` — never prompt-based JSON parsing
- Tests: Written on the same day as the code, not retroactively

### Agent Contract
Every agent follows this exact I/O shape:

```python
@dataclass
class AgentInput:
    task: str
    context: dict[str, Any]
    trace_id: str
    conversation_id: str

@dataclass
class AgentOutput:
    success: bool
    result: Any
    agent: str
    duration_ms: int
    tokens_used: int | None = None
    error: str | None = None
    requires_approval: bool = False
    approval_prompt: str | None = None
```

### Commit Format
```
feat(forge): add React component generation with TypeScript support
fix(echo): handle Gmail API rate limit with exponential backoff
chore(db): add trace_id index to agent_logs

Types: feat | fix | refactor | test | docs | chore
Scopes: cruz | forge | echo | reach | catch | pm | titan |
        mark | qt | sentinel | raw | pulse | api | db | voice | mobile
```

---

## Running Locally

### Services Required
```bash
brew services start postgresql@16
brew services start redis
docker run -d -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant
# Ollama starts automatically
```

### Start CRUZ
```bash
source venv/bin/activate
python backend/api/main.py
# or for production:
pm2 start ecosystem.config.js
```

### Test CRUZ
```bash
# Health check
curl http://localhost:3000/health

# Talk to CRUZ
curl -X POST http://localhost:3000/command \
  -H "Content-Type: application/json" \
  -d '{"message": "What can you help me with?", "stream": false}'

# Run tests
pytest tests/ -v --cov=agents
```

---

## Environment Variables

```bash
# Database
DATABASE_URL=postgresql://cruz:password@localhost:5432/cruz_db
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333

# AI Services — Cloud
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
INWORLD_API_KEY=...

# AI Services — Local
OLLAMA_URL=http://localhost:11434

# Voice
PICOVOICE_ACCESS_KEY=...         # Porcupine wake word
INWORLD_VOICE_ID=...             # Your cloned JARVIS voice

# Integrations
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GOOGLE_CALENDAR_ID=...
GITHUB_TOKEN=...
NOTION_API_KEY=...
PLANEIO_API_KEY=...
APOLLO_API_KEY=...
HUNTER_API_KEY=...
SENDGRID_API_KEY=...
SLACK_BOT_TOKEN=...
TELEGRAM_BOT_TOKEN=...
VERCEL_TOKEN=...
RAILWAY_TOKEN=...

# CRUZ Config
CRUZ_CONFIDENCE_THRESHOLD=0.7    # below this → ask for clarification
CRUZ_MAX_LOOP_STEPS=10           # max agentic loop iterations
CRUZ_STREAM=true

# Security
JWT_SECRET=...
SESSION_SECRET=...
PORT=3000
ENVIRONMENT=development

# Monitoring
SENTRY_DSN=...                   # optional
```

---

## Key Engineering Decisions

| Decision | Choice | Rejected alternative | Why |
|---|---|---|---|
| Routing mechanism | Native Claude `tool_use` | Separate RELAY LLM call | 0 extra LLM calls, parallel execution, schema-validated |
| Task queue | ARQ (Python + Redis) | BullMQ (Node.js) | Same runtime as backend — no Node.js process to manage |
| Schema migrations | Alembic | Raw schema.sql | Versioned, reversible, team-scalable |
| Streaming | SSE from day 1 | Blocking JSON response | Voice requires it; perceived latency 3s→<300ms |
| Agent base class | Mandatory for all agents | Per-agent patterns | Consistent logging, trace propagation, error handling |
| Human gates | Before all irreversible actions | Auto-execute | Deploy/send/delete cannot be undone |
| Local models | Ollama (Qwen + Llama) | All cloud | ~₹15,000/mo savings; offline capability |
| Context strategy | Last 50 msgs + top 10 vector | Full history OR no history | Balance between token cost and recall |
| Mobile | PWA primary + React Native | Web only | Phone on train = primary use case |
| Process manager | PM2 | Docker Compose for services | Simple single-machine setup; 24/7 auto-restart |
| Voice quality | Inworld TTS 1.5 Max | ElevenLabs, Google TTS | #1 ELO score, WebSocket streaming, voice cloning |

---

**Developer:** Darshan Parmar
**Start Date:** April 12, 2026
**Target MVP:** April 26, 2026 (2 weeks)
**Target Production:** May 24, 2026 (6 weeks)
**Monthly Cost:** ₹3,288 → ₹3,172 from Month 3
**Primary Stack:** Python 3.11 + FastAPI + Claude Sonnet 4 + Ollama + PostgreSQL + Redis
