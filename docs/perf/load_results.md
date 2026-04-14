# Load Test Results — Phase 6.6

**Stack under test:** PM2-managed API (`backend/api/main.py`) + ARQ worker + Qdrant (Docker) + Postgres + Redis, running on Mac Mini M4 (24GB).

**Driver:** Locust 2.x — `scripts/load/locustfile.py`, launched via `scripts/load/run_scenarios.sh`.

> ⚠️ This file is a template. Populate the rows below after running each scenario against the live PM2 stack. Raw CSV/HTML outputs land in `scripts/load/results/` (gitignored).

## SLOs

| Scenario | Target p95 | Target error rate | Notes |
|---|---|---|---|
| Morning rush | ≤ 1500ms | < 1% | Warm context, short prompts |
| Agent mix (50 RPS) | ≤ 2500ms | < 2% | Mixed local+Claude agents |
| SSE streaming | First byte ≤ 600ms | < 1% | Voice path gate |
| Overnight cron | N/A (throughput) | 0 job drops | ARQ completes inside window |

## Run log

### Scenario 1 — Morning rush
- Command: `LOCUST_SCENARIO=morning_rush locust ... --users 20 --spawn-rate 20 --run-time 60s`
- Date: _TBD_
- p50 / p95 / p99: _TBD_ / _TBD_ / _TBD_ ms
- Error rate: _TBD_
- Pass SLO? _TBD_

### Scenario 2 — Agent mix
- Command: `... --users 50 --spawn-rate 10 --run-time 2m`
- Date: _TBD_
- p50 / p95 / p99: _TBD_
- Error rate: _TBD_
- Pass SLO? _TBD_

### Scenario 3 — SSE streaming
- Command: `... --users 10 --spawn-rate 10 --run-time 90s`
- Date: _TBD_
- First-byte p50 / p95: _TBD_
- Stream completion rate: _TBD_
- Pass SLO? _TBD_

### Scenario 4 — Overnight cron
- Command: `... --users 3 --spawn-rate 1 --run-time 3m`
- Date: _TBD_
- PULSE / RAW / REACH durations: _TBD_
- ARQ queue depth max: _TBD_
- Pass SLO? _TBD_

## Reproduction

```bash
# Terminal 1 — full PM2 stack
pm2 start ecosystem.config.js

# Terminal 2 — run one or all scenarios
cd scripts/load
HOST=http://localhost:3000 ./run_scenarios.sh all
```

Results land in `scripts/load/results/<scenario>_<timestamp>.{csv,html}`.
