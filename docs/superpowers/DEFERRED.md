# Deferred Tasks — SP1 & SP2

> Living checklist of operational/verification work that was intentionally deferred during SP1 and SP2 implementation. Per user direction (2026-04-26): probe testing and exit-gate verification will run together at the end of SP7, when the full system is brought up live.

**Owner:** Darshan Parmar
**Created:** 2026-04-26
**Last updated:** 2026-04-26

---

## SP1 — Finish Operational Deployment (deferred)

Code is complete (Phase 6 in PROGRESS.md). What remains is operator-side install + 4-criterion charter exit gate (charter §5.1 SP1).

### Day 1 / Day 2 — install & external services

- [ ] Run `pm2 save && pm2 startup` and confirm PM2 processes survive a test reboot (Mac Mini)
- [ ] Verify Cloudflare Tunnel resolves `cruz.simpleinc.cloud` from cellular
- [ ] Track B — Telegram bot wired to alerts (`services/alerts.py`) — fire test alert
- [ ] Track C — Google Cloud project + Drive API + service account JSON at `~/.config/cruz/gdrive-sa.json`
- [ ] Track C — Drive folder created and shared with `cruz-backup-sa@…iam.gserviceaccount.com` as **Editor** (not Viewer — silent-failure trap)
- [ ] Manual `run_backup` produces `cruz-pg-*.dump`, `cruz-redis-*.rdb`, `cruz-qdrant-*.tar.gz` in the Drive folder

### Day 3 — Charter override #2 (SPA mount)

- [ ] Confirm SPA-mount charter override #2 is documented and signed off (already drafted; verify still applies)

### Day 3 — Nightly cron

- [ ] launchd or cron entry for backup at 04:00 IST (Gate 3)
- [ ] Verify the first scheduled run lands in Drive within 24h of registration

### Days 4–6 — passive 72h probe + spot-checks

- [ ] Probe started: 2026-04-26T07:10:05Z → closes ~2026-04-29T07:10Z (was running at SP2 kickoff)
- [ ] Day-4 spot-check: `/health` green, no PM2 restarts, last alert non-critical
- [ ] Day-5 spot-check
- [ ] Day-6 spot-check
- [ ] GCP service-account key rotation before sign-off

### Charter SP1 exit gate (all 4 must hold simultaneously)

- [ ] **Gate 1:** 72h continuous uptime with `/health` green
- [ ] **Gate 2:** voice command from phone over cellular → streamed SSE response (already met — see `docs/perf/sp1-voice-cellular-test.md`)
- [ ] **Gate 3:** one successful automated backup landed in Drive within last 24h
- [ ] **Gate 4:** Telegram alert fires on deliberately induced failure (already met — see `docs/perf/sp1-alert-test.md` + `.png`)

### Sign-off

- [ ] Append SP1 sign-off block to `PROGRESS.md` per template in `docs/superpowers/plans/2026-04-20-sp1-operational-deployment.md` (line ~168)

### Three follow-ups raised during SP1 brainstorming (not gate-blocking)

- [ ] Qdrant backup retention policy (currently keeps all snapshots — needs prune rule)
- [ ] Drive OAuth flow vs service-account trade-off documented
- [ ] Locust load harness — one full run against prod Mac Mini, P95 baseline captured into `docs/perf/load_results.md`

---

## SP2 — Knowledge Base (deferred)

Code is complete (24 commits on `claude/frosty-chatelet-65f66f`, 673 tests pass). What remains is operator-side data population + charter exit gate.

### Task 23 — populate `local_path` for projects

- [ ] Update 5 project rows with absolute paths on Mac Mini:

```sql
UPDATE projects SET local_path = '/Users/darshan/Projects/ama-solutions'  WHERE slug = 'ama-solutions';
UPDATE projects SET local_path = '/Users/darshan/Projects/shooterista'    WHERE slug = 'shooterista';
UPDATE projects SET local_path = '/Users/darshan/Projects/suiteadvisors'  WHERE slug = 'suiteadvisors';
UPDATE projects SET local_path = '/Users/darshan/Projects/asia-capital'   WHERE slug = 'asia-capital';
UPDATE projects SET local_path = '/Users/darshan/Projects/midar'          WHERE slug = 'midar';
```

(Replace paths with actual Mac Mini locations.)

- [ ] Run `python scripts/seed_kb.py` against prod DB; confirm each of the 5 projects prints `indexed N docs`
- [ ] Spot-check Qdrant `cruz_projects_docs` collection has ≥1 point per project

### Task 24 — Charter SP2 exit gate (charter §5.1 SP2)

- [ ] **Gate A:** All 13 retrofitted agents passing tests + 1 RELAY exempt (charter override §11) — already met (673 tests pass on this branch)
- [ ] **Gate B:** `cruz_activities` Qdrant collection has ≥100 records from real daily use (accumulates over time once SP2 deploys)
- [ ] **Gate C:** Blind A/B test wins ≥2/3 rounds (instructions in `docs/superpowers/plans/2026-04-26-sp2-knowledge-base.md` Task 24 Step 3)
- [ ] **Gate C — supporting artifact:** `docs/perf/sp2-ab-test.md` filled in with all 3 rounds + verdict
- [ ] **Gate D:** P95 latency regression <20% vs SP1 baseline — run `./scripts/load/run_scenarios.sh all`, record in `docs/perf/load_results.md`

### Sign-off

- [ ] Append SP2 sign-off block to `PROGRESS.md` per template in `docs/superpowers/plans/2026-04-26-sp2-knowledge-base.md` Task 24 Step 5

### Two SP2 follow-ups (not gate-blocking)

- [ ] `services/llm.chat` does not yet exist — `_extract_and_write_pattern()` lazily imports it; either land a thin shim (one function call into the existing LLMRouter) or drop pattern inference until SP5 (where llm.chat may already exist for proactive agents)
- [ ] CRUZ retrofit `process()` and `stream_response()` are now mostly duplicate-shaped — consider a refactor to share KB hook logic. **Defer this** until SP3 lands and a third entry point is on the horizon (rule of three).

---

## SP3 — Messenger / iMessage (deferred to v2.1)

Pre-emptively cut from SP3 per charter §6 cut-list row 9 ("SP3 Messenger agent — use AppleScript primitives only, no agent"). Decision recorded in `docs/superpowers/specs/2026-04-26-sp3-mac-controller-design.md` Section 2 (Charter Override #2).

### Why deferred

- iMessage delivery via AppleScript (`tell application "Messages" to send`) has a silent-failure mode: AppleScript returns OK, message never delivers.
- The only reliable verification is read-only access to `~/Library/Messages/chat.db`, which requires Full Disk Access (TCC permission) granted to the Python process or PM2's launchd plist.
- The `chat.db` schema is undocumented and changes between macOS versions.
- The 10/10 delivery exit-gate criterion is achievable but the engineering + ongoing maintenance cost is disproportionate to SP3's strategic role (which is to provide Mac primitives that unblock SP6, not to ship messaging).

### What v2.1 must do if Messenger is reconsidered

- [ ] Decide transport: iMessage via AppleScript + chat.db verification, OR an alternative (Telegram, SMS gateway) that doesn't need TCC
- [ ] If sticking with iMessage: design Full Disk Access flow (one-time grant on Mac Mini; survives reboots; re-grant required on macOS major-version upgrade)
- [ ] Recipient input shape: phone (E.164) / email / contact name (resolves via `tell application "Contacts"`)
- [ ] Approval gate per Rule 4: default `send=False`, draft only; `send=True` proceeds
- [ ] Live tier needs 10 verified test recipients (charter §5.1 SP3 original criterion); requires deciding what "test recipient" means (multiple personal Apple IDs, or family/colleague consenting recipients)

### Re-evaluation trigger

After SP7 ships, when Full Disk Access is already granted for one-time monitoring use cases (e.g., voice daemon log access). At that point the marginal cost of adding Messenger drops materially.

---

## Tracking

When you run the end-of-SP7 verification batch:

1. Walk this file top-to-bottom — both SP1 and SP2 sections
2. Tick boxes as criteria are confirmed live
3. When all SP1 boxes ticked → append SP1 sign-off to `PROGRESS.md`
4. When all SP2 boxes ticked → append SP2 sign-off to `PROGRESS.md`
5. Once both signed off → delete or archive this file (e.g. move to `docs/superpowers/archive/2026-DEFERRED.md`)
