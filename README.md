# CRUZ AI System

> **FRIDAY from Iron Man — built for a freelance developer.**
> You talk to CRUZ. CRUZ handles everything else.

CRUZ is a personal AI command center running 24/7 on a Mac Mini M4. One natural-language interface routes to 12 specialist agents — code generation, email drafting, deployments, lead generation, meeting transcription, sprint planning, and more.

---

## What CRUZ Does

```
You: "Hey CRUZ, the AMA site is broken in prod"

CRUZ: Checking recent commits...
      SENTINEL found a null check failure on api/orders.js:84.
      FORGE patched it. QT: 12/12 tests passing.
      Ready to deploy. Confirm?

You: Yes

CRUZ: Deployed to prod. Client notified.
```

One command. Multiple agents working in parallel. Human approval before anything irreversible.

---

## Architecture

```
POST /command
      │
      ▼
 CruzAgent (Claude Sonnet 4 + native tool_use)
      │
      ├── forge   → Code generation, bug fixes, refactoring
      ├── echo    → Email drafts, Slack messages (approval required to send)
      ├── reach   → Lead research + personalized outreach
      ├── catch   → Meeting transcription + action items
      ├── pm      → Sprint planning, Linear task creation
      ├── titan   → Deployments (approval gate, auto-rollback)
      ├── mark    → API docs, README, changelogs
      ├── qt      → Tests, Playwright, Lighthouse (gates TITAN)
      ├── sentinel→ PR code review, OWASP security audit
      ├── raw     → Tech research, dependency updates
      └── pulse   → 6 AM daily briefing
```

No separate routing LLM call. Claude's native `tool_use` IS the router — zero overhead, parallel execution, schema-validated.

---

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI 0.110 + Uvicorn (ASGI, SSE streaming) |
| Cloud LLM | Claude Sonnet 4 (CRUZ, FORGE, SENTINEL) |
| Local LLM | Qwen 2.5 Coder 14B + Llama 3.1 8B via Ollama |
| Database | PostgreSQL 16 (conversations, logs, tasks) |
| Cache/Queue | Redis 7 + ARQ (background workers) |
| Vector DB | Qdrant (semantic memory, all-MiniLM-L6-v2) |
| Migrations | Alembic |
| Voice STT | Whisper Large v3 (local) |
| Voice TTS | Inworld TTS 1.5 Max (streaming) |
| Wake word | Porcupine 3.x ("Hey CRUZ") |
| Frontend | React 18 + TypeScript + Tailwind (Phase 5) |
| Mobile | React Native + PWA (Phase 5) |
| Process mgr | PM2 (Phase 6) |

---

## Project Structure

```
cruz-ai-system/
├── agents/
│   ├── base_agent.py          # Mandatory parent for all agents
│   ├── cruz/cruz_agent.py     # Main assistant — only entry point
│   ├── relay/relay_agent.py   # Keyword classifier (no LLM)
│   ├── general/               # Catch-all sub-agent
│   ├── forge/                 # Code generation
│   ├── echo/                  # Email + messaging
│   ├── reach/                 # Lead generation (Phase 3)
│   ├── catch/                 # Meeting transcription (Phase 3)
│   └── pm/                    # Sprint planning (Phase 3)
├── backend/api/main.py        # FastAPI app + all routes
├── services/
│   ├── db.py                  # PostgreSQL async pool
│   ├── redis_client.py        # Redis singleton
│   ├── ollama.py              # Ollama local model client
│   ├── conversation.py        # Conversation persistence
│   ├── qdrant.py              # Vector DB client
│   ├── embedding.py           # all-MiniLM-L6-v2 embeddings
│   └── semantic_memory.py     # Semantic memory (store + search)
├── migrations/                # Alembic versioned migrations
├── tests/                     # 366 tests — agents, api, services
├── docs/superpowers/specs/    # Design documents
├── CLAUDE.md                  # Full project bible
└── PROGRESS.md                # Build progress tracker
```

---

## API

### Talk to CRUZ
```bash
POST /command
{
  "command": "Build a contact form for AMA Solutions",
  "conversation_id": "uuid",   # omit to start new conversation
  "stream": true               # SSE stream or JSON response
}
```

### SSE Stream events
```
data: {"type": "text",              "content": "Working on it..."}
data: {"type": "approval_required", "approval_prompt": "Deploy to prod?"}
data: {"type": "done",              "trace_id": "uuid", "tokens_used": 450}
```

### Other endpoints
```
GET  /health                         — all dependency health (always 200)
GET  /conversations/:id/messages     — load history for cross-device handoff
GET  /logs/:trace_id                 — full execution trace for debugging
```

---

## Memory Architecture

| Layer | Storage | Scope |
|---|---|---|
| Working | Claude context window (200k tokens) | Current turn |
| Session | PostgreSQL: messages table (last 50) | Conversation |
| Semantic | Qdrant: vector similarity search (top 10) | All time |
| Procedural | PostgreSQL: user_preferences JSONB | All time (Phase 4) |

---

## Running Locally

### Prerequisites
```bash
brew install postgresql@16 redis
brew services start postgresql@16
brew services start redis
docker run -d -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant
# Install Ollama from ollama.ai, then:
ollama pull qwen2.5-coder:14b
ollama pull llama3.1:8b
```

### Setup
```bash
git clone https://github.com/drprockz/cruz-ai-system.git
cd cruz-ai-system
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
alembic upgrade head
```

### Start
```bash
source venv/bin/activate
python backend/api/main.py
```

### Test
```bash
# Health check
curl http://localhost:3000/health

# Talk to CRUZ
curl -X POST http://localhost:3000/command \
  -H "Content-Type: application/json" \
  -d '{"command": "What can you help me with?", "stream": false}'

# Run test suite
pytest tests/ -v
```

---

## Environment Variables

```bash
# Copy and fill in:
cp .env.example .env
```

Key variables:
```
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql://cruz:password@localhost:5432/cruz_db
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333
OLLAMA_URL=http://localhost:11434
PORT=3000
```

See `.env.example` for the full list.

---

## Build Progress

See [PROGRESS.md](PROGRESS.md) for detailed task tracking.

| Phase | Status | Description |
|---|---|---|
| 1 — Foundation | ✅ Done | BaseAgent, DB, CRUZ, POST /command, SSE, memory |
| 2 — Core Agents | ⚠️ Partial | FORGE + ECHO shells done; voice pipeline pending |
| 3 — Automation | ⚠️ Partial | Semantic memory done; REACH/CATCH/PM/ARQ pending |
| 4 — DevOps | ❌ Not started | QT, SENTINEL, TITAN, MARK |
| 5 — Intelligence | ❌ Not started | RAW, PULSE, cross-device, React Native |
| 6 — Production | ❌ Not started | PM2, monitoring, Cloudflare, load testing |

**366 tests passing.**

---

## Cost

| Category | Monthly |
|---|---|
| Mac Mini power (35W 24/7) | ₹202 |
| Claude API | ₹900 |
| Inworld TTS | ₹187 |
| Google Drive backup | ₹130 |
| Everything else | ₹0 (free tiers) |
| **Total** | **~₹3,300** |

vs ₹15,000+/month for a virtual assistant doing a fraction of this.

---

**Developer:** Darshan Parmar
**Target MVP:** April 26, 2026
**Target Production:** May 24, 2026
