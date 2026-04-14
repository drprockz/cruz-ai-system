# CRUZ AI System — Build Progress

**Last updated:** April 14, 2026
**Tests passing:** 1035 / 1035 mocked + 10 skipped (9 real-PostgreSQL integration tests opt-in via `DATABASE_URL_TEST`; 1 locust import guard when `locust` not installed)

> ⚠️ **AUDIT NOTE (2026-04-13):** Task-scope completion is accurate, but a deep audit revealed
> the spec (CLAUDE.md) promises agent integrations that were never in the task list. The
> agents are skeletons for those integrations. See **Reality Gaps** at the bottom.

---

## Phase 1 — Foundation ✅ SCOPE DONE (8/8)

**Goal:** CRUZ is live, talks back, remembers conversations, routes to agents via tool_use.

| Task | Description | Status |
|---|---|---|
| 1.1 | `agents/base_agent.py` — BaseAgent, AgentInput, AgentOutput, handle_error, log | ✅ |
| 1.2 | Alembic setup + schema migration (conversations, messages, agent_logs, tasks, users) | ✅ |
| 1.3 | `services/db.py`, `services/redis_client.py`, `services/ollama.py` — shared singletons | ✅ |
| 1.4 | `agents/relay/relay_agent.py` — keyword classifier, zero LLM calls | ✅ Wired as pre-filter (R17) |
| 1.5 | `agents/general/general_agent.py` — Claude catch-all sub-agent | ✅ |
| 1.6 | `agents/cruz/cruz_agent.py` — tool_use orchestration, agentic loop, conversation persistence | ✅ |
| 1.7 | `POST /command` + SSE streaming, `GET /health`, `GET /conversations/:id/messages`, `GET /logs/:trace_id` | ✅ |
| 1.8 | Tests: base_agent, relay, general, cruz_agent, cruz_conversation, command_endpoint, health, streaming, logs, conversations, db, redis, ollama | ✅ |

**Notes:** RELAY wired as tool-list pre-filter (R17 2026-04-14) — deterministic keyword hits narrow Claude's tool list; otherwise Claude native tool_use decides.

---

## Phase 2 — Core Agents ⚠️ SCOPE DONE (4/4), SPEC PARTIAL

**Goal:** FORGE generates real code, ECHO drafts and sends emails, voice pipeline live.

| Task | Description | Status |
|---|---|---|
| 2.1 | `agents/forge/forge_agent.py` — read_file, write_file, run_linter (Python+JS/TS), list_directory, agentic loop, agent logging | ✅ |
| 2.2 | `agents/echo/echo_agent.py` — Qwen 14B via Ollama, approval gate, Claude fallback, agent logging | ✅ drafts only |
| 2.3 | `services/voice.py` — Whisper Large v3 STT (lazy load), `speak()` stub, `POST /voice/transcribe` endpoint | ⚠️ STT only, no TTS |
| 2.4 | Integration test: FORGE + ECHO end-to-end | ✅ mocked |

**Spec gaps (not in any task but CLAUDE.md promises them):**
- ECHO doesn't actually send email (no Gmail/SendGrid code after approval)
- Voice TTS (`speak()`) is a stub — no Inworld or macOS `say` wiring
- No Porcupine wake-word detection

---

## Phase 3 — Automation ⚠️ SCOPE DONE (5/5), SPEC PARTIAL

**Goal:** Overnight automation, meeting intelligence, sprint planning, Qdrant memory.

| Task | Description | Status |
|---|---|---|
| 3.1 | `services/qdrant.py`, `services/embedding.py`, `services/semantic_memory.py` — Qdrant + all-MiniLM-L6-v2 wired into CruzAgent | ✅ |
| 3.2 | `workers/arq_worker.py` — ARQ background workers (PULSE 6AM, RAW 3AM, REACH 2AM) | ✅ |
| 3.3 | `agents/reach/reach_agent.py` — Gemini discovery + Qwen personalization + Apollo.io | ⚠️ drafts only |
| 3.4 | `agents/catch/catch_agent.py` — Whisper transcription + Llama summarization + Notion + Linear | ⚠️ no Notion/Linear |
| 3.5 | `agents/pm/pm_agent.py` — Qwen sprint planning + Linear/JIRA integration | ⚠️ Plane only, no JIRA |

**Spec gaps:**
- REACH discovers and drafts but never sends outreach emails
- Apollo.io and Hunter.io integrations are not actually called
- CATCH transcribes/summarises but doesn't push to Notion or Linear
- PM uses Plane.so; CLAUDE.md says Linear/JIRA — neither is integrated

---

## Phase 4 — DevOps Pipeline ⚠️ SCOPE DONE (4/4), SPEC PARTIAL

**Goal:** QT gates deployments, SENTINEL reviews PRs, TITAN deploys, MARK documents.

| Task | Description | Status |
|---|---|---|
| 4.1 | `agents/qt/qt_agent.py` — pytest, npm audit, test generation | ⚠️ no Playwright/Lighthouse |
| 4.2 | `agents/sentinel/sentinel_agent.py` — Claude PR review, OWASP | ⚠️ no GitHub comment posting |
| 4.3 | `agents/titan/titan_agent.py` — Vercel/Railway/SSH deploy with approval gate | ✅ (no auto-rollback) |
| 4.4 | `agents/mark/mark_agent.py` — OpenAPI spec, JSDoc, README, changelog | ⚠️ generates but doesn't publish |

**Spec gaps:**
- QT claims Playwright + Lighthouse — neither wired
- SENTINEL does `GET /pulls` but never POSTs inline comments after approval
- TITAN has no auto-rollback on failed deploy
- MARK generates markdown but never writes to GitHub or Notion

---

## Phase 5 — Intelligence Layer ⚠️ 3/4, SPEC PARTIAL

**Goal:** CRUZ becomes proactive. Morning briefings. Cross-device handoff. React Native app.

| Task | Description | Status |
|---|---|---|
| 5.1 | `agents/raw/raw_agent.py` — Llama 3.1 8B, dependency updates, tech research → Qdrant | ⚠️ no Notion |
| 5.2 | `agents/pulse/pulse_agent.py` — 6AM briefing: calendar, overnight tasks, client alerts | ⚠️ no RSS/HN/Reddit/Notion |
| 5.3 | Cross-device handoff — Redis pub/sub device-switch detection, proactive context surfacing | ✅ |
| 5.4 | React Native app — voice interface, conversation history, task dashboard, push notifications | ❌ |

**Spec gaps:**
- RAW stores research in Qdrant ✅ but doesn't cross-post to Notion
- PULSE reads Calendar + Qdrant + DB ✅ but doesn't read RSS feeds, Hacker News, Reddit

---

## Phase 6 — Production Hardening ✅ code-side done (6/6); Mac-Mini install still needed

| Task | Description | Status |
|---|---|---|
| 6.1 | PM2 config (`ecosystem.config.js`) — API + ARQ worker + Ollama, auto-restart on reboot | ✅ R1 |
| 6.2 | Monitoring stack — Uptime Kuma + Grafana Loki + Sentry + Telegram alerts | ✅ Session C (2026-04-14) |
| 6.3 | Performance validation — latency targets, 10 concurrent requests, P95 DB queries | ✅ Session B (2026-04-14) |
| 6.4 | Cloudflare Tunnel — `cruz.simpleinc.cloud`, webhooks from GitHub/Vercel/Google Calendar | ✅ Session C (2026-04-14) |
| 6.5 | Backup automation — pg_dump + Redis + Qdrant → Google Drive via ARQ cron | ✅ Session B (2026-04-14) |
| 6.6 | Load testing + final validation — 4 production scenarios, 72-hour uptime test | ✅ harness (Session D 2026-04-14) |

**Session C (2026-04-14) deliverables:**
- 6.2 — `services/alerts.py` AlertService (Telegram+Sentry) + LokiHandler;
  wired into CruzAgent (unhandled exc), TITAN (deploy failure), ARQ
  after_job_end; lifespan inits Sentry + Loki when env vars set; docker
  compose `monitoring` profile brings up Uptime Kuma + Loki + Grafana;
  SETUP.md monitoring bring-up + probe list; **20 new tests**.
- 6.4 — `POST /webhooks/github` (HMAC-SHA256), `/webhooks/vercel`
  (HMAC-SHA1), `/webhooks/google-calendar` (X-Goog-Channel-Token);
  each verifies signature → enqueues ARQ job → returns 200; 401 on bad
  sig; `workers/tasks/webhook_tasks.py` + WorkerSettings registration;
  `cloudflared/config.yml` template + `docs/cloudflare/setup.md`;
  **11 new tests**.

**Session D (2026-04-14) deliverables:**
- `scripts/load/locustfile.py` — 4 scenarios: morning_rush, agent_mix, sse_streaming, overnight
- `scripts/load/run_scenarios.sh` — `--dry-run` supported, per-scenario CSV + HTML output
- `scripts/uptime/check_stability.py` — 72h `/health` probe, JSONL append, `--once` / `--summary` modes
- `docs/perf/load_results.md` — SLO table + run log template
- `docs/perf/uptime_test.md` — launchd / cron / systemd-timer procedures
- `docs/production/readiness_checklist.md` — 12 programmatic gates before `ENVIRONMENT=production`
- `tests/scripts/test_check_stability.py` — 5 passing unit tests + locust import smoke test

**Session B (2026-04-14) deliverables:**
- 6.3 — `scripts/perf/bench_command.py` + `bench_db.py` + `bench_concurrent.py`,
  `docs/perf/baseline.md` template, 14 unit tests with external I/O mocked.
- 6.5 — `services/backup.py` (pg_dump / redis-cli --rdb / qdrant tar.gz /
  Google Drive upload), `workers/tasks/backup_tasks.py`, cron(run_backup, hour=4),
  SETUP.md docs for service-account + env vars, 10 new unit tests.

6.2 and 6.4 code now landed in Session C. Installation on the Mac Mini
(running `docker compose --profile monitoring up -d` + `cloudflared service
install`) is the only remaining step; the readiness checklist covers it.

## What's next

- **5.4 — React Native app** (voice, conversation history, tasks, push). Only remaining scoped feature.
- **Ops gating** — 6.2 / 6.4 / 6.5 install steps + run the 72h uptime probe.

---

## Summary

| Phase | Scope | Spec | Tasks Done |
|---|---|---|---|
| 1 — Foundation | ✅ | ✅ | 8 / 8 |
| 2 — Core Agents | ✅ | ⚠️ partial | 4 / 4 |
| 3 — Automation | ✅ | ⚠️ partial | 5 / 5 |
| 4 — DevOps Pipeline | ✅ | ⚠️ partial | 4 / 4 |
| 5 — Intelligence Layer | ⚠️ | ⚠️ partial | 3 / 4 |
| 6 — Production Hardening | ⚠️ code done | ⏭️ ops pending | 2 / 6 code + 3 deferred to ops |
| **Total** | | | **26 / 31** |

**MVP target:** April 26, 2026 | **Production target:** May 24, 2026

---

## Reality Gaps (from 2026-04-13 deep audit)

Tasks pass their scope tests, but **first-run smoke test (2026-04-13) revealed the system
crashes before responding to any command** because:

### 🔴 Infrastructure gaps (P0 — blocks any real use) — ✅ ALL CLOSED 2026-04-14

| # | Gap | Status |
|---|---|---|
| R1 | **No PM2 config** — `ecosystem.config.js` missing | ✅ Written — api + worker with auto-restart, log rotation |
| R2 | **No docker-compose.yml** — Qdrant setup is a manual `docker run` | ✅ Written — Qdrant primary + optional postgres/redis profile |
| R3 | **No startup env-var validation** — missing keys fail lazily mid-request | ✅ `_validate_required_env()` — lifespan fails fast on missing ANTHROPIC_API_KEY, DATABASE_URL, REDIS_URL, QDRANT_URL |
| R4 | **No Ollama model pre-check** — `/health` reports "reachable" even if no models pulled | ✅ `/health` now reports `ollama.required`, `ollama.missing`; status degrades if required model missing |
| R5 | **Qdrant service has no connectivity guard** — crashes AttributeError if `.client is None` | ✅ `_require_client()` raises clear RuntimeError naming Qdrant URL |
| R6 | **No real integration tests** — everything mocks `get_db_service`, `anthropic`, `httpx` | ✅ `tests/integration/test_real_db.py` — 9 tests: schema shape, UUID round-trip, BaseAgent.log SQL; skip when `DATABASE_URL_TEST` unset |

### 🟠 Spec vs implementation gaps (P1 — CLAUDE.md promises vs code)

| # | Gap | Impact |
|---|---|---|
| R7 | ~~ECHO drafts emails, never sends~~ | ✅ 2026-04-14 — `services/email.py` (SendGrid); `context={"send":True}` sends after draft. `context["to"]` overrides draft recipient. |
| R8 | ~~REACH drafts outreach, never sends~~ | ✅ 2026-04-14 — same EmailService; `context={"send":True}` sends each lead; per-lead sent/failed tracking; partial failure non-fatal |
| R9 | ~~SENTINEL never posts GitHub inline comments~~ | ✅ 2026-04-14 — `services/github.py` + `context={"send":True}` posts review via `/pulls/:n/reviews` with inline comments, severity prefixed |
| R10 | ~~MARK generates docs, never publishes~~ | ✅ 2026-04-14 — `context={"send":True,"target":"github"\|"notion"\|"both"}` publishes via new services |
| R11 | ~~Notion missing across agents~~ | ✅ 2026-04-14 — `services/notion.py` with `create_page`; chunking past 2000 chars; MARK is first consumer. CATCH/RAW/PULSE can reuse. |
| R12 | ~~PM drafts but creates nothing~~ | ✅ 2026-04-14 — `services/plane.py` + PM send mode creates one Plane issue per sprint task; per-ticket flags |
| R13 | ~~CATCH doesn't push action items~~ | ✅ 2026-04-14 — CATCH send mode creates one Plane issue per action item; partial failures non-fatal |
| R14 | ~~TITAN has no auto-rollback~~ | ✅ 2026-04-14 — on deploy failure, target-specific rollback (Vercel promote, Railway redeploy prior, SSH custom command); `auto_rollback=False` opts out; skipped gracefully if no rollback params supplied |
| R15 | ~~QT has no Playwright, no Lighthouse~~ | ✅ 2026-04-14 — two new test_type modes: `playwright` (parses pass/fail counts) and `lighthouse` (gates on score threshold, default 0.9) |
| R16 | ~~Voice speak is a stub~~ | ✅ 2026-04-14 — Inworld TTS via REST + macOS `say` fallback; `WakeWordDetector` wrapping pvporcupine; new `POST /voice/speak` endpoint |
| R17 | ~~RELAY is dead code~~ | ✅ 2026-04-14 — wired as tool-list pre-filter. `classify(task)` narrows Claude's CRUZ_TOOLS list when a deterministic keyword matches; full list otherwise. Zero LLM calls. |

### 🟡 Documentation drift (P2)

| # | Gap |
|---|---|
| R18 | README.md says "366 tests" — real count is 796 |
| R19 | SETUP.md doesn't document `ollama pull qwen2.5-coder:14b` / `llama3.1:8b` as required |
| R20 | No troubleshooting guide for Qdrant down, Ollama model missing, API credits exhausted |

---

## Remediation progress

### ✅ P0 complete (2026-04-14) — foundation is now runnable
- R1 PM2 ecosystem.config.js + `logs/` directory
- R2 docker-compose.yml (Qdrant primary, optional postgres/redis profile)
- R3 startup env validation (fail-fast on missing ANTHROPIC_API_KEY etc.)
- R4 /health reports required Ollama models + degrades status when missing
- R5 QdrantService None-guards (clear RuntimeError instead of AttributeError)
- R6 9 real-PostgreSQL integration tests that actually run migrations + exercise SQL

### ⏭️ P1 queue (CLAUDE.md promises not yet delivered)

Tackle in client-value order:
1. ✅ **R7** ECHO send email (SendGrid) — done 2026-04-14
2. ✅ **R8** REACH send outreach (SendGrid, per-lead) — done 2026-04-14
3. ✅ **R9** SENTINEL post GitHub review comments — done 2026-04-14
4. ✅ **R10** MARK publish to GitHub/Notion — done 2026-04-14
5. ✅ **R11** Shared Notion service (`services/notion.py`) — done 2026-04-14 (MARK is first consumer; CATCH/RAW/PULSE remain to adopt it in follow-ups)
6. ✅ **R12** PM push tickets to Plane.so — done 2026-04-14
7. ✅ **R13** CATCH push action items to Plane.so — done 2026-04-14
8. ✅ **R14** TITAN auto-rollback on failed deploy — done 2026-04-14
9. ✅ **R15** QT Playwright + Lighthouse — done 2026-04-14
10. ✅ **R16** VoicePipeline.speak() + Porcupine wake word — done 2026-04-14
11. ✅ **R17** RELAY wired as pre-filter — done 2026-04-14

### 📝 Docs still drifting (P2)
- R18 README test count ✅ fixed
- R19 SETUP.md ollama pull instructions ✅ fixed
- R20 Troubleshooting guide still TODO
