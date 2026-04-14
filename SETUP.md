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

### Qdrant (Docker — preferred)
```bash
# Start Docker Desktop first, then:
docker compose up -d qdrant

# Verify:
docker compose ps                        # should list cruz-qdrant as healthy
curl http://localhost:6333/healthz       # should return {"title":"qdrant"}
```

Raw equivalent (if you don't want Docker Compose):
```bash
docker run -d --name cruz-qdrant --restart unless-stopped \
  -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant
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

### Production (recommended — 24/7 auto-restart via PM2)

```bash
# Install PM2 once (requires Node.js):
npm install -g pm2

# Start CRUZ API + ARQ worker:
pm2 start ecosystem.config.js
pm2 status                         # should show cruz-api and cruz-worker online
pm2 logs                           # tail combined logs

# Persist across reboots (follow the command pm2 prints):
pm2 save
pm2 startup
```

### Development (foreground)

```bash
source venv/bin/activate
python backend/api/main.py
```

You should see:
```
🚀 CRUZ AI System starting on port 3000
INFO:     Uvicorn running on http://0.0.0.0:3000
```

> **Startup validation (R3):** If any of `ANTHROPIC_API_KEY`, `DATABASE_URL`,
> `REDIS_URL`, or `QDRANT_URL` are missing/empty in `.env`, CRUZ refuses to
> start and prints exactly which variables to fix. No silent failures.

---

## Step 8 — Test it

```bash
# Full health check — reports status per service + required Ollama models
curl http://localhost:3000/health | python3 -m json.tool
```

The health payload now includes `ollama.required`, `ollama.missing`, and
overall `status` downgrades to `"degraded"` when any required model is missing.
That is how you know to run `ollama pull`.

```bash
# Talk to CRUZ
curl -X POST http://localhost:3000/command \
  -H "Content-Type: application/json" \
  -d '{"command": "What can you help me with?", "device": "mac_mini", "stream": false}'

# Run the mock-based test suite (no services needed)
source venv/bin/activate
pytest tests/ -v
```

Expected: `814 passed, 9 skipped`

### Real-DB integration tests (opt-in)

The 9 skipped tests verify migrations apply cleanly and SQL round-trips
against real PostgreSQL. Opt in by pointing at a throwaway DB:

```bash
# Create throwaway DB (one-time):
psql postgres -c "CREATE DATABASE cruz_test_db OWNER drprockz;"

# Run real-DB integration tests:
export DATABASE_URL_TEST="postgresql://drprockz@localhost:5432/cruz_test_db"
pytest tests/integration/test_real_db.py -v
```

Expected: `9 passed`. These tests drop+recreate the schema on each run.

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

---

## Backup automation (Phase 6.5)

CRUZ runs a **daily 04:00 backup** via the ARQ worker (see `workers/tasks/backup_tasks.py`).
It snapshots Postgres (pg_dump -Fc), Redis (RDB), and Qdrant (tar.gz of
`qdrant_storage/`), then uploads each file to Google Drive.

Required env vars (in `.env`):

```bash
# Folder inside your Drive where snapshots land
GOOGLE_DRIVE_FOLDER_ID=0AxxxxxxxxxxxxxxxxxX

# Path to a Google service-account JSON key with drive.file scope
GOOGLE_APPLICATION_CREDENTIALS=/Users/drprockz/.config/cruz/drive-sa.json

# Optional — defaults are sensible
QDRANT_STORAGE_DIR=./qdrant_storage
```

**Create the service account:**
1. Google Cloud Console → IAM → Service Accounts → Create
2. Grant it no project roles (we only need Drive scope).
3. Keys → Add key → JSON → save to the path in `GOOGLE_APPLICATION_CREDENTIALS`.
4. In Drive, share the destination folder with the service account's email
   (Editor permission).

**Test a one-off run:**
```bash
source venv/bin/activate
python -c "import asyncio; from workers.tasks.backup_tasks import run_backup; \
           print(asyncio.run(run_backup({})))"
```

**Verify cron is registered:**
```bash
arq workers.arq_worker.WorkerSettings --check
```

Partial failures are tolerated — if (e.g.) redis-cli is unavailable, the
other two snapshots still upload and the failure is logged.
