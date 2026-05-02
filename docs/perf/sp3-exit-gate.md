# SP3 Exit-Gate Verification

> Manual checklist filled in once at SP3 sign-off. Maps directly to charter §5.1 SP3 (modified by spec Override #2 — Messenger criterion deferred).

**Run on:** Mac Mini, with PM2 stack live (PostgreSQL, Redis, Qdrant, Ollama, FastAPI).

**Spec:** [`../superpowers/specs/2026-04-26-sp3-mac-controller-design.md`](../superpowers/specs/2026-04-26-sp3-mac-controller-design.md)
**Charter:** [`../superpowers/specs/2026-04-20-v2-program-charter.md`](../superpowers/specs/2026-04-20-v2-program-charter.md) §5.1 SP3

---

## Pre-flight

- [ ] PM2 process `cruz-api` is running (`pm2 list`)
- [ ] `/health` is green: `curl -s http://localhost:3000/health | jq`
- [ ] `~/.config/cruz/gcal-token.json` exists, mode 0600, not expired
- [ ] Calendar.app is open and subscribed to the Google account `gcal-token.json` is authenticated against (System Settings → Internet Accounts → Google → Calendars enabled)
- [ ] All unit tests pass: `pytest tests/ --ignore=tests/services/test_mac_controller_live.py --ignore=tests/agents/test_calendar_agent_live.py -q`
- [ ] Live mac tests pass: `CRUZ_LIVE_MAC_TESTS=1 pytest tests/services/test_mac_controller_live.py -v`
- [ ] Live calendar tests pass: `CRUZ_LIVE_MAC_TESTS=1 pytest tests/agents/test_calendar_agent_live.py -v`

---

## Exit-gate criteria (charter §5.1 SP3 + Override #2)

### G1 — `mac_screenshot` from a CRUZ tool call

- [ ] `curl -X POST http://localhost:3000/command -H 'Content-Type: application/json' -d '{"message":"take a screenshot of the screen and tell me how big it is", "stream":false}'`
- [ ] CRUZ picks `mac_screenshot` (verify in `agent_logs` filtered by trace_id)
- [ ] CRUZ replies with the byte size and mime type
- [ ] Operator confirmation: did the response indicate a non-zero PNG was captured? **YES / NO**

### G2 — `mac_clipboard_read` from a CRUZ tool call

- [ ] Manually copy a known string: `pbcopy <<< "sentinel-7f3a"`
- [ ] `curl -X POST http://localhost:3000/command -H 'Content-Type: application/json' -d '{"message":"what is on my clipboard right now", "stream":false}'`
- [ ] CRUZ picks `mac_clipboard_read`
- [ ] CRUZ replies containing `sentinel-7f3a`. **YES / NO**

### G3 — `mac_clipboard_write` from a CRUZ tool call

- [ ] `curl -X POST http://localhost:3000/command -H 'Content-Type: application/json' -d '{"message":"copy this to my clipboard: hello-from-cruz", "stream":false}'`
- [ ] CRUZ picks `mac_clipboard_write`
- [ ] Manually paste in Notes / TextEdit: `pbpaste` returns `hello-from-cruz`. **YES / NO**

### G4 — `mac_open_app` from a CRUZ tool call

- [ ] `curl -X POST http://localhost:3000/command -H 'Content-Type: application/json' -d '{"message":"open TextEdit for me", "stream":false}'`
- [ ] CRUZ picks `mac_open_app`
- [ ] TextEdit launches and comes to the foreground. **YES / NO**
- [ ] Cleanup: quit TextEdit (`osascript -e 'tell application "TextEdit" to quit'`)

### G5 — `mac_notify` from a CRUZ tool call

- [ ] `curl -X POST http://localhost:3000/command -H 'Content-Type: application/json' -d '{"message":"send me a reminder notification: take a break", "stream":false}'`
- [ ] CRUZ picks `mac_notify`
- [ ] Notification banner appears in macOS Notification Center. **YES / NO**

### G6 — Calendar event in BOTH Google Calendar AND Calendar.app

- [ ] `curl -X POST http://localhost:3000/command -H 'Content-Type: application/json' -d '{"message":"block 14:00 to 14:30 tomorrow as deep work", "stream":false}'`
- [ ] CRUZ picks `calendar_create_event`
- [ ] Open https://calendar.google.com — event visible at 14:00 tomorrow with title "deep work" (or similar). **YES / NO**
- [ ] Open Calendar.app on the Mac Mini — same event visible. **YES / NO**
- [ ] Cleanup: delete the event from Google Calendar (Calendar.app will sync the deletion within ~60s)

### G7 — Test calendar cleanup ran clean

- [ ] No `CRUZ TEST —` events remain in primary Google Calendar
- [ ] No `CRUZ TEST —` events remain in Calendar.app

---

## Sign-off

When all 7 gates above tick **YES**:

1. Append SP3 sign-off block to `docs/superpowers/PROGRESS.md`:

```markdown
## SP3 — Mac Controller (signed off YYYY-MM-DD)

- Mac Controller primitives (5 CRUZ tools) live and verified
- Calendar agent (3 CRUZ tools) live and verified
- Charter Override #1 (self-only auto-create) confirmed in production
- Charter Override #2 (Messenger deferred to v2.1) recorded in DEFERRED.md
- Exit gate: docs/perf/sp3-exit-gate.md ticked
- Live tests: docs/perf/sp3-exit-gate.md "Pre-flight" all green
```

2. Commit: `git commit -am "chore(sp3): sign-off — exit gate green"`

3. Notify Darshan; SP4 brainstorming may begin.
