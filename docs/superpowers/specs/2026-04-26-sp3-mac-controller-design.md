# SP3 — Mac Controller (Layer 2) — Design Spec

**Date:** 2026-04-26
**Status:** Draft for user review
**Author:** Brainstormed with Darshan (2026-04-26)
**Charter:** [`2026-04-20-v2-program-charter.md`](2026-04-20-v2-program-charter.md)
**Sub-project:** SP3 (charter §2)
**Depends on:** SP1 (operational deployment, code complete; verification deferred per `docs/superpowers/DEFERRED.md`)
**Build budget:** 1 week (charter §2)
**Cut-triggers active:** §6 rows 9–11 (Messenger pre-emptively cut here; rows 10–11 remain available in-build)

---

## 1. Scope

### In scope

1. **`services/mac_controller.py`** — AppleScript-driven primitive layer for macOS host control. Four primitives, exposed as five typed CRUZ tools.
2. **`agents/calendar/calendar_agent.py`** — Calendar agent with Google Calendar OAuth (primary write) + Calendar.app AppleScript mirror (local visibility). Three CRUZ tools.

### Out of scope (deferred to v2.1)

- **Messenger agent + iMessage send.** Pre-emptive invocation of charter §6 cut-list row 9. Captured in `docs/superpowers/DEFERRED.md` for v2.1 reconsideration. Saves the riskiest piece of the original SP3 exit gate (Full Disk Access, `chat.db` schema fragility, silent-delivery-failure mode).

### Non-goals (explicit)

- No event update/delete tools (YAGNI; add when a real caller exists).
- No PyObjC dependency. AppleScript executes via `osascript` subprocess only.
- No load testing (volumes too low to matter — distinct from SP2's P95 gate).
- No periodic screen capture. SP6 owns on-demand screen perception.

---

## 2. Charter overrides (Rule 8)

Both overrides have user verbal approval (2026-04-26 brainstorming session). Re-affirmed by user approval of this spec.

### Override #1 — Rule 4 application (interpretation, not deviation)

**Rule cited:** Rule 4 — "All destructive or externally visible actions require explicit `context["send"] = True`."

**Default behavior:** All `create_event` calls return `requires_approval=True`.

**Override:** Calendar `create_event` auto-creates when `attendees == []` (self-only); calls with non-empty `attendees` require the approval gate.

**Reasoning:** Rule 4's text says "externally visible." A self-only calendar block (a future-self note like "block 2-4pm for AMA work") sends no email, generates no invite, and is not visible outside the user's own machine. It is not externally visible by any literal reading of the rule. Treating self-only blocks as a destructive action adds friction to the most common voice flow ("hey CRUZ, block tomorrow morning") with no safety benefit. Events with attendees DO trigger Google to send invite emails on insert — those remain gated.

**Blast radius if wrong:** A self-only calendar event created in error costs ~10 seconds to delete and is invisible to anyone but the user.

### Override #2 — Charter §5.1 SP3 exit gate (scope reduction)

**Rule cited:** Charter §5.1 SP3 row, criterion "Messenger sends iMessage to 10/10 test targets."

**Default behavior:** SP3 ships a Messenger agent that sends iMessage to 10/10 verified targets.

**Override:** Messenger criterion removed from SP3 exit gate. Messenger agent + iMessage send deferred to v2.1.

**Reasoning:** Pre-emptive invocation of charter §6 cut-list row 9 ("SP3 Messenger agent — use AppleScript primitives only, no agent"). The cut was already pre-committed by the charter; this spec invokes it now rather than mid-build. iMessage delivery requires Full Disk Access for `chat.db` read-only verification (the only way to detect AppleScript's silent-delivery failures), introduces a TCC permission burden, and the `chat.db` schema is undocumented and changes between macOS versions. The 10/10 gate is achievable but the engineering and ongoing maintenance cost is disproportionate to SP3's strategic role (which is to provide Mac primitives that unblock SP6, not to ship messaging).

**Blast radius if wrong:** Messenger is the lowest-leverage SP3 chunk. Deferring it does not block SP4–SP7. SP6 (Screen Perception) depends on Mac Controller primitives, not on Messenger.

### Revised exit gate

| Criterion | Status |
|---|---|
| ~~Messenger sends iMessage to 10/10 test targets~~ | **Deferred to v2.1** (Override #2) |
| Calendar creates events in both Calendar.app and Google Calendar | Required |
| Mac Controller primitives (screenshot, clipboard, app-open, notify) each tested live from a CRUZ tool call | Required |

---

## 3. Mac Controller (`services/mac_controller.py`)

### Module shape

Module-level singleton (matches `services/knowledge_base.py`, `services/db.py`). All public methods `async`. Builds AppleScript / shell strings, executes via `asyncio.create_subprocess_exec` with a 10s timeout. Non-zero return code raises `MacControllerError(stderr)`. No silent failures.

```python
# services/mac_controller.py

class MacControllerError(RuntimeError): ...

class MacControllerService:
    async def screenshot(self, region: tuple[int, int, int, int] | None = None) -> bytes: ...
    async def clipboard_read(self) -> str: ...
    async def clipboard_write(self, text: str) -> None: ...
    async def open_app(self, name: str) -> None: ...
    async def notify(self, title: str, body: str, sound: bool = False) -> None: ...

    # Internal helper used by Calendar agent only — not a CRUZ tool.
    async def _calendar_create_local(self, title: str, start_iso: str, end_iso: str) -> None: ...

def get_mac_controller_service() -> MacControllerService: ...
```

### Per-primitive specification

| Primitive | Mechanism | Notes |
|---|---|---|
| `screenshot` | `screencapture -x -t png -` reading binary stdout | `region` → `-R x,y,w,h`. Returns raw PNG bytes; SP6 will pass these to Claude Vision. |
| `clipboard_read` | `osascript -e 'the clipboard as text'` | Strips trailing newline; empty clipboard returns `""`. |
| `clipboard_write` | `osascript -e 'set the clipboard to "..."'` | All input strings escaped via `_escape_applescript_string` (handles `"`, `\`, newline, unicode). |
| `open_app` | `osascript -e 'tell application "X" to activate'` | App name is sanitized — only `[A-Za-z0-9 ._-]` allowed. AppleScript error → `MacControllerError`. |
| `notify` | `osascript -e 'display notification "body" with title "title"'` | `sound=True` appends `sound name "Submarine"`. Title and body escaped. |

### Approval gates (Rule 4)

None. Per Rule 4 ("destructive or externally visible"), the 5 primitives are local-only and not destructive in the rule's sense:

- `screenshot`, `clipboard_read` — read-only.
- `clipboard_write` — overwrites local clipboard state. Not externally visible. Annoying-but-not-dangerous; CRUZ frequently writes to clipboard for "copy this for me" flows.
- `open_app` — launches a local app. Locally visible to the user only.
- `notify` — fires a local notification. Visible only on the user's own Mac.

This is documented in the spec to prevent silent assumption.

### Logging (Rule 5)

Primitives are pure services. They do not write `agent_logs` themselves. Logging happens in the calling agent (CRUZ records the tool call as part of its own activity log, with the existing `trace_id` propagation from `BaseAgent.log()`).

### Knowledge base (Rule 3)

Not applicable. Primitives are services, not agents (Rule 1 — no agentic loop, no persistent state). CRUZ's existing KB write-back captures activity around the tool call.

### CRUZ tool registration

CRUZ's tool manifest (`agents/cruz/cruz_agent.py`) gains 5 entries with typed JSON schemas:

| Tool | Input schema |
|---|---|
| `mac_screenshot` | `{region?: [int, int, int, int]}` |
| `mac_clipboard_read` | `{}` |
| `mac_clipboard_write` | `{text: string}` |
| `mac_open_app` | `{name: string}` |
| `mac_notify` | `{title: string, body: string, sound?: boolean}` |

Dispatch in CRUZ's `_execute_tool` delegates to `get_mac_controller_service()`. Five new branches.

### Why discrete tools, not a single `mac_controller(action, params)` tool

A single dispatched tool would move schema validation from compile-time (per-tool JSON schema enforced by Anthropic's tool_use) to runtime (string-typed action switch in our code). That breaks the "tools as typed contracts" principle that makes Claude's routing reliable. Discrete tools cost 5 manifest entries and gain schema validation per call. Charter §1 cites tool_use as the routing mechanism; this respects that.

### Why split clipboard into read and write

Read and write have different blast radii. `clipboard_read` is trivially safe. `clipboard_write` overwrites user state (could wipe a copied password). Different blast radii → different tools makes Claude's reasoning easier and lets us add an approval gate later if `clipboard_write` ever becomes annoying.

---

## 4. Calendar Agent (`agents/calendar/calendar_agent.py`)

### Class shape (matches FORGE/ECHO)

```python
class CalendarAgent(BaseAgent):
    KNOWLEDGE_RINGS = ["cruz_activities", "cruz_user_patterns"]

    def __init__(self):
        super().__init__()
        self.name = "CALENDAR"

    async def process(self, input: AgentInput) -> AgentOutput: ...
```

The agent does **not** run an internal agentic loop (unlike FORGE). The CRUZ tool call already specifies one of the three operations; the agent is single-shot dispatch with optional natural-language parsing for `create_event`.

### Tool surface

Exposed to CRUZ via tool_use:

| Tool | Schema | Approval |
|---|---|---|
| `calendar_create_event` | `{title: string, start_iso: string, end_iso: string, attendees?: string[], description?: string, location?: string}` | Auto if `attendees` empty/absent. Approval gate if `attendees` non-empty. |
| `calendar_list_events` | `{start_iso: string, end_iso: string, calendar_id?: string}` | Read-only. No gate. |
| `calendar_find_free_slot` | `{duration_minutes: int, earliest_iso: string, latest_iso: string, working_hours?: [int, int]}` | Read-only. No gate. |

### Authentication (`services/gcal.py`)

OAuth 2.0 with stored refresh token (per Q5a = A; rejected: service account, reused Drive SA).

**One-time operator setup (`scripts/gcal_auth.py`):**
1. Run on Mac Mini: `python scripts/gcal_auth.py`.
2. Opens browser → consent screen for scope `https://www.googleapis.com/auth/calendar.events`.
3. Persists refresh token + client metadata to `~/.config/cruz/gcal-token.json` (mode 0600).
4. Confirms by listing calendars and printing primary.

**Runtime auth in `services/gcal.py`:**
- Wraps `google-auth` + `google-auth-oauthlib` + `google-api-python-client`.
- Refreshes access token transparently when expired.
- Public functions: `create_event(title, start, end, attendees=[], **kwargs) -> dict`, `list_events(start, end, calendar_id="primary") -> list[dict]`, `delete_event(event_id, calendar_id="primary") -> None` (used only by test cleanup).

**Env vars (added to `.env.example`):**
- `GCAL_CLIENT_ID`
- `GCAL_CLIENT_SECRET`
- `GCAL_TOKEN_PATH` (default `~/.config/cruz/gcal-token.json`)
- `GCAL_DEFAULT_CALENDAR_ID` (default `primary`)

**Scope:** `https://www.googleapis.com/auth/calendar.events` only. Not `calendar` or `calendar.readonly` — minimum needed.

### Dual-write semantics (Q5b = A)

Google Calendar is source-of-truth. Calendar.app is a mirror.

```
async def create_event(...):
    # Step 1 — Google API write.
    google_event = await gcal.create_event(...)
    if google_event is None:
        return AgentOutput(success=False, error="Google Calendar create failed")

    # Step 2 — AppleScript mirror (best-effort).
    try:
        await mac_controller._calendar_create_local(title, start_iso, end_iso)
    except MacControllerError as exc:
        logger.warning("Calendar.app mirror failed (non-fatal): %s", exc)
        # Google sync will reconcile — Calendar.app subscribes to the user's
        # Google account, so the event still appears within ~60s.

    return AgentOutput(success=True, result=google_event)
```

**Operator prerequisite (one-time, ticked at exit-gate run):** Calendar.app on the Mac Mini must already subscribe to the same Google account `gcal-token.json` is authenticated against. Documented in `docs/perf/sp3-exit-gate.md`. If the subscription is missing, the AppleScript mirror creates a local-only event that does NOT sync back to Google — but Step 1 has already succeeded, so the event exists in Google and will appear cross-device anyway.

### `find_free_slot` algorithm

Deterministic (no LLM call). Per Rule 2 — Qwen-default applies to other tasks; finding gaps is structured arithmetic, not language work.

```
1. Pull busy events from Google for [earliest_iso, latest_iso].
2. Subtract from working_hours window (default 09:00–18:00 in user's tz).
3. Iterate gaps; return first gap >= duration_minutes.
4. If no gap fits, return None and surface the suggestion (next-day window).
```

Working hours can be overridden per call. Future enhancement (NOT in this spec) reads default working hours from `cruz_user_patterns`.

### LLM use (Rule 2 — Q9b = A)

- Default model: Ollama `qwen2.5-coder:14b` for natural-language parsing of `create_event` requests like "block 2-4pm tomorrow for AMA work" → structured `{title, start_iso, end_iso}`.
- `intelligence: "high"` → Claude Sonnet 4.6 for ambiguous parsing or pattern-aware reasoning ("find me 2 hours next week that doesn't clash with deep work blocks and respects my morning routine").
- CRUZ is the only setter of `intelligence` (per Rule 2). The Calendar agent does not self-escalate.
- `find_free_slot` and `list_events` make zero LLM calls when called directly with structured args.

### Approval gate (Rule 4 + Override #1)

```python
needs_approval = bool(parsed.get("attendees"))
if needs_approval and not input["context"].get("send"):
    return AgentOutput(
        success=True,
        result=parsed,  # the draft event
        requires_approval=True,
        approval_prompt=(
            f"Send invite to {parsed['attendees']}?\n"
            f"  Title: {parsed['title']}\n"
            f"  When: {parsed['start_iso']}–{parsed['end_iso']}\n"
            "Reply 'yes' to send or 'no' to discard."
        ),
    )
# Self-only OR send approved → proceed.
await create_event(...)
```

Same shape as ECHO's send-mode branching, with the gate condition narrowed to `bool(attendees)`.

### Knowledge base hooks (Rule 3, Q9a = A)

`KNOWLEDGE_RINGS = ["cruz_activities", "cruz_user_patterns"]`.

**At process start** (matches FORGE/ECHO):
```python
kb_context = await kb.build_agent_context(input["task"], self.KNOWLEDGE_RINGS, input["trace_id"])
```

**At process end** (in `finally`, fire-and-forget):
```python
await kb.record_agent_activity("calendar", input["task"], summary, success, input["trace_id"])
```

**Time-of-day pattern learning:**
- When a user accepts a self-only block at hour H, fire `kb.observe_interaction("calendar", "preferred_block_hour", str(H))`.
- Threshold (5 observations) → background extract → `cruz_user_patterns` write ("Darshan prefers blocking morning hours" or similar).
- This is the path that lets "Darshan never books before 10am" emerge from observation, not configuration.
- Approval not required for `observe_interaction` (Rule 4 — internal only).

### Rule 1 satisfaction

Calendar passes the bar:
- (a) Multi-step agentic loop with tool_use? **No** — single-shot dispatch.
- (b) External integration beyond Claude/Ollama? **Yes** — Google Calendar API + Calendar.app via AppleScript.
- (c) Persistent state across invocations? **Yes** — OAuth refresh token, learned patterns in KB.

Two of three → qualifies as an agent (not a handler). Documented per Rule 1's requirement that sub-specs list which two criteria.

---

## 5. Testing strategy

Three tiers (Q10 = A).

### Unit tier

| File | Coverage |
|---|---|
| `tests/services/test_mac_controller.py` | Subprocess mocked. Asserts AppleScript escaping for special chars (apostrophes, newlines, unicode), region argument handling, returncode != 0 → `MacControllerError`, timeout handling. |
| `tests/services/test_gcal.py` | `httpx` / Google client mocked. Token refresh on expiry, expired-token retry, auth-error vs network-error distinction, dry-run mode. |
| `tests/agents/test_calendar.py` | Natural-language parse → structured fields, self-only auto-create vs attendees-approval branching, `find_free_slot` deterministic algorithm against fixed busy-list fixtures, KB hooks called with right args, error path on Google API failure. |

Runs on every commit. Linux-compatible (no real subprocess to macOS). Pre-commit hook unchanged.

### Live tier (env-gated `CRUZ_LIVE_MAC_TESTS=1`)

| File | Coverage |
|---|---|
| `tests/services/test_mac_controller_live.py` | Round-trip clipboard with sentinel string. Fire test notification (auto-dismissed). Open TextEdit, assert process exists, `pkill TextEdit`. Screenshot returns valid PNG (`PIL.Image.open` parses). |
| `tests/agents/test_calendar_live.py` | Create `CRUZ TEST — <uuid>` event with `attendees=[]` → assert visible in Google API list AND in Calendar.app via `osascript` query. Create with `attendees=["nonexistent-cruz-test@example.com"]` → assert `requires_approval=True` returned, no Google call made. |

**Safety:**
- Cleanup function runs in pytest `finalizer` even on failure — deletes all events with title prefix `CRUZ TEST —` from the last hour.
- Live tests skip with clear message if `CRUZ_LIVE_MAC_TESTS != 1`.
- Live tier never runs in CI.
- Run manually on Mac Mini before each commit that touches `services/mac_controller.py` or `agents/calendar/`, and once at SP3 sign-off.

### Exit-gate verification (`docs/perf/sp3-exit-gate.md`)

Manual checklist filled in once at SP3 sign-off. Each line maps to a charter §5.1 criterion:

- [ ] **Calendar.app subscribed to Google account** (`gcal-token.json` account == one of the accounts in Calendar.app preferences)
- [ ] **`mac_screenshot` from CRUZ:** `curl /command` with prompt that requires a screenshot → CRUZ picks `mac_screenshot` → returns PNG bytes → operator confirms image
- [ ] **`mac_clipboard_read` from CRUZ:** copy known string manually → curl /command → CRUZ returns the string
- [ ] **`mac_clipboard_write` from CRUZ:** curl /command → CRUZ writes specified string → operator pastes into Notes, confirms match
- [ ] **`mac_open_app` from CRUZ:** curl /command "open TextEdit" → CRUZ picks `mac_open_app` → TextEdit launches
- [ ] **`mac_notify` from CRUZ:** curl /command "remind me to take a break" → CRUZ picks `mac_notify` → notification appears
- [ ] **Calendar event created in BOTH:** curl /command "block 2-4pm tomorrow" → event in Google Calendar + visible in Calendar.app on Mac Mini
- [ ] **Test calendar cleanup ran clean:** no `CRUZ TEST —` events remain in primary calendar

Sign-off: append to `PROGRESS.md` once all 8 lines are ticked.

---

## 6. File layout & build order

### File additions

```
agents/
  calendar/                           # NEW
    __init__.py
    calendar_agent.py

services/
  mac_controller.py                   # NEW
  gcal.py                             # NEW

scripts/
  gcal_auth.py                        # NEW (one-time OAuth runner)

tests/
  services/
    test_mac_controller.py            # NEW (unit, mock subprocess)
    test_mac_controller_live.py       # NEW (live, env-gated)
    test_gcal.py                      # NEW (unit, mock httpx)
  agents/
    test_calendar.py                  # NEW (unit)
    test_calendar_live.py             # NEW (live, env-gated)

docs/perf/
  sp3-exit-gate.md                    # NEW (filled in at SP3 sign-off)
```

### Existing-file modifications (small, surgical)

- **`agents/cruz/cruz_agent.py`** — add 8 tool entries (5 mac + 3 calendar) to CRUZ's tool manifest + 8 dispatch branches in `_execute_tool`. No restructuring.
- **`.env.example`** — add 4 new env vars (`GCAL_CLIENT_ID`, `GCAL_CLIENT_SECRET`, `GCAL_TOKEN_PATH`, `GCAL_DEFAULT_CALENDAR_ID`).
- **`requirements.txt`** — add `google-auth`, `google-auth-oauthlib`, `google-api-python-client`.
- **`docs/superpowers/DEFERRED.md`** — add Messenger/iMessage v2.1 section.

**No DB migration.** KB writes use existing `cruz_user_patterns` / `cruz_activities` Qdrant collections + `learned_patterns` table (all from SP2).

### Build order (1 week, Q1 = A primitives-first)

| Day | Chunk | Deliverables |
|---|---|---|
| **1** | `services/mac_controller.py` skeleton + 4 primitives + escaping helper | Service module + unit tests passing (mocked) |
| **2** | CRUZ tool registration for 5 mac tools + live-tier mac tests | `test_mac_controller_live` passes on Mac Mini; CRUZ can call each tool via curl |
| **3** | `services/gcal.py` + `scripts/gcal_auth.py` + OAuth flow run | OAuth token persisted; `gcal.create_event` works against real account from REPL |
| **4** | `agents/calendar/calendar_agent.py` skeleton + `create_event` (self-only path) + AppleScript mirror | Self-only events round-trip via Google + Calendar.app |
| **5** | Calendar agent: `list_events`, `find_free_slot`, attendees+approval branching | Full 3-tool surface complete; unit tier green |
| **6** | Live-tier tests for Calendar + KB write-back wiring | `test_calendar_live` passes; `record_agent_activity` + `observe_interaction` firing |
| **7** | Exit-gate dry run + `docs/perf/sp3-exit-gate.md` filled + sign-off | All 8 exit-gate lines ticked; PR opened |

**Bounded fix window:** if day 7 closes red, charter §5.1 grants ≤25% of estimate (1.75 days, rounded to 2 days = day 9). At day 10 (>50% overrun), K2 fires → forced cut decision.

---

## 7. In-build cut-trigger order

Pre-committed. If something slips, cuts happen in this order — not re-litigated mid-week.

| Order | What gets cut | Saves | Trigger | Charter ref |
|---|---|---|---|---|
| **1** | Drop `observe_interaction` time-of-day learning (keep `record_agent_activity`) | ~2hr | Day 6 chunk slipping | KB-internal |
| **2** | Drop AppleScript Calendar mirror — ship Google-only | 1 day | Day 7 closes red OR mirror brittle in live tier | Charter §6 row 10 |
| **3** | Drop Calendar agent entirely — ship only Mac Controller primitives | 3+ days | Day 9 closes red (end of fix window) | Partial of charter §6 row 11 |
| **4** | Defer SP3 entirely to v2.1 | full week | K2 fires (day 10+) AND cuts 1–3 don't close the gap | Charter §6 row 11 |

**Cut decision authority:** Darshan only. Claude Code agents executing the plan surface trigger conditions; they do not unilaterally invoke cuts.

**Uncuttable inside SP3:** the 4 Mac Controller primitives. SP6 depends on `mac_screenshot` + `mac_open_app`. Cutting primitives ripples to SP6 (already cut at charter §6 row 3, so consistent — but leaves the program with no Layer 2 at all).

**Cut-trigger interpretation:** a cut requires a fired condition (test failure, day count, gate fail) — not "feeling behind."

---

## 8. Open questions / future enhancements

Out of scope for this spec. Listed so they don't get lost.

- **Update / delete event tools.** Add when a real caller exists (e.g., a future Reschedule agent). Both will need approval gates with attendees. Each opens a new blast-radius surface — not done speculatively.
- **Default working hours from KB.** `find_free_slot` could read user's `cruz_user_patterns` for default working hours instead of hard-coding 09:00–18:00. Add when there's a real complaint about the defaults.
- **Multi-calendar awareness.** Currently writes to `primary` (or `GCAL_DEFAULT_CALENDAR_ID`). Could route to project-tagged calendars (AMA / Shooterista / etc.) based on context. Future spec, post-v2.
- **Messenger / iMessage.** Deferred to v2.1. See `docs/superpowers/DEFERRED.md`. Re-evaluate after SP7 ships and Full Disk Access flow is one-time-paid for `chat.db` read.
- **Mac primitives — adjacent tools.** `app_close`, `app_focus`, `key_press`, `system_volume`. Add when there's a real caller (Rule 1 spirit).

---

## 9. Inheritance from charter

Per charter §8, this sub-spec inherits all §3 shared rules automatically. Cited explicitly:

| Rule | Application here |
|---|---|
| **Rule 1 — Agent inclusion** | Calendar passes (b) external integration + (c) persistent state. Mac Controller is a service, not an agent. |
| **Rule 2 — LLM escalation** | Calendar pinned to Ollama Qwen by default; CRUZ can set `intelligence: "high"` → Claude Sonnet 4.6. |
| **Rule 3 — Knowledge base** | Calendar declares `KNOWLEDGE_RINGS = ["cruz_activities", "cruz_user_patterns"]` and calls `build_agent_context` + `record_agent_activity`. |
| **Rule 4 — Approval gates** | Self-only events auto-create (Override #1, interpretation). Events with attendees gated. Mac primitives are not externally visible (none gated). |
| **Rule 5 — Trace and log** | Inherits `BaseAgent.log()` for Calendar. Mac Controller logging happens in CRUZ (the caller). |
| **Rule 6 — Token cap** | No new pin needed; Qwen is Ollama (zero token cost). Claude escalations counted under existing CRUZ budget. |
| **Rule 7 — Handler contract** | N/A — this spec adds no handlers. |
| **Rule 8 — Charter override** | Two overrides, Section 2. Both have user verbal approval; re-affirmed by approval of this spec. |

---

## 10. Sign-off

This spec is approved when:

1. User reviews and approves Section 2 (charter overrides) — these are the only deviations.
2. Spec-document-reviewer subagent passes.
3. User explicitly approves to proceed to writing-plans.

After approval, the next step is `superpowers:writing-plans` to produce an executable implementation plan. Implementation does NOT start in the current session — it lives in a separate session per the brainstorming-skill terminal state.
