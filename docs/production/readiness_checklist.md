# CRUZ Production Readiness Checklist

Gate every item before flipping `ENVIRONMENT=production`. Each row lists a
manual check and, where feasible, a programmatic verifier you can run from
the repo root.

## Runtime prerequisites

- [ ] **Ollama models pulled and reported healthy**
  ```bash
  ollama list | grep -E 'qwen2.5-coder:14b|llama3.1:8b'
  curl -s http://localhost:3000/health | jq '.ollama'
  # Expect: .missing == [] and .required contains both models
  ```

- [ ] **All env vars set (cross-reference `.env.example`)**
  ```bash
  python - <<'PY'
  from dotenv import dotenv_values
  need = set(dotenv_values('.env.example'))
  have = set(dotenv_values('.env'))
  missing = sorted(need - have)
  print('MISSING:', missing or 'none')
  raise SystemExit(1 if missing else 0)
  PY
  ```

- [ ] **PM2 saved + startup registered**
  ```bash
  pm2 jlist | jq '.[].name'          # expect cruz-api, cruz-worker
  pm2 save
  pm2 startup                        # run the printed sudo command once
  ```

- [ ] **Qdrant container up**
  ```bash
  docker compose up -d qdrant
  curl -s http://localhost:6333/readyz
  ```

- [ ] **Real-DB integration tests green**
  ```bash
  DATABASE_URL_TEST=postgresql+asyncpg://cruz:cruz@localhost:5432/cruz_test \
    pytest tests/integration/ -v
  ```

## External surface

- [ ] **Cloudflare tunnel alive at `https://cruz.simpleinc.cloud`**
  ```bash
  curl -sS https://cruz.simpleinc.cloud/health | jq '.status'
  ```

- [ ] **`/health` reachable from outside LAN**
  ```bash
  curl -sS --resolve cruz.simpleinc.cloud:443:<public-ip> \
    https://cruz.simpleinc.cloud/health
  ```

## Data protection

- [ ] **Latest backup visible in Google Drive** — at least one of
      `pg_dump_*.sql.gz`, `redis_dump_*.rdb.gz`, `qdrant_snapshot_*.tar.gz`
      dated within the last 24h.
  ```bash
  # If gdrive CLI configured:
  gdrive list --query "name contains 'cruz_backup'" | head
  ```

## Monitoring

- [ ] **Uptime Kuma watches all 5 services** — API, Qdrant, Redis, Postgres,
      Ollama. Each monitor shows a green square for the last hour.
- [ ] **Telegram alert fires on a simulated outage**
  ```bash
  pm2 stop cruz-api   # wait 90s, confirm Telegram DM, then:
  pm2 start cruz-api
  ```

## Performance

- [ ] **Load scenarios 1–4 all pass their SLOs** — see
      `docs/perf/load_results.md` for targets and commands.
  ```bash
  ./scripts/load/run_scenarios.sh all
  ```

- [ ] **72h uptime test ≥ 99% green** — see `docs/perf/uptime_test.md`.
  ```bash
  python scripts/uptime/check_stability.py --summary \
    --output logs/uptime/stability.jsonl
  # Expect pct_ok ≥ 99
  ```

## Sign-off

Record the final pass with the commit hash and date at the bottom of
`PROGRESS.md` under "Phase 6 — Production Hardening" once every box above
is checked.
