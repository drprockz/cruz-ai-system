# CRUZ AI System — Setup Guide

Complete setup from a fresh clone to a running CRUZ instance.

---

## Prerequisites

You need these installed before starting:

| Tool | Install | Version |
|---|---|---|
| Python | [python.org](https://python.org) or `brew install python` | 3.11+ |
| PostgreSQL | `brew install postgresql@16` | 16+ |
| Redis | `brew install redis` | 7+ |
| Docker | [docker.com](https://docker.com) | Any recent |
| Ollama | [ollama.ai](https://ollama.ai) | Any recent |

---

## Step 1 — Clone and enter the repo

```bash
git clone https://github.com/drprockz/cruz-ai-system.git
cd cruz-ai-system
```

---

## Step 2 — Create virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate          # macOS/Linux
# venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

This installs everything: FastAPI, Anthropic SDK, asyncpg, Qdrant client, sentence-transformers, Alembic, pytest, and all other dependencies.

> **Note:** `sentence-transformers` downloads the `all-MiniLM-L6-v2` model (~80MB) on first run. This is automatic.

---

## Step 3 — Environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:

### Required to start (minimum)
```
DATABASE_URL=postgresql://cruz:your_password@localhost:5432/cruz_db
REDIS_URL=redis://localhost:6379
ANTHROPIC_API_KEY=sk-ant-...        # get from console.anthropic.com
PORT=3000
```

### Required for full functionality
```
QDRANT_URL=http://localhost:6333
OLLAMA_URL=http://localhost:11434
GEMINI_API_KEY=...                  # free at aistudio.google.com
```

### Generate secure secrets
```bash
openssl rand -hex 32   # run twice — once for JWT_SECRET, once for SESSION_SECRET
```

All other keys (Gmail, Notion, Slack, etc.) are for Phase 2+ agents. CRUZ will work without them — those agents just won't have real integrations yet.

---

## Step 4 — Start infrastructure services

### PostgreSQL
```bash
brew services start postgresql@16

# Create the database and user
psql postgres -c "CREATE USER cruz WITH PASSWORD 'your_password';"
psql postgres -c "CREATE DATABASE cruz_db OWNER cruz;"
```

### Redis
```bash
brew services start redis
```

### Qdrant (Docker)
```bash
docker run -d \
  --name qdrant \
  --restart unless-stopped \
  -p 6333:6333 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant
```

### Ollama + models
```bash
# Ollama starts automatically after install
# Pull the models CRUZ uses for local agents:
ollama pull qwen2.5-coder:14b    # ECHO, PM, TITAN, MARK, QT (~9GB)
ollama pull llama3.1:8b          # RAW, PULSE (~5GB)

# Optional — smaller model for testing:
ollama pull qwen2.5-coder:7b
```

---

## Step 5 — Run database migrations

```bash
source venv/bin/activate
alembic upgrade head
```

This creates all tables: `conversations`, `messages`, `agent_logs`, `tasks`, `users` plus all indexes.

---

## Step 6 — Verify setup

```bash
# Check all services are reachable
curl http://localhost:5432    # should refuse connection (postgres listening)
redis-cli ping               # should return PONG
curl http://localhost:6333/healthz   # should return {"title":"qdrant"}
curl http://localhost:11434/api/tags # should list your Ollama models
```

---

## Step 7 — Start CRUZ

```bash
source venv/bin/activate
python backend/api/main.py
```

You should see:
```
🚀 CRUZ AI System starting on port 3000
INFO:     Uvicorn running on http://0.0.0.0:3000
```

---

## Step 8 — Test it

```bash
# Full health check (all services)
curl http://localhost:3000/health | python3 -m json.tool

# Talk to CRUZ
curl -X POST http://localhost:3000/command \
  -H "Content-Type: application/json" \
  -d '{"command": "What can you help me with?", "stream": false}'

# Run the test suite
source venv/bin/activate
pytest tests/ -v
```

Expected: `366 passed`

---

## Common Issues

### `psycopg2` connection error
Make sure PostgreSQL is running and `DATABASE_URL` matches the user/password/db you created:
```bash
brew services list | grep postgresql
psql postgresql://cruz:your_password@localhost:5432/cruz_db -c "SELECT 1;"
```

### `sentence-transformers` slow on first run
It downloads `all-MiniLM-L6-v2` (~80MB) once and caches it. Subsequent starts are instant.

### Qdrant collection not found
CRUZ creates the `cruz_memories` collection automatically on first semantic memory write. No manual setup needed.

### Ollama model not loaded
```bash
ollama list              # check what's available
ollama pull qwen2.5-coder:14b   # re-pull if missing
```

### `alembic upgrade head` fails
Check your `DATABASE_URL` in `.env` matches the PostgreSQL user/db you created. Also ensure `alembic.ini` points to the correct migrations folder (it does by default).

---

## Running Tests Only (no services needed)

All tests mock external services. You can run the full suite without PostgreSQL, Redis, Qdrant, or Ollama running:

```bash
source venv/bin/activate
pytest tests/ -v
```

---

## Project Layout (quick reference)

```
cruz-ai-system/
├── backend/api/main.py      # Start here — FastAPI app
├── agents/cruz/cruz_agent.py # Main CRUZ orchestrator
├── agents/base_agent.py     # Extend this for every new agent
├── services/                # DB, Redis, Qdrant, Ollama singletons
├── migrations/              # Alembic schema versions
├── tests/                   # 366 tests — run with pytest
├── .env                     # Your secrets (never commit this)
├── .env.example             # Template — copy to .env
├── requirements.txt         # All Python dependencies
├── CLAUDE.md                # Full project bible + architecture
└── PROGRESS.md              # Phase tracking (what's done / what's next)
```

---

## Updating from remote

```bash
git pull origin main
source venv/bin/activate
pip install -r requirements.txt   # pick up any new dependencies
alembic upgrade head              # apply any new migrations
pytest tests/ -v                  # verify nothing broke
```

---

## Environment-specific notes

### Running on a different machine (not Mac Mini)
- Replace `brew services start` with your OS equivalent
- PostgreSQL on Linux: `sudo systemctl start postgresql`
- Redis on Linux: `sudo systemctl start redis`
- Qdrant Docker command is the same on all platforms

### Cross-device access via Tailscale
```bash
# Install Tailscale, authenticate, then access CRUZ from any device:
http://100.x.x.x:3000/health
```

### Public access via Cloudflare Tunnel (Phase 6)
```bash
cloudflared tunnel run --url http://localhost:3000 cruz
# CRUZ available at https://cruz.simpleinc.cloud
```
