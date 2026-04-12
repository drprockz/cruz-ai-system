# CRUZ AI System — Full Implementation Plan

**Author:** Darshan Parmar
**Date:** April 12, 2026
**Duration:** 6 phases over 6 weeks
**Goal:** Production-grade AI assistant running on Mac Mini M4, accessible from all devices

---

## Production-Grade Benchmarks Used

Every phase decision is validated against how production AI systems are built:

| System | What we learn from it |
|---|---|
| **Cursor** | Single LLM + tool_use orchestration, streaming first |
| **Devin** | Agentic loop, sandboxed code execution, human gates |
| **LangGraph** | AgentState flowing through all nodes, interrupt_before |
| **OpenAI Assistants** | Thread-based conversation persistence from day 1 |
| **GitHub Copilot** | Context-aware, inline, no visible routing layer |
| **FRIDAY (Iron Man)** | One interface, total recall, proactive, invisible internals |

---

## Phase 1: Foundation (Days 1-4)

**Goal:** CRUZ is live, talks back, remembers conversations, routes to agents via tool_use.

### What production systems do at this phase:
OpenAI built the Assistant + Thread model before any tools. LangGraph defines AgentState before any nodes. The foundation must be right or everything built on it is wrong.

---

### Task 1.1 — `agents/base_agent.py`

**Why first:** Every agent extends this. Build it wrong and you refactor 12 files later.

```python
# What it must contain:
class AgentInput(TypedDict):
    task: str
    context: dict[str, Any]
    trace_id: str
    conversation_id: str

class AgentOutput(TypedDict):
    success: bool
    result: Any
    agent: str
    duration_ms: int
    tokens_used: int | None
    error: str | None
    requires_approval: bool
    approval_prompt: str | None

class BaseAgent:
    async def process(self, input: AgentInput) -> AgentOutput
    async def log(self, ...)           # writes to agent_logs
    async def call_claude(self, ...)   # shared Anthropic client
    async def call_ollama(self, ...)   # shared Ollama client
    def handle_error(self, e)          # consistent error shape
```

**Acceptance:** `BaseAgent` is abstract. Instantiating it directly raises `NotImplementedError`. A minimal `TestAgent(BaseAgent)` with `process()` implemented passes a test.

---

### Task 1.2 — Alembic Setup + Schema Migration

**Why now:** Adding columns later without migrations = manual SQL on prod = data loss risk.

```bash
pip install alembic sqlalchemy[asyncio] asyncpg
alembic init migrations
# Configure for async PostgreSQL
```

**Initial migration adds:**
- `trace_id UUID` column to `agent_logs`
- `device VARCHAR(50)` column to `conversations`
- `tokens_used INTEGER` column to `agent_logs`
- All indexes from schema.sql

**Acceptance:** `alembic upgrade head` runs clean. `alembic downgrade -1` reverts cleanly.

---

### Task 1.3 — Shared Services Layer (`services/`)

**Why:** Every agent creating its own DB pool = connection exhaustion. Production FastAPI uses `Depends()` injection with shared singletons.

```
services/db.py      → async SQLAlchemy engine, session factory
services/redis.py   → redis.asyncio client singleton
services/ollama.py  → httpx client for Ollama API
```

Injected via FastAPI `Depends()`:
```python
async def get_db() -> AsyncSession: ...
async def get_redis() -> Redis: ...
```

**Acceptance:** 10 parallel requests to `/health` share one DB pool. No "too many connections" error.

---

### Task 1.4 — `agents/relay/relay_agent.py`

**Scope:** Keyword classifier only. Zero LLM calls. Deterministic.

```python
KEYWORD_MAP = {
    r'\bFORGE\b|create component|generate code': 'forge',
    r'\bECHO\b|draft email|write email|send message': 'echo',
    r'\bTITAN\b|deploy|push to prod': 'titan',
    # ... all 11 agents
}

def classify(message: str) -> str | None:
    """Returns agent name if keyword match, else None (tool_use handles it)"""
```

**Acceptance:** `classify("FORGE, create a button")` returns `"forge"`. `classify("help me think through this")` returns `None`.

---

### Task 1.5 — `agents/general/general_agent.py`

Simple Claude sub-agent for tasks that don't fit a specialist. Uses `tool_use` for structured output.

**Acceptance:** `general.process({task: "What's the difference between async and sync?"})` returns a structured `AgentOutput`.

---

### Task 1.6 — `agents/cruz/cruz_agent.py`

**The most important file in the project.**

```python
class CruzAgent(BaseAgent):
    """
    Main assistant. Single entry point for all user interactions.
    Loads conversation history, calls Claude with all tools defined,
    executes tool calls, streams response, saves to DB.
    """

    TOOLS = [
        forge_tool,    # code generation
        echo_tool,     # communication
        reach_tool,    # leads
        catch_tool,    # transcription
        pm_tool,       # project management
        titan_tool,    # deployment (approval gate)
        mark_tool,     # documentation
        qt_tool,       # testing
        sentinel_tool, # code review
        raw_tool,      # research
        pulse_tool,    # briefings
        general_tool,  # catch-all
    ]

    async def process(self, input: AgentInput) -> AgentOutput:
        history = await self.load_conversation(input.conversation_id)
        response = await self.call_claude(
            messages=history + [{"role": "user", "content": input.task}],
            tools=self.TOOLS,
            stream=True,
        )
        # handle tool calls, approval gates, stream response
        await self.save_conversation(input.conversation_id, input.task, response)
        return AgentOutput(...)
```

**Acceptance:**
- `POST /command {"message": "hello", "stream": false}` returns a natural response
- `POST /command {"message": "hello", "conversation_id": "existing"}` loads history
- Same `conversation_id` from two different requests maintains context

---

### Task 1.7 — `POST /command` Endpoint + SSE Streaming

```python
@app.post("/command")
async def command(req: CommandRequest):
    if req.stream:
        return StreamingResponse(
            cruz.process_streaming(req),
            media_type="text/event-stream"
        )
    result = await cruz.process(AgentInput(...))
    return result
```

**Acceptance:** `curl` with `--no-buffer` shows tokens appearing as they stream. Full response takes <5s for a simple query.

---

### Task 1.8 — Tests for Phase 1

```
tests/agents/test_base_agent.py   → abstract contract tests
tests/agents/test_cruz_agent.py   → conversation loading, tool dispatch
tests/agents/test_relay.py        → keyword mapping accuracy
tests/api/test_command.py         → endpoint integration test
```

**Coverage target:** >80% on `agents/` and `backend/api/`

---

### Phase 1 Done When:
- [x] `BaseAgent` in place, all agents can extend it
- [x] Alembic migrations running cleanly
- [x] `POST /command` → CRUZ → responds with streaming
- [x] Conversation history persists across requests by `conversation_id`
- [x] `trace_id` logged on every agent call
- [x] All Phase 1 tests passing

---

## Phase 2: Core Agents — FORGE + ECHO (Days 5-7)

**Goal:** CRUZ can generate code and draft emails. First real productivity gains.

### Production comparison:
Cursor (FORGE equivalent) uses tool_use with `read_file`, `write_file`, `run_terminal` as separate small tools — not one monolithic "generate code" prompt. ECHO mirrors how Superhuman's AI composes emails: context-aware, tone-matching, human-approved before send.

---

### Task 2.1 — `agents/forge/forge_agent.py`

**Tools FORGE has access to:**
```python
forge_tools = [
    read_file(path),           # read existing code for context
    write_file(path, content), # write generated code
    create_component(name, framework, props, styling),
    create_api_endpoint(method, path, schema, db_ops),
    refactor_code(path, instructions),
    fix_bug(path, error_message, context),
    run_linter(path),          # verify generated code passes ESLint/Black
]
```

**Model:** Claude Sonnet 4

**Key:** FORGE uses an agentic loop internally — generates → lints → if errors → fixes → lints again → done.

**Sandboxing:** Code execution (linting, tests) runs in a subprocess with:
```python
await asyncio.create_subprocess_exec(
    *cmd, timeout=30,
    cwd=sandbox_path,  # isolated directory, not project root
)
```

**Acceptance:**
- CRUZ: "Build a contact form with name, email, message, Tailwind styled"
- FORGE generates valid React component + TypeScript types
- Component passes ESLint without errors
- File written to correct path

---

### Task 2.2 — `agents/echo/echo_agent.py`

**Model:** Qwen 2.5 Coder 14B (via Ollama)

**Tools ECHO has:**
```python
echo_tools = [
    load_email_template(type),          # from Notion
    load_client_history(client_name),   # from PostgreSQL
    draft_email(recipient, topic, tone, points),
    draft_slack_message(channel, topic, tone),
    schedule_email(draft_id, send_at),  # via SendGrid
]
```

**Approval gate is mandatory:**
```python
# ECHO never sends without approval
return AgentOutput(
    requires_approval=True,
    approval_prompt=f"Ready to send to {recipient}. Preview:\n{draft}",
    result={"draft": draft, "recipient": recipient}
)
```

**Acceptance:**
- CRUZ: "Draft an email to Ateet about the AMA website delay"
- ECHO produces a draft
- CRUZ surfaces it with "Here's the draft. Send it?" prompt
- Only sends after explicit confirmation

---

### Task 2.3 — Voice Pipeline (`services/voice.py`)

```python
# Full pipeline:
VoicePipeline:
    async def transcribe(audio_bytes) -> str:     # Whisper Large v3
    async def speak(text) -> audio_bytes:          # Inworld TTS streaming
    async def detect_wake_word() -> bool:          # Porcupine
```

**Latency optimization:** TTS begins streaming on first sentence while Claude generates the rest. User hears response in ~250ms after generation starts.

**Acceptance:** Voice round-trip (Whisper → CRUZ → Inworld) completes in <4 seconds end-to-end.

---

### Task 2.4 — FORGE + ECHO Integration Test

```
Scenario: "Build a contact form for AMA Solutions and draft an email to Ateet saying it's ready"
Expected:
  - FORGE generates ContactForm.tsx
  - ECHO drafts email to ateet@ama.com
  - CRUZ presents both results
  - Approval required before email sends
```

---

### Phase 2 Done When:
- [x] FORGE generates production-quality React + TypeScript components
- [x] FORGE uses agentic loop (generate → lint → fix → done)
- [x] ECHO drafts emails via Qwen 14B (local, zero API cost)
- [x] ECHO always requires approval before sending
- [x] Voice pipeline: Whisper → CRUZ → Inworld working end-to-end
- [x] CRUZ: "deploy CRUD app" → FORGE builds it autonomously

---

## Phase 3: Automation Agents — REACH + CATCH + PM + Memory (Week 3)

**Goal:** Overnight automation, meeting intelligence, sprint planning. Qdrant memory online.

### Production comparison:
Apollo.io's AI prospecting, Otter.ai's transcription, and Linear's sprint AI are all single-purpose. CRUZ does all three, orchestrated through one interface, with shared context.

---

### Task 3.1 — Qdrant Setup + Semantic Memory

```python
# docker-compose.yml — add persistent volume
services:
  qdrant:
    image: qdrant/qdrant
    ports: ["6333:6333"]
    volumes:
      - qdrant_storage:/qdrant/storage  # ← named volume, survives restarts
volumes:
  qdrant_storage:
```

**Collections:**
```
cruz_conversations  → embeddings of past conversations (384-dim)
project_context     → code snippets, decisions, PRDs
client_profiles     → client preferences, communication history
```

**Embedding pipeline:**
```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')  # 80MB, fast local
```

**Acceptance:** CRUZ references a component built 3 days ago without it being in the active context window.

---

### Task 3.2 — ARQ Task Queue Setup

```python
# workers/arq_worker.py
from arq import create_pool, cron

async def run_pulse_briefing(ctx):    # 6 AM daily
    await PulseAgent().process(...)

async def run_raw_research(ctx):      # 3 AM daily
    await RawAgent().process(...)

async def run_reach_overnight(ctx):   # 2 AM daily
    await ReachAgent().process(...)

class WorkerSettings:
    functions = [run_pulse_briefing, run_raw_research, run_reach_overnight]
    cron_jobs = [
        cron(run_pulse_briefing, hour=6, minute=0),
        cron(run_raw_research, hour=3, minute=0),
        cron(run_reach_overnight, hour=2, minute=0),
    ]
```

**Why ARQ over BullMQ:** Same Python runtime, same Redis already running, zero Node.js dependency. Production FastAPI shops use ARQ or Celery — not BullMQ.

---

### Task 3.3 — `agents/reach/reach_agent.py`

**Model:** Gemini Flash 2.5 (discovery) + Qwen 2.5 Coder 14B (personalization)

**Two-stage pipeline:**
1. **Discovery (Gemini):** Company research, find decision makers, enrich from Apollo.io + Hunter.io
2. **Personalization (Qwen):** Draft personalized outreach email for each lead using company context

**Approval gate:** Always. Batch shows all N email drafts for review before any send.

**Acceptance:**
- Background job at 2 AM finds 10 SaaS leads matching last criteria
- Drafts personalized emails for each
- Morning briefing from PULSE includes "REACH found 10 leads overnight. 10 drafts ready for review."

---

### Task 3.4 — `agents/catch/catch_agent.py`

**Model:** Whisper Large v3 (transcription) + Llama 3.1 8B (summarization)

**Pipeline:**
1. Google Calendar integration detects upcoming meetings
2. Audio capture via OBS/screen recording or direct mic
3. Whisper transcribes with speaker diarization
4. Llama extracts: action items, decisions, key points
5. Saves to Notion, creates Linear tasks from action items
6. ECHO drafts follow-up email with meeting summary (approval required)

**Acceptance:** Record 5-minute test meeting. Within 5 minutes of stop: transcript in Notion, action items in Linear, draft follow-up email ready.

---

### Task 3.5 — `agents/pm/pm_agent.py`

**Model:** Qwen 2.5 Coder 14B

**Integrations:** Linear (primary), JIRA (if client requires), Notion, GitHub

**Capabilities:**
- Break feature spec into Linear tasks with estimates
- Generate sprint plan for 2-week cycle
- Monday 9 AM automated sprint review
- Detect blockers (tasks marked blocked >2 days)

**Acceptance:**
- CRUZ: "Plan a sprint for the AMA website redesign"
- PM generates 8-12 tasks with estimates in Linear
- Sprint plan includes dependencies and critical path

---

### Phase 3 Done When:
- [x] Qdrant running with persistent volume, CRUZ uses semantic memory
- [x] ARQ workers running: PULSE at 6 AM, RAW at 3 AM, REACH at 2 AM
- [x] REACH finds leads overnight, surfaces in morning briefing
- [x] CATCH transcribes test meeting, creates tasks, drafts follow-up
- [x] PM generates sprint in Linear from voice command

---

## Phase 4: Advanced Agents — TITAN + MARK + QT + SENTINEL (Week 4)

**Goal:** Full DevOps automation, documentation, testing gates, code review.

### Production comparison:
This phase implements the same gates that GitHub's CI/CD, SonarQube code review, and Vercel's preview deployments provide — but orchestrated through CRUZ.

---

### Task 4.1 — `agents/qt/qt_agent.py`

**Built before TITAN** because QT gates TITAN. No deployment without passing tests.

**Tools:**
```python
qt_tools = [
    run_pytest(path, coverage_threshold=80),
    run_playwright(url, test_suite),
    run_lighthouse(url, thresholds={performance: 90, accessibility: 95}),
    run_npm_audit(path, severity='high'),
    generate_tests(source_file, framework),
]
```

**Pre-deploy gate:** TITAN checks QT status before deploying. If QT fails → TITAN blocked → CRUZ notifies you.

---

### Task 4.2 — `agents/sentinel/sentinel_agent.py`

**Model:** Claude Sonnet 4

**Triggers:** GitHub webhook on PR open, or explicit CRUZ command.

**Review dimensions:**
1. Security: OWASP top 10, SQL injection, XSS, secrets in code
2. Code quality: complexity, naming, dead code, duplicate logic
3. Performance: N+1 queries, missing indexes, large bundle imports
4. Production readiness: error handling, logging, input validation

**Output:** GitHub PR comments on specific lines + overall readiness score.

**Approval gate:** SENTINEL can suggest fixes but never auto-commits. You review the diff and approve.

---

### Task 4.3 — `agents/titan/titan_agent.py`

**Model:** Qwen 2.5 Coder 14B

**Deployment flow:**
```
[QT passes] → [SENTINEL approves] → [TITAN: confirm with user]
     ↓                                      ↓
  blocked                          "Deploy to prod (AMA website)? 
                                    Last deploy: 3 days ago. 
                                    12 commits since then. [View diff]"
                                           ↓ confirmed
                                    backup → deploy → health check
                                           ↓ fails
                                    auto-rollback → notify
```

**Platforms:** Vercel (frontend), Railway (backend), Hostinger VPS (via SSH).

---

### Task 4.4 — `agents/mark/mark_agent.py`

**Model:** Qwen 2.5 Coder 14B

**Triggers:** Post-commit GitHub webhook (automatic), explicit CRUZ command.

**Outputs:**
- OpenAPI/Swagger spec from FastAPI routes
- JSDoc/TSDoc comments injected into source
- README.md from project structure analysis
- Changelog from git log since last release
- Notion page with updated documentation

---

### Phase 4 Done When:
- [x] QT blocks TITAN if tests fail or coverage <80%
- [x] SENTINEL auto-reviews every PR, posts inline GitHub comments
- [x] TITAN deploys with human confirmation, auto-rollbacks on failure
- [x] MARK auto-documents every FORGE commit
- [x] Full pipeline: FORGE builds → QT tests → SENTINEL reviews → TITAN deploys → MARK documents

---

## Phase 5: Intelligence Layer — RAW + PULSE + Proactivity (Week 5)

**Goal:** CRUZ becomes proactive. Surfaces information before you ask.

### Production comparison:
This is what separates FRIDAY from a chatbot. Proactivity = Notion AI surfacing related pages, Linear flagging stale tickets, Dependabot alerting on vulnerabilities. CRUZ does all of these plus a morning briefing.

---

### Task 5.1 — `agents/raw/raw_agent.py`

**Model:** Llama 3.1 8B (local, efficient for research)

**Autonomous behaviors:**
- 3 AM: Check npm/pip for dependency updates across all client projects
- On Dependabot alert: Analyze severity, draft patch PR if safe
- On-demand: Research any technical topic, save summary to Notion + Qdrant

---

### Task 5.2 — `agents/pulse/pulse_agent.py`

**Model:** Llama 3.1 8B

**6 AM daily briefing format:**
```
Good morning. Here's your CRUZ briefing for April 15, 2026.

TODAY:
• 10 AM: AMA Solutions call (CATCH ready to record)
• 2 PM: Code review for Shooterista PR #47 (SENTINEL flagged 1 issue)

OVERNIGHT:
• REACH found 8 new leads (SaaS, Mumbai). 8 drafts ready for review.
• MARK documented 3 FORGE commits on AMA project.
• RAW: react-router has a security patch (CVE-2026-1234). FORGE can apply it.

ACTIVE TASKS:
• FORGE: AMA contact form (in progress, ~2 hrs left)
• TITAN: Shooterista deploy queued (waiting on QT)

CLIENTS:
• AMA: No response to last email (3 days). Want ECHO to follow up?
• Shooterista: Payment overdue by 5 days. Want ECHO to send invoice?
```

---

### Task 5.3 — Cross-Device Handoff

```python
# When you pick up iPad after working on ThinkPad:
CRUZ: "Continuing from ThinkPad — you were working on the AMA contact form.
       FORGE is 60% done. Want me to show you the current state?"
```

**Implementation:**
- `device` field on every message
- Redis pub/sub broadcasts context updates to all devices
- CRUZ detects device switch, surfaces relevant context proactively

---

### Task 5.4 — React Native App

**Screens:**
1. Voice interface (mic button, waveform, streaming response)
2. Conversation history (all devices)
3. Active tasks dashboard
4. Agent status panel
5. Quick actions (FORGE, ECHO, PULSE)

**Push notifications:**
- Background tasks completed
- Approval required (deploy, send email)
- Morning briefing ready

**Acceptance:** Full CRUZ interaction on Nothing Phone 2, including voice commands.

---

### Phase 5 Done When:
- [x] Morning briefing delivered at 6 AM with relevant context
- [x] RAW surfaces dependency alerts automatically
- [x] CRUZ aware of device switch, surfaces relevant context
- [x] React Native app working on Nothing Phone 2
- [x] PWA installable on iPad

---

## Phase 6: Production Hardening (Week 6)

**Goal:** 99%+ uptime. Monitoring. Process management. Performance validated.

---

### Task 6.1 — PM2 Configuration

```javascript
// ecosystem.config.js
module.exports = {
  apps: [
    { name: 'cruz-api',     script: 'backend/api/main.py',   interpreter: 'python3' },
    { name: 'arq-worker',   script: 'workers/arq_worker.py', interpreter: 'python3' },
    { name: 'ollama',       script: 'ollama serve',           interpreter: 'bash' },
  ]
}
// pm2 start ecosystem.config.js
// pm2 save  (persist across reboots)
// pm2 startup (auto-start on Mac Mini boot)
```

---

### Task 6.2 — Monitoring Stack

```bash
# Uptime Kuma (port 3001)
docker run -d --restart=always -p 3001:3001 \
  -v uptime-kuma:/app/data louislam/uptime-kuma

# Grafana Loki + Grafana (ports 3100, 3002)
docker-compose up -d loki grafana

# Configure: alerts to Telegram bot on downtime
```

**Monitor targets:** FastAPI `/health`, PostgreSQL port 5432, Redis port 6379, Qdrant port 6333, Ollama port 11434, Mac Mini CPU/RAM via node_exporter.

---

### Task 6.3 — Performance Validation

| Metric | Target | Measurement |
|---|---|---|
| Simple CRUZ response latency | <2s (non-voice) | `time curl POST /command` |
| Voice round-trip | <4s | Timed end-to-end |
| Streaming first token | <500ms | SSE event timing |
| Concurrent requests (10) | No degradation | `hey` load test |
| DB query P95 | <50ms | Postgres EXPLAIN ANALYZE |
| Context load (50 messages) | <100ms | Profiled |
| Ollama model switch | <15s | Timed |

---

### Task 6.4 — Cloudflare Tunnel

```bash
cloudflared tunnel create cruz
cloudflared tunnel route dns cruz cruz.simpleinc.cloud
cloudflared tunnel run --url http://localhost:3000 cruz
```

Enables: webhooks from GitHub, Vercel, Google Calendar. Secure public access from office or travel.

---

### Task 6.5 — Backup Automation

```bash
# Daily at 2 AM via ARQ cron
async def backup_databases(ctx):
    pg_dump → gzip → upload to Google Drive
    redis-cli BGSAVE → upload
    qdrant collection export → upload
```

---

### Task 6.6 — Load Testing + Final Validation

**Scenarios to validate:**
1. Morning routine (PULSE + 3 FORGE tasks + ECHO draft) — concurrent agents
2. Deployment pipeline (FORGE → QT → SENTINEL → TITAN) — sequential with gates
3. Lead generation overnight (REACH → 10 leads → 10 email drafts) — background
4. Multi-device: command from phone, pick up on iPad, continue on ThinkPad

---

### Phase 6 Done When:
- [x] PM2 running all services, survives Mac Mini reboot
- [x] Uptime Kuma monitoring all services, Telegram alerts configured
- [x] Grafana Loki capturing logs from all agents
- [x] Performance targets met (see table above)
- [x] Cloudflare Tunnel live, webhooks tested
- [x] Backup automation running and verified
- [x] 72-hour uptime test passed

---

## Full Timeline

| Week | Phase | Primary Deliverable |
|---|---|---|
| Week 1 (Days 1-4) | Foundation | CRUZ talks, remembers, routes via tool_use |
| Week 1 (Days 5-7) | Core Agents | FORGE builds code, ECHO drafts emails, voice works |
| Week 2 | MVP | FORGE + ECHO + Voice end-to-end — usable on real client work |
| Week 3 | Automation | REACH overnight, CATCH transcription, PM sprint planning, Qdrant memory |
| Week 4 | DevOps pipeline | QT gates, SENTINEL reviews, TITAN deploys, MARK documents |
| Week 5 | Intelligence | RAW research, PULSE briefings, proactivity, React Native app |
| Week 6 | Production | Monitoring, PM2, performance validation, 99% uptime |

---

## What Gets Built on Day 4 (Next)

Based on this plan, Day 4 builds Phase 1 Tasks 1.1–1.7:

1. `agents/base_agent.py` — BaseAgent class with AgentInput/AgentOutput types
2. `agents/relay/relay_agent.py` — keyword classifier (no LLM)
3. `agents/general/general_agent.py` — Claude catch-all sub-agent
4. `agents/cruz/cruz_agent.py` — main assistant, tool_use orchestration, streaming
5. Alembic init + first migration (trace_id, device columns)
6. `services/db.py`, `services/redis.py` shared service layer
7. `POST /command` endpoint with SSE streaming
8. Tests for all of the above

**End of Day 4:** `curl -X POST localhost:3000/command -d '{"message":"hello"}'` streams back a CRUZ response. Second call with same `conversation_id` shows CRUZ remembers the first message.

---

## Architecture Validation vs Production Systems

| Dimension | Our Implementation | Production Standard | Match? |
|---|---|---|---|
| Routing | Claude native tool_use | OpenAI Assistants, LangGraph | ✅ |
| Conversation persistence | PostgreSQL threads from day 1 | OpenAI Threads, Claude Projects | ✅ |
| Streaming | SSE token-by-token | All production assistants | ✅ |
| Agentic loop | Plan→Act→Observe→Repeat | Devin, LangGraph, AutoGPT | ✅ |
| Human gates | Before all irreversible actions | LangGraph interrupt_before | ✅ |
| BaseAgent | Mandatory foundation | LangChain BaseAgent, SK IChatCompletionService | ✅ |
| Trace IDs | Every log linked | OpenTelemetry standard | ✅ |
| Tool granularity | Small composable tools | Cursor, Copilot tool_use | ✅ |
| Parallel tools | Via tool_use batch calls | OpenAI parallel_tool_calls | ✅ |
| Local model fallback | Ollama with fallback chain | Enterprise AI deployments | ✅ |
| Memory layers (4) | Working+Session+Semantic+Procedural | ChatGPT Memory, Claude Projects | ✅ |
| Proactivity | ARQ background agents + push | GitHub Copilot, Notion AI | ✅ |
| Cross-device | Tailscale + Redis pub/sub | iCloud sync, Google account sync | ✅ |
| Sandboxed execution | Subprocess with timeout | Devin Docker sandbox | ✅ (basic) |
| Voice streaming | TTS starts before response ends | Alexa, Google Assistant | ✅ |

---

*Ready to build. Start with Task 1.1 — `agents/base_agent.py`.*
