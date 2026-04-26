# SP2 — Knowledge Base (Layer 1)

**Date:** 2026-04-26
**Status:** Draft for user review
**Sub-project of:** CRUZ v2 Program Charter (`docs/superpowers/specs/2026-04-20-v2-program-charter.md`)
**Inherits:** All charter Section 3 rules. Exit gate from charter Section 5.1. Cut-triggers from charter Section 6.
**Depends on:** SP1 (operational deployment — exit gate must be closed before SP2 execution begins)
**Enables:** SP4 (Browser Automation) and SP5 (Event Loop) — both read from KB rings at runtime

---

## 1. Goal and scope

**Goal.** Add a multi-ring knowledge base layer on top of the existing v1 system. When any of the 14 agents processes a task, it retrieves relevant past work, project context, and learned preferences before generating its response. Over time, CRUZ gets measurably better at project-specific tasks because it remembers what worked.

**One-line description.** Four new Qdrant collections + two new Postgres tables + one service + a mechanical retrofit of 14 existing agents.

### In scope

- `services/knowledge_base.py` — `KnowledgeBaseService` singleton with all read/write methods
- Alembic migration: two new Postgres tables (`projects`, `learned_patterns`)
- Four new Qdrant collections: `cruz_activities`, `cruz_projects_docs`, `cruz_user_patterns`, `cruz_domain_knowledge`
- `scripts/seed_kb.py` — one-shot codebase index for all five projects
- Retrofit all 14 existing agents: add `KNOWLEDGE_RINGS` class variable + two method calls per `process()`
- Pattern inference logic in `observe_interaction()`: threshold=5 observations before writing to `cruz_user_patterns`
- Tests for `KnowledgeBaseService` and each retrofitted agent (written same day as code, per dev standards)

### Out of scope

- No changes to `services/semantic_memory.py` or the `cruz_memories` collection — v1 conversation recall is untouched
- No new agents in this sub-project (all KB writes happen via `KnowledgeBaseService` methods, not new agent modules)
- No frontend UI for KB browsing — deferred to a later polish pass
- RELAY: no retrofit (deterministic classifier, no LLM, no KB participation per Rule 3 exemption — see Section 8)

### Success = charter SP2 exit gate holds (verbatim)

> All 14 existing agents retrofitted; Qdrant `cruz_activities` has ≥100 real activity records from daily use; a blind A/B test on one real task shows post-KB output is measurably better (user picks the winner without knowing which is which); no P95 latency regression >20%

---

## 2. Architecture

### Ring model

SP2 uses a **5-ring total model**. The existing `cruz_memories` collection (conversation exchange vectors) stays completely unchanged. `KnowledgeBaseService` owns only the four new structured rings. No migration of existing vectors is required.

```
┌─────────────────────────────────────────────────────────────────┐
│  v1 — untouched                                                 │
│  cruz_memories ←── SemanticMemoryService (CRUZ conversation)   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SP2 — new                                                      │
│  KnowledgeBaseService (services/knowledge_base.py)              │
│    ├── cruz_activities     ← what agents did + outcomes         │
│    ├── cruz_projects_docs  ← per-client project knowledge       │
│    ├── cruz_user_patterns  ← your preferences + style           │
│    └── cruz_domain_knowledge ← tech/industry research           │
└─────────────────────────────────────────────────────────────────┘
          ↕ read/write
  13 retrofitted agents + RELAY exempt (KNOWLEDGE_RINGS declared per agent)
```

All four new collections use `vector_size=384` (all-MiniLM-L6-v2, matching `cruz_memories`). The existing `EmbeddingService` is reused without modification.

### Write strategy

- **`cruz_activities`** — automatic. Every agent writes on every `process()` completion via `record_agent_activity()`. No manual intervention.
- **`cruz_projects_docs`** — seed-first. `scripts/seed_kb.py` indexes priority files for all five projects on SP2 launch day. FORGE adds incremental entries as it reads/edits project files thereafter.
- **`cruz_user_patterns`** — both explicit and inferred. Explicit writes via "remember" command land immediately. Inferred writes require ≥5 observations of the same behavioral pattern before committing.
- **`cruz_domain_knowledge`** — lazy auto. RAW agent writes research summaries nightly. Manual writes via CRUZ available from day one; ring starts empty and fills over time.

### Service architecture

A unified `KnowledgeBaseService` class owns all four rings — consistent with the existing `QdrantService`, `SemanticMemoryService` singleton pattern. A single `get_kb_service()` import is all agents need.

---

## 3. Data model

### 3.1 Qdrant ring schemas

All rings use `vector_size=384`.

#### `cruz_activities`

Embedded text: `"agent {agent_name}: {task} → {result_summary}"`

| Payload field | Type | Description |
|---|---|---|
| `agent_name` | str | e.g. `"forge"`, `"echo"` |
| `task` | str | The input task text |
| `result_summary` | str | What was produced or done |
| `success` | bool | Whether the agent succeeded |
| `project_id` | str \| null | FK to `projects.id` if applicable |
| `trace_id` | str | Links to `agent_logs` |
| `timestamp` | float | Unix epoch |
| `tokens_used` | int \| null | For cost tracking |

#### `cruz_projects_docs`

Embedded text: the `content` field directly.

| Payload field | Type | Description |
|---|---|---|
| `project_id` | str | FK to `projects.id` |
| `project_name` | str | e.g. `"AMA Solutions"` |
| `doc_type` | str | `"file_summary"` \| `"readme"` \| `"requirement"` \| `"note"` |
| `file_path` | str \| null | Repo-relative path |
| `content` | str | The text chunk (≤500 tokens) |
| `timestamp` | float | Unix epoch |

#### `cruz_user_patterns`

Embedded text: the `content` field directly.

| Payload field | Type | Description |
|---|---|---|
| `pattern_type` | str | `"code_style"` \| `"comm_style"` \| `"preference"` \| `"workflow"` |
| `content` | str | e.g. `"Darshan prefers snake_case in Python"` |
| `source` | str | `"explicit"` \| `"inferred"` |
| `agent_name` | str \| null | Agent that inferred this pattern |
| `observation_count` | int | For inferred patterns; explicit = 1 |
| `confidence` | float | 1.0 for explicit; 0.0–1.0 for inferred |
| `timestamp` | float | Unix epoch |

#### `cruz_domain_knowledge`

Embedded text: the `content` field directly.

| Payload field | Type | Description |
|---|---|---|
| `topic` | str | e.g. `"Next.js App Router"`, `"Playwright selectors"` |
| `content` | str | The knowledge chunk |
| `source` | str | `"raw_agent"` \| `"manual"` |
| `timestamp` | float | Unix epoch — staleness derived at query time as `int((now - timestamp) / 86400)`; default filter threshold = 90 days, configurable |

### 3.2 Postgres tables (Alembic migration)

```sql
CREATE TABLE projects (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(100) NOT NULL,      -- "AMA Solutions"
    slug         VARCHAR(50)  UNIQUE NOT NULL, -- "ama-solutions"
    type         VARCHAR(20)  NOT NULL,      -- "client" | "personal"
    status       VARCHAR(20)  DEFAULT 'active', -- "active" | "inactive" | "archived"
    tech_stack   JSONB,                      -- ["React", "PostgreSQL", "FastAPI"]
    github_url   TEXT,
    local_path   TEXT,                       -- abs path to local repo (used by seed script)
    description  TEXT,
    metadata     JSONB,                      -- flexible per-project KV
    created_at   TIMESTAMP    DEFAULT NOW(),
    updated_at   TIMESTAMP    DEFAULT NOW()
);

CREATE TABLE learned_patterns (
    id                UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_type      VARCHAR(50)  NOT NULL, -- "code_style" | "comm_style" | "preference" | "workflow"
    content           TEXT         NOT NULL,
    source            VARCHAR(20)  NOT NULL, -- "explicit" | "inferred"
    agent_name        VARCHAR(50),           -- agent that inferred this
    observation_count INTEGER      DEFAULT 1,
    confidence        FLOAT        DEFAULT 1.0,
    qdrant_id         UUID,                  -- backref to cruz_user_patterns vector
    active            BOOLEAN      DEFAULT TRUE,
    created_at        TIMESTAMP    DEFAULT NOW(),
    updated_at        TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX idx_projects_status        ON projects(status);
CREATE INDEX idx_learned_patterns_type  ON learned_patterns(pattern_type, active);
CREATE INDEX idx_learned_patterns_src   ON learned_patterns(source, observation_count);
```

Initial data: insert the five known projects on migration run.

```sql
INSERT INTO projects (name, slug, type, status) VALUES
    ('AMA Solutions',    'ama-solutions',    'client',   'active'),
    ('Shooterista',      'shooterista',      'client',   'active'),
    ('SuiteAdvisors',    'suiteadvisors',    'client',   'active'),
    ('Asia Capital',     'asia-capital',     'client',   'active'),
    ('MIDAR',            'midar',            'personal', 'active');
```

`local_path`, `tech_stack`, `github_url`, and `description` are filled manually after migration or via CRUZ ("Hey CRUZ, remember AMA Solutions is at ~/Projects/ama-solutions").

---

## 4. KnowledgeBaseService interface

**File:** `services/knowledge_base.py`

```python
class KnowledgeBaseService:
    """Singleton. Access via get_kb_service()."""

    # ── READ ──────────────────────────────────────────────────────────────

    async def build_agent_context(
        self,
        task: str,
        rings: list[str],
        trace_id: str,
        project_id: str | None = None,
        limit_per_ring: int = 5,
    ) -> str:
        """
        Query requested rings, merge top-N results, return a formatted
        context string for injection into the agent's system prompt.

        Returns empty string when all rings are empty (first-run safe).
        Only requested rings are queried — never all four.

        Section headings are defined as module-level string constants
        (CONTEXT_HEADER_ACTIVITIES, CONTEXT_HEADER_PROJECTS,
        CONTEXT_HEADER_PATTERNS, CONTEXT_HEADER_DOMAIN) to ensure
        consistency across calls. The format below is non-normative:

          ## Relevant past work
          - forge: added GET /api/orders endpoint to AMA Solutions (2 days ago)

          ## Project context — AMA Solutions
          Stack: React 18, Node.js/Express, PostgreSQL 15 ...

          ## Your patterns
          - Prefer snake_case in Python, camelCase in JavaScript
        """

    # ── WRITE — activities (every agent, every completion) ───────────────

    async def record_agent_activity(
        self,
        agent_name: str,
        task: str,
        result_summary: str,
        success: bool,
        trace_id: str,
        project_id: str | None = None,
        tokens_used: int | None = None,
    ) -> None:
        """Embed and upsert one activity record into cruz_activities."""

    # ── WRITE — project docs (FORGE + seed script) ───────────────────────

    async def write_project_doc(
        self,
        project_id: str,
        project_name: str,
        content: str,
        doc_type: str,
        file_path: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        """
        Upsert a project knowledge chunk.
        Point ID = sha256(project_id + file_path + str(chunk_index))[:32]
        Re-runs are idempotent. trace_id is None for seed-script calls
        (which originate outside a CRUZ request).
        """

    # ── WRITE — user patterns (explicit) ─────────────────────────────────

    async def write_user_pattern(
        self,
        content: str,
        pattern_type: str,
        source: str = "explicit",
        agent_name: str | None = None,
    ) -> None:
        """Write a pattern immediately. Bypasses the 5-observation threshold."""

    # ── WRITE — user patterns (inferred, threshold=5) ────────────────────

    async def observe_interaction(
        self,
        agent_name: str,
        interaction_type: str,
        observed_pattern: str,
    ) -> None:
        """
        Increment observation_count for this pattern in learned_patterns.
        When count reaches 5, call Claude Sonnet to extract a clean
        pattern description and write to both learned_patterns and
        cruz_user_patterns.
        """

    # ── WRITE — domain knowledge (RAW agent + manual) ────────────────────

    async def write_domain_knowledge(
        self,
        content: str,
        topic: str,
        source: str = "raw_agent",
        trace_id: str | None = None,
    ) -> None:
        """
        Upsert a domain knowledge chunk into cruz_domain_knowledge.
        trace_id is None for RAW agent scheduled writes (originate
        outside a CRUZ request context).
        """
```

---

## 5. Agent retrofit

### 5.1 Retrofit pattern

Every agent except RELAY gets two additions to `process()` and one new class variable:

```python
class FORGEAgent(BaseAgent):
    KNOWLEDGE_RINGS = ["cruz_activities", "cruz_projects_docs"]  # ← new

    async def process(self, input: AgentInput) -> AgentOutput:
        kb = get_kb_service()

        # ← new: read context before doing anything
        ctx = await kb.build_agent_context(
            input.task,
            self.KNOWLEDGE_RINGS,
            input.trace_id,
            project_id=input.context.get("project_id"),
        )

        # ... existing agent logic, inject ctx into system prompt ...

        # ← new: record activity after completing
        await kb.record_agent_activity(
            "forge", input.task, result_summary,
            output.success, input.trace_id,
            project_id=input.context.get("project_id"),
            tokens_used=output.tokens_used,
        )
        return output
```

Context injection: `ctx` is prepended to the agent's existing system prompt string. If `ctx` is empty (rings not yet populated), the system prompt is unchanged — all retrofits are first-run safe.

### 5.2 Ring assignments

| Agent | KNOWLEDGE_RINGS | Notes |
|---|---|---|
| FORGE | activities, projects_docs | Also writes to projects_docs on file read/edit |
| ECHO | activities, projects_docs, user_patterns | Client tone + writing style |
| REACH | activities, domain_knowledge | Lead context + industry research |
| CATCH | activities, projects_docs | Meeting context needs project awareness |
| PM | activities, projects_docs | Sprint history + project tech constraints |
| TITAN | activities, projects_docs | Deploy history + infra per project |
| MARK | activities, projects_docs | Prior doc style + project context |
| QT | activities, projects_docs | Test history + project test patterns |
| SENTINEL | activities, projects_docs | Prior security findings per project |
| RAW | activities, domain_knowledge | RAW also writes to domain_knowledge |
| PULSE | activities, domain_knowledge | Briefings informed by research + prior briefings |
| GENERAL | activities | Catch-all — minimal KB needs |
| CRUZ | activities, user_patterns | Uses cruz_memories separately (v1 path). Patterns shape CRUZ's tone. |
| RELAY | *(none)* | Deterministic classifier — see Section 8 charter override |

---

## 6. Seed script

**File:** `scripts/seed_kb.py`

**Usage:**

```bash
# Seed all active projects (reads local_path from projects table)
python scripts/seed_kb.py

# Seed specific projects
python scripts/seed_kb.py --projects ama-solutions shooterista
```

**Process:**

1. Read active projects from `projects` table where `local_path IS NOT NULL`
2. For each project, walk `local_path` and collect priority files:
   - Always: `README.md`, `CLAUDE.md`, `.env.example`
   - Dependency manifests: `package.json`, `requirements.txt`, `pyproject.toml`
   - Schema files: `models/schema.sql`, `prisma/schema.prisma`, `*.sql`
   - Entry points: `src/index.ts`, `main.py`, `app.py`, `server.ts`, `backend/api/main.py`
   - Config: `docker-compose.yml`, `alembic.ini`
3. Chunk files at ≤500-token boundaries (split on blank lines; never split mid-sentence)
4. For each chunk: call `kb.write_project_doc(project_id, project_name, content, doc_type, file_path)`
5. Upsert point ID = `sha256(project_id + file_path + str(chunk_index))[:32]` — re-runs are idempotent
6. Skip: `node_modules/`, `.git/`, `__pycache__/`, `dist/`, `build/`, `*.lock`, `*.min.js`
7. Report: `AMA Solutions: indexed 28 docs (12 files) in 43s`

---

## 7. Pattern inference

`observe_interaction()` is called by CRUZ after interactions where the user modifies an agent's output. Trigger examples:

| Agent | interaction_type | Trigger |
|---|---|---|
| ECHO | `email_draft_edited` | User rewrites tone, shortens text, changes structure |
| FORGE | `code_edited` | User renames vars, adds type hints, restructures |
| PM | `plan_reordered` | User reorders tasks or changes estimates |
| MARK | `doc_rewritten` | User rewrites a documentation section |

**Trigger mechanism — no frontend required:**

CRUZ's system prompt (added during Day 5 CRUZ retrofit) instructs CRUZ to call a `record_pattern_observation` tool when it identifies that the user's message is a behavioral correction — e.g., "no, use formal tone", "that code is wrong, always use camelCase", "stop adding comments". CRUZ maps this to `observe_interaction()` internally. The tool is in CRUZ's tool list; no new API endpoint is needed.

Day 3 work includes: define the `record_pattern_observation` tool schema in `agents/cruz/tools.py`. Day 5 CRUZ retrofit wires CRUZ's system prompt to call it.

**Inference flow:**

```
User sends correction message to CRUZ
  → CRUZ detects behavioral correction via its system prompt guidance
  → CRUZ calls record_pattern_observation tool
  → observe_interaction("echo", "email_draft_edited", "<observed pattern>") fires
  → Upsert row in learned_patterns with observation_count += 1
  → If observation_count < 5: stop
  → If observation_count == 5:
      Background asyncio task: call Claude Sonnet to extract clean pattern
      (non-blocking to CRUZ's response; falls back gracefully on API error — logs, does not raise)
      Write cleaned pattern to learned_patterns (source="inferred", confidence=0.8)
      Write vector to cruz_user_patterns via write_user_pattern()
```

Patterns are soft-disableable (`active=False`) without deletion. "Hey CRUZ, forget that pattern about email tone" flips `active=False`. Explicit "remember" writes bypass the threshold entirely and land with `confidence=1.0`.

---

## 8. Exit gate verification

From charter Section 5.1:

| Gate criterion | Verification | Artifact |
|---|---|---|
| All 14 agents retrofitted | `pytest tests/agents/ -v` — all pass with KB calls present | Test run output |
| `cruz_activities` ≥100 records | `python -c "from services.knowledge_base import get_kb_service; ..."` count query | Count + timestamp in PROGRESS.md |
| Blind A/B test wins | FORGE on "add endpoint to AMA Solutions" — no-KB vs with-KB, blind pick | Comparison doc at `docs/perf/sp2-ab-test.md` |
| P95 latency regression <20% | Run existing load scenarios before and after retrofit; compare P95 | `docs/perf/load_results.md` updated row |

**A/B test protocol (3 paired runs, KB must win ≥2/3):**

1. Task: `"Add a new REST endpoint to the AMA Solutions backend for listing active orders by client"`
2. For each of 3 rounds:
   - Run A: call FORGE with `KNOWLEDGE_RINGS = []` (no KB context)
   - Run B: call FORGE with `KNOWLEDGE_RINGS = ["cruz_activities", "cruz_projects_docs"]`
   - Strip agent labels from both outputs; assign opaque labels ("Output 1" / "Output 2")
   - Pick the better output blind
3. Reveal which was which after all 3 rounds
4. Gate passes if KB-backed output wins ≥2 of the 3 rounds
5. Document all 3 round results in `docs/perf/sp2-ab-test.md` with commit SHA

**Sign-off line for PROGRESS.md:**

```
SP2 sign-off — 2026-MM-DD
  agents_retrofitted:  13/13 retrofitted + 1 exempt (RELAY — charter override §11)
  activities_count:    XXX records
  ab_test:             KB wins X/3 rounds (see docs/perf/sp2-ab-test.md)
  p95_regression:      X% (within 20% limit)
  commit:              <sha>
```

---

## 9. Risks and mitigations

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| 1 | Latency regression >20% from KB queries on every agent call | Medium | Query only declared rings; limit_per_ring=5 (configurable); async parallel ring queries; empty rings return immediately |
| 2 | Seed script indexes low-value content, pollutes ring with noise | Medium | Priority file list is conservative; skip patterns exclude binaries and build artifacts; re-seeding is idempotent so bad entries can be cleared and re-run |
| 3 | Pattern inference writes wrong patterns at 5-observation threshold | Medium | Claude Sonnet extracts the pattern description — quality gate is Claude's judgment; patterns are soft-disableable; threshold is configurable via env var. The Claude call inside `observe_interaction()` runs as a background asyncio task — non-blocking to the caller; falls back gracefully (logs error, does not raise) on API failure |
| 4 | KB context string pushes agent prompts past model context limits | Low | Limit is 5 items per ring × 4 rings = 20 items max; each item is a summary (not full content); typical context string is <500 tokens; monitored via token_count in agent_logs |
| 5 | `projects.local_path` not set for a project — seed silently skips it | Low | Seed script prints a warning for each skipped project; gate criterion requires ≥100 activities, not a fully seeded ring |
| 6 | 14-agent retrofit introduces a regression in existing tests | Low | Each agent retrofit adds KB calls behind existing test mocks; `get_kb_service()` returns a mock in test fixtures; retrofit is mechanical — same two lines in all agents |

---

## 10. Work breakdown (1-week estimate)

| Day | Work |
|---|---|
| **Day 1** | Alembic migration (projects + learned_patterns tables) + insert 5 projects + KnowledgeBaseService skeleton + tests |
| **Day 2** | `build_agent_context()` + `record_agent_activity()` implementation + unit tests |
| **Day 3** | `write_project_doc()` + `write_user_pattern()` + `observe_interaction()` + `write_domain_knowledge()` + `record_pattern_observation` tool schema + tests |
| **Day 4** | **Prereq:** populate `local_path` (and optionally `tech_stack`) for all 5 projects via direct DB update or CRUZ command. Then: `scripts/seed_kb.py` + run seed on all 5 projects |
| **Day 5** | **Prereq:** confirm user approval of RELAY KB exemption (charter override §11) before starting. Retrofit 13 agents (FORGE, ECHO, REACH, CATCH, PM, TITAN, MARK, QT, SENTINEL, RAW, PULSE, GENERAL, CRUZ) + CRUZ system prompt update for `record_pattern_observation` tool |
| **Day 6** | Retrofit tests + integration test (full loop: FORGE task → KB write → FORGE task again → KB read) |
| **Day 7** | A/B test + latency comparison + sign-off |

---

## Appendix A — Charter rule compliance

| Rule | Compliance |
|---|---|
| Rule 1 (agent inclusion) | SP2 adds no new agents. All new functionality lives in `services/knowledge_base.py` and `scripts/seed_kb.py`. N/A. |
| Rule 2 (LLM escalation) | `observe_interaction()` calls Claude Sonnet for pattern extraction — this is a one-time write triggered at threshold=5, not a per-request escalation. No self-escalation. CRUZ is the only caller. |
| Rule 3 (KB participation) | 13 agents retrofitted. RELAY is exempt — see charter override §11. |
| Rule 4 (approval gates) | SP2 adds no externally visible actions. `record_agent_activity()` is a local write. N/A. |
| Rule 5 (trace and log) | `record_agent_activity()` includes `trace_id` in the Qdrant payload (always available from `AgentInput`). `write_project_doc()` and `write_domain_knowledge()` accept `trace_id=None` — seed-script and RAW scheduled writes originate outside a CRUZ request and carry no trace; they are identifiable by the `source` payload field. No information loss since these writes are not triggered by user requests. |
| Rule 6 (token-cap signal) | KB context tokens are tracked via `agent_logs.tokens_used` (existing). No new enforcement needed. |
| Rule 7 (handler contract) | SP2 adds no handlers. N/A. |
| Rule 8 (charter override) | One override — see Section 11. |

## 11. Charter override — RELAY KB exemption

**Override 1 — RELAY KB exemption (Rule 3)**

- **Rule cited:** Rule 3 — every agent calls `build_agent_context()` and `record_agent_activity()`
- **Why the default doesn't fit:** RELAY is a deterministic keyword classifier with no LLM call and no `AgentInput`/`AgentOutput` contract. It has no `process()` method to retrofit and no output that would benefit from KB context. Calling `record_agent_activity()` on a keyword match would generate low-value noise in `cruz_activities`.
- **Alternative:** RELAY is excluded from both KB calls. Its keyword matches are already captured in `agent_logs` via CRUZ's trace. No information is lost.
- **Requires user approval before implementing:** Yes — Darshan Parmar must approve this override per charter Section 3 Rule 8.
