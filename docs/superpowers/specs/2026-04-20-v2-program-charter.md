# CRUZ v2 — Program Charter

**Date:** 2026-04-20
**Status:** Draft for user review
**Author:** Synthesized from brainstorming session with Darshan
**Supersedes:** The 15-week all-in-one v2 spec pasted 2026-04-20. That document is retired as a single unit; it is decomposed into seven sub-specs, each governed by this charter.

---

## 1. Program framing

**What v2 is.** An additive evolution of the existing Cruz v1 — 14 agents, FastAPI backend, Qdrant + Postgres + Redis + Ollama, LLMRouter, voice STT+TTS, Cloudflare Tunnel, monitoring stack, all built and passing 1,073 tests. v2 adds: a multi-ring knowledge base on top of what's already wired, a Mac controller primitive layer, a browser automation primitive layer, an always-on event loop, on-demand screen perception, and multi-modal device polish. New specialist agents and handlers ride on those layers.

**What v2 is not.** A rebuild. A rewrite of existing agents. A single atomic release. Cruz v1 keeps running throughout; each sub-project ships independently and makes v1 more capable without replacing it.

**Charter role.** This document is the shared decision set that every v2 sub-spec inherits. Rules here are not re-debated per sub-project. If a sub-spec needs to deviate, it must cite the reason in its own doc (see Rule 8). The charter itself is short and stable — updated only when a gate fires or a rule proves wrong in practice.

**Build model.** Claude Code (Max plan) is the build tool; API burn during construction is approximately flat (~₹6.6K over 13–16 weeks). Labor is the user's personal time — not billable-hour trade-off. The real budget is **calendar weeks** (phases) and **sustainable hours per week** (health gate). The charter enforces stop-gates on those axes, not on rupees.

---

## 2. Sub-project decomposition

v2 is seven independent sub-specs. Each ships on its own. Each has a spec → plan → implementation cycle with its own exit gate (Section 5).

| # | Sub-project | Scope summary | Build estimate | Depends on |
|---|---|---|---|---|
| **SP1** | Finish operational deployment | Physical install of already-written code on Mac Mini; 72h uptime probe; external access validated from phone over cellular. No new code. | 3–5 days | — |
| **SP2** | Knowledge Base (Layer 1) | Multi-ring Qdrant (`cruz_activities`, `cruz_projects_docs`, `cruz_user_patterns`, `cruz_domain_knowledge`) + `projects` and `learned_patterns` tables + `context_builder` + `write_back`. Retrofit all 14 existing agents. | 1 week | SP1 |
| **SP3** | Mac Controller (Layer 2) | `services/mac_controller.py` AppleScript primitives + Messenger agent + Calendar agent (native + Google dual). | 1 week | SP1 |
| **SP4** | Browser Automation (Layer 3) | Playwright + persistent Chrome + anti-detect + LinkedIn + Job Hunter + WhatsApp agents. The dangerous one — selector maintenance burden starts here. | 2–3 weeks | SP2 |
| **SP5** | Event Loop (Layer 4) | Webhook engine + ProactiveEngine + event-driven agent base class. **Agents (~8):** Reply Triage, Meeting Prep, Followup, Funded Watcher, Warm Network, Invoice Enforcer, Health Guardian, Orchestrator. **Handlers (~5, per Rule 1):** Expense Auditor, Portfolio Watcher, Tax Helper, Relationship Maintenance, Travel Planner — all are scheduled prompts + Claude call, no persistent state or tool loops. Intent Monitor cut entirely — see Section 4 → *Consequence — data-source constraint*. | 2–3 weeks | SP2 |
| **SP6** | Screen Perception (Layer 5, scoped) | On-demand only. Mac screenshot + Claude Vision single-shot. Answer "what am I working on?" Active-app detection for context injection. No periodic capture, no Context Tracker agent. | 3–4 days | SP3 |
| **SP7** | Multi-modal polish (Layer 6) | Voice daemon glue (wake → STT → /command → TTS, always-on) + menu bar app + PWA install polish + FCM push + React Native shell (or PWA-only if time-cut). | 1–2 weeks | SP1 |

**Recommended order:** SP1 → SP2 → SP3 → SP4 → SP5 → SP6 → SP7.

**Reasoning.** SP1 unlocks everything. SP2 is highest-leverage because every later agent reads from it — building it first means you never retrofit twice. SP3 before SP4 because Mac Controller is smaller and lower-risk, giving an early confidence win before entering LinkedIn selector-hell. SP4 before SP5 because the Event Loop's most valuable agents (Reply Triage) depend on browser-sourced signals. SP6 last among the layers because it's the lowest-leverage. SP7 absorbs polish work naturally at the end.

**Swap option.** If revenue pressure is acute and pipeline must land in Month 2 rather than Month 3, swap SP3 and SP4: build Browser Automation first. Trades the easy confidence-win for ~1 week earlier LinkedIn outreach.

**What each sub-spec owns.** Its own design doc in `docs/superpowers/specs/`, its own implementation plan, its own exit gate. Charter's shared rules apply to all seven; anything agent- or layer-specific lives in the sub-spec itself.

---

## 3. Shared rules (apply to all seven sub-specs)

### Rule 1 — Agent inclusion (strict)
A new module in `agents/<name>/` requires **2 of 3**:
(a) multi-step agentic loop with tool_use,
(b) external integration beyond Claude/Ollama,
(c) persistent state across invocations.

Anything failing this bar lives in `workers/handlers/<name>.py` as a prompt-template handler fired by scheduler or webhook. Sub-specs that propose new agents must list which two criteria each agent satisfies.

### Rule 2 — LLM escalation (local-first, CRUZ-controlled)
Default model per agent is pinned in config (`AGENT_MODEL_CONFIG` table or env-backed):

- Default code/structured work: Ollama `qwen2.5-coder:14b`
- Default general/draft work: Ollama `llama3.1:8b`
- Cloud pins: `CRUZ`, `SENTINEL`, and any agent whose output is client-visible on first draft

Per-task override via `AgentInput.context["intelligence"] = "high"` routes the call through Claude Sonnet 4.6. **CRUZ is the only setter.** No self-escalation. No quality-heuristic retry loops.

### Rule 3 — Knowledge base participation
Every new agent (and every retrofit in SP2) calls `build_agent_context()` at the start of `process()` and `record_agent_activity()` after completion. Rings requested are declared in the agent's class definition, not per-call. Agents that skip KB participation must justify it in their sub-spec.

### Rule 4 — Approval gates
All destructive or externally visible actions (send email/message, create ticket, deploy, post PR comment, spend money, send DM, apply to job) require explicit `context["send"] = True`. Default = draft only. This is the existing v1 pattern; it is not re-debated per agent. Browser Automation extends the pattern: all outbound DMs/applications use the same gate.

### Rule 5 — Trace and log
Every invocation propagates `trace_id` and writes to `agent_logs` via `BaseAgent.log()`. No new logging patterns. Sub-specs that need additional structured data add JSONB columns to `agent_logs`, never new tables.

### Rule 6 — Token-cap signal (soft only)
Per-agent monthly token budget lives in `AGENT_MODEL_CONFIG`. Breach does **not** block — it emits a Telegram alert and flags the agent `degraded` in `/agents/status`. You decide whether to flip the pin from Claude to Ollama or pause the agent. Hard enforcement is deferred; code enforcement added only if a real overrun actually happens during operation.

### Rule 7 — Handler contract
Handlers (per Rule 1) live in `workers/handlers/<name>.py`. Signature:

```python
async def handle(payload: dict, context: HandlerContext) -> HandlerResult: ...
```

They can call `build_agent_context()` but cannot be invoked as CRUZ tools. They are scheduler- or webhook-triggered only.

### Rule 8 — Charter override
Sub-specs can deviate from these rules but must (a) cite which rule, (b) state why the default doesn't fit, (c) propose the alternative in the sub-spec's design section under a labeled "Charter override" heading, (d) get explicit user approval (Darshan) before implementing. Charter overrides cannot be approved by Claude Code agents on their own authority.

---

## 4. Budget framing

**Build-phase spend.** Claude Code Max ₹1,660/mo × 13–16 weeks ≈ **₹5K–7K** total. Near-zero direct-API spend.

**Runtime spend — fixed, always on.**

| Line | Monthly |
|---|---|
| Mac Mini power | ₹202 |
| UPS amortized | ₹167 |
| Domain + Google Workspace outreach | ₹1,350 |
| Google Drive backup (100GB) | ₹130 |
| Claude Max (build tool + `intelligence: high` escalations post-build) | ₹1,660 |
| Inworld TTS (post-cache) | ₹71 |
| **Fixed baseline** | **~₹3,580** |

**Runtime spend — variable, only when lit.**

| Trigger | Line | Monthly |
|---|---|---|
| Reach sending outreach regularly | MailReach (1 inbox) | ₹2,000 |
| CAPTCHA fallback (rare, browser automation) | 2Captcha pay-per-use | ~₹500 |
| **Max variable, fully lit** | | **~₹2,500** |

**Full-lit ceiling:** ~₹6,080/mo. **Realistic steady-state:** ~₹3,600–5,000/mo.

### Consequence — data-source constraint

**No paid data APIs.** Apollo, Crunchbase, and Twitter API are cut from v2. Sub-specs that assumed these must re-scope:

- **Reach.** Lead discovery uses Hunter.io free tier (50 searches/mo) + LinkedIn browser automation + manually curated source lists + Gemini Flash free tier for enrichment. Lower volume, higher signal.
- **Funded Company Watcher.** Reads free RSS feeds (TechCrunch, YourStory, Inc42, HN "Who's funded") and browser-scrapes Crunchbase news pages. Lower fidelity, zero cost.
- **Intent Monitor.** Cut from v2 entirely. Reconsider post-v2 only if a free signal source proves reliable.

### No hard code caps
Per Rule 6, token budgets are soft. External APIs have vendor-side quotas that act as natural ceilings. Kill criteria (Section 5) catch runaway scenarios at the phase level.

### Monthly review ritual
First of each month: look at the prior month's `agent_logs` aggregated spend + the list of lit variable services. Decide what to keep lit. 15 minutes, not a process.

---

## 5. Go/no-go gates

Two layers: **per-phase gates** (must pass before starting the next sub-project) and **composite kill criteria** (can fire any time, forcing pause or cut).

### 5.1 Per-phase exit gate

Each sub-project must prove all of the following before the next one starts.

| SP | Exit criteria (all must hold) |
|---|---|
| **SP1** | 72 hours continuous uptime with `/health` green; voice command from phone over cellular produces a streamed response end-to-end; one successful automated backup; Telegram alert fires on a deliberately induced failure |
| **SP2** | All 14 existing agents retrofitted; Qdrant `cruz_activities` has ≥100 real activity records from daily use; a blind A/B test on one real task shows post-KB output is measurably better (user picks the winner without knowing which is which); no P95 latency regression >20% |
| **SP3** | Messenger sends iMessage to 10/10 test targets; Calendar creates events in both Calendar.app and Google Calendar; Mac Controller primitives (screenshot, clipboard, app-open, notifications) each tested live from a CRUZ tool call |
| **SP4** | Playwright loads LinkedIn authenticated from the persistent profile; LinkedIn agent sends 20 DMs over 14 days with **zero account warnings**; Job Hunter applies to 10 roles successfully; daily caps enforced in code, not just configured |
| **SP5** | Reply Triage classifies 50 real emails with ≥80% agreement against user's manual judgment; ≥3 proactive pings/day for 7 consecutive days with no false-critical alerts |
| **SP6** | "What am I working on?" answers correctly on 10/10 ad-hoc tests across different apps; active-app context reaches at least one agent and improves its output on a test case |
| **SP7** | Wake-word + voice daemon operates 24 hours continuously; PWA installed on phone with offline support confirmed; FCM push delivers to all registered devices within 5 seconds |

A sub-project that fails its gate doesn't progress — it either gets a bounded fix window (≤25% of original estimate) or goes into a "v2.1 deferred" bucket. The next sub-project doesn't start until the gate passes or the failing SP is explicitly shelved.

**Precedence with K2.** Fix-window time counts toward the 50% overrun calculation in K2. If SP4's 2–3-week estimate is still failing at the end of a fix window that would push total elapsed past week 4.5, K2 fires and forces a cut regardless of whether the gate is close to passing. This prevents "one more fix window" drift.

### 5.2 Composite kill criteria

Can fire at any time, forcing action.

**K1 — Revenue gate.** After SP4 ships, 6 weeks to produce at least **1 paid client attributable to outreach** (LinkedIn agent or Reach). If week 6 closes with zero, SP5–7 scope is cut: drop revenue-focused agents (Warm Network, Funded Watcher), keep only personal-productivity agents (Health Guardian, Followup, Meeting Prep). No argument — this is a pre-commit.

**K2 — Time-overrun gate.** Any sub-project exceeding its estimate by >50% (e.g., SP4 budgeted 2–3 weeks crossing week 4) triggers **stop-and-reassess**. Outputs: (a) what's eating time, (b) cut scope, or (c) defer to v2.1. "Just push through" is explicitly forbidden. This rule is specifically for SP4 — historically where projects like this die.

**K3 — Health gate.** Maintain a private daily 1-line journal entry: sleep OK (Y/N) / commitments met (Y/N) / relationship calm (Y/N). "Week" is a **rolling 7-day window** evaluated each Sunday evening. Three or more "N"s across any single-dimension in that 7-day window (e.g., 3 nights of poor sleep, or 3 days of missed commitments) = **hard pause, 7 days, no Cruz work**. Journal lives in `docs/personal/health-journal.md` (gitignored). Two consecutive pause-weeks = charter reopens; reconsider whether to continue v2 at all.

### 5.3 What "pause" means operationally

Pause = v1 keeps running (no feature goes away); no new sub-project work; existing agents unmaintained except for P0 incidents; no client commitments that require v2 features. Genuine rest, not "light work."

---

## 6. Cut order if late

Pre-committed cut-list. If a gate fires (K1/K2/K3) and scope must shrink, cuts happen in this order — no re-litigation in the moment. Top of list = cut first. v1 keeps running throughout every cut.

| Order | What gets cut | Saves | Signal |
|---|---|---|---|
| 1 | **Intent Monitor** (provisionally cut in Section 4 → *Consequence — data-source constraint*; ratified here) | 1 week | SP5 starting |
| 2 | **Warm Network + Funded Watcher agents** | 4–5 days each | SP4 revenue gate (K1) fires |
| 3 | **SP6 entirely** (Screen Perception) | 3–4 days | SP5 trending over estimate |
| 4 | **SP7 React Native shell** (ship PWA-only) | 3–4 days | SP7 start |
| 5 | **SP7 menu bar app** (use global keyboard shortcut from the OS) | 1–2 days | SP7 mid-build |
| 6 | **SP5 secondary agents** (Meeting Prep, Expense Auditor, Portfolio Watcher, Tax Helper, Relationship Maintenance, Travel Planner) — keep only Reply Triage, Followup, Health Guardian | 1+ week | SP5 trending over estimate |
| 7 | **SP4 WhatsApp agent** (keep LinkedIn + Job Hunter) | 3–4 days | SP4 trending over estimate |
| 8 | **SP4 Job Hunter agent** (keep LinkedIn only) | 4–5 days | SP4 deep in selector-hell |
| 9 | **SP3 Messenger agent** (use AppleScript primitives only, no agent) | 2–3 days | SP3 mid-build |
| 10 | **SP3 Calendar native integration** (keep Google Calendar via existing API only) | 2–3 days | SP3 mid-build |
| 11 | **SP3 entirely** (Mac Controller deferred to v2.1). Ripple: SP6 (Screen Perception) loses its Mac-primitive dependency and must defer too — already cut at #3, consistent. | 1 week | Late-phase rescue |
| 12 | **SP4 entirely** (Browser Automation deferred to v2.1). Ripple: SP5 Reply Triage loses browser-sourced signals and must fall back to Gmail-only input. SP5 still ships but with reduced proactive surface. | 2–3 weeks | Emergency — reopen charter |

**Uncuttable.** SP1 (operational deployment) and SP2 (knowledge base). SP1 is the foundation; SP2 makes the existing 14-agent v1 meaningfully better and is cheap.

**Cut-trigger interpretation.** A cut is triggered by a fired gate, not by "feeling behind." This prevents premature pessimism from destroying scope mid-week-3.

**If cuts reach #11.** Pause v2 and re-evaluate framing. SP1 + SP2 + partial SP3/SP4 is still a materially better Cruz than today. Shipping there and harvesting learnings is legitimate.

**If cuts reach #12.** Stop. The charter has failed. Reopen brainstorming with different scope.

---

## 7. Success criteria

v2 is "done" when **6 of 8** hold. Below 4 = v2 underdelivered; reopen charter.

1. **Uptime.** 30 consecutive days with `/health` green and no manual restart.
2. **Cross-device.** One conversation carried across phone + iPad + laptop in the same day with continuity preserved.
3. **Knowledge-base quality.** Blind A/B on 10 real tasks (pre-KB vs post-KB output for Forge and Echo) — post-KB wins ≥7/10.
4. **Browser automation safety.** 100+ LinkedIn DMs sent over 30 days with zero account warnings or restrictions.
5. **Proactive value.** ≥3 actionable pings/day for 14 consecutive days. "Actionable" = user took action on it within 24h. (Distinct from SP5's exit gate in Section 5.1, which measures classification accuracy and zero false-criticals on a 7-day window — that's the minimum bar to *ship* SP5; criterion 5 is the higher bar to call v2 a success.)
6. **Revenue attribution.** ≥1 paid client attributable to v2 outreach within 6 weeks of SP4 completion.
7. **Sales pipeline.** ≥3 sales calls booked via LinkedIn agent within 6 weeks of SP4 completion.
8. **Screen perception (if SP6 shipped).** On-demand "what am I working on" correct on 9/10 ad-hoc tests.

**Deliberately cut from the original spec's list:** "voice >5 commands/day" (behavior, not capability), "stopped opening claude.ai" (can't measure reliably).

---

## 8. Hand-off

**Each sub-spec.** Lives at `docs/superpowers/specs/YYYY-MM-DD-sp{N}-{slug}-design.md`. Inherits all Section 3 rules automatically. Must explicitly cite its charter exit gate from Section 5.1 and its cut-triggers from Section 6. Any deviation from charter rules requires a labeled "Charter override" section citing Rule 8.

**Sub-spec workflow.**

1. Brainstorm sub-spec → write design doc → spec-review loop → user approval.
2. Invoke `superpowers:writing-plans` → produce implementation plan → user approval.
3. Execute (likely via `superpowers:executing-plans` or `superpowers:subagent-driven-development` in a dedicated worktree).
4. Run the sub-project's exit gate (Section 5.1).
5. If gate passes → start next sub-spec. If fails → bounded fix window or shelve.

**Charter update rule.** This charter is stable. Updated only when (a) a gate fires and forces a cut, (b) a shared rule proves wrong in practice, or (c) v2 completes and the document retires to an archive. No speculative edits.

**Sub-project 1 starts next.** After this charter is committed and user-approved, brainstorming proceeds for SP1 (finish operational deployment). SP1 is 3–5 days of real work — physical install + uptime probe + external access validation. No new code.

---

## Appendix A — Decisions locked during brainstorming

For audit. These are the decisions that constitute the charter's substantive content.

| # | Decision | Alternatives considered | Chosen |
|---|---|---|---|
| 1 | Layer 5 scope | Full / On-demand / Cut | On-demand only (Section 2, SP6) |
| 2 | Agent inclusion bar | Strict / Moderate / None | Strict — 2 of 3 criteria (Rule 1) |
| 3 | Go/no-go gate shape | Revenue-only / Composite / Soft | Composite — revenue + time + health (Section 5.2) |
| 4 | LLM escalation | Pinned / Attempt-and-escalate / Tag-based | Pinned default + CRUZ-tag override (Rule 2) |
| 5 | Paid data APIs | Apollo/Crunchbase/Twitter in / out | All out (Section 4) |
| 6 | Build cost framing | API-burn / Subscription-flat | Claude Code Max subscription — flat (Section 1) |
| 7 | Opportunity cost framing | Billable-hours / Personal-time | Personal time, not billable trade-off (Section 1) |

## Appendix B — Known v1 reality to inherit

Facts from `PROGRESS.md` that sub-specs must respect.

- 14 agents built; 1,073 tests passing.
- LLMRouter already dispatches to Anthropic / Ollama / Gemini — Rule 2 plugs into it.
- `context={"send": True}` approval-gate pattern is already wired for ECHO, REACH, SENTINEL, MARK, PM, CATCH — Rule 4 extends it, doesn't replace it.
- Qdrant + `services/semantic_memory.py` exist — SP2 adds collections and wrappers, doesn't create infra.
- PM2, Cloudflare Tunnel, monitoring stack, backup tasks, load harness, 72h uptime probe — all code-complete. SP1 is installation only.
- Voice STT + TTS wired; wake word detector exists; voice daemon glue (always-on loop) is not yet wired — it lands in SP7.
- Plane.so is the PM system of record (user preference; overrides any Linear/JIRA mention in older spec text).
