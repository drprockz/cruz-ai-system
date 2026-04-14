# CRUZ Performance Baseline

**Baseline captured:** _not yet measured_
**Target environment:** Mac Mini M4 (24GB RAM, 10-core), PM2-managed API + PG 16 + Redis 7 + Qdrant (Docker).

This file holds the first-measured performance numbers for CRUZ. Re-run the benchmarks
after any change that could affect latency (new agent, schema change, model swap, infra
change) and append a new section — do **not** overwrite existing rows.

## How to populate

```bash
# 1. Start the stack
brew services start postgresql@16
brew services start redis
docker compose up -d qdrant
pm2 start ecosystem.config.js   # or: python backend/api/main.py

# 2. Wait for /health to return green, then:
source venv/bin/activate
python -m scripts.perf.bench_command   --n 100
python -m scripts.perf.bench_db        --n 100
python -m scripts.perf.bench_concurrent --concurrency 10
```

Paste the stdout of each run into the section below, with the date + git SHA.

## Targets (from CLAUDE.md)

| Metric | Target |
|---|---|
| `/command` plain chat P95 | < 1500 ms |
| `/command` RELAY-narrowed P95 | < 1200 ms |
| SSE first byte | < 500 ms |
| DB hot-query P95 | < 25 ms |
| 10 concurrent `/command` | 0 errors |

## Baseline run — _pending_

_Run the commands above and paste results here._

```
path                  n     p50(ms)   p95(ms)   p99(ms)
------------------------------------------------------------
plain_chat            ...
relay_forge           ...
relay_titan           ...
sse_stream            ...

query                       n     p50(ms)   p95(ms)   p99(ms)
----------------------------------------------------------------
load_history              ...
agent_log_insert          ...
logs_by_trace_id          ...

concurrency=10  ok=10  errors=0  min=...  max=...
```
