# SP5 — Event Loop (Layer 4)

**Date:** 2026-04-26
**Status:** Draft for user review
**Sub-project of:** CRUZ v2 Program Charter (`docs/superpowers/specs/2026-04-20-v2-program-charter.md`)
**Inherits:** All charter Section 3 rules. Exit gate from charter Section 5.1. Cut-triggers from charter Section 6.
**Depends on:** SP1 (operational deployment) ✓, SP2 (Knowledge Base) ✓
**Soft-depends on:** SP4 (Browser Automation) — Funded Watcher and Warm Network gracefully degrade if SP4 has not shipped; SP5 ships regardless
**Enables:** Daily proactive value to user; serves as the substrate for SP3/SP7 notification channel registrations

---

## 1. Goal and scope

**Goal.** Make CRUZ proactive. Event-driven agents react to inbound webhooks (Gmail, Calendar, GitHub) and scheduled triggers without being asked, surface ≥3 actionable pings/day to Telegram, and never falsely interrupt the user.

**One-line description.** A central gate + notification router + event-driven agent base class, with 6 new agents and 6 new handlers, layered on top of v1's existing webhook + ARQ infrastructure.

### 1.1 In scope

- `services/proactive_engine.py` — `ProactiveEngine.allow()` gate: severity ladder, dedup, cooldown, global rate limit
- `services/notification_router.py` — Telegram-only in SP5; pluggable channel registry
- `services/agent_state.py` — `StateService` over new Postgres `agent_state` table
- `agents/event_driven_agent.py` — `EventDrivenAgent(BaseAgent)` base with `KNOWLEDGE_RINGS`, `TRIGGERS`, `CRITICAL_REASONS` declarations + `emit()` helper
- Alembic migration `0005_agent_state` — new Postgres table (Charter override under Rule 8)
- Webhook engine extension: `workers/tasks/webhook_tasks.py` extended to dispatch to registered event-driven agents (currently logs only)
- Six new agents in `agents/<name>/`:
  - `reply_triage`, `followup`, `meeting_prep`, `funded_watcher`, `warm_network`, `health_guardian`
- Six new handlers in `workers/handlers/<name>.py` (new directory):
  - `expense_auditor`, `portfolio_watcher`, `tax_helper`, `relationship_maintenance`, `travel_planner`, `daily_briefing`
- ARQ cron registrations in `workers/arq_worker.py` for the 6 handlers + Reply Triage's 5-minute Gmail-poll fallback + Gmail-watch resubscription cron + `agent_state` cleanup cron
- `scripts/calibrate_reply_triage.py` — day-1 50-email accuracy test
- Tests for every new module, written same day per dev standards

### 1.2 Out of scope

- iMessage / FCM / voice notification channels (ship as `NotificationRouter` registrations in SP3/SP7 — the router is built so they drop in)
- Cross-agent collision synthesis ("Orchestrator" agent — explicitly cut, see §10)
- Invoice tracking ("Invoice Enforcer" agent — explicitly cut, see §10)
- Browser-sourced signals for Reply Triage (per charter §6 row 12 fallback) and Warm Network — degrade gracefully if SP4 has not shipped
- Reply Triage learning loop (user corrections improving classifications over time) — deferred to v2.1
- Frontend UI for inspecting gate decisions, agent state, ping history — deferred
- Entity model linking emails ↔ invoices ↔ followups for the same client — deferred to v2.1 (current `project_id` linkage by email-domain matching is sufficient for SP5)

### 1.3 Success criteria — charter SP5 exit gate (verbatim)

> Reply Triage classifies 50 real emails with ≥80% agreement against user's manual judgment; ≥3 proactive pings/day for 7 consecutive days with no false-critical alerts.

Operationalized in §8.

---

## 2. Architecture

### 2.1 Event flow

```
                    ┌─────────────────────────────────────────┐
                    │ TRIGGER SOURCES                         │
                    │  • Webhooks (GitHub, Vercel, Calendar)  │
                    │  • Gmail watch + 5min poll fallback     │
                    │  • ARQ cron (handlers + RSS pulls)      │
                    │  • Health journal file watcher (daily)  │
                    └─────────────────┬───────────────────────┘
                                      ▼
                    ┌─────────────────────────────────────────┐
                    │ DISPATCH                                │
                    │  workers/tasks/webhook_tasks.py         │
                    │   → reads EVENT_REGISTRY by trigger     │
                    │   → enqueues agent.process()            │
                    └─────────────────┬───────────────────────┘
                                      ▼
              ┌───────────────────────┴────────────────────────┐
              ▼                                                ▼
   ┌────────────────────────┐                     ┌────────────────────────┐
   │ EVENT-DRIVEN AGENT     │                     │ HANDLER                │
   │  agents/<name>/        │                     │  workers/handlers/     │
   │  • Reads KB context    │                     │  • Reads KB context    │
   │  • LLM call (loop OK)  │                     │  • Single LLM call     │
   │  • emit() to gate      │                     │  • Returns dict        │
   │  • Writes agent_state  │                     │  • No persistent state │
   └─────────┬──────────────┘                     └─────────┬──────────────┘
             ▼                                              ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │ PROACTIVE ENGINE — gate.allow(GateRequest) → GateDecision          │
   │  1. Whitelist: critical iff reason_code ∈ agent.CRITICAL_REASONS   │
   │  2. Dedup: same (agent, dedup_key) within DEDUP_WINDOW → drop      │
   │  3. Per-agent cooldown: 1h any, 24h critical                       │
   │  4. Global rate: ≤8 pings/day across all agents                    │
   │  Returns: ALLOW | SUPPRESS | DEMOTE_TO_WARN | DEMOTE_TO_INFO       │
   └─────────┬──────────────────────────────────────────────────────────┘
             ▼ (if allow / demote)
   ┌────────────────────────────────────────────────────────────────────┐
   │ NOTIFICATION ROUTER                                                │
   │  channels = {telegram: TelegramChannel()}  ← SP3/SP7 add more       │
   │  for ch in channels: ch.send(severity, payload) if severity in ch  │
   └────────────────────────────────────────────────────────────────────┘
             │
             ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │ KB writeback (per Rule 3)                                          │
   │  kb.record_agent_activity(...) on every dispatch                   │
   └────────────────────────────────────────────────────────────────────┘
```

### 2.2 Why this shape (architectural rationale)

- **Webhook → ARQ → agent** reuses the exact pattern v1 already runs (HMAC verify → enqueue → background task in `workers/tasks/webhook_tasks.py`). The only addition is a registration table mapping event types to agent classes.
- **The gate is the single choke point** for severity, cooldown, rate limit, and dedup. One place to enforce the SP5 exit gate's "no false-criticals" requirement. Tested in isolation.
- **NotificationRouter is a registry, not a switch** — channels are registered at startup, not selected by routing logic in the agent or the gate. Future SP3 (`IMessageChannel`) and SP7 (`FCMChannel`, `VoiceDaemonChannel`) drop in as `register()` calls without touching the gate or any agent.
- **EventDrivenAgent layers on top of `BaseAgent`, doesn't replace it.** `KNOWLEDGE_RINGS` (per Rule 3), `TRIGGERS` (event types this agent subscribes to), `CRITICAL_REASONS` (whitelist of legitimate critical conditions) are class-level declarations the registry reads at startup.
- **Hybrid event-driven + governed.** Real-time response (no tick-loop polling) for events that matter (inbound email, calendar change), with a synchronous gate that enforces governance before any notification fires. Architecture decision documented in §11 Appendix.

### 2.3 Component ownership

| Component | New / extends | Lines (estimate) | Charter rules touched |
|---|---|---|---|
| `services/proactive_engine.py` | new | ~250 | Rule 5 (logs `gate_decision` to `agent_logs`) |
| `services/notification_router.py` | new | ~120 | — |
| `services/agent_state.py` | new | ~150 | **Rule 5 override** |
| `agents/event_driven_agent.py` | new | ~180 | Rules 1, 3, 4 |
| Alembic `0005_agent_state` | new | ~30 | Rule 5 override |
| `workers/tasks/webhook_tasks.py` | extends v1 | +~100 | Rule 5 |
| `workers/handlers/__init__.py` + 6 files | new dir | ~10 each | Rule 7 |
| `agents/<6 new agents>/` | new | ~250 each | Rules 1, 2, 3, 4 |
| `scripts/calibrate_reply_triage.py` | new | ~80 | — |
| Tests for each module | new | ~150 each | dev standards |

---

## 3. Core infrastructure

### 3.1 `agent_state` table (Charter override under Rule 8)

```sql
CREATE TABLE agent_state (
    agent_name  VARCHAR(50)  NOT NULL,
    key         VARCHAR(200) NOT NULL,
    value       JSONB        NOT NULL,
    expires_at  TIMESTAMP,                       -- nullable; null = never expires
    updated_at  TIMESTAMP    DEFAULT NOW(),
    PRIMARY KEY (agent_name, key)
);
CREATE INDEX idx_agent_state_expires
    ON agent_state(expires_at) WHERE expires_at IS NOT NULL;
```

**Use cases (representative):**

| Agent | Key pattern | Value | TTL |
|---|---|---|---|
| `reply_triage` | `last_classified:<message_id>` | `{label, urgency, client_match, confidence, reason}` | 30d |
| `reply_triage` | `false_critical:<dedup_key>` | `{ack_at, raw_payload}` | 365d |
| `health_guardian` | `streak:sleep_n` | integer | none |
| `health_guardian` | `intervention_history` | list of `{at, type, dedup_key}` | 365d |
| `followup` | `queue` | list of `{client, due_date, thread_id}` | none |
| `funded_watcher` | `seen_articles` | set of URLs | 90d |
| `_global` | `daily_count:<YYYY-MM-DD>` | integer | 30d |
| `_gate` | `cooldown:<agent>:any` | timestamp | computed |
| `_gate` | `cooldown:<agent>:critical` | timestamp | computed |
| `_gate` | `dedup:<agent>:<dedup_key>` | timestamp | DEDUP_WINDOW |

`services/agent_state.py` provides:

```python
class StateService:
    async def get(self, agent: str, key: str, default: Any = None) -> Any: ...
    async def set(self, agent: str, key: str, value: Any,
                  ttl_seconds: int | None = None) -> None: ...
    async def delete(self, agent: str, key: str) -> None: ...
    async def cleanup_expired(self) -> int: ...   # called by daily cron
```

Hot reads (cooldown, dedup checks during gate evaluation) cache through Redis with the same key; cold reads hit Postgres. Source of truth is Postgres so state survives Redis restarts during the 7-day exit-gate measurement window.

**Charter override block (per Rule 8):**

> **Override Rule 5 (no new logging tables; add JSONB to `agent_logs`).**
> *Reason:* `agent_logs` is an append-only event/audit log. Mutable per-agent state (cooldown timers, streak counters, dedup sets, follow-up queues) is a different concern; storing it in `agent_logs` would require unbounded `ORDER BY created_at DESC LIMIT 1` reads on a fast-growing table and corrupts the trace-log semantics that Rule 5 is protecting.
> *Rule 5's intent is preserved:* `agent_state` is not a log; it does not fragment the `agent_logs` trace surface. All audit/trace events continue to land in `agent_logs`.
> *Alternatives rejected:*
> - Redis-only — loses cooldown and streak state on restart; unacceptable risk during the 7-day exit-gate measurement window.
> - `users.preferences` JSONB — turns into a junk drawer mixing learned patterns with hot agent state.
> - JSONB column on `agent_logs` — see "reason" above.

### 3.2 `ProactiveEngine` — the gate

```python
# services/proactive_engine.py

class GateDecision(Enum):
    ALLOW           = "allow"
    SUPPRESS        = "suppress"        # rate limit, dedup, or critical cooldown
    DEMOTE_TO_WARN  = "demote_warn"     # critical without whitelisted reason
    DEMOTE_TO_INFO  = "demote_info"     # warn during active per-agent cooldown

@dataclass
class GateRequest:
    agent: str
    severity: Literal["info", "warn", "critical"]
    reason_code: str | None     # required when severity == "critical"
    dedup_key: str               # e.g. "email:<message_id>", "client:ama"
    payload: dict                # for the notification

class ProactiveEngine:
    GLOBAL_DAILY_RATE_LIMIT = 8           # max non-info pings/day across all agents
    PER_AGENT_COOLDOWN_ANY  = 3600        # 1h between any pings from same agent
    PER_AGENT_COOLDOWN_CRIT = 86400       # 24h between criticals from same agent
    DEDUP_WINDOW            = 86400 * 7   # 7d dedup on (agent, key)

    async def allow(self, req: GateRequest) -> GateDecision: ...
```

**Decision algorithm (in order, short-circuit on first match):**

1. If `severity == "critical"`:
   - If `req.reason_code` is `None` or not in the agent's `CRITICAL_REASONS` → **DEMOTE_TO_WARN** (log violation; the gate is the structural defense against false-criticals).
2. Read `_gate.dedup:<agent>:<dedup_key>`. If set within `DEDUP_WINDOW` → **SUPPRESS**.
3. If `severity == "critical"`:
   - Read `_gate.cooldown:<agent>:critical`. If within `PER_AGENT_COOLDOWN_CRIT` → **SUPPRESS**.
4. Read `_gate.cooldown:<agent>:any`. If within `PER_AGENT_COOLDOWN_ANY`:
   - If `severity == "info"` → **ALLOW** (info isn't rate-limited at agent level).
   - Else → **DEMOTE_TO_INFO**.
5. Read `_global.daily_count:<YYYY-MM-DD>`. If `>= GLOBAL_DAILY_RATE_LIMIT` AND `severity != "info"` → **SUPPRESS** (`info` still routed; high-frequency `info` is collapsed by Daily Briefing).
6. Otherwise → **ALLOW**.

On `ALLOW` (or any DEMOTE that still routes), update:
- `_gate.cooldown:<agent>:any` ← now
- `_gate.cooldown:<agent>:critical` ← now (if severity was critical and reason whitelisted)
- `_gate.dedup:<agent>:<dedup_key>` ← now (TTL = DEDUP_WINDOW)
- `_global.daily_count:<YYYY-MM-DD>` ← incremented (skip for `info`)

Every gate decision is logged to `agent_logs` with `action="gate_decision"` so the Daily Briefing handler can summarize "what was suppressed today and why."

### 3.3 `NotificationRouter`

```python
# services/notification_router.py

class Channel(Protocol):
    name: str
    handles_severities: set[str]

    async def send(self, severity: str, payload: dict) -> None: ...

class NotificationRouter:
    def __init__(self) -> None:
        self._channels: list[Channel] = []

    def register(self, channel: Channel) -> None: ...

    async def route(self, severity: str, payload: dict) -> None:
        for ch in self._channels:
            if severity in ch.handles_severities:
                try:
                    await ch.send(severity, payload)
                except Exception as exc:
                    logger.warning("channel %s failed: %s", ch.name, exc)
```

**SP5 ships exactly one channel:**

```python
class TelegramChannel(Channel):
    name = "telegram"
    handles_severities = {"info", "warn", "critical"}

    async def send(self, severity, payload):
        # info     → silent message in #cruz-feed thread (disable_notification=True)
        # warn     → normal message
        # critical → message with notification + inline button "❌ False alarm"
        #            Button click → POST /notifications/false-alarm
        #            → writes agent_state(agent, "false_critical:<dedup_key>")
```

**Future channel registrations (do not ship in SP5):**

```python
# Added in SP3:
class IMessageChannel(Channel):
    name = "imessage"
    handles_severities = {"critical"}   # only criticals reach iMessage
    async def send(self, severity, payload):
        await get_mac_controller().send_imessage(USER_HANDLE, payload["text"])

# Added in SP7:
class FCMChannel(Channel):
    name = "fcm"
    handles_severities = {"warn", "critical"}
    ...

class VoiceDaemonChannel(Channel):
    name = "voice"
    handles_severities = {"critical"}
    async def send(self, severity, payload):
        await get_voice_daemon().speak(payload["text"])
```

The router and the gate do not change between SP5 and SP3/SP7; only `NotificationRouter.register(...)` calls are added.

### 3.4 `EventDrivenAgent` base class

```python
# agents/event_driven_agent.py

class EventDrivenAgent(BaseAgent):
    """Layer on top of BaseAgent for SP5 proactive agents."""

    KNOWLEDGE_RINGS: list[str]          = []   # Rule 3 — declared per agent
    TRIGGERS: list[str]                  = []   # event types this agent subscribes to
    CRITICAL_REASONS: dict[str, str]     = {}   # whitelist: code → human description
    DEFAULT_DEDUP_TTL_SECONDS: int       = 7 * 86400

    async def process(self, input: AgentInput) -> AgentOutput:
        """Standard BaseAgent contract — subclasses implement."""

    async def emit(
        self,
        severity: Literal["info", "warn", "critical"],
        reason_code: str | None,
        dedup_key: str,
        payload: dict,
    ) -> GateDecision:
        """Convenience: build GateRequest, call gate, route notification."""
        req = GateRequest(
            agent=self.name,
            severity=severity,
            reason_code=reason_code,
            dedup_key=dedup_key,
            payload=payload,
        )
        decision = await get_proactive_engine().allow(req)
        if decision == GateDecision.ALLOW:
            await get_notification_router().route(severity, payload)
        elif decision == GateDecision.DEMOTE_TO_WARN:
            await get_notification_router().route("warn", payload)
        elif decision == GateDecision.DEMOTE_TO_INFO:
            await get_notification_router().route("info", payload)
        # SUPPRESS: silent
        return decision
```

**Registry built at app boot:**

```python
EVENT_REGISTRY: dict[str, list[type[EventDrivenAgent]]] = {}

def register_event_agents() -> None:
    for cls in discover_event_driven_agents():
        for trigger in cls.TRIGGERS:
            EVENT_REGISTRY.setdefault(trigger, []).append(cls)
```

`workers/tasks/webhook_tasks.py` reads from `EVENT_REGISTRY[trigger]` and enqueues each registered agent's `process()` with the event payload as `AgentInput["context"]["event"]`.

### 3.5 Webhook engine extension (additive)

The existing v1 webhook tasks (`process_github_webhook`, `process_vercel_webhook`, `process_google_calendar_webhook`) currently parse + log only. SP5 extends them with a single trailing block:

```python
# At the end of each existing process_*_webhook function:
trigger = _trigger_for_webhook(event, payload)   # e.g. "webhook.gmail.new_message"
for cls in EVENT_REGISTRY.get(trigger, []):
    pool = await get_arq_pool()
    await pool.enqueue_job(
        "dispatch_event_to_agent",
        cls.__module__,
        cls.__name__,
        {"event": payload, "trigger": trigger},
    )
```

`dispatch_event_to_agent` is a new ARQ task that instantiates the agent class and calls `process()`. The original logging behavior is unchanged — the dispatch is purely additive.

A new `gmail_webhook_tasks.py` file adds `process_gmail_webhook` (Pub/Sub push notification handler — Gmail's notification mechanism uses Google Cloud Pub/Sub, requiring a `POST /webhooks/gmail` endpoint that verifies Pub/Sub auth and enqueues the task). A 5-minute polling fallback (`cron.5min.gmail_poll`) covers Gmail-watch expiry windows.

---

## 4. The 6 agents (Rule 1 justifications)

Per charter §3 Rule 1, each agent must satisfy **2 of 3** of: (a) multi-step agentic loop with `tool_use`, (b) external integration beyond Claude/Ollama, (c) persistent state across invocations.

| Agent | (a) loop | (b) external | (c) state | Score |
|---|---|---|---|---|
| Reply Triage | ✓ tool_use: `classify`, `fetch_thread_context`, `read_user_pattern` | ✓ Gmail API | ✓ classification cache, false-positive log | **3/3** |
| Followup | ✓ tool_use: `read_sent_folder`, `read_plane_tasks`, `check_thread_replied` | ✓ Gmail + Plane.so | ✓ followup queue, last-replied tracker | **3/3** |
| Meeting Prep | ✓ tool_use: `fetch_calendar_event`, `fetch_attendee_threads`, `fetch_notion_meeting_notes` | ✓ Calendar + Gmail + Notion | ✓ per-meeting dedup | **3/3** |
| Funded Watcher | ✓ tool_use: `fetch_rss(feed)`, `scrape_article(url)`, `match_icp` | ✓ RSS feeds + browser scrape (post-SP4) | ✓ seen-articles set | **3/3** |
| Warm Network | ✓ tool_use: `rank_contacts`, `fetch_last_interaction`, `fetch_linkedin_signal` (post-SP4) | ✓ Gmail + LinkedIn (post-SP4) | ✓ last-nudge per contact | **3/3** |
| Health Guardian | ✓ tool_use: `read_journal`, `compute_streak`, `read_intervention_history`, `draft_intervention` | ✗ file-only | ✓ streak counters, intervention history | **2/3** |

All 6 declare `KNOWLEDGE_RINGS` and call `kb.build_agent_context()` + `kb.record_agent_activity()` per Rule 3.

### 4.1 Reply Triage (gate-determining)

```python
class ReplyTriageAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_activities", "cruz_user_patterns"]
    TRIGGERS         = ["webhook.gmail.new_message", "cron.5min.gmail_poll"]
    CRITICAL_REASONS = {
        "client_email_unanswered_72h":
            "Email from a known client requires reply, age >72h",
    }
```

- **Default model:** Qwen `qwen2.5-coder:14b` (per Rule 2). Day-1 calibration (§8.1) determines whether to flip to Claude. If flipped, a Rule 8 override is added to this spec at calibration time.
- **Classification output schema:**
  ```json
  {
    "label": "needs_reply" | "fyi" | "spam" | "promo",
    "urgency": "now" | "today" | "this_week" | "later",
    "client_match": "<projects.id>" | null,
    "confidence": 0.0-1.0,
    "reason": "<short explanation>"
  }
  ```
- **`client_match` resolution:** sender's email domain matched against `projects` table seeded by SP2 (e.g., `@ama.com` → `slug="ama-solutions"`). The activity record gets `project_id` for KB linkage.
- **Critical fires only when ALL hold:**
  - `label == "needs_reply"`
  - `urgency in {"now", "today"}`
  - `client_match is not None`
  - email age > 72h
- This conjunction is the structural defense against false-criticals — anything missing one condition demotes to `warn`.

### 4.2 Followup

```python
class FollowupAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_activities", "cruz_user_patterns"]
    TRIGGERS         = ["cron.daily.10:00", "webhook.gmail.outbound_sent"]
    CRITICAL_REASONS = {
        "followup_due_5d":
            "Outbound message to a client received no reply in 5 days",
        "client_promised_deliverable_overdue":
            "A deliverable promised to a client is past its committed date",
    }
```

- Maintains a `queue` in `agent_state` of `{client, sent_at, thread_id, due_date}` records.
- Daily cron evaluates each queue entry; thread-replied check via Gmail API removes resolved items.
- Plane.so integration reads tasks tagged `client_commitment` for the deliverable-overdue reason.

### 4.3 Meeting Prep

```python
class MeetingPrepAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_activities", "cruz_projects_docs"]
    TRIGGERS         = ["webhook.google-calendar.event_starts_in_30min"]
    CRITICAL_REASONS = {}   # never fires critical — wrong prep doesn't warrant interruption
```

- Calendar webhook delivers events; Meeting Prep filters to events starting in 25–35 min.
- Composes a Telegram `warn` with: agenda summary, attendee context (last 5 emails per attendee), recent Notion notes mentioning the project.
- Per-meeting dedup key = `meeting:<event_id>`.

### 4.4 Funded Watcher

```python
class FundedWatcherAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_activities", "cruz_domain_knowledge"]
    TRIGGERS         = ["cron.daily.08:00"]
    CRITICAL_REASONS = {}   # warn-only; "company fits ICP" is not a 3am-wake event

    RSS_FEEDS = [
        "https://techcrunch.com/feed/",
        "https://yourstory.com/rss",
        "https://inc42.com/feed/",
        "https://hnrss.org/newest?points=100",   # Hacker News high-signal
    ]
```

- Pre-SP4: RSS-only (feed pulls + Claude ICP-match against user's freelance offering).
- Post-SP4: adds Crunchbase News browser-scrape via `services/browser.py`.
- `seen_articles` set in `agent_state` (TTL 90d) prevents re-flagging.

### 4.5 Warm Network

```python
class WarmNetworkAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_activities", "cruz_user_patterns"]
    TRIGGERS         = ["cron.weekly.monday.09:00"]
    CRITICAL_REASONS = {}   # warn-only
```

- Pre-SP4: stub returning empty (logs warning; emits no notification). Tested in this state.
- Post-SP4: ranks LinkedIn contacts by (a) recency of their activity, (b) signal of openness to conversation (job change, post comments), (c) staleness of last contact (>6w in Gmail).
- Suggests 1–3 people to reach out to, with a draft opener (per Rule 4, draft only — no auto-send).
- `last_nudge:<contact_id>` per-contact dedup.

### 4.6 Health Guardian

```python
class HealthGuardianAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_user_patterns"]
    TRIGGERS         = ["cron.daily.21:00", "filewatch.health_journal"]
    CRITICAL_REASONS = {
        "health_3n_streak":
            "Three consecutive Ns in any single dimension over the rolling 7d window",
    }
    JOURNAL_PATH = "docs/personal/health-journal.md"
```

- Inputs are **journal-only** per design decision (charter K3 itself is journal-only).
- Reads journal; computes 3 rolling-7d streaks (sleep_n, commitments_n, relationship_n).
- If any dimension hits 3 N's: critical with reason `health_3n_streak`.
- Tool-use loop drafts the intervention message: `read_intervention_history` → choose intervention type that wasn't used in last 7 days → `draft_intervention` (Claude Sonnet, persona-aware) → emit.
- Streak counters and intervention history persist in `agent_state` indefinitely.

### 4.7 K1 cut-readiness (per charter §6 row 6 + row 2)

K1 fires after SP4 ships if no paid client lands in 6 weeks. Surviving 3 agents = **Reply Triage, Followup, Health Guardian**. All three are journal/Gmail/Plane-only — no SP4 dependency. They run identically on K1-cut SP5.

---

## 5. The 6 handlers (Rule 7 contract)

Each handler is a scheduled-prompt + Claude/Ollama call with no tool-use loop and no persistent agent state. Lives in `workers/handlers/<name>.py` per Rule 7.

```python
# workers/handlers/<name>.py
async def handle(payload: dict, context: HandlerContext) -> HandlerResult: ...
```

`HandlerContext` provides `kb`, `db`, `trace_id`, `now`. Handlers can call `kb.build_agent_context()` (per Rule 3) but cannot be invoked as CRUZ tools (per Rule 7). All handlers route through the gate at `info` severity only — they cannot bypass to `warn`/`critical`.

| Handler | Schedule | Inputs | Output | Rule 1 score |
|---|---|---|---|---|
| **Expense Auditor** | `cron.monthly.1st.09:00` | Gmail vendor receipts (last 30d) + Notion expense log | Telegram digest of categorized expenses + missing receipts | 1/3 |
| **Portfolio Watcher** | `cron.weekly.friday.17:00` | RSS feeds tagged with each client's tech stack (from `projects.tech_stack`) | Telegram digest of relevant tech news per client | 1/3 |
| **Tax Helper** | `cron.quarterly.1st.10:00` (Apr/Jul/Oct/Jan) | Gmail + Notion expense log | Telegram message + Notion page draft: GST/income-tax checklist | 1/3 |
| **Relationship Maintenance** | `cron.weekly.sunday.18:00` | Gmail (last-contact timestamps for known contacts) | Telegram digest: 3 people you haven't messaged in >6w | 0/3 |
| **Travel Planner** | `webhook.google-calendar` (event with `location:` outside city) | Calendar event | Telegram digest: travel logistics + suggested checklist | 1/3 |
| **Daily Briefing** | `cron.daily.07:00` | `agent_state` + `agent_logs` last 24h | Telegram digest: collapsed `info`-tier pings + agent activity summary | 0/3 |

**K1 cut surface:** Expense Auditor, Portfolio Watcher, Tax Helper, Relationship Maintenance, Travel Planner — all listed in charter §6 row 6, deletable. Daily Briefing is not in any cut row but loses most value when only 3 agents remain; kept as low-cost survivor since the file is ~80 lines.

---

## 6. Trigger inventory

Complete list of triggers that the SP5 agents and handlers subscribe to. Anything not on this list is not a SP5 trigger.

| Trigger | Source | Subscribers |
|---|---|---|
| `webhook.gmail.new_message` | Gmail Pub/Sub push (new endpoint `POST /webhooks/gmail`) | Reply Triage |
| `cron.5min.gmail_poll` | New ARQ cron — Gmail-watch expiry fallback | Reply Triage |
| `webhook.gmail.outbound_sent` | Gmail Pub/Sub push (filtered) | Followup |
| `webhook.google-calendar.event_starts_in_30min` | Computed: Google Calendar webhook → `dispatch_event_to_agent` filters to events 25–35min out | Meeting Prep |
| `webhook.google-calendar` (event with `location:` outside city) | Existing webhook; new location filter | Travel Planner |
| `webhook.github` | Existing v1 endpoint | (none new in SP5; remains v1 logging) |
| `webhook.vercel` | Existing v1 endpoint | (none new in SP5; remains v1 logging) |
| `cron.daily.08:00` | New ARQ cron | Funded Watcher |
| `cron.daily.10:00` | New ARQ cron | Followup |
| `cron.daily.21:00` | New ARQ cron | Health Guardian |
| `filewatch.health_journal` | New filesystem watcher on `docs/personal/health-journal.md` | Health Guardian |
| `cron.weekly.monday.09:00` | New ARQ cron | Warm Network |
| `cron.weekly.friday.17:00` | New ARQ cron | Portfolio Watcher (handler) |
| `cron.weekly.sunday.18:00` | New ARQ cron | Relationship Maintenance (handler) |
| `cron.monthly.1st.09:00` | New ARQ cron | Expense Auditor (handler) |
| `cron.quarterly.1st.10:00` | New ARQ cron | Tax Helper (handler) |
| `cron.daily.07:00` | New ARQ cron | Daily Briefing (handler) |
| `cron.daily.06:00` | New ARQ cron | Gmail-watch resubscription (no agent — infrastructure cron) |
| `cron.daily.04:30` | New ARQ cron | `agent_state` cleanup (no agent — infrastructure cron) |

---

## 7. Notification surface

**Telegram-only in SP5.** Three threads in the user's existing CRUZ Telegram chat:

| Severity | Telegram behavior |
|---|---|
| `info` | `disable_notification=True` posted to `#cruz-feed` topic. Folded into Daily Briefing. |
| `warn` | Normal message in the main chat thread. |
| `critical` | Message in main thread with iOS notification + inline button `❌ False alarm`. Click hits `POST /notifications/false-alarm` which writes `agent_state(<agent>, "false_critical:<dedup_key>")` and surfaces the violation for human review (tracked toward exit-gate failure). |

**SP3/SP7 channel additions** (not built in SP5): see §3.3.

---

## 8. Exit gate plan (per charter §5.1)

> *Reply Triage classifies 50 real emails with ≥80% agreement against user's manual judgment; ≥3 proactive pings/day for 7 consecutive days with no false-critical alerts.*

### 8.1 Reply Triage calibration (day 1 of SP5 execution)

`scripts/calibrate_reply_triage.py`:
1. Pull last 50 inbound emails from Gmail.
2. For each: agent classifies → CLI presents `(subject, sender_excerpt, agent_label, agent_urgency)`.
3. User keys in their own label (4 options) and urgency (4 options).
4. Script computes per-field agreement rate (label-match-rate, urgency-match-rate, joint-match-rate).
5. **Pass criterion:** joint-match-rate ≥ 80%.
6. **If pass on Qwen:** ship Qwen.
7. **If fail on Qwen:** flip config (`AGENT_MODEL_CONFIG["reply_triage"] = "claude-sonnet-4-6"`), add Rule 8 override block to this spec, re-run calibration. Cost impact: ~₹22/mo.
8. **If fail on Claude:** SP5 enters fix window per charter §5.1. Likely root cause: classification schema needs refinement; iterate on prompt + schema, not on model.

### 8.2 Seven-day proactive measurement window

Days 8–14 of SP5 execution (after agents have a week of warmup data in `agent_state`).

- Daily Briefing handler aggregates from `agent_logs`: `pings_count_by_severity`, `pings_count_by_agent`, `false_critical_acks` (from `agent_state` `false_critical:*` records added in window).
- **Pass criteria (all must hold):**
  - Every day in window has `count(severity in {info, warn, critical}) >= 3`.
  - `count(false_critical_acks during window) == 0`.
- **Failure modes:**
  - Any single day with a false-critical ack → window resets from that day.
  - Any single day with `<3` pings → window resets.
  - Two consecutive resets → bounded fix window (per charter §5.1).
- **Exception case:** if user is on holiday during measurement window (no email/calendar activity), pause window and resume on return — documented in `agent_state(_global, "measurement_paused")`.

### 8.3 Out-of-gate components

Funded Watcher, Warm Network, Meeting Prep, and the 6 handlers are **not** gate-bound. They ship at whatever quality day 14 produces. K1 (revenue gate, charter §5.2) is the next checkpoint for those.

---

## 9. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Qwen <80% on calibration → 1-day flip to Claude | Medium | Day-1 test, config-only flip, Rule 8 override block, ~₹22/mo cost |
| False-critical from Reply Triage on novel email pattern | Medium | Conjunctive whitelist (label+urgency+client_match+age); user `❌ False alarm` ack writes to `agent_state` and surfaces for review |
| Gmail watch subscription expires (Google requires re-subscribe every 7d) | High | `cron.daily.06:00` re-subscribes Gmail watch; 5-min poll fallback always running |
| Funded Watcher / Warm Network ship pre-SP4 with no browser data | Certain | Graceful degradation: Funded Watcher → RSS-only (no Crunchbase scrape); Warm Network → stub returning empty + warning log; no false-criticals possible |
| `agent_state` grows unboundedly (dedup sets, seen-articles) | Medium | TTL on dedup keys (7d default); `expires_at` index supports `cron.daily.04:30` cleanup |
| Telegram bot rate-limited (Telegram API: 30 msgs/sec) | Low | Global rate limit (8/day non-info) is well under; one ARQ retry on 429 |
| Webhook engine extension breaks v1 webhook handlers | Medium | Existing `process_*_webhook` functions unchanged; new dispatch is additive — registry lookup added, old logging kept; tests pin v1 behavior |
| User goes on holiday → 7-day measurement window has 0 emails some days | Low-Med | Pause/resume mechanism in §8.2; documented |
| K1 fires mid-SP5 build | None | K1 timing (6 weeks post-SP4) makes mid-SP5 firing physically impossible |
| ProactiveEngine bug emits unauthorized critical | Low | Test coverage of gate decision matrix; whitelist rejection logged separately so violations are visible in monitoring |
| Notion API token expires mid-build | Low | v1 already monitors token; Telegram alert exists; no SP5-specific risk |

---

## 10. Cuts from charter — explicit rationale

The charter §2 SP5 row lists **8 agents and 5 handlers**. This spec ships **6 agents and 6 handlers**, with explicit cuts and additions:

**Cut:**
- **Orchestrator** (charter agent) — vague placeholder with no concrete responsibility that survives Rule 1 today. Best candidate framing (cross-agent collision synthesis) requires an entity model linking emails ↔ invoices ↔ followups for the same client, which doesn't exist in v1 or SP2. Building speculatively violates YAGNI. Re-evaluate in v2.1 once SP5 traffic shows whether multi-agent collisions on the same entity are common.
- **Invoice Enforcer** (charter agent) — v1 has no invoicing integration. The two viable approaches (Notion-tracked DB or Gmail-parsed) both have significant problems: Notion-tracked requires manual upkeep the user is unsure about; Gmail-parsed is unreliable because clients pay through varied channels (UPI, bank transfer) with no standard email confirmation. Honest cut now is better than shipping a fragile agent.

**Added:**
- **Daily Briefing** (handler) — replaces the cross-agent synthesis value Orchestrator was reaching for. Folds `info`-tier pings into a single 7am digest; summarizes gate-suppression activity. Single Claude call, no state, no loop — handler per Rule 7.

**Net surface:** 6 agents + 6 handlers (charter listed 8 + 5 = 13; this spec 6 + 6 = 12).

This is a deviation from charter §2 wording but not from charter §3 rules. Charter §2 is descriptive (it lists what was sketched at charter-write time); §3 (Rule 1, Rule 7) is normative. Where they conflict, normative rules win — Orchestrator and Invoice Enforcer either don't pass Rule 1 cleanly (Orchestrator) or have no implementation path within scope (Invoice Enforcer). Surfacing the deviation here per charter §8 ("Hand-off — sub-spec must explicitly cite its charter exit gate from §5.1 and cut-triggers from §6").

---

## 11. Charter overrides (per Rule 8)

### Override 1 — Rule 5 (no new tables)

See §3.1 above for the full block. Summary: `agent_state` is mutable per-agent state, not a log. `agent_logs` would corrupt log semantics if used as a state store. Override approved by user during brainstorming (2026-04-26).

### No other overrides at spec time

- Rule 1 — all 6 agents pass 2/3.
- Rule 2 — Reply Triage default Qwen with empirical calibration; if calibration fails, an additional Rule 8 override block will be added to this spec at calibration time, not now.
- Rule 3 — every agent declares `KNOWLEDGE_RINGS` and calls `build_agent_context()` + `record_agent_activity()`.
- Rule 4 — SP5 agents emit notifications, not destructive actions; no new approval-gate territory.
- Rule 6 — soft only; SP5 introduces no new enforcement.
- Rule 7 — handlers follow `async def handle(payload, context) -> HandlerResult`.

---

## 12. Dependencies and assumptions

- **Hard dependencies:**
  - SP1 (operational deployment) — shipped ✓
  - SP2 (Knowledge Base) — shipped ✓
- **Soft dependency:**
  - SP4 (Browser Automation) — Funded Watcher and Warm Network ship pre-SP4 in degraded mode; full mode unlocks when SP4 ships.
- **External assumptions:**
  - User maintains `docs/personal/health-journal.md` daily (charter K3 already requires this).
  - User maintains a `Sent`-folder discipline in Gmail sufficient for Followup tracking (i.e., replies happen in Gmail, not WhatsApp).
  - Gmail watch + Notion API + Plane.so API tokens stay valid (already configured in v1; v1 already alerts on expiry).
  - Telegram bot token stays valid (already configured).

---

## 13. Build sequence (executive view; full plan via writing-plans)

This section is a sequence sketch only. The detailed implementation plan is produced by `superpowers:writing-plans` after this spec is approved.

1. Migration `0005_agent_state` + `services/agent_state.py` + tests.
2. `services/proactive_engine.py` + tests (gate decision matrix).
3. `services/notification_router.py` + `TelegramChannel` + tests.
4. `agents/event_driven_agent.py` + tests.
5. Webhook engine extension in `workers/tasks/webhook_tasks.py` + `dispatch_event_to_agent` ARQ task + tests (assert v1 behavior unchanged).
6. `workers/handlers/__init__.py` + handler context + 6 handlers (smallest first: Daily Briefing).
7. Reply Triage + `scripts/calibrate_reply_triage.py` + Gmail Pub/Sub endpoint + watch resubscription cron.
8. Followup, Meeting Prep, Health Guardian (K1 survivors) — independent, build in parallel.
9. Funded Watcher (RSS-only initially) + Warm Network (stub initially).
10. ARQ cron registrations + `EVENT_REGISTRY` discovery.
11. Day-1 calibration test → ship-or-flip Qwen/Claude decision.
12. Days 8–14 measurement window → exit gate verdict.

**Estimate:** 2–3 weeks per charter §2.

---

## 14. Appendix — architectural decisions captured during brainstorming

| Decision | Alternatives considered | Chosen |
|---|---|---|
| ProactiveEngine architecture | A: pure event-driven; B: tick-based loop; **C: hybrid (immediate dispatch + central gate)** | C — real-time response with single governance choke point |
| False-critical prevention | A: 2-tier severity + manual labeling; **B: 3-tier + whitelisted reason codes**; C: confidence-weighted | B — exit gate is a binary check, whitelist provides binary criterion; cooldown layered on top |
| Notification surface | A: Telegram-only; B: Telegram + iMessage hybrid (depends on SP3); **C: Telegram now + pluggable router** | C — keeps SP5 → SP2 charter dependency clean; SP3/SP7 channels drop in later |
| State storage | **A: new `agent_state` Postgres table (Charter override)**; B: Redis + `users.preferences`; C: JSONB on `agent_logs` | A — state and logs are different concerns; Redis-only loses state on restart during measurement window |
| Orchestrator scope | A: daily briefing composer (must be handler); B: cross-agent coordinator; **C: cut + add briefing handler** | C — coordinator needs entity model that doesn't exist; YAGNI |
| Health Guardian inputs | **A: journal-only**; B: journal + calendar; C: journal + calendar + activity logs | A — mirrors charter K3's bar; calendar awareness is v2.1 follow-on |
| Invoice Enforcer | D: Notion-tracked; E: Gmail-parsed; **F: cut** | F — both viable approaches have material problems; honest cut |
| Reply Triage model | A: pin Claude now; B: Qwen + escalate on low confidence; **C: Qwen default + day-1 calibration** | C — empirical decision; flip is config-only; preserves Rule 2 force |

---

**End of SP5 design spec.**
