# SP1 — Finish Operational Deployment

**Date:** 2026-04-20
**Status:** Draft for user review
**Sub-project of:** CRUZ v2 Program Charter (`docs/superpowers/specs/2026-04-20-v2-program-charter.md`)
**Inherits:** All charter Section 3 rules. Exit gate from charter Section 5.1. Cut-triggers from charter Section 6.
**Depends on:** Nothing (SP1 is the foundation sub-project).
**Enables:** SP2 (Knowledge Base) starts after SP1 exit gate passes.

---

## 1. Goal and scope

**Goal.** Take all the code and config already built in v1 — PM2 ecosystem, Cloudflare Tunnel code, monitoring stack, backup tasks, 72h probe harness, load scenarios — and make it actually run as a 24/7 production system on this Mac, reachable from phone over cellular, with alerts firing and backups landing in Google Drive.

### In scope

- Configure and start every external dependency the code already expects:
  - Cloudflare Tunnel live at `cruz.simpleinc.cloud`
  - Telegram bot authenticated and receiving alerts
  - Google Drive backup target accepting service-account uploads
- Verify every readiness-checklist item (12 gates in `docs/production/readiness_checklist.md`).
- Run the 72-hour uptime probe with ≥99% green.
- Induce one deliberate failure and confirm Telegram alert fires.
- Confirm PWA voice-command path works end-to-end from phone over cellular.

### Out of scope

- **No new code.** Any bug revealed during install that's beyond config becomes a P0 ticket; SP1 pauses until the fix lands via normal dev flow. Writing that fix is not itself SP1 work.
- Voice daemon (wake-word always-on loop). Deferred to SP7.
- Sentry DSN configuration. Code supports Sentry optionally; DSN stays blank in SP1. User can flip it on later in ~30 min without a spec change.
- React Native app. Deferred to SP7 or cut per charter Section 6 row 4.
- Any new agent, new layer, or new capability.

### Success = charter SP1 exit gate holds (verbatim)

> 72 hours continuous uptime with `/health` green; voice command from phone over cellular produces a streamed response end-to-end; one successful automated backup; Telegram alert fires on a deliberately induced failure.

### Physical target confirmed

The production Mac is the same Mac where v1 development has happened. No physical migration. SP1 is "turn dev into prod" — flip the environment, persist services across reboot, validate external reach.

---

## 2. Work breakdown

Two kinds of work: **active** (install, configure, validate) and **passive** (wait on the 72h probe). Active ≈ 3 days. Passive consumes wall-clock but no attention. Total wall-clock ≈ 6 days.

### Day 1 — Local prod-readiness

| Task | Command / artifact | Done when |
|---|---|---|
| Pull Ollama models (start first — long download) | `ollama pull qwen2.5-coder:14b && ollama pull llama3.1:8b` | ~25GB on disk; `ollama list` shows both |
| Audit `.env` against `.env.example` | Python one-liner from readiness checklist | `MISSING: none` |
| Start full stack via existing launcher | `./scripts/start-cruz.sh` | `pm2 status` shows all 5 apps `online` |
| Register PM2 with launchd | `pm2 save && pm2 startup` (run printed sudo command once) | PM2 processes survive a test reboot (`sudo reboot now` + verify auto-start) |
| Qdrant container up | `docker compose up -d qdrant` | `curl localhost:6333/readyz` returns ready |
| Local `/health` all-green | `curl -s localhost:3000/health \| jq` | `.ollama.missing == []`, every service reports connected |
| Real-DB integration tests pass | `DATABASE_URL_TEST=postgresql+asyncpg://cruz:cruz@localhost:5432/cruz_test pytest tests/integration/ -v` | All green |

### Day 2 — External services (three parallelizable tracks)

**Track A — Cloudflare Tunnel.**

1. Install cloudflared: `brew install cloudflared`
2. Authenticate: `cloudflared tunnel login` (opens browser)
3. Create tunnel: `cloudflared tunnel create cruz` — save the UUID
4. Route DNS: `cloudflared tunnel route dns cruz cruz.simpleinc.cloud`
5. Fill `cloudflared/config.yml` with the tunnel UUID + ingress rules (template exists per Session C)
6. Validate config: `cloudflared tunnel ingress validate`
7. Smoke-test in foreground first: `cloudflared tunnel run cruz` → `curl https://cruz.simpleinc.cloud/health` from a different network
8. Install as service: `sudo cloudflared service install`
9. Verify service running: `launchctl list | grep cloudflared`

**Done when** `curl https://cruz.simpleinc.cloud/health` returns green from cellular (phone off WiFi).

**Track B — Telegram bot.**

1. Message `@BotFather` on Telegram → `/newbot` → save the token
2. Start a chat with your new bot, send any message
3. Fetch `chat_id`: `curl https://api.telegram.org/bot<TOKEN>/getUpdates` → pick `result[0].message.chat.id`
4. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
5. Reload env: `pm2 reload ecosystem.config.js --update-env`
6. Send manual test alert from a Python REPL or via `services/alerts.py`

**Done when** a test alert DM arrives on your phone within 10 seconds.

**Track C — Google Drive backup.**

1. Create (or reuse) GCP project
2. Enable Drive API in the project console
3. Create a service account → download JSON key to `~/.config/cruz/gdrive-sa.json` (or equivalent path outside the repo)
4. Create a Drive folder (e.g., "CRUZ Backups"); copy its folder ID from the URL
5. Share the folder with the service account's email as **Editor** (not Viewer)
6. Set `GDRIVE_SERVICE_ACCOUNT_JSON` (path to JSON) and `GDRIVE_FOLDER_ID` in `.env`
7. Reload env: `pm2 reload ecosystem.config.js --update-env`
8. Trigger a manual backup (confirm exact invocation during SP1 — likely via `arq` enqueue or `python -m workers.tasks.backup_tasks`)

**Done when** a file matching `pg_dump_*.sql.gz`, `redis_dump_*.rdb.gz`, or `qdrant_snapshot_*.tar.gz` appears in the Drive folder within 5 minutes.

### Day 3 — Monitoring, perf, voice validation

| Task | Done when |
|---|---|
| Start monitoring stack | `docker compose --profile monitoring up -d`; Uptime Kuma at `localhost:3001`, Grafana at `localhost:3002` |
| Configure Uptime Kuma monitors | 5 monitors (API, Qdrant, Redis, Postgres, Ollama) all green for last hour; API monitor interval = 30s |
| Induced outage + confirm alert | `pm2 stop cruz-api`; Telegram DM arrives within 120s; `pm2 start cruz-api` restores service |
| Load scenarios pass SLOs | `./scripts/load/run_scenarios.sh all`; all 4 scenarios pass per `docs/perf/load_results.md` |
| **Voice-over-cellular validation** | Open `https://cruz.simpleinc.cloud` on phone with WiFi off; tap mic in PWA; speak a command; receive a streamed response |

### Day 3 evening — Start 72h probe

1. Copy the launchd plist template from `docs/perf/uptime_test.md` to `~/Library/LaunchAgents/com.cruz.uptime.plist`
2. Activate: `launchctl load ~/Library/LaunchAgents/com.cruz.uptime.plist`
3. Verify running: `launchctl list | grep com.cruz.uptime`
4. Before sleeping for the night: `sudo pmset -a disablesleep 1` (or wrap probe in `caffeinate -d -i -s`); record original pmset state to revert after SP1
5. Note start timestamp in a scratch file

### Days 4–6 — Passive wait + daily spot-check

- 2-minute daily check: `/health` still green, Kuma still green, no angry Telegram DMs
- **Do not** restart services, push code, or touch `.env` during the probe
- Target = ≥99% pct_ok; tolerate ≤8 failed probes out of 864 (72h × 12/hr at 5-min cadence)
- Automated daily backup should run at cron(hour=4); confirm ≥2 backup files in Drive by Day 6

### Day 6 — Collect + sign off

1. `python scripts/uptime/check_stability.py --summary --output logs/uptime/stability.jsonl` → confirm `pct_ok ≥ 99.0`
2. Append result row to `docs/perf/load_results.md` uptime section
3. Append sign-off line to `PROGRESS.md` Phase 6 (format in Section 3)
4. Revert `pmset` if changed
5. SP1 exit gate closed → SP2 brainstorming can start

---

## 3. Exit gate verification

Each gate criterion from charter Section 5.1 maps to a concrete check and an artifact.

| Gate criterion | Verification | Artifact |
|---|---|---|
| 72h continuous uptime with `/health` green | `scripts/uptime/check_stability.py --summary` over 72h reports `pct_ok ≥ 99.0` (≤8 failed probes out of 864) | `logs/uptime/stability.jsonl` + summary appended to `docs/perf/load_results.md` |
| Voice command from phone over cellular produces streamed response | Phone with WiFi off → open `https://cruz.simpleinc.cloud` → tap mic → speak → receive streamed SSE response | Short screen recording or screenshot series saved to `docs/perf/sp1-voice-cellular-test.md` (timestamp, phone model, response excerpt) |
| One successful automated backup | ≥1 file matching `pg_dump_*.sql.gz`, `redis_dump_*.rdb.gz`, or `qdrant_snapshot_*.tar.gz` dated within 24h, visible in the Drive folder | Backup filename + timestamp in sign-off line |
| Telegram alert fires on deliberately induced failure | `pm2 stop cruz-api`; Telegram DM arrives within 120s; `pm2 start cruz-api` | Screenshot of DM saved to `docs/perf/sp1-alert-test.md` |

**All four must hold simultaneously within the same 7-day SP1 window** for the gate to pass.

**If any fail:** the charter's fix-window rule applies (≤25% of original estimate ≈ ≤1.5 days). If the fix window expires without all four holding, SP1 is shelved and the charter reopens. Per charter Section 5.1 precedence-with-K2 note, fix-window time counts toward the 50% overrun calculation.

### Sign-off procedure

When all four verifications are captured, append to `PROGRESS.md` under Phase 6:

```
SP1 sign-off — 2026-MM-DD
  uptime:         pct_ok=XX.X (window: YYYY-MM-DDTHH:MM:SSZ → YYYY-MM-DDTHH:MM:SSZ)
  voice-cellular: verified (see docs/perf/sp1-voice-cellular-test.md)
  backup:         <filename>.gz landed at YYYY-MM-DDTHH:MM:SSZ
  alert:          verified (see docs/perf/sp1-alert-test.md, observed_latency_seconds=N)
  commit:         <sha>       # .env final state; no code commits in SP1
```

---

## 4. Risks and mitigations

Ordered by probability × impact.

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Cloudflare tunnel config error (UUID mismatch, wrong ingress, DNS not propagated, auth-cert mismatch) | High | Eats 2–6 hours | Run `cloudflared tunnel ingress validate` before `service install`; smoke-test in foreground with `cloudflared tunnel run cruz` first; confirm `dig cruz.simpleinc.cloud +short` shows Cloudflare IP |
| 2 | PM2 startup not actually persisting across reboot (sudo command skipped; `pm2 save` not re-run after process list changes) | Medium-high | 72h probe resets if Mac reboots mid-run | Day 1 includes a deliberate `sudo reboot now` test after `pm2 save` + sudo startup; verify all 5 apps auto-start before Day 2 |
| 3 | Ollama disk space tight (~25GB + OS + caches on 256GB) | Medium | Blocks Day 1 mid-pull | `df -h /` before `ollama pull`; if free < 50GB, clean `~/.cache/`, `~/Library/Caches/`, Xcode DerivedData |
| 4 | Google Drive service account permissions wrong (folder shared Viewer instead of Editor; API disabled; JSON path wrong in `.env`) | Medium | Silent backup failure for weeks | Day 2 gate = one manual backup visible in Drive within 5 min; do not move to Day 3 until a file lands |
| 5 | macOS sleeps during 72h probe (lid-close, idle sleep, App Nap suspends processes) | Medium | Probe drops below 99% pct_ok | Before Day 3 evening: `sudo pmset -a disablesleep 1` (or `caffeinate -d -i -s` wrapper); document revert command |
| 6 | Load scenarios fail SLOs in prod config (regression hidden in dev) | Medium | Pushes Day 3 into Day 4; compresses probe window | Run scenarios before starting probe; failure → SP1 pauses at Day 3 and enters 25% fix window |
| 7 | Phone-over-cellular blocked (ISP-level, CG-NAT edge cases, Cloudflare rate limit) | Low-medium | Can't prove voice gate | Validate Day 2 end (WiFi-off test) not Day 3; fallback: test via Tailscale mesh IP; if persistent, try alternate carrier SIM |
| 8 | macOS permissions prompts stall startup (microphone, Accessibility, Full Disk Access for backups) | Low | Services half-start silently | First `./scripts/start-cruz.sh` run on Day 1 done interactively; grant every prompt as it appears; verify via `pm2 logs` that no process is stuck |
| 9 | Real-DB integration tests fail (test DB doesn't exist, migration drift) | Low | Day 1 blocker | `createdb cruz_test -U cruz` + `alembic -c alembic.ini upgrade head` against `cruz_test` before `pytest tests/integration/` |
| 10 | Telegram 90s alert window tight (Kuma default interval 60s + retry logic) | Low | Induced-outage test times out | Kuma API monitor at 30s interval; accept up to 120s observed in SP1 (charter exit gate uses 120s, not 90s) |

**Catch-all.** Any risk materialized not on this list that blocks a gate: invoke the charter's 25% fix-window rule (≤1.5 days).

**What counts as "P0 bug" that pauses SP1 entirely.** Only a reproducible crash in v1 code revealed by production config — not config errors, not env mistakes, not Cloudflare misconfigurations. P0 bugs are fixed via normal dev flow, then SP1 resumes. Setup errors are SP1 work.

---

## 5. Sequence dependencies

```
Day 1:  Ollama pull ────┐
                        ├─► /health green locally ─► real-DB tests ─► PM2 survives reboot
        .env audit ─────┤
                        │
        start-cruz ─────┘

Day 2:  ┌─► Cloudflare tunnel live ──► external /health ──► phone-cellular voice test
        │                                                   (gate criterion #2)
        ├─► Telegram bot + .env ──► alert path live
        │                           (feeds Day 3 induced-outage)
        │
        └─► Google Drive creds ──► one manual backup lands
                                   (gate criterion #3)

Day 3:  (all Day 2 complete) ──► Monitoring stack
                              ──► Uptime Kuma configured
                              ──► Induced-outage test
                                  (gate criterion #4)
                              ──► Load scenarios pass
                              ──► Start 72h probe
                                  (opens gate criterion #1)

Day 4-6: 72h probe runs ──► pct_ok ≥ 99 ──► Day 6 sign-off
                            (closes gate criterion #1)
```

**Critical path.** Ollama pull (Day 1 start) → Cloudflare tunnel (Day 2) → 72h probe start (Day 3 evening).

**Parallelizable.** Day 2's three tracks (Cloudflare, Telegram, Drive) are independent. Run whichever is easiest first based on the blocker in hand.

**Soft dependency.** Load scenarios could overlap with the probe (acceptable additive traffic), but running them before the probe is safer.

---

## 6. Hand-off to SP2

On SP1 close, SP2 inherits this state and must not re-verify:

- All v1 services under PM2, auto-restart on reboot, registered with launchd
- Qdrant container running via `docker compose`; collection `cruz_conversations` exists (pre-SP1)
- Cloudflare tunnel live at `cruz.simpleinc.cloud`; external API reachable from any device
- Telegram alerts functional; unhandled exceptions in CRUZ / ARQ worker / TITAN DM the phone
- Daily backup to Google Drive at cron(hour=4); service-account credentials working
- `/health` reports `llm_backend`, Ollama model status, Qdrant connectivity
- 72h probe harness and log format at `logs/uptime/stability.jsonl` — reusable for future long-running validation
- `PROGRESS.md` Phase 6 has SP1 sign-off row with commit sha

**What SP2 must NOT assume exists:**

- New Qdrant collections (`cruz_activities`, `cruz_projects_docs`, `cruz_user_patterns`, `cruz_domain_knowledge`) — SP2 creates these
- New Postgres tables (`projects`, `learned_patterns`) — SP2 creates these via Alembic
- `build_agent_context` / `record_agent_activity` services — SP2 writes these
- Retrofit to any of the 14 existing agents — SP2 does this work

**Clean cut.** SP1 produces no new code. SP2 is where new code starts.

---

## Appendix A — Charter override log

No overrides. SP1 complies with every Section 3 rule as written:

- Rule 1 (agent inclusion): SP1 adds no agents. N/A.
- Rule 2 (LLM escalation): SP1 adds no agents. N/A.
- Rule 3 (KB participation): SP1 adds no agents. N/A.
- Rule 4 (approval gates): SP1 adds no externally visible actions beyond the existing backup ARQ task. N/A.
- Rule 5 (trace and log): SP1 uses existing `BaseAgent.log()` paths.
- Rule 6 (token-cap signal): SP1 makes no LLM calls beyond existing v1 code paths.
- Rule 7 (handler contract): SP1 adds no handlers.
- Rule 8 (charter override): no overrides requested.

## Appendix B — Scripts and docs referenced

| Path | Purpose in SP1 |
|---|---|
| `scripts/start-cruz.sh` | Day 1 launcher |
| `scripts/stop-cruz.sh` | Clean stop during reboot test |
| `scripts/uptime/check_stability.py` | 72h probe + summary |
| `scripts/load/run_scenarios.sh` | Day 3 load scenarios |
| `docs/production/readiness_checklist.md` | 12-gate checklist; Day 1 reference |
| `docs/perf/uptime_test.md` | launchd plist template for 72h probe |
| `docs/perf/load_results.md` | SLO targets + sign-off row location |
| `docs/cloudflare/setup.md` | Cloudflare tunnel setup reference |
| `cloudflared/config.yml` | Tunnel ingress config |
| `docker-compose.yml` | Qdrant + `monitoring` profile (Uptime Kuma, Loki, Grafana) |
| `ecosystem.config.js` | PM2 process definitions (5 apps) |
