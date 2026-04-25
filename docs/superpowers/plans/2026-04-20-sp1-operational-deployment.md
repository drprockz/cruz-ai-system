# SP1 — Operational Deployment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **NOTE on execution model:** SP1 is install/operations work, not code work. Many steps require physical presence (clicking through @BotFather on a phone, GCP console auth, plugging in a phone on cellular, running `sudo reboot now`). Subagent-driven execution is NOT appropriate for SP1 — the plan is for Darshan (user) to execute, with Claude Code available as an inline helper for verifying commands, writing config snippets, and preparing commit messages. Tasks that REQUIRE physical human action are marked **[HUMAN]**. Tasks a subagent/Claude could fully execute are marked **[CLAUDE-OK]**.

**Goal:** Take all v1 code and config already built (PM2, Cloudflare Tunnel, monitoring, backups, 72h probe) and make it run as 24/7 production on this Mac, reachable from phone over cellular, with alerts firing and backups landing in Google Drive.

**Architecture:** No new code. Configure external services (Cloudflare Tunnel, Telegram bot, Google Drive). Verify every item in `docs/production/readiness_checklist.md`. Run the 72h uptime probe. Sign off when all 4 charter exit-gate criteria hold simultaneously.

**Tech Stack:** macOS (Sequoia), PM2, cloudflared, Docker, Postgres 15/16, Redis 7, Qdrant, Ollama (qwen2.5-coder:14b + llama3.1:8b), launchd, Google Cloud (service account + Drive API), Telegram Bot API.

**Governing spec:** `docs/superpowers/specs/2026-04-20-sp1-operational-deployment-design.md`
**Program charter:** `docs/superpowers/specs/2026-04-20-v2-program-charter.md` (exit gate in Section 5.1, kill criteria in Section 5.2, cut order in Section 6)

---

## File Structure

SP1 produces no code. All modifications are configuration, docs, or new artifacts. No existing Python/JS files change.

### Files CREATED in SP1

| Path | Purpose | Content source |
|---|---|---|
| `~/Library/LaunchAgents/com.cruz.uptime.plist` | Runs the 72h uptime probe via launchd | Template in `docs/perf/uptime_test.md` |
| `~/.config/cruz/gdrive-sa.json` | Google Drive service account credentials (NOT in repo; outside home-dir is fine) | Downloaded from GCP console |
| `docs/perf/sp1-voice-cellular-test.md` | Voice-over-cellular exit-gate artifact | Written by hand during Day 3 |
| `docs/perf/sp1-alert-test.md` + `docs/perf/sp1-alert-test.png` | Induced-outage alert artifact | Written + screenshot during Day 3 |
| `logs/uptime/stability.jsonl` | 72h probe JSONL output (auto-created) | Produced by `scripts/uptime/check_stability.py` |

### Files MODIFIED in SP1

| Path | Change | Committed? |
|---|---|---|
| `.env` (local, gitignored) | Fill in final production values | No (gitignored) |
| `.env.example` | Add `TELEGRAM_CHAT_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_DRIVE_FOLDER_ID` keys with placeholder values | Yes |
| `cloudflared/config.yml` | Fill in tunnel UUID + ingress rules (if template) | Decide: yes if template placeholders were there, no if tunnel UUID is per-deployment and should stay in a local-only file |
| `docs/production/readiness_checklist.md` | Fix wrong backup filename patterns (`pg_dump_*.sql.gz` → `cruz-pg-*.dump`, etc.) | Yes |
| `docs/perf/load_results.md` | Append Uptime section row with 72h probe result | Yes |
| `PROGRESS.md` | Append SP1 sign-off row under Phase 6 | Yes |

### Files that MUST NOT change in SP1

Any file under `agents/`, `services/`, `workers/`, `backend/`, `frontend/`, `tests/`, `migrations/`, `scripts/` (except the ones called). If a bug requires code change, it's a P0 fixed via normal dev flow, then SP1 resumes.

---

## Chunks

- **Chunk 1: Day 1 — Local prod-readiness** (Tasks 1–8)
- **Chunk 2: Day 2 — External services (three parallelizable tracks)** (Tasks 9–23)
- **Chunk 3: Day 3 — Monitoring, perf, voice validation, probe start** (Tasks 24–33)
- **Chunk 4: Days 4–6 — Passive probe wait + Day 6 sign-off** (Tasks 34–40)

Each chunk ends with a checkpoint: verify all chunk exit criteria hold before moving to the next.

---

## Chunk 1: Day 1 — Local prod-readiness

**Chunk goal.** The Mac, running nothing but local services, reports green on every readiness-checklist local gate. PM2 persists across reboot. Ollama models available. Real-DB integration tests pass.

**Chunk exit criteria (all must hold before Chunk 2):**
- `pm2 status` shows all 5 apps `online` (cruz-api, cruz-worker, cruz-voice-worker, cruz-daemon, cruz-ui)
- `curl -s localhost:3000/health | jq '.status'` returns `"healthy"` and `.ollama.missing == []`
- `docker compose ps` shows `qdrant` running
- After `sudo reboot now`, PM2 auto-restarts and all 5 apps return `online` within 60s
- `DATABASE_URL_TEST=... pytest tests/integration/` all green

---

### Task 1: Pre-flight — check disk space and port collisions

**Files:** none (read-only checks)

- [ ] **Step 1: Check disk free space [CLAUDE-OK]**

```bash
df -h /
```

Expected: free space ≥ 50GB. If less, clean before pulling Ollama models (Ollama requires ~25GB for both models).

- [ ] **Step 2: If disk is tight, clean caches [HUMAN]**

```bash
du -sh ~/Library/Caches/* 2>/dev/null | sort -h | tail -20
# Candidates to delete:
rm -rf ~/Library/Developer/Xcode/DerivedData
brew cleanup --prune=all
docker system prune -a
```

Skip if disk is already ≥ 50GB free.

- [ ] **Step 3: Check for port collisions [CLAUDE-OK]**

```bash
lsof -i :3000 -i :3001 -i :3002 -i :3100 -i :6333 -i :5173
```

Expected: no output (no listeners) OR only CRUZ-related processes. If something else owns a port, kill or reconfigure it before proceeding. If `cruz-*` processes appear from a previous run, that's fine — Task 4 stops them cleanly.

- [ ] **Step 4: No commit** — this is pre-flight; no files changed.

---

### Task 2: Pull Ollama models (start first — long download)

**Files:** none (models stored in `~/.ollama/models/`)

- [ ] **Step 1: Pull models sequentially [HUMAN — watches for a long-running download]**

```bash
ollama pull qwen2.5-coder:14b && ollama pull llama3.1:8b
```

Expected: both complete without error. This can take 15–30 minutes depending on network. Parallel pulls interleave progress bars illegibly on a 24GB Mac — prefer sequential. Continue to Tasks 3–6 (they don't depend on Ollama) in a second terminal while this runs.

- [ ] **Step 2: Verify both models present [CLAUDE-OK]**

```bash
ollama list | grep -E 'qwen2.5-coder:14b|llama3.1:8b'
```

Expected: two lines, one per model, each with a size column showing GB. If either is missing, re-run its `ollama pull`.

- [ ] **Step 3: No commit** — models live in `~/.ollama/`, not the repo.

---

### Task 3: Audit `.env` against `.env.example`

**Files:**
- Read: `.env.example`, `.env`

- [ ] **Step 1: Run the readiness-checklist env diff [CLAUDE-OK]**

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

Expected: `MISSING: none`.

**Note:** This audit is acknowledged to be incomplete — `.env.example` currently omits `TELEGRAM_CHAT_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, and `GOOGLE_DRIVE_FOLDER_ID` per the SP1 design doc. Those keys are added in Chunk 2 (Tracks B and C). Don't try to fix that here.

- [ ] **Step 2: If anything other than the three known-missing keys is flagged [HUMAN]**

Fill it in `.env` by consulting `.env.example` for the intended value pattern. Then re-run Step 1 until `MISSING: none`.

- [ ] **Step 3: No commit yet** — `.env` is gitignored; final `.env.example` update lands in Chunk 2.

---

### Task 4: Start the full stack via existing launcher

**Files:**
- Run: `scripts/start-cruz.sh`

- [ ] **Step 1: Make the launcher executable (once) [CLAUDE-OK]**

```bash
chmod +x scripts/start-cruz.sh
```

Expected: no output. Idempotent.

- [ ] **Step 2: Run it [HUMAN — may hit macOS permission prompts]**

```bash
./scripts/start-cruz.sh
```

Expected output tail:

```
[CRUZ]  CRUZ is running.  Useful commands:
[CRUZ]
[CRUZ]  pm2 logs                    # tail all logs
...
```

Grant any macOS permission prompts (microphone, Full Disk Access, Accessibility) as they appear. Each service on first run may block until you click Allow.

- [ ] **Step 3: Verify all 5 apps online [CLAUDE-OK]**

```bash
pm2 status
```

Expected: table with 5 rows (`cruz-api`, `cruz-worker`, `cruz-voice-worker`, `cruz-daemon`, `cruz-ui`), each with status `online` and `uptime` a few seconds. If any shows `errored`, run `pm2 logs <app-name>` to diagnose.

- [ ] **Step 4: No commit** — scripts already exist, no files modified.

---

### Task 5: Start Qdrant container and verify readiness

**Files:**
- Run: `docker-compose.yml`

- [ ] **Step 1: Start Qdrant [CLAUDE-OK]**

```bash
docker compose up -d qdrant
```

Expected: `Container cruz-qdrant  Started` (container_name is set in `docker-compose.yml`). If container already running, `docker compose up -d qdrant` is a no-op.

- [ ] **Step 2: Verify readiness [CLAUDE-OK]**

```bash
curl -sS http://localhost:6333/readyz
```

Expected: HTTP 200 with body `"ok"` or empty (Qdrant returns 200 no-body on readyz).

- [ ] **Step 3: No commit** — Docker state, not repo state.

---

### Task 6: Verify `/health` is all-green locally

**Files:** none

- [ ] **Step 1: Call /health [CLAUDE-OK]**

```bash
curl -s http://localhost:3000/health | jq
```

Expected JSON shape:

```json
{
  "status": "healthy",
  "api": "healthy",
  "postgresql": "connected",
  "redis": "connected",
  "qdrant": "connected",
  "ollama": {
    "required": ["qwen2.5-coder:14b", "llama3.1:8b"],
    "missing": [],
    "loaded": ["qwen2.5-coder:14b", "llama3.1:8b"]
  },
  "llm_backend": "anthropic",
  ...
}
```

The critical assertions: `status == "healthy"`, `ollama.missing == []`.

- [ ] **Step 2: If status is `degraded` or any service shows `disconnected` [HUMAN]**

Read the specific field's error message and fix it. Common causes:
- Postgres not running: `brew services start postgresql@15` (or @16)
- Redis not running: `brew services start redis`
- Qdrant not reachable: repeat Task 5
- Ollama missing: repeat Task 2

Re-run Step 1 until green.

- [ ] **Step 3: No commit**

---

### Task 7: Real-DB integration tests pass

**Files:**
- Run: `tests/integration/`

- [ ] **Step 1: Create test DB and run migrations [CLAUDE-OK]**

```bash
createdb cruz_test -U cruz 2>/dev/null || true
DATABASE_URL=postgresql+asyncpg://cruz:cruz@localhost:5432/cruz_test alembic -c alembic.ini upgrade head
```

Expected: Alembic reports "Running upgrade" lines ending with the latest head revision. If the DB already exists, `createdb` fails silently (the `|| true` swallows it); Alembic then no-ops if at head.

- [ ] **Step 2: Run the real-DB integration suite [CLAUDE-OK]**

```bash
DATABASE_URL_TEST=postgresql+asyncpg://cruz:cruz@localhost:5432/cruz_test \
  pytest tests/integration/ -v
```

Expected: all tests pass (`N passed` with no failures). Some may be marked skipped if they require specific env; that's OK.

- [ ] **Step 3: No commit** — tests reveal state, don't change it.

---

### Task 8: PM2 survives a reboot

**Files:** none

- [ ] **Step 1: Save the PM2 process list [CLAUDE-OK]**

```bash
pm2 save
```

Expected: `[PM2] Saving current process list...` → `[PM2] Successfully saved in ~/.pm2/dump.pm2`.

- [ ] **Step 2: Register PM2 with launchd [HUMAN — requires sudo]**

```bash
pm2 startup
```

Expected output: PM2 prints a `sudo` command like:

```
sudo env PATH=$PATH:/opt/homebrew/Cellar/node/.../bin \
  /opt/homebrew/lib/node_modules/pm2/bin/pm2 startup launchd \
  -u drprockz --hp /Users/drprockz
```

Copy that exact printed command and run it. Do NOT improvise.

- [ ] **Step 3: Warning — save any unsaved work before rebooting [HUMAN]**

Close editors, commit in-progress work (WIP branch if needed), confirm no important terminal state is in memory only.

- [ ] **Step 4: Reboot the Mac [HUMAN]**

```bash
sudo reboot now
```

Expected: Mac reboots. Log back in.

- [ ] **Step 5: After login, verify PM2 auto-restarted everything [HUMAN — runs first post-login terminal command]**

Wait ~60 seconds after desktop loads, then:

```bash
pm2 status
```

Expected: all 5 apps `online`. If any show `stopped` or missing, `pm2 resurrect` should recover them; if that fails, `./scripts/start-cruz.sh` brings them up manually and indicates the launchd registration didn't take.

- [ ] **Step 6: Verify /health still green [CLAUDE-OK]**

```bash
curl -s http://localhost:3000/health | jq '.status'
```

Expected: `"healthy"`.

- [ ] **Step 7: No commit** — system state only.

---

### Chunk 1 checkpoint

Confirm the 5 chunk exit criteria before proceeding to Chunk 2. If any fails, fix now; don't carry state-problems into external-service setup.

```bash
# Single-shot verification (each line should print the expected value or exit 0):
pm2 status | grep -c 'online'                        # expect: 5
curl -s localhost:3000/health | jq -re '.status'     # expect: healthy
curl -s localhost:3000/health | jq -e '.ollama.missing == []' # expect exit 0
docker compose ps qdrant | grep -c 'Up'              # expect: 1 (Docker Compose v2.x)
```

---

## Chunk 2: Day 2 — External services (three parallelizable tracks)

**Chunk goal.** Three external services fully configured and proven working:
1. Cloudflare Tunnel live at `cruz.simpleinc.cloud`; `/health` reachable from cellular.
2. Telegram bot authenticated; a manual test alert DMs the phone.
3. Google Drive backup configured; one backup file visible in the Drive folder within 5 min of trigger.

Plus: `.env.example` updated with the three currently-missing keys; `docs/production/readiness_checklist.md` backup filename patterns corrected.

**Chunk exit criteria (all must hold before Chunk 3):**
- `curl -sS https://cruz.simpleinc.cloud/health` returns `status: healthy` from a phone on cellular (WiFi off)
- Telegram test alert DM received on phone within 10s of manual send
- At least one file matching `cruz-pg-*.dump`, `cruz-redis-*.rdb`, or `cruz-qdrant-*.tar.gz` visible in the Drive folder, dated within the last 10 min
- `.env.example` contains `TELEGRAM_CHAT_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, and `GOOGLE_DRIVE_FOLDER_ID` with placeholder values; `readiness_checklist.md` uses correct patterns; one commit landed with these config/doc fixes

**Parallelization.** The three tracks (A, B, C) are independent at the execution level. Pick based on what's easiest to start first based on which service's signup is fastest for you. Typical order: Track B (Telegram — 5 min), Track C (GCP — 20 min of console clicks + manual backup), Track A (Cloudflare — 30–60 min with DNS waits).

---

### Track A — Cloudflare Tunnel

**Reference doc:** `docs/cloudflare/setup.md`

---

### Task 9: Install cloudflared

**Files:** none

- [ ] **Step 1: Install via Homebrew [CLAUDE-OK]**

```bash
brew install cloudflared
```

Expected: Homebrew installs the binary. If already installed, `brew install` is a no-op.

- [ ] **Step 2: Verify install [CLAUDE-OK]**

```bash
cloudflared --version
```

Expected: version string like `cloudflared version 2026.x.y (built ...)`. Any recent version is fine.

- [ ] **Step 3: No commit**

---

### Task 10: Authenticate cloudflared to your Cloudflare account

**Files:** none (writes `~/.cloudflared/cert.pem` locally)

- [ ] **Step 1: Run login [HUMAN — opens browser, requires Cloudflare login]**

```bash
cloudflared tunnel login
```

Expected: opens a browser window at `https://dash.cloudflare.com/argotunnel?...`. Log in to your Cloudflare account, pick the zone for `simpleinc.cloud`, click Authorize.

Expected terminal output:
```
Successfully logged in.
You have successfully logged in.
If you wish to copy your credentials to a server, they have been saved to:
/Users/drprockz/.cloudflared/cert.pem
```

- [ ] **Step 2: Verify cert exists [CLAUDE-OK]**

```bash
ls -l ~/.cloudflared/cert.pem
```

Expected: file exists, owned by you.

- [ ] **Step 3: No commit** — cert lives in `~/.cloudflared/`, not the repo.

---

### Task 11: Create the tunnel

**Files:** none (writes `~/.cloudflared/<UUID>.json` locally)

- [ ] **Step 1: Create tunnel named `cruz` [CLAUDE-OK]**

```bash
cloudflared tunnel create cruz
```

Expected output:
```
Tunnel credentials written to /Users/drprockz/.cloudflared/<UUID>.json. cloudflared chose this file based on where your origin certificate was found.
Created tunnel cruz with id <UUID>
```

**Save the UUID** — you need it for Task 13. (Also visible via `cloudflared tunnel list`.)

- [ ] **Step 2: Verify tunnel exists [CLAUDE-OK]**

```bash
cloudflared tunnel list
```

Expected: one line for `cruz` with its ID and creation timestamp.

- [ ] **Step 3: No commit**

---

### Task 12: Route DNS to the tunnel + verify propagation

**Files:** none

- [ ] **Step 1: Add DNS route [CLAUDE-OK]**

```bash
cloudflared tunnel route dns cruz cruz.simpleinc.cloud
```

Expected: `Added CNAME cruz.simpleinc.cloud which will route to this tunnel.`

If it says "An A, AAAA, or CNAME record with that host already exists" → delete the existing record in the Cloudflare dashboard (DNS tab), then re-run.

- [ ] **Step 2: Verify DNS propagation [CLAUDE-OK]**

```bash
dig cruz.simpleinc.cloud +short
```

Expected: one or more IPs that belong to Cloudflare's edge network (typically in the 104.x, 172.67.x, or 188.114.x ranges). If empty, wait 60s and retry; Cloudflare propagation is usually <30s but can be longer on first provision.

- [ ] **Step 3: No commit**

---

### Task 13: Fill `cloudflared/config.yml`

**Files:**
- Modify: `cloudflared/config.yml`

- [ ] **Step 1: Read the existing template [CLAUDE-OK]**

```bash
cat cloudflared/config.yml
```

Inspect which fields are placeholders. The file was created by Session C (2026-04-14) as a template; likely has `tunnel: <UUID>`, `credentials-file: /Users/drprockz/.cloudflared/<UUID>.json`, and ingress rules mapping `cruz.simpleinc.cloud` → `http://localhost:3000`.

- [ ] **Step 2: Replace placeholders [HUMAN — manual edit]**

Use your tunnel's actual UUID (from Task 11) and the JSON path it generated. Minimal working content:

```yaml
tunnel: <YOUR-UUID>
credentials-file: /Users/drprockz/.cloudflared/<YOUR-UUID>.json

ingress:
  - hostname: cruz.simpleinc.cloud
    service: http://localhost:3000
  - service: http_status:404
```

- [ ] **Step 3: Validate the config [CLAUDE-OK]**

```bash
cloudflared tunnel --config cloudflared/config.yml ingress validate
```

Expected: `Validating rules from cloudflared/config.yml\nOK`. Any syntax or rule-order error fails here.

- [ ] **Step 4: Decision — commit or not [HUMAN]**

The tunnel UUID and credentials-file path are deployment-specific. Two valid choices:

**Option X:** keep `cloudflared/config.yml` as a template (no UUID in git) and use a local-only override like `~/.cloudflared/config.yml`. Revert any UUID edits you just made to `cloudflared/config.yml` — put the real values at `~/.cloudflared/config.yml` instead, then use `cloudflared tunnel --config ~/.cloudflared/config.yml run cruz`.

**Option Y:** commit the config with the real UUID (private single-user repo is acceptable; the UUID alone without the credentials JSON is not sensitive).

Pick one and document in your sign-off line. Recommend **Option X** for cleanliness.

If Option X: revert changes to `cloudflared/config.yml` (keep placeholders), save the real config at `~/.cloudflared/config.yml`. From here on, substitute `~/.cloudflared/config.yml` wherever `cloudflared/config.yml` is written.

- [ ] **Step 5: No commit yet** — held for end-of-Chunk-2 batch commit.

---

### Task 14: Smoke-test the tunnel in the foreground

**Files:** none

- [ ] **Step 1: Run in foreground [HUMAN — blocks terminal]**

```bash
cloudflared tunnel --config <path-from-Task-13> run cruz
```

Expected: logs showing `INF Starting tunnel`, then `INF Connection <id> registered connIndex=N`. Should see at least 2 connections registered.

Leave this running in one terminal.

- [ ] **Step 2: From a second terminal, test from this Mac [CLAUDE-OK]**

```bash
curl -sS https://cruz.simpleinc.cloud/health | jq '.status'
```

Expected: `"healthy"`.

- [ ] **Step 3: Test from outside your LAN [HUMAN — requires phone]**

Turn OFF WiFi on your phone. On cellular, visit `https://cruz.simpleinc.cloud/health` in a browser OR use a mobile terminal app.

Expected: same healthy JSON as Step 2. If it fails, check: (a) phone has cellular data, (b) DNS propagation from Task 12, (c) the foreground `cloudflared` process didn't die.

- [ ] **Step 4: Stop the foreground tunnel [HUMAN]**

In the first terminal: `Ctrl-C`. The tunnel disconnects. The tunnel itself persists in Cloudflare; only the foreground client stops.

- [ ] **Step 5: No commit**

---

### Task 15: Install cloudflared as a service (auto-start)

**Files:** none (installs a LaunchDaemon plist in `/Library/LaunchDaemons/`)

- [ ] **Step 1: Install as service [HUMAN — requires sudo]**

**If you chose Option X in Task 13 Step 4 (config at default `~/.cloudflared/config.yml`):**

```bash
sudo cloudflared service install
```

This matches the reference command in `docs/cloudflare/setup.md` and reads from the default path.

**If you chose Option Y (custom config path):** the `--config` flag is a global flag in cloudflared and must come BEFORE the subcommand:

```bash
sudo cloudflared --config <path-from-Task-13> service install
```

Expected either form: `Service installed successfully.` The plist is at `/Library/LaunchDaemons/com.cloudflare.cloudflared.plist`.

If Gatekeeper prompts for the binary, approve it in System Settings → Privacy & Security → "Allow anyway".

- [ ] **Step 2: Verify service running [CLAUDE-OK]**

```bash
sudo launchctl list | grep cloudflared
```

Expected: one line with PID (non-zero) and `com.cloudflare.cloudflared`.

- [ ] **Step 3: Confirm external reach still works [CLAUDE-OK]**

```bash
curl -sS https://cruz.simpleinc.cloud/health | jq '.status'
```

Expected: `"healthy"`. This is the Track A "done" gate.

- [ ] **Step 4: No commit**

---

### Track B — Telegram bot

---

### Task 16: Create the bot via @BotFather

**Files:** none (runs entirely on Telegram app)

- [ ] **Step 1: Open Telegram, message @BotFather [HUMAN]**

In the Telegram app (phone or desktop), search for `@BotFather`, start a chat.

Send: `/newbot`

BotFather asks for:
- A display name (e.g., `CRUZ Alerts`)
- A username ending in `bot` (e.g., `cruz_alerts_bot` or `darshan_cruz_bot` — must be globally unique)

- [ ] **Step 2: Save the token [HUMAN]**

BotFather replies with:
```
Done! Congratulations on your new bot. ...
Use this token to access the HTTP API:
<LONG-TOKEN-HERE>
```

Copy the token into a scratch file (don't paste into this document). You'll put it in `.env` in Task 18.

- [ ] **Step 3: No commit** — bot metadata lives in Telegram, not the repo.

---

### Task 17: Get your chat_id

**Files:** none

- [ ] **Step 1: Start a chat with your new bot [HUMAN]**

In Telegram, search for the bot by its `@username` from Task 16. Open the chat. Send any message (e.g., "hello").

- [ ] **Step 2: Fetch updates to extract chat_id [CLAUDE-OK, but needs the token]**

```bash
curl -s "https://api.telegram.org/bot<YOUR-TOKEN>/getUpdates" | jq '.result[0].message.chat.id'
```

Replace `<YOUR-TOKEN>` with the token from Task 16. Expected: a number like `123456789`. If `.result` is `[]`, send another message in Telegram and retry.

Save this number.

- [ ] **Step 3: No commit**

---

### Task 18: Add `TELEGRAM_CHAT_ID` to `.env.example`; set both in `.env`

**Files:**
- Modify: `.env.example`
- Modify: `.env` (gitignored)

- [ ] **Step 1: Add the key to `.env.example` [CLAUDE-OK]**

Find the line `TELEGRAM_BOT_TOKEN=your-telegram-bot-token` in `.env.example` and add, immediately after:

```
TELEGRAM_CHAT_ID=your-telegram-chat-id
```

- [ ] **Step 2: Set real values in `.env` [HUMAN — gitignored, local only]**

```bash
# In .env, add or update:
TELEGRAM_BOT_TOKEN=<token-from-Task-16>
TELEGRAM_CHAT_ID=<chat-id-from-Task-17>
```

- [ ] **Step 3: Reload PM2 with the new env [CLAUDE-OK]**

```bash
pm2 reload ecosystem.config.js --update-env
```

Expected: PM2 reloads all apps with the new env vars propagated.

- [ ] **Step 4: No commit yet** — `.env.example` edit held for end-of-Chunk-2 batch commit.

---

### Task 19: Send a manual test alert

**Files:** none

- [ ] **Step 1: Invoke AlertService.notify directly [CLAUDE-OK, runs in repo venv]**

```bash
python -c "import asyncio; from services.alerts import get_alert_service; asyncio.run(get_alert_service().notify('info', 'SP1 test', 'manual alert from Track B'))"
```

Expected: no Python errors; exits 0. The method signature per `services/alerts.py:37` is `notify(severity, title, message)`.

- [ ] **Step 2: Verify DM received [HUMAN — check phone]**

Check Telegram on your phone. Expected: within 10 seconds, a DM from your bot containing "SP1 test" and "manual alert from Track B" (formatted with an info emoji per `services/alerts.py:30`).

If nothing arrives:
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` match Tasks 16/17
- Verify `pm2 reload ... --update-env` actually reloaded (rerun if uncertain)
- Check `pm2 logs cruz-api` for any Telegram API errors
- Confirm you started a chat with your bot (Telegram requires this before the bot can DM you)

- [ ] **Step 3: No commit**

---

### Track C — Google Drive backup

---

### Task 20: GCP project + Drive API + service account + JSON key

**Files:**
- Create: `~/.config/cruz/gdrive-sa.json`

- [ ] **Step 1: Create or reuse a GCP project [HUMAN — GCP console]**

Go to https://console.cloud.google.com/. Either reuse an existing personal project or create a new one (e.g., `cruz-ai-prod`).

- [ ] **Step 2: Enable Drive API [HUMAN]**

In the GCP console: APIs & Services → Library → search "Google Drive API" → Enable.

- [ ] **Step 3: Create a service account [HUMAN]**

IAM & Admin → Service Accounts → Create Service Account.
- Name: `cruz-backup-sa`
- Roles: none needed at project level (Drive access is granted via folder sharing, not IAM)
- Click Done.

- [ ] **Step 4: Create a JSON key [HUMAN]**

Click the new service account → Keys tab → Add Key → Create New Key → JSON → Create.

A JSON file downloads. Move it to `~/.config/cruz/gdrive-sa.json`:

```bash
mkdir -p ~/.config/cruz
mv ~/Downloads/cruz-ai-prod-*.json ~/.config/cruz/gdrive-sa.json
chmod 600 ~/.config/cruz/gdrive-sa.json
```

- [ ] **Step 5: Note the service account's email [HUMAN]**

Open `~/.config/cruz/gdrive-sa.json`; note the `client_email` field. Looks like `cruz-backup-sa@cruz-ai-prod.iam.gserviceaccount.com`. You'll share the Drive folder with this email in Task 21.

- [ ] **Step 6: No commit** — the JSON is outside the repo.

---

### Task 21: Create and share the Drive folder

**Files:** none (Drive-side only)

- [ ] **Step 1: Create a folder in Google Drive [HUMAN]**

Go to https://drive.google.com. Create a new folder named `CRUZ Backups` (or any name you prefer).

- [ ] **Step 2: Copy the folder ID [HUMAN]**

Open the folder. The URL looks like:
```
https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsTuVwXyZ
```
Copy the ID at the end (`1aBcDeFgHiJkLmNoPqRsTuVwXyZ` in the example).

- [ ] **Step 3: Share the folder with the service account as Editor [HUMAN]**

Right-click the folder → Share → paste the service account email from Task 20 Step 5 → choose **Editor** (not Viewer — Viewer is a silent-failure trap because `services/backup.py` needs write access). Click Share.

- [ ] **Step 4: No commit**

---

### Task 22: Add GOOGLE_* keys to `.env.example`; set in `.env`

**Files:**
- Modify: `.env.example`
- Modify: `.env` (gitignored)

- [ ] **Step 1: Add both keys to `.env.example` [CLAUDE-OK]**

Append to `.env.example` (or place alongside other Google-prefixed keys like `GOOGLE_CALENDAR_ID`):

```
GOOGLE_APPLICATION_CREDENTIALS=/Users/drprockz/.config/cruz/gdrive-sa.json
GOOGLE_DRIVE_FOLDER_ID=your-drive-folder-id
```

- [ ] **Step 2: Set real values in `.env` [HUMAN — gitignored]**

```bash
# In .env, add or update:
GOOGLE_APPLICATION_CREDENTIALS=/Users/drprockz/.config/cruz/gdrive-sa.json
GOOGLE_DRIVE_FOLDER_ID=<folder-id-from-Task-21>
```

- [ ] **Step 3: Reload PM2 [CLAUDE-OK]**

```bash
pm2 reload ecosystem.config.js --update-env
```

- [ ] **Step 4: No commit yet** — held for end-of-Chunk-2 batch commit.

---

### Task 23: Trigger a manual backup and verify it lands in Drive

**Files:** none

- [ ] **Step 1: Sanity-check env is readable from a fresh shell [CLAUDE-OK]**

```bash
set -a; source .env; set +a
python -c "import os; print('telegram_chat:', bool(os.environ.get('TELEGRAM_CHAT_ID'))); print('gdrive_folder:', bool(os.environ.get('GOOGLE_DRIVE_FOLDER_ID'))); print('gdrive_creds:', bool(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')))"
```

Expected: all three print `True`. This catches the "my shell doesn't know .env" trap before the expensive backup run. `pm2 reload --update-env` only helps PM2-managed processes; an ad-hoc `python -c` inherits from the shell, which requires the `source .env` step above.

- [ ] **Step 2: Invoke `run_backup` directly [CLAUDE-OK]**

(Runs in the same shell that sourced `.env` in Step 1.)

```bash
python -c "import asyncio; from workers.tasks.backup_tasks import run_backup; asyncio.run(run_backup({}))"
```

Expected: a few seconds to a minute of output as pg_dump, redis-cli, and the qdrant snapshot run, then uploads complete. No Python traceback; exits 0.

If you see `RuntimeError: GOOGLE_APPLICATION_CREDENTIALS not set` or `RuntimeError: GOOGLE_DRIVE_FOLDER_ID not set`, re-run Step 1's `set -a; source .env; set +a` in the CURRENT shell (new subprocess inherits from the current shell only). Do not rely on `pm2 reload --update-env` for this — that only updates env for PM2 processes, not ad-hoc python invocations.

- [ ] **Step 3: Verify files in Drive [HUMAN]**

Open the Drive folder in your browser. Expected: three new files, timestamped within the last few minutes:

- `cruz-pg-<YYYYMMDD-HHMMSS>.dump`
- `cruz-redis-<YYYYMMDD-HHMMSS>.rdb`
- `cruz-qdrant-<YYYYMMDD-HHMMSS>.tar.gz`

If nothing shows up, check:
- Service account email is an Editor on the folder (not Viewer, not unshared)
- Drive API is enabled on the GCP project
- `GOOGLE_APPLICATION_CREDENTIALS` path exists and is readable
- `pm2 logs cruz-worker` may have clues if the upload is triggered through ARQ

- [ ] **Step 4: No commit** — Drive-side artifact, not repo state.

---

### Track D (cleanup) — Fix stale docs and commit Day-2 config

This track is not parallel with A/B/C; do it last, after all three tracks are green.

---

### Task 24: Correct backup filename patterns in readiness checklist

**Files:**
- Modify: `docs/production/readiness_checklist.md`

- [ ] **Step 1: Locate the stale patterns [CLAUDE-OK]**

```bash
grep -n 'pg_dump_\|redis_dump_\|qdrant_snapshot_' docs/production/readiness_checklist.md
```

Expected: one or two matching lines near the Data-protection section.

- [ ] **Step 2: Replace with correct patterns [CLAUDE-OK]**

Change `pg_dump_*.sql.gz` → `cruz-pg-*.dump`, `redis_dump_*.rdb.gz` → `cruz-redis-*.rdb`, `qdrant_snapshot_*.tar.gz` → `cruz-qdrant-*.tar.gz`. These match the actual output of `services/backup.py:57,76,105`.

- [ ] **Step 3: Verify no stale patterns remain [CLAUDE-OK]**

```bash
grep -E 'pg_dump_|redis_dump_|qdrant_snapshot_' docs/production/readiness_checklist.md || echo 'clean'
```

Expected: `clean`.

- [ ] **Step 4: No commit yet** — batched with Task 25.

---

### Task 25: Commit Day-2 config + doc updates

**Files:**
- `.env.example`
- `docs/production/readiness_checklist.md`

- [ ] **Step 1: Stage and confirm the diff [HUMAN]**

```bash
git status
git diff .env.example docs/production/readiness_checklist.md
```

Expected diff:
- `.env.example` gains `TELEGRAM_CHAT_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_DRIVE_FOLDER_ID`
- `docs/production/readiness_checklist.md` has 3 filename patterns updated

**Sanity check:** `git status` should show NO other modified files. If `cloudflared/config.yml` shows as modified, revert it (Option X from Task 13 Step 4).

```bash
# Only if you chose Option X and config.yml was edited:
git checkout cloudflared/config.yml
```

- [ ] **Step 2: Commit [CLAUDE-OK]**

```bash
git add .env.example docs/production/readiness_checklist.md
git commit -m "chore(ops): align .env.example and readiness checklist with v1 code

- Add TELEGRAM_CHAT_ID (required by services/alerts.py:42)
- Add GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_DRIVE_FOLDER_ID
  (required by services/backup.py:119,130)
- Correct backup filename patterns in readiness checklist
  (cruz-pg-*.dump, cruz-redis-*.rdb, cruz-qdrant-*.tar.gz)
  to match services/backup.py:57,76,105

Part of SP1 operational deployment. No code changes."
```

- [ ] **Step 3: Verify [CLAUDE-OK]**

```bash
git log -1 --stat
```

Expected: one commit, 2 files changed.

---

### Chunk 2 checkpoint

Verify all 4 chunk-exit criteria hold before Chunk 3:

```bash
# A: external reach
curl -sS https://cruz.simpleinc.cloud/health | jq -re '.status'   # expect: healthy

# B: Telegram
# Manual — re-run Task 19 Step 1 and confirm DM on phone

# C: Drive backup
# Manual — open Drive folder, confirm cruz-pg-*.dump / cruz-redis-*.rdb / cruz-qdrant-*.tar.gz exist, dated within last 10 min

# D: commit landed
git log -1 --oneline | grep 'chore(ops): align .env.example'
```

Plus: phone-over-cellular test (Task 14 Step 3) passed — that's the voice-gate precondition for Chunk 3.

---

## Chunk 3: Day 3 — Monitoring, perf, voice validation, probe start

**Chunk goal.** Stand up the monitoring stack. Prove the induced-outage path fires a Telegram alert end-to-end (gate criterion #4). Run load scenarios to confirm no prod-mode regression. Prove voice-over-cellular PWA flow end-to-end (gate criterion #2). Disable macOS sleep. Start the 72h uptime probe (opens gate criterion #1).

**Chunk exit criteria (all must hold before Chunk 4):**
- `docker compose ps` shows `uptime-kuma`, `loki`, `grafana` all running; Kuma UI responds at `http://localhost:3001`
- 5 Kuma monitors configured and green for ≥30 min before probe start
- Induced-outage test produced a Telegram DM within 120s; screenshot saved as `docs/perf/sp1-alert-test.png` and written up in `docs/perf/sp1-alert-test.md`
- Load scenarios all 4 pass their SLOs (per `docs/perf/load_results.md`)
- PWA voice path works end-to-end from phone on cellular; notes in `docs/perf/sp1-voice-cellular-test.md`
- `sudo pmset -a disablesleep 1` in effect (or `caffeinate` wrapping probe)
- launchd plist installed and loaded; `launchctl list | grep com.cruz.uptime` shows a PID
- One commit landed with the two test artifacts (`sp1-alert-test.md` + `.png`, `sp1-voice-cellular-test.md`)

---

### Task 26: Start the monitoring stack

**Files:**
- Run: `docker-compose.yml` (monitoring profile: `uptime-kuma`, `loki`, `grafana`)

- [ ] **Step 1: Bring up monitoring profile [CLAUDE-OK]**

```bash
docker compose --profile monitoring up -d
```

Expected: three new containers start (uptime-kuma on :3001, loki on :3100, grafana on :3002). Output looks like:
```
Container cruz-loki           Started
Container cruz-uptime-kuma    Started
Container cruz-grafana        Started
```

- [ ] **Step 2: Verify all three are running [CLAUDE-OK]**

```bash
docker compose --profile monitoring ps
```

Expected: rows for `uptime-kuma`, `loki`, and `grafana`, each with STATUS containing `Up`.

- [ ] **Step 3: Verify Uptime Kuma responds [CLAUDE-OK]**

```bash
curl -sI http://localhost:3001/ | head -1
```

Expected: `HTTP/1.1 200 OK` (or `302` if redirecting to setup page on first run).

- [ ] **Step 4: No commit**

---

### Task 27: Configure Uptime Kuma monitors for the 5 services

**Files:** none (Kuma stores state in the Kuma container's volume)

- [ ] **Step 1: Open Kuma in a browser [HUMAN]**

Visit `http://localhost:3001`. First run asks you to create an admin user — do so and save the credentials in your password manager.

- [ ] **Step 2: Add 5 monitors [HUMAN — clickthrough UI]**

For each, click `+ Add New Monitor`. Use these exact configurations:

| Name | Monitor Type | URL / Hostname / Command | Interval |
|---|---|---|---|
| CRUZ API | HTTP(s) | `http://localhost:3000/health` | 30s |
| Qdrant | HTTP(s) | `http://localhost:6333/readyz` | 60s |
| Redis | TCP Port | host: `localhost`, port: `6379` | 60s |
| Postgres | TCP Port | host: `localhost`, port: `5432` | 60s |
| Ollama | HTTP(s) | `http://localhost:11434/api/tags` | 60s |

For each: Save. Kuma immediately starts probing.

- [ ] **Step 3: Pre-configure Telegram notification channel in Kuma [HUMAN — optional but recommended]**

Kuma UI → Settings → Notifications → Add New → Telegram. Use the same `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from `.env`. Save. Then attach this notification to each of the 5 monitors (edit each → Notifications tab → toggle on).

This makes the induced-outage test in Task 28 deterministic — you know the DM came from Kuma directly, not via `services/alerts.py`. Without this, Task 28 may still pass if CRUZ's own health-check self-reports, but it's fuzzier.

- [ ] **Step 4: Wait 30 min; verify all green [HUMAN]**

After 30 minutes, all 5 should show an unbroken green bar for the observed period. If any is red, fix its underlying service (see Chunk 1 for how each should behave) before proceeding — red on Kuma = something's actually broken, not a Kuma issue.

- [ ] **Step 5: No commit** — Kuma state lives in its Docker volume.

---

### Task 28: Induced-outage test — gate criterion #4

**Files:**
- Create: `docs/perf/sp1-alert-test.md`
- Create: `docs/perf/sp1-alert-test.png`

- [ ] **Step 1: Note the exact time [HUMAN]**

Record the UTC timestamp just before stopping the API, e.g., using `date -u -Iseconds`.

- [ ] **Step 2: Stop the API [CLAUDE-OK]**

```bash
pm2 stop cruz-api
```

Expected: `[PM2] Applying action stopProcessId on app [cruz-api](ids: [0])` etc.; `pm2 status` now shows `cruz-api` as `stopped`.

- [ ] **Step 3: Wait for the alert DM [HUMAN — watch phone]**

Observe Telegram. Expected: within 120s of Step 2, a DM from your bot indicating the API/Kuma detected downtime. Note the observed latency in seconds (from Step 1's timestamp to DM arrival).

If no DM arrives within 180s:
- Check Kuma: is the CRUZ API monitor showing red?
- Check Kuma notification settings — Kuma may need an explicit notification channel configured (in Kuma UI: Settings → Notifications → Add Telegram notification with the same token/chat_id from `.env`)
- Check `pm2 logs cruz-worker` for any alert-pipeline errors

(Note: The plan's assumption is that `services/alerts.py` is wired into the unhandled-exception and service-health paths per Session C 2026-04-14. The induced-outage test may fire via Kuma's own notification channel OR via CRUZ's self-monitoring loop — either counts for the gate.)

- [ ] **Step 4: Restart the API [CLAUDE-OK]**

```bash
pm2 start cruz-api
```

Expected: app returns `online` within 5 seconds.

- [ ] **Step 5: Screenshot the DM [HUMAN — save to repo]**

Screenshot the Telegram DM. Transfer to your Mac. Save as `docs/perf/sp1-alert-test.png`.

- [ ] **Step 6: Write up the test [HUMAN]**

Create `docs/perf/sp1-alert-test.md` with content like:

```markdown
# SP1 Alert Test — Induced Outage

**Date:** 2026-MM-DD
**Stop time (UTC):** <timestamp from Step 1>
**Alert received (UTC):** <timestamp from DM header>
**Observed latency:** <N> seconds
**Kuma monitor:** CRUZ API (30s interval)
**Alert path:** <Kuma direct | services/alerts.py | both>

See [sp1-alert-test.png](sp1-alert-test.png) for the DM screenshot.

**Gate met:** yes — DM arrived within SP1 budget of 120s.
```

- [ ] **Step 7: No commit yet** — batched at Task 33.

---

### Task 29: Run load scenarios

**Files:** none (results in `scripts/load/results/`, gitignored)

- [ ] **Step 1: Ensure locust is installed [CLAUDE-OK]**

```bash
source venv/bin/activate
pip install locust 2>&1 | tail -3
locust --version
```

Expected: `Successfully installed locust-X.Y.Z` or `Requirement already satisfied`, then a `locust X.Y.Z` version line. Locust is a test-only dep; not in `requirements.txt`. If `locust --version` reports "command not found" despite install, the venv isn't active in this shell — re-run `source venv/bin/activate`.

- [ ] **Step 2: Run all four scenarios [CLAUDE-OK, but takes ~7 min total]**

```bash
./scripts/load/run_scenarios.sh all
```

Expected duration: morning_rush 60s + agent_mix 2m + sse_streaming 90s + overnight 3m ≈ ~7.5 min. Each scenario prints a summary at the end.

- [ ] **Step 3: Verify SLOs met [HUMAN — compare against docs/perf/load_results.md]**

Open `docs/perf/load_results.md`; compare the actual scenario outputs to the documented SLO targets. If any scenario fails its SLO:
- This is a gate-blocker for SP1 (load-test pass is part of the checklist)
- Enter the 25% fix-window — investigate whether it's a resource contention (e.g., Kuma+Loki+Grafana eating CPU during the run) or a real regression
- Do NOT proceed to 72h probe until SLOs hold

- [ ] **Step 4: No commit** — scenario outputs go to `scripts/load/results/` which is gitignored.

---

### Task 30: Voice-over-cellular validation — gate criterion #2

**Files:**
- Create: `docs/perf/sp1-voice-cellular-test.md`

- [ ] **Step 1: Turn off WiFi on your phone [HUMAN]**

iPhone: Settings → Wi-Fi → toggle off. Confirm cellular data is on.

Android: Settings → Network → toggle off Wi-Fi.

- [ ] **Step 2: Visit CRUZ PWA [HUMAN]**

On phone, open browser → navigate to `https://cruz.simpleinc.cloud`.

Expected: PWA loads the CRUZ dashboard UI.

- [ ] **Step 3: Tap the mic, speak a command [HUMAN]**

Tap the microphone icon. Grant browser microphone permission if prompted. Speak: `"What can you help me with?"` (or any command).

Expected: live transcription appears; then CRUZ's streamed response starts appearing token-by-token.

- [ ] **Step 4: Let it finish, observe the response [HUMAN]**

Expected: complete response arrives within a few seconds of finishing speaking. Content doesn't matter — what matters is that STT + orchestration + SSE streaming + response all complete over cellular.

- [ ] **Step 5: Optional: screen recording [HUMAN]**

If feasible, take a short screen recording (10–20s) showing the exchange. Save to `docs/perf/sp1-voice-cellular-test.mov` or `.mp4`. Reference it in the write-up below.

- [ ] **Step 6: Write up the test [HUMAN]**

Create `docs/perf/sp1-voice-cellular-test.md`:

```markdown
# SP1 Voice-over-Cellular Test

**Date:** 2026-MM-DD
**Device:** <phone model>
**Carrier:** <e.g., Airtel/Jio>
**WiFi:** off, cellular only confirmed
**PWA URL:** https://cruz.simpleinc.cloud
**Spoken command:** "<what you said>"
**Response excerpt:** "<first 1–2 sentences of CRUZ's response>"
**Round-trip observation:** streamed response began within <N> seconds of end-of-speech.

<Optional: Link to screen recording.>

**Gate met:** yes — voice command over public cellular produced streamed response end-to-end.
```

- [ ] **Step 7: No commit yet** — batched at Task 33.

---

### Task 31: Disable macOS sleep before starting the probe

**Files:** none (system pmset state)

- [ ] **Step 1: Record current pmset state [HUMAN — needed to revert later]**

```bash
pmset -g | tee /tmp/sp1-pmset-before.txt
```

Save the output; you'll use it in Chunk 4 to revert.

- [ ] **Step 2: Disable sleep + display sleep [HUMAN — requires sudo]**

```bash
sudo pmset -a disablesleep 1
sudo pmset -a displaysleep 0    # display can stay off, but don't suspend processes
sudo pmset -a sleep 0           # system sleep 0 = never
```

Expected: no output. Verify:

```bash
pmset -g | grep -E '^ *(sleep|disablesleep|displaysleep)'
```

Expected: `sleep 0`, `disablesleep 1`, `displaysleep 0`.

- [ ] **Step 3: No commit** — pmset state is not in the repo.

---

### Task 32: Install the launchd plist for the 72h probe

**Files:**
- Create: `~/Library/LaunchAgents/com.cruz.uptime.plist`

- [ ] **Step 1: Ensure logs directory exists [CLAUDE-OK]**

```bash
mkdir -p logs/uptime
```

- [ ] **Step 2: Write the plist [CLAUDE-OK]**

Copy the template from `docs/perf/uptime_test.md` Section 2 Option A (launchd). Save it verbatim (paths are hardcoded to `/Users/drprockz/Projects/cruz-ai-system/...`) as `~/Library/LaunchAgents/com.cruz.uptime.plist`.

Quick inline version if you want to avoid manual editing:

```bash
cat > ~/Library/LaunchAgents/com.cruz.uptime.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.cruz.uptime</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/drprockz/Projects/cruz-ai-system/venv/bin/python</string>
    <string>/Users/drprockz/Projects/cruz-ai-system/scripts/uptime/check_stability.py</string>
    <string>--url</string><string>http://localhost:3000/health</string>
    <string>--interval</string><string>300</string>
    <string>--duration</string><string>259200</string>
    <string>--output</string><string>/Users/drprockz/Projects/cruz-ai-system/logs/uptime/stability.jsonl</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>StandardOutPath</key><string>/Users/drprockz/Projects/cruz-ai-system/logs/uptime/stdout.log</string>
  <key>StandardErrorPath</key><string>/Users/drprockz/Projects/cruz-ai-system/logs/uptime/stderr.log</string>
</dict></plist>
PLIST
```

- [ ] **Step 3: Validate plist syntax [CLAUDE-OK]**

```bash
plutil -lint ~/Library/LaunchAgents/com.cruz.uptime.plist
```

Expected: `OK`.

- [ ] **Step 4: No commit** — the plist lives in `~/Library`, not the repo.

---

### Task 33: Activate probe + commit Day-3 artifacts

**Files:**
- `docs/perf/sp1-alert-test.md`
- `docs/perf/sp1-alert-test.png`
- `docs/perf/sp1-voice-cellular-test.md` (+ optional `.mov`/`.mp4`)

- [ ] **Step 1: Do a one-shot sanity probe first [CLAUDE-OK]**

```bash
source venv/bin/activate
python scripts/uptime/check_stability.py --once
```

Expected: one JSON line printed; exit 0 if healthy. If it exits non-zero, fix the underlying issue before loading the launchd agent.

- [ ] **Step 2: Load the launchd agent [HUMAN]**

```bash
launchctl load ~/Library/LaunchAgents/com.cruz.uptime.plist
```

Expected: no output.

- [ ] **Step 3: Verify it's running [CLAUDE-OK]**

```bash
launchctl list | grep com.cruz.uptime
```

Expected: one line with a PID (non-zero) and `com.cruz.uptime`.

- [ ] **Step 4: Record probe start timestamp [HUMAN]**

Note start time in UTC:

```bash
date -u -Iseconds | tee /tmp/sp1-probe-start.txt
```

You'll record this in the sign-off (Chunk 4).

- [ ] **Step 5: Verify probes are being written [CLAUDE-OK]**

Wait 6 minutes (one probe cycle at 300s interval), then:

```bash
tail -1 logs/uptime/stability.jsonl | jq
```

Expected: a JSON record with `"ok": true` (or `"ok": false` with reasons). Writes should accumulate one per 5 minutes.

- [ ] **Step 6: Stage and commit artifacts [CLAUDE-OK — but you must fill in placeholders]**

**Before running `git commit`**, replace `<N>`, `<phone model>`, and `<timestamp>` in the commit message template below with the actual values from Tasks 28 (latency), 30 (phone), and 33 Step 4 (probe start).

```bash
git add docs/perf/sp1-alert-test.md docs/perf/sp1-alert-test.png docs/perf/sp1-voice-cellular-test.md
# Optional:
git add docs/perf/sp1-voice-cellular-test.mov 2>/dev/null || true

git commit -m "docs(perf): add SP1 Day-3 gate artifacts

- sp1-alert-test.md / .png: induced-outage Telegram alert
  observed at <N>s (under 120s budget)
- sp1-voice-cellular-test.md: PWA voice path verified over
  cellular from <phone model>

Gate criteria #2 and #4 satisfied. 72h probe now running
via launchctl com.cruz.uptime (start: <timestamp>)."
```

Sanity check before `git commit`: `grep '<' <<< "$(git log -1 --pretty=%B)"` on any COMMITTED message should be empty. (Run this check AFTER committing; if placeholders leaked, amend with `git commit --amend -m "..."`.)

- [ ] **Step 7: Verify [CLAUDE-OK]**

```bash
git log -1 --stat
```

Expected: one commit, 2 or 3 files changed.

---

### Chunk 3 checkpoint

Before leaving the Mac running for Days 4–6, verify:

```bash
# Monitoring up
docker compose --profile monitoring ps | grep -Ec '(uptime-kuma|loki|grafana).*Up'  # expect: 3

# Probe running
launchctl list | grep -c com.cruz.uptime  # expect: 1

# Sleep disabled
pmset -g | grep -c 'disablesleep *1'  # expect: 1

# Services still healthy
pm2 status | grep -c 'online'  # expect: 5
curl -s localhost:3000/health | jq -re '.status'  # expect: healthy
```

All four should be true. If any is not, fix it before walking away.

---

## Chunk 4: Days 4–6 — Passive probe wait + Day 6 sign-off

**Chunk goal.** The probe runs untouched for 72h. Daily 2-min spot-check confirms nothing is actively breaking. Automated backup runs at cron(hour=4) at least twice during the window. On Day 6, compute final probe summary, append sign-off rows, revert sleep-disable, close the SP1 exit gate.

**Chunk exit criteria (all must hold — this closes SP1):**
- `scripts/uptime/check_stability.py --summary` reports `pct_ok ≥ 99.0` over the 72h window
- At least 2 backup files in Google Drive dated within the 72h window (cron hour=4 runs twice over 72h)
- `docs/perf/load_results.md` has an appended Uptime section row with the summary
- `PROGRESS.md` Phase 6 has a sign-off row referencing the commit sha
- `pmset` sleep state reverted
- One final commit landed: "chore(ops): SP1 sign-off — 72h probe <pct>% green"

After this chunk: SP1 exit gate is closed. SP2 brainstorming can start.

---

### Task 34: Day 4 spot-check (morning)

**Files:** none (read-only)

- [ ] **Step 1: Health still green [CLAUDE-OK]**

```bash
curl -s localhost:3000/health | jq -re '.status'                          # expect: healthy
curl -sS https://cruz.simpleinc.cloud/health | jq -re '.status'           # expect: healthy
launchctl list | grep com.cruz.uptime | awk '{print $1}'                  # expect: a PID, not 0 or -
pm2 status | grep -c 'online'                                             # expect: 5
```

- [ ] **Step 2: Recent probe activity [CLAUDE-OK]**

```bash
wc -l logs/uptime/stability.jsonl                          # should increase by ~12/hr since probe start
tail -1 logs/uptime/stability.jsonl | jq '{ts, ok, reason}' # most recent probe
```

Expected: line count grew, most recent probe within the last 10 min has `ok: true`.

- [ ] **Step 3: Do NOT touch anything else [HUMAN — discipline]**

No `pm2 restart`, no `docker compose restart`, no `.env` edits, no `git push` to branches that affect PM2 processes. The probe is measuring uninterrupted uptime — interrupting it resets the 72h clock.

If you discover a bug that's actively affecting uptime (e.g., Telegram alerts firing repeatedly): stop, note the time, decide whether it's severe enough to reset the probe. Small transient issues that self-recover are expected and consumed by the 99% budget (allows ≤8 failures in 864 probes).

- [ ] **Step 4: No commit**

---

### Task 35: Day 4 cron-backup verification

**Files:** none

- [ ] **Step 1: After the first 4 AM cron backup fires (any time Day 4 morning onward) [HUMAN]**

Open the Drive backup folder. Expected: a new set of `cruz-pg-*`, `cruz-redis-*`, `cruz-qdrant-*` files dated from the most recent 4 AM run. If missing:
- Check `pm2 logs cruz-worker` around 4 AM local time for the job trigger
- Check `services/backup.py` for RuntimeErrors in the logs
- If the automated cron didn't fire, re-trigger manually (same command as Task 23 Step 2) to keep the gate-criterion-#3 check passable with a fresh file; note the discrepancy in your scratch notes

- [ ] **Step 2: No commit**

---

### Task 36: Day 5 spot-check

**Files:** none

- [ ] **Step 1: Same health checks as Task 34 [CLAUDE-OK]**

Re-run the four curl/launchctl/pm2 commands from Task 34 Step 1. Re-run the tail from Task 34 Step 2.

- [ ] **Step 2: If anything is red [HUMAN]**

Note the time of the incident. If it self-recovered, let the probe continue. If it's still broken, debug via the usual paths (`pm2 logs`, docker logs, `journalctl` where applicable). Decide case-by-case whether to reset the probe.

Important mental model: **99% budget allows ~43 minutes of total downtime over 72h**. A 10-min blip consumes ~25% of the budget. Two such blips and you're perilously close to gate failure.

- [ ] **Step 3: No commit**

---

### Task 37: Day 6 — Probe summary (probe window reached ≥72h)

**Files:** none (summary is computed from `stability.jsonl`)

- [ ] **Step 1: Confirm probe has collected ≥72h of data [CLAUDE-OK]**

```bash
head -1 logs/uptime/stability.jsonl | jq -r '.ts'       # earliest ts
tail -1 logs/uptime/stability.jsonl | jq -r '.ts'       # latest ts
wc -l logs/uptime/stability.jsonl                       # total probes
```

Expected: difference between earliest and latest ts ≥ 259200s (72h). Expected total probes: ~864 (72h × 12 per hour at 5-min cadence). If fewer, wait until the 72h window closes (the launchd plist duration is 259200s so it will self-stop).

- [ ] **Step 2: Compute summary [CLAUDE-OK]**

```bash
source venv/bin/activate
python scripts/uptime/check_stability.py --summary \
  --output logs/uptime/stability.jsonl
```

Expected output (JSON):
```json
{ "total": 864, "ok": ≥856, "fail": ≤8, "pct_ok": ≥99.0 }
```

If `pct_ok < 99.0`, the gate fails. Enter the 25% fix-window (~1.5 days) per charter Section 5.1. If the fix window expires without recovery, SP1 is shelved per charter rules; otherwise start a new 72h probe after fixing.

- [ ] **Step 3: Save summary to a scratch file [CLAUDE-OK]**

```bash
python scripts/uptime/check_stability.py --summary \
  --output logs/uptime/stability.jsonl > /tmp/sp1-probe-summary.txt
cat /tmp/sp1-probe-summary.txt
```

- [ ] **Step 4: No commit yet** — summary is used in Task 38.

---

### Task 38: Stop probe, unload launchd, revert sleep

**Files:** none

- [ ] **Step 1: Unload the launchd agent [CLAUDE-OK]**

```bash
launchctl unload ~/Library/LaunchAgents/com.cruz.uptime.plist
```

Expected: no output. Verify:

```bash
launchctl list | grep com.cruz.uptime || echo "unloaded"
```

Expected: `unloaded` (the grep finds nothing).

- [ ] **Step 2: Revert pmset to pre-SP1 state [HUMAN — sudo]**

```bash
cat /tmp/sp1-pmset-before.txt       # reminder of pre-SP1 state
sudo pmset -a disablesleep 0        # allow sleep again
sudo pmset -a sleep 1               # set a modest idle-sleep timer (adjust to your preference)
```

Note: if you WANT the Mac to stay awake forever (it is your 24/7 command center, after all), you can skip the `sleep 1` revert and keep `disablesleep 1`. The spec treats sleep as an SP1-transitional constraint, not a permanent v2 config. If you keep it disabled, note that choice in the sign-off.

- [ ] **Step 3: Verify current pmset state [CLAUDE-OK]**

```bash
pmset -g | grep -E '^ *(sleep|disablesleep|displaysleep)'
```

Document what you chose in the sign-off.

- [ ] **Step 4: No commit** — system state, not repo.

---

### Task 39: Update docs/perf/load_results.md with uptime row + append PROGRESS.md sign-off

**Files:**
- Modify: `docs/perf/load_results.md`
- Modify: `PROGRESS.md`

- [ ] **Step 1: Append to load_results.md [HUMAN]**

Append (or create if missing) a section like:

```markdown
## Uptime test — SP1

| Run | Start (UTC) | End (UTC) | Probes | OK | Fail | pct_ok |
|---|---|---|---|---|---|---|
| SP1 | <start from /tmp/sp1-probe-start.txt> | <end ts> | <total> | <ok> | <fail> | <pct_ok> |

Full probe log: `logs/uptime/stability.jsonl` (not committed — regenerable).
```

Fill in with the summary values from Task 37.

- [ ] **Step 2: Append SP1 sign-off to PROGRESS.md [HUMAN]**

Find the Phase 6 section in `PROGRESS.md`. Append:

```markdown
SP1 sign-off — <YYYY-MM-DD>
  uptime:         pct_ok=<XX.X> (window: <start UTC> → <end UTC>, total=<N>, ok=<N>, fail=<N>)
  voice-cellular: verified (see docs/perf/sp1-voice-cellular-test.md)
  backup:         <cruz-pg-YYYYMMDD-HHMMSS>.dump landed at <UTC>
  alert:          verified (observed_latency_seconds=<N>, see docs/perf/sp1-alert-test.md)
  config:         cloudflared config option <X|Y>; pmset disablesleep <kept|reverted>
```

Note on sign-off format: the spec's Section 3 sign-off template lists a `commit:` line. The plan intentionally **omits** that field — it cannot hold the sha of the commit that itself adds the row (the sha only exists AFTER commit, and amending to backfill the sha would change the sha again, invalidating the reference). The final commit is discoverable via `git log --grep='SP1 sign-off'`.

The plan also enriches the uptime row with `total=`, `ok=`, `fail=` inside the window parens and adds a `config:` row documenting cloudflared-config-option and pmset choice. These are additive and not a deviation from the spec's intent; they preserve diagnostic detail that would otherwise live only in transient logs.

- [ ] **Step 3: Verify both files have the expected changes [CLAUDE-OK]**

```bash
git diff docs/perf/load_results.md PROGRESS.md
```

Expected: both show only the appended rows. No other files modified.

- [ ] **Step 4: Commit [CLAUDE-OK — fill in placeholders FIRST]**

Before running `git commit`, replace `<pct_ok>`, `<ok>`, `<total>`, `<N>` in the message below with actual numbers from Task 37.

```bash
git add docs/perf/load_results.md PROGRESS.md
git commit -m "chore(ops): SP1 sign-off — 72h probe <pct_ok>% green

Charter SP1 exit gate (all four) closed:
- 72h uptime: <pct_ok>% (<ok>/<total> probes)
- Voice-over-cellular: verified
- Automated backup: ≥1 file in Drive within 24h
- Induced-outage alert: DM within <N>s (budget 120s)

SP2 (Knowledge Base) brainstorming unblocked."
```

Post-commit sanity check:

```bash
git log -1 --pretty=%B | grep '<' && echo "PLACEHOLDER LEAK — amend the commit message" || echo "commit message clean"
```

Expected: `commit message clean`. If placeholders leaked, `git commit --amend -m "..."` with the filled-in version.

---

### Task 40: Close SP1, hand off to SP2

**Files:** none (status handoff only)

- [ ] **Step 1: Verify all 4 gate criteria documented [HUMAN]**

Re-read `PROGRESS.md` Phase 6 SP1 sign-off. All four criteria (uptime, voice-cellular, backup, alert) should have evidence.

- [ ] **Step 2: Final `/health` check [CLAUDE-OK]**

```bash
curl -s localhost:3000/health | jq -re '.status'                # expect: healthy
curl -sS https://cruz.simpleinc.cloud/health | jq -re '.status' # expect: healthy
pm2 status | grep -c 'online'                                   # expect: 5
```

- [ ] **Step 3: Announce [HUMAN]**

Announce in any relevant channels (internal TODO, notes file, Telegram to self): SP1 closed, <date>, <pct_ok>%. SP2 next.

- [ ] **Step 4: Optional — run `/clean_gone` or tidy local branches [CLAUDE-OK]**

If SP1 was built on a feature branch (likely the worktree you're in), merge it to your main trunk or open a PR. Discuss with the human whether to squash-merge — the commits are config/doc only and may be worth preserving individually.

---

### Chunk 4 checkpoint (= SP1 exit gate closed)

```bash
# Charter SP1 gate #1: uptime
jq -s '.[-1]' logs/uptime/stability.jsonl | jq '.ok'  # latest probe ok
# Re-run the summary for final pct_ok:
python scripts/uptime/check_stability.py --summary --output logs/uptime/stability.jsonl | jq '.pct_ok'
# Expect: ≥ 99.0

# Charter SP1 gate #2: voice-over-cellular
ls docs/perf/sp1-voice-cellular-test.md            # expect: exists, in git history

# Charter SP1 gate #3: automated backup
# (Manual — confirm Drive folder has ≥1 cruz-pg-*.dump from the 72h window)

# Charter SP1 gate #4: induced-outage alert
ls docs/perf/sp1-alert-test.md docs/perf/sp1-alert-test.png

# Sign-off recorded
git log -1 --oneline | grep 'SP1 sign-off'
```

If all four pass → SP1 complete. Hand off to SP2 brainstorming.

---

## Appendix A — What to do if a gate fails

| Gate | Failure mode | First action |
|---|---|---|
| #1 Uptime <99% | Probe captured too many failures | Read `logs/uptime/stability.jsonl`; group failure reasons; if they cluster around a specific subsystem (e.g., Ollama), fix that. Start a new 72h probe once the root cause is addressed. Only 1 fix-window restart per charter Section 5.1 (≤1.5 days). |
| #2 Voice-over-cellular | PWA mic request fails; no transcription; no streaming response | Diagnose via Tailscale first (prove CRUZ is responsive); then test PWA from Mac over localhost (rule out CORS); then cellular again. Most common cause: browser mic permission denied on phone. |
| #3 Automated backup | Cron didn't fire, or upload failed | Check `pm2 logs cruz-worker` at 4 AM local. If ARQ scheduler didn't trigger, verify `ecosystem.config.js` has the worker running and that `workers/arq_worker.py` WorkerSettings is correct. Re-trigger manually per Task 23 to prove the code path; then debug the schedule. |
| #4 Induced-outage alert | No DM within 120s | See Task 28 Step 3 fallback. Most common cause: Kuma Telegram channel not configured (Task 27 Step 3). |

## Appendix B — What to do if K2 time-overrun fires

Per charter Section 5.2 K2, SP1 overruns at 50% of 6-day estimate ≈ 3 days of slip (total 9 days). If that happens:

1. Stop active work.
2. List what's eaten the time (selector debugging? cert issues? GCP console friction?).
3. Decide: cut scope (options: skip Sentry — already done; skip Uptime Kuma — keep Loki only — trades visibility for speed), accept the slip (do not — charter forbids), or defer SP1 remainder to v2.1.
4. Document the decision in a short note appended to this plan file.
5. Charter's fix-window rule does NOT reset the K2 counter — fix-window time counts toward the overrun.

---

**End of SP1 plan.**

**Next:** SP2 — Knowledge Base — has its own brainstorm → spec → plan → execute cycle. Do NOT start SP2 code until SP1 exit gate is closed per Task 40.
