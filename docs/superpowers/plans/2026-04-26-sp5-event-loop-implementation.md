# SP5 Event Loop Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CRUZ proactive — ship a webhook-driven event loop with a central gate, notification router, 6 event-driven agents, and 6 scheduled handlers, riding on v1's existing webhook + ARQ infrastructure.

**Architecture:** Hybrid event-driven (real-time webhooks/cron → agent dispatch) + central `ProactiveEngine` gate (severity ladder, dedup, cooldown, global rate limit) + pluggable `NotificationRouter` (Telegram only in SP5, SP3/SP7 add channels). Agents extend a new `EventDrivenAgent(BaseAgent)` base with class-level `KNOWLEDGE_RINGS`, `TRIGGERS`, `CRITICAL_REASONS` declarations. Persistent per-agent state lives in a new `agent_state` Postgres table (Charter Rule 5 override).

**Tech Stack:** Python 3.11, FastAPI, asyncpg via custom `services.db`, Alembic 0005+0006 migrations, ARQ + Redis, pytest + pytest-asyncio, Anthropic + Ollama via `services.llm`, Gmail Pub/Sub, Telegram Bot API, watchdog (filesystem watcher).

**Spec:** `docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md`

**Charter:** `docs/superpowers/specs/2026-04-20-v2-program-charter.md`

---

## Working agreements

- **TDD throughout.** Every step that adds production code is preceded by a failing test. No exceptions. Reference: @superpowers:test-driven-development.
- **Frequent commits.** Commit at the end of every numbered Task. Use the conventional-commit prefix (`feat`, `fix`, `test`, `chore`, `docs`) with scope `sp5` (e.g., `feat(sp5): add agent_state migration`).
- **DRY / YAGNI.** Build only what the spec requires. Do not pre-build SP3/SP7 channels — register hooks only.
- **Async-only.** Every I/O path uses `async/await`. Tests use `@pytest.mark.asyncio`.
- **Type hints required.** Use `from __future__ import annotations` at the top of every new module.
- **Logger naming.** `logging.getLogger("cruz.<area>.<module>")` — matches v1 convention.
- **Test isolation.** Tests that touch Postgres use the existing `tests/conftest.py` env (real local DB). Tests for the gate use a fake `StateService` to keep them fast.
- **Skill references:** When working on this plan, also read @superpowers:verification-before-completion before claiming any chunk done.

## Scope check

Spec is one sub-project (SP5). Scope is event-loop infrastructure + 6 agents + 6 handlers — a single subsystem with internal cohesion (gate + router + agents share the `agent_state` and `EVENT_REGISTRY` substrates). No subdivision required.

## File structure (locked decomposition)

### New files (created)

| Path | Responsibility | Rough LoC |
|---|---|---|
| `migrations/versions/0005_agent_state.py` | `agent_state` table + index | ~40 |
| `migrations/versions/0006_projects_add_email_domains.py` | `email_domains TEXT[]` column on `projects` | ~25 |
| `services/agent_state.py` | `StateService` — Postgres-backed state with Redis hot cache | ~180 |
| `services/proactive_engine.py` | `ProactiveEngine` — gate decision logic | ~280 |
| `services/notification_router.py` | `NotificationRouter` + `Channel` protocol + `TelegramChannel` | ~150 |
| `services/file_watcher.py` | `FileWatcher` — watchdog wrapper for filewatch triggers | ~80 |
| `agents/event_driven_agent.py` | `EventDrivenAgent(BaseAgent)` + `EVENT_REGISTRY` + `emit()` helper | ~200 |
| `agents/reply_triage/__init__.py` | exports | ~10 |
| `agents/reply_triage/reply_triage_agent.py` | `ReplyTriageAgent` class | ~280 |
| `agents/reply_triage/tools.py` | `classify`, `fetch_thread_context`, `read_user_pattern` tool definitions | ~120 |
| `agents/followup/__init__.py` | exports | ~10 |
| `agents/followup/followup_agent.py` | `FollowupAgent` class | ~250 |
| `agents/followup/tools.py` | tool definitions | ~100 |
| `agents/meeting_prep/__init__.py` | exports | ~10 |
| `agents/meeting_prep/meeting_prep_agent.py` | `MeetingPrepAgent` class | ~220 |
| `agents/funded_watcher/__init__.py` | exports | ~10 |
| `agents/funded_watcher/funded_watcher_agent.py` | `FundedWatcherAgent` class | ~200 |
| `agents/warm_network/__init__.py` | exports | ~10 |
| `agents/warm_network/warm_network_agent.py` | `WarmNetworkAgent` class (stub-mode pre-SP4) | ~180 |
| `agents/health_guardian/__init__.py` | exports | ~10 |
| `agents/health_guardian/health_guardian_agent.py` | `HealthGuardianAgent` class | ~240 |
| `workers/handlers/__init__.py` | package init + handler discovery helper | ~20 |
| `workers/handlers/context.py` | `HandlerContext`, `HandlerResult`, `emit_info()` | ~80 |
| `workers/handlers/daily_briefing.py` | daily 7am digest handler | ~150 |
| `workers/handlers/expense_auditor.py` | monthly expense digest | ~120 |
| `workers/handlers/portfolio_watcher.py` | weekly client tech digest | ~120 |
| `workers/handlers/tax_helper.py` | quarterly tax checklist | ~120 |
| `workers/handlers/relationship_maintenance.py` | weekly people-to-message digest | ~120 |
| `workers/handlers/travel_planner.py` | calendar-triggered travel checklist | ~120 |
| `workers/tasks/dispatch.py` | `dispatch_event_to_agent` ARQ task | ~70 |
| `workers/tasks/gmail_webhook_tasks.py` | `process_gmail_webhook` + Pub/Sub auth verify | ~120 |
| `workers/tasks/maintenance_tasks.py` | `gmail_watch_resubscribe`, `agent_state_cleanup`, `gmail_poll_fallback` | ~150 |
| `scripts/calibrate_reply_triage.py` | day-1 50-email calibration CLI | ~100 |
| `tests/services/test_agent_state.py` | unit tests for StateService | ~200 |
| `tests/services/test_proactive_engine.py` | unit tests — gate decision matrix | ~350 |
| `tests/services/test_notification_router.py` | unit tests — router + Telegram channel | ~150 |
| `tests/services/test_file_watcher.py` | unit tests | ~80 |
| `tests/agents/test_event_driven_agent.py` | base class behavior + emit() | ~180 |
| `tests/agents/test_reply_triage.py` | classification + critical conjunction | ~250 |
| `tests/agents/test_followup.py` | queue + 5d threshold | ~180 |
| `tests/agents/test_meeting_prep.py` | calendar filter + tool calls | ~150 |
| `tests/agents/test_funded_watcher.py` | RSS pull + ICP match + dedup | ~180 |
| `tests/agents/test_warm_network.py` | stub mode + post-SP4 ranking | ~150 |
| `tests/agents/test_health_guardian.py` | streak detection + intervention | ~220 |
| `tests/workers/test_dispatch.py` | dispatch task | ~120 |
| `tests/workers/test_webhook_tasks_dispatch.py` | webhook → registry → enqueue | ~150 |
| `tests/workers/test_gmail_webhook_tasks.py` | Pub/Sub auth + parse | ~150 |
| `tests/workers/test_maintenance_tasks.py` | resubscribe + cleanup | ~120 |
| `tests/workers/handlers/__init__.py` | empty | ~0 |
| `tests/workers/handlers/test_daily_briefing.py` | digest assembly | ~120 |
| `tests/workers/handlers/test_expense_auditor.py` | per-handler smoke | ~80 |
| `tests/workers/handlers/test_portfolio_watcher.py` | per-handler smoke | ~80 |
| `tests/workers/handlers/test_tax_helper.py` | per-handler smoke | ~80 |
| `tests/workers/handlers/test_relationship_maintenance.py` | per-handler smoke | ~80 |
| `tests/workers/handlers/test_travel_planner.py` | per-handler smoke | ~80 |
| `tests/api/test_gmail_webhook_endpoint.py` | endpoint auth + enqueue | ~100 |
| `tests/api/test_false_alarm_endpoint.py` | false-alarm callback | ~80 |
| `tests/scripts/test_calibrate_reply_triage.py` | calibration script flow | ~100 |

### Modified files

| Path | Change | Why |
|---|---|---|
| `backend/api/main.py` | add `POST /webhooks/gmail`, `POST /notifications/false-alarm` endpoints | Gmail Pub/Sub trigger + Telegram inline-button callback |
| `workers/tasks/webhook_tasks.py` | extend each `process_*_webhook` to dispatch to `EVENT_REGISTRY` | Webhook engine extension (additive — v1 logging unchanged) |
| `workers/arq_worker.py` | register new task functions + 9 new cron jobs | Hooks SP5 work into the existing worker |

### Files NOT touched

- `agents/base_agent.py` — unchanged. `EventDrivenAgent` extends it without modifying the base.
- `services/knowledge_base.py` — unchanged. Agents call `get_kb_service()` exactly as v1 agents do.
- `agents/cruz/cruz_agent.py`, `agents/forge/forge_agent.py`, etc. — none of the v1 agents are modified.

---

## Chunk 1: Foundations — migrations + StateService

This chunk lands the database tables and the state-access service. After it, every later chunk has a place to write per-agent state. No agent or gate code yet — just the substrate.

### Task 1.1: Create `0005_agent_state` migration

**Files:**
- Create: `migrations/versions/0005_agent_state.py`
- Test: (verified via Task 1.3 integration test)

- [ ] **Step 1: Write the migration file**

```python
"""agent_state

Add agent_state table for SP5 event-driven per-agent persistent state.

Spec:    docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.1
Charter override: Rule 5 (no new tables) — see spec §11.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_state",
        sa.Column("agent_name", sa.String(50),    nullable=False),
        sa.Column("key",        sa.String(200),   nullable=False),
        sa.Column("value",      postgresql.JSONB, nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP,     nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP,
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("agent_name", "key"),
    )
    # Partial index — only rows with expires_at need fast cleanup scans.
    op.execute(
        "CREATE INDEX idx_agent_state_expires "
        "ON agent_state(expires_at) WHERE expires_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_agent_state_expires")
    op.drop_table("agent_state")
```

- [ ] **Step 2: Run the migration**

```bash
alembic upgrade head
```

Expected output: `INFO  [alembic.runtime.migration] Running upgrade 0004 -> 0005, agent_state`

- [ ] **Step 3: Verify schema**

```bash
psql "$DATABASE_URL" -c "\d agent_state"
```

Expected: table with 5 columns; primary key on `(agent_name, key)`; partial index on `expires_at`.

- [ ] **Step 4: Test downgrade then re-upgrade (rollback safety)**

```bash
# Sanity check we're at 0005 before stepping back
alembic current | grep -q "0005" || { echo "not at 0005, abort"; exit 1; }
alembic downgrade -1 && alembic upgrade head
```

Expected: clean down + clean up, no errors. `alembic current` should show `0005 (head)` after.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/0005_agent_state.py
git commit -m "feat(sp5): add agent_state table migration

Per spec §3.1 — Charter Rule 5 override (mutable per-agent state, not a log)."
```

---

### Task 1.2: Create `0006_projects_add_email_domains` migration

**Files:**
- Create: `migrations/versions/0006_projects_add_email_domains.py`

- [ ] **Step 1: Write the migration file**

```python
"""projects_add_email_domains

Add email_domains TEXT[] column to projects table for Reply Triage
client_match resolution.

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §4.1

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "email_domains",
            postgresql.ARRAY(sa.Text),
            nullable=True,
        ),
    )
    # GIN index for "is this domain in any project's email_domains?" lookups
    op.execute(
        "CREATE INDEX idx_projects_email_domains "
        "ON projects USING GIN (email_domains)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_projects_email_domains")
    op.drop_column("projects", "email_domains")
```

- [ ] **Step 2: Run the migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade 0005 -> 0006, projects_add_email_domains`

- [ ] **Step 3: Verify column + index**

```bash
psql "$DATABASE_URL" -c "\d projects"
psql "$DATABASE_URL" -c "\di idx_projects_email_domains"
```

Expected: `email_domains | text[]` column; GIN index present.

- [ ] **Step 4: Seed user's known projects with their email domains (manual one-time, document for the user)**

This is a manual data step the operator runs once. Document in commit message. Do NOT script — operator may not want every domain populated yet.

First verify the actual slugs that SP2 seeded into the projects table — this protects against silently UPDATE-ing zero rows if the SP2 spec used different slugs:

```bash
psql "$DATABASE_URL" -c "SELECT slug, name FROM projects ORDER BY slug;"
```

Then map the operator's real client email domains to those slugs. Example based on SP2 §3.2 lines 179–187 seed values:

```sql
-- Run when ready (substitute the slugs you actually saw above):
UPDATE projects SET email_domains = ARRAY['ama.com']           WHERE slug = 'ama-solutions';
UPDATE projects SET email_domains = ARRAY['shooterista.com']   WHERE slug = 'shooterista';
UPDATE projects SET email_domains = ARRAY['suiteadvisors.com'] WHERE slug = 'suiteadvisors';
UPDATE projects SET email_domains = ARRAY['asiacapital.com']   WHERE slug = 'asia-capital';
-- MIDAR: personal — no email_domains needed
```

After UPDATE, verify row counts match expectations:
```bash
psql "$DATABASE_URL" -c "SELECT slug, email_domains FROM projects WHERE email_domains IS NOT NULL;"
```

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/0006_projects_add_email_domains.py
git commit -m "feat(sp5): add email_domains column to projects table

Per spec §4.1 — used by Reply Triage client_match resolution."
```

---

### Task 1.3: Implement `StateService`

**Files:**
- Create: `services/agent_state.py`
- Test: `tests/services/test_agent_state.py`

- [ ] **Step 1: Write the failing test file**

```python
# tests/services/test_agent_state.py
"""StateService unit tests — verifies Postgres-backed per-agent state."""

from __future__ import annotations

import asyncio
import time

import pytest

from services.agent_state import StateService, get_state_service
from services.db import get_db_service


@pytest.fixture
async def db():
    svc = get_db_service()
    await svc.connect()
    # Clean slate
    await svc.execute("DELETE FROM agent_state WHERE agent_name LIKE 'test_%'")
    yield svc
    await svc.execute("DELETE FROM agent_state WHERE agent_name LIKE 'test_%'")


@pytest.fixture
async def state(db):
    """Must be async so pytest-asyncio resolves the `db` async generator first."""
    return StateService(db)


@pytest.mark.asyncio
async def test_set_and_get_returns_value(state):
    await state.set("test_agent", "key1", {"foo": "bar"})
    result = await state.get("test_agent", "key1")
    assert result == {"foo": "bar"}


@pytest.mark.asyncio
async def test_get_missing_returns_default(state):
    result = await state.get("test_agent", "missing", default={"d": 1})
    assert result == {"d": 1}


@pytest.mark.asyncio
async def test_set_overwrites_existing(state):
    await state.set("test_agent", "key1", {"v": 1})
    await state.set("test_agent", "key1", {"v": 2})
    result = await state.get("test_agent", "key1")
    assert result == {"v": 2}


@pytest.mark.asyncio
async def test_set_with_ttl_populates_expires_at(state, db):
    await state.set("test_agent", "k_ttl", {"x": 1}, ttl_seconds=60)
    # immediately readable
    assert await state.get("test_agent", "k_ttl") == {"x": 1}
    # row has expires_at populated (~60s in future)
    row = await db.fetchrow(
        "SELECT expires_at FROM agent_state WHERE agent_name=$1 AND key=$2",
        "test_agent", "k_ttl",
    )
    assert row["expires_at"] is not None


@pytest.mark.asyncio
async def test_get_skips_expired_row_without_cleanup(state, db):
    """Verify the WHERE clause `expires_at > NOW()` works on its own."""
    await state.set("test_agent", "k_exp_read", {"x": 1}, ttl_seconds=60)
    # Force expiry without running cleanup_expired — get() must still skip it.
    await db.execute(
        "UPDATE agent_state SET expires_at = NOW() - INTERVAL '1 minute' "
        "WHERE agent_name=$1 AND key=$2",
        "test_agent", "k_exp_read",
    )
    assert await state.get("test_agent", "k_exp_read", default="MISS") == "MISS"


@pytest.mark.asyncio
async def test_delete_removes_row(state):
    await state.set("test_agent", "k_del", {"y": 1})
    await state.delete("test_agent", "k_del")
    assert await state.get("test_agent", "k_del") is None


@pytest.mark.asyncio
async def test_cleanup_expired_removes_only_expired(state, db):
    # one expired, one not
    await state.set("test_agent", "k_exp", {"a": 1}, ttl_seconds=1)
    await state.set("test_agent", "k_keep", {"b": 1})
    # force expiry by direct UPDATE in past
    await db.execute(
        "UPDATE agent_state SET expires_at = NOW() - INTERVAL '1 hour' "
        "WHERE agent_name=$1 AND key=$2",
        "test_agent", "k_exp",
    )
    deleted = await state.cleanup_expired()
    assert deleted >= 1
    assert await state.get("test_agent", "k_exp") is None
    assert await state.get("test_agent", "k_keep") == {"b": 1}


@pytest.mark.asyncio
async def test_set_rejects_non_serialisable_value(state):
    """Use a self-referencing dict — survives `default=str` fallback,
    triggers ValueError("Circular reference detected")."""
    circular: dict = {}
    circular["self"] = circular
    with pytest.raises(ValueError, match="not JSON-serialisable"):
        await state.set("test_agent", "k_bad", circular)


@pytest.mark.asyncio
async def test_get_state_service_returns_singleton():
    # Reset module-level singleton so this test is order-independent.
    import services.agent_state as mod
    mod._instance = None
    svc1 = get_state_service()
    svc2 = get_state_service()
    assert svc1 is svc2
```

- [ ] **Step 2: Run the failing test**

```bash
pytest tests/services/test_agent_state.py -v
```

Expected: all 9 tests fail with `ImportError: cannot import StateService`.

- [ ] **Step 3: Implement `StateService`**

```python
# services/agent_state.py
"""
StateService — Postgres-backed per-agent persistent state for SP5.

Used by:
  - ProactiveEngine cooldown / dedup / global-rate-limit reads & writes
  - EventDrivenAgent subclasses for streak counters, queues, dedup sets

Schema: see migrations/versions/0005_agent_state.py
Spec:   docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.1

Charter override (Rule 5): see spec §11. agent_state is mutable state,
not a log; storing in agent_logs would corrupt log semantics.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from services.db import get_db_service

logger = logging.getLogger("cruz.services.agent_state")

_instance: Optional["StateService"] = None


def get_state_service() -> "StateService":
    """Return the module-level StateService singleton."""
    global _instance
    if _instance is None:
        _instance = StateService(get_db_service())
    return _instance


class StateService:
    """Read/write per-agent state with optional TTL."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def get(
        self,
        agent: str,
        key: str,
        default: Any = None,
    ) -> Any:
        """Return the value at (agent, key), or default if absent or expired."""
        row = await self._db.fetchrow(
            """
            SELECT value
            FROM agent_state
            WHERE agent_name = $1
              AND key = $2
              AND (expires_at IS NULL OR expires_at > NOW())
            """,
            agent, key,
        )
        if row is None:
            return default
        # JSONB columns: asyncpg returns dict/list directly. Belt-and-braces
        # str fallback in case a future driver upgrade changes that.
        v = row["value"]
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v

    async def set(
        self,
        agent: str,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """Upsert (agent, key) → value with optional TTL.

        Raises:
            ValueError: if value cannot be JSON-serialised.
        """
        try:
            value_json = json.dumps(value, default=str)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"agent_state value for ({agent}, {key}) is not JSON-serialisable: {exc}"
            ) from exc

        if ttl_seconds is not None:
            await self._db.execute(
                """
                INSERT INTO agent_state (agent_name, key, value, expires_at, updated_at)
                VALUES ($1, $2, $3::jsonb, NOW() + ($4::int * INTERVAL '1 second'), NOW())
                ON CONFLICT (agent_name, key) DO UPDATE
                  SET value      = EXCLUDED.value,
                      expires_at = EXCLUDED.expires_at,
                      updated_at = NOW()
                """,
                agent, key, value_json, ttl_seconds,
            )
        else:
            await self._db.execute(
                """
                INSERT INTO agent_state (agent_name, key, value, expires_at, updated_at)
                VALUES ($1, $2, $3::jsonb, NULL, NOW())
                ON CONFLICT (agent_name, key) DO UPDATE
                  SET value      = EXCLUDED.value,
                      expires_at = NULL,
                      updated_at = NOW()
                """,
                agent, key, value_json,
            )

    async def delete(self, agent: str, key: str) -> None:
        """Remove a single (agent, key) row."""
        await self._db.execute(
            "DELETE FROM agent_state WHERE agent_name = $1 AND key = $2",
            agent, key,
        )

    async def cleanup_expired(self) -> int:
        """Delete all rows where expires_at <= NOW(). Returns count deleted."""
        result = await self._db.execute(
            "DELETE FROM agent_state WHERE expires_at IS NOT NULL AND expires_at <= NOW()"
        )
        # asyncpg returns "DELETE <n>" — best-effort parse
        try:
            return int(result.split()[-1]) if result else 0
        except Exception:
            return 0
```

- [ ] **Step 4: Run the tests**

```bash
pytest tests/services/test_agent_state.py -v
```

Expected: all 9 tests pass.

> **Note on Redis hot cache:** Spec §3.1 mentions hot cooldown/dedup reads cache through Redis. Chunk 1 deliberately omits the Redis cache layer because the only hot consumer is `ProactiveEngine`, built in Chunk 2. The cache will be added there as a thin wrapper around `StateService.get()` keyed on `(agent, key)`. `StateService` itself stays Postgres-only, single responsibility.

- [ ] **Step 5: Commit**

```bash
git add services/agent_state.py tests/services/test_agent_state.py
git commit -m "feat(sp5): add StateService for agent_state table

Per spec §3.1. Upsert via INSERT ON CONFLICT; TTL via expires_at;
cleanup_expired() called by daily 04:30 maintenance cron."
```

---

### Task 1.4: Verify Chunk 1 end-to-end

- [ ] **Step 1: Run all SP5 service tests so far**

```bash
pytest tests/services/test_agent_state.py -v --tb=short
```

Expected: 9 passed.

- [ ] **Step 2: Verify migration head**

```bash
alembic current
```

Expected: `0006 (head)`.

- [ ] **Step 3: Verify nothing v1 broke**

```bash
# Run v1 service tests EXCLUDING our new file. No -x: a flaky unrelated
# test must not block the chunk's verification.
pytest tests/services/ --ignore=tests/services/test_agent_state.py --tb=short
```

Expected: all v1 service tests still pass. If any pre-existing test is flaky for environmental reasons (Redis/Ollama not running locally), document the skip reason; it must not be a regression caused by Chunk 1.

- [ ] **Step 4: Tag chunk done (local-only recovery anchor)**

```bash
git tag claude/sp5-chunk-1-done
```

(Tag uses `claude/` prefix to mark it as machine-generated; delete before merge.)

---

**End of Chunk 1.** Foundations laid: `agent_state` table exists; `StateService` reads/writes/cleans it; `projects` table extended for Reply Triage. No agent or gate code yet.

---

## Chunk 2: ProactiveEngine — the gate

This chunk lands the central governance choke point. After it, agents have somewhere to call `gate.allow()` and be guaranteed false-criticals are structurally prevented. Includes Redis hot-cache wrapper deferred from Chunk 1.

### Task 2.1: Define `GateRequest` and `GateDecision` types

**Files:**
- Create: `services/proactive_engine.py` (initial — types only)
- Test: `tests/services/test_proactive_engine.py` (initial — type tests)

- [ ] **Step 1: Write failing test for type contracts**

```python
# tests/services/test_proactive_engine.py
"""ProactiveEngine gate — type contract tests come first."""

from __future__ import annotations

import pytest

from services.proactive_engine import GateDecision, GateRequest


def test_gate_decision_has_four_outcomes():
    assert {d.value for d in GateDecision} == {
        "allow", "suppress", "demote_warn", "demote_info"
    }


def test_gate_request_requires_severity():
    with pytest.raises(TypeError):
        GateRequest(agent="x", reason_code=None, dedup_key="k", payload={},
                    valid_critical_reasons=set())  # missing severity


def test_gate_request_accepts_valid_critical_reasons_set():
    req = GateRequest(
        agent="reply_triage",
        severity="critical",
        reason_code="client_email_unanswered_72h",
        dedup_key="email:abc",
        payload={"text": "..."},
        valid_critical_reasons={"client_email_unanswered_72h"},
    )
    assert req.severity == "critical"
    assert req.valid_critical_reasons == {"client_email_unanswered_72h"}
```

- [ ] **Step 2: Run failing test**

```bash
pytest tests/services/test_proactive_engine.py -v
```

Expected: 3 failures with `ImportError: cannot import GateDecision`.

- [ ] **Step 3: Implement types**

```python
# services/proactive_engine.py
"""
ProactiveEngine — the central gate for SP5 proactive notifications.

Every event-driven agent calls gate.allow(GateRequest) before emitting.
The gate enforces:
  1. Whitelist: criticals must declare a known reason_code per agent
  2. Dedup: same (agent, dedup_key) within DEDUP_WINDOW → SUPPRESS
  3. Per-agent cooldown: 1h between any pings, 24h between criticals
  4. Per-agent info cap: 20 info pings/agent/day
  5. Global daily rate limit: 8 non-info pings across all agents

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.2
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from services.agent_state import StateService, get_state_service
from services.db import get_db_service
from services.redis_client import get_redis_service

logger = logging.getLogger("cruz.services.proactive_engine")


class GateDecision(str, Enum):
    """Outcome of gate.allow() — see spec §3.2."""

    ALLOW          = "allow"
    SUPPRESS       = "suppress"
    DEMOTE_TO_WARN = "demote_warn"
    DEMOTE_TO_INFO = "demote_info"


@dataclass
class GateRequest:
    """One request to the gate — built by EventDrivenAgent.emit()."""

    agent: str
    severity: Literal["info", "warn", "critical"]
    reason_code: Optional[str]
    dedup_key: str
    payload: dict
    valid_critical_reasons: set[str] = field(default_factory=set)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/services/test_proactive_engine.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/proactive_engine.py tests/services/test_proactive_engine.py
git commit -m "feat(sp5): add GateRequest and GateDecision types

Per spec §3.2. ProactiveEngine.allow() implementation in next task."
```

---

### Task 2.2: Implement the gate decision algorithm (no Redis cache yet)

**Files:**
- Modify: `services/proactive_engine.py` — add `ProactiveEngine` class
- Modify: `tests/services/test_proactive_engine.py` — add gate decision tests

This task is large — the algorithm has 6 steps and many test cases. Each gate rule gets a test pair (the rule fires + the rule doesn't fire when conditions aren't met).

- [ ] **Step 1: Add the ProactiveEngine class skeleton + decision constants**

Append to `services/proactive_engine.py`:

```python
class ProactiveEngine:
    """Central gate. One instance per process."""

    # ── Gate parameters (spec §3.2) ─────────────────────────────────
    GLOBAL_DAILY_RATE_LIMIT  = 8           # non-info pings/day across all agents
    PER_AGENT_INFO_DAILY_CAP = 20          # info pings/day per agent
    PER_AGENT_COOLDOWN_ANY   = 3600        # 1h
    PER_AGENT_COOLDOWN_CRIT  = 86400       # 24h
    DEDUP_WINDOW             = 86400 * 7   # 7d

    GATE_AGENT = "_gate"
    GLOBAL_AGENT = "_global"

    def __init__(self, state: StateService, db: Any) -> None:
        self._state = state
        self._db = db


_instance: Optional[ProactiveEngine] = None


def get_proactive_engine() -> ProactiveEngine:
    global _instance
    if _instance is None:
        _instance = ProactiveEngine(get_state_service(), get_db_service())
    return _instance
```

- [ ] **Step 2: Write the failing test for whitelist enforcement**

Append to `tests/services/test_proactive_engine.py`:

```python
from services.proactive_engine import ProactiveEngine, get_proactive_engine


@pytest.fixture(autouse=True)
def _reset_proactive_engine_singleton():
    """Insulate tests from any code path that calls get_proactive_engine()
    against a real DB. Reset before AND after every test."""
    import services.proactive_engine as mod
    mod._instance = None
    yield
    mod._instance = None


class FakeStateService:
    """In-memory StateService for fast unit tests — no DB required."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], tuple[Any, float | None]] = {}

    async def get(self, agent: str, key: str, default: Any = None) -> Any:
        v = self.store.get((agent, key))
        if v is None:
            return default
        value, expires = v
        if expires is not None and expires <= time.time():
            return default
        return value

    async def set(self, agent: str, key: str, value: Any,
                  ttl_seconds: int | None = None) -> None:
        expires = time.time() + ttl_seconds if ttl_seconds else None
        self.store[(agent, key)] = (value, expires)

    async def delete(self, agent: str, key: str) -> None:
        self.store.pop((agent, key), None)


class FakeDB:
    """Records execute() calls so we can assert agent_logs writes happened."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    async def execute(self, sql: str, *args) -> str:
        self.calls.append((sql, args))
        return "INSERT 0 1"


@pytest.fixture
def fake_state():
    return FakeStateService()


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def gate(fake_state, fake_db):
    return ProactiveEngine(fake_state, fake_db)


# ── Whitelist tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_critical_without_reason_code_demotes_to_warn(gate):
    req = GateRequest(
        agent="x", severity="critical", reason_code=None,
        dedup_key="k1", payload={},
        valid_critical_reasons={"some_reason"},
    )
    decision = await gate.allow(req)
    assert decision == GateDecision.DEMOTE_TO_WARN


@pytest.mark.asyncio
async def test_critical_with_unwhitelisted_reason_demotes_to_warn(gate):
    req = GateRequest(
        agent="x", severity="critical", reason_code="invented_reason",
        dedup_key="k1", payload={},
        valid_critical_reasons={"only_this_one_is_valid"},
    )
    assert await gate.allow(req) == GateDecision.DEMOTE_TO_WARN


@pytest.mark.asyncio
async def test_critical_with_whitelisted_reason_allows(gate):
    req = GateRequest(
        agent="x", severity="critical", reason_code="valid_reason",
        dedup_key="k1", payload={},
        valid_critical_reasons={"valid_reason"},
    )
    assert await gate.allow(req) == GateDecision.ALLOW
```

- [ ] **Step 3: Run failing tests**

```bash
pytest tests/services/test_proactive_engine.py -v -k whitelist
```

Expected: 3 failures — `ProactiveEngine` has no `allow` method yet.

- [ ] **Step 4: Implement `allow()` step 1 (whitelist) + step 6 (default ALLOW + counters)**

Add to `ProactiveEngine`:

```python
    async def allow(self, req: GateRequest) -> GateDecision:
        """Run the gate decision algorithm (spec §3.2)."""
        decision = await self._decide(req)
        await self._post_decision(req, decision)
        await self._log_decision(req, decision)
        return decision

    async def _decide(self, req: GateRequest) -> GateDecision:
        # Step 1: Whitelist
        if req.severity == "critical":
            if (req.reason_code is None
                    or req.reason_code not in req.valid_critical_reasons):
                return GateDecision.DEMOTE_TO_WARN

        # Step 2: Dedup
        dedup_key = f"dedup:{req.agent}:{req.dedup_key}"
        if await self._state.get(self.GATE_AGENT, dedup_key) is not None:
            return GateDecision.SUPPRESS

        # Step 3: Critical cooldown
        if req.severity == "critical":
            cool_crit = await self._state.get(
                self.GATE_AGENT, f"cooldown:{req.agent}:critical")
            if cool_crit is not None and time.time() - cool_crit < self.PER_AGENT_COOLDOWN_CRIT:
                return GateDecision.SUPPRESS

        # Step 4: Per-agent cooldown
        cool_any = await self._state.get(
            self.GATE_AGENT, f"cooldown:{req.agent}:any")
        if cool_any is not None and time.time() - cool_any < self.PER_AGENT_COOLDOWN_ANY:
            if req.severity == "info":
                # Step 4a: per-agent info safety cap
                today = self._today()
                cnt = await self._state.get(
                    self.GLOBAL_AGENT,
                    f"info_count_per_agent:{req.agent}:{today}",
                    default=0,
                )
                if cnt >= self.PER_AGENT_INFO_DAILY_CAP:
                    return GateDecision.SUPPRESS
                return GateDecision.ALLOW
            return GateDecision.DEMOTE_TO_INFO

        # Step 5: Global daily rate limit (non-info only)
        if req.severity != "info":
            today = self._today()
            daily = await self._state.get(
                self.GLOBAL_AGENT, f"daily_count:{today}", default=0)
            if daily >= self.GLOBAL_DAILY_RATE_LIMIT:
                return GateDecision.SUPPRESS

        # Step 4a (re-check for info path that didn't hit cooldown)
        if req.severity == "info":
            today = self._today()
            cnt = await self._state.get(
                self.GLOBAL_AGENT,
                f"info_count_per_agent:{req.agent}:{today}",
                default=0,
            )
            if cnt >= self.PER_AGENT_INFO_DAILY_CAP:
                return GateDecision.SUPPRESS

        return GateDecision.ALLOW

    async def _post_decision(self, req: GateRequest, decision: GateDecision) -> None:
        """Update counters/cooldowns after a non-suppressed decision."""
        if decision == GateDecision.SUPPRESS:
            return

        now_ts = time.time()
        today = self._today()

        # Per-agent any-cooldown (always set when something routes)
        await self._state.set(
            self.GATE_AGENT, f"cooldown:{req.agent}:any", now_ts,
            ttl_seconds=self.PER_AGENT_COOLDOWN_ANY,
        )

        # Critical cooldown only when this was actually a critical that ALLOWed
        if decision == GateDecision.ALLOW and req.severity == "critical":
            await self._state.set(
                self.GATE_AGENT, f"cooldown:{req.agent}:critical", now_ts,
                ttl_seconds=self.PER_AGENT_COOLDOWN_CRIT,
            )

        # Dedup key (always set when routed — prevents repeat of the same logical ping)
        await self._state.set(
            self.GATE_AGENT, f"dedup:{req.agent}:{req.dedup_key}", now_ts,
            ttl_seconds=self.DEDUP_WINDOW,
        )

        # Counter: routed severity. Use the EFFECTIVE severity after demotion.
        eff_severity = self._effective_severity(req.severity, decision)
        if eff_severity == "info":
            cnt_key = f"info_count_per_agent:{req.agent}:{today}"
            cnt = await self._state.get(self.GLOBAL_AGENT, cnt_key, default=0)
            await self._state.set(
                self.GLOBAL_AGENT, cnt_key, cnt + 1,
                ttl_seconds=86400 * 2,
            )
        else:
            cnt = await self._state.get(
                self.GLOBAL_AGENT, f"daily_count:{today}", default=0)
            await self._state.set(
                self.GLOBAL_AGENT, f"daily_count:{today}", cnt + 1,
                ttl_seconds=86400 * 2,
            )

    async def _log_decision(self, req: GateRequest, decision: GateDecision) -> None:
        """Write a row to agent_logs with action='gate_decision'."""
        try:
            await self._db.execute(
                """
                INSERT INTO agent_logs
                    (trace_id, agent, action, status, input_data, output_data,
                     tokens_used, duration_ms)
                VALUES ($1, $2, 'gate_decision', $3, $4::jsonb, $5::jsonb, 0, 0)
                """,
                req.payload.get("trace_id", "no-trace"),
                req.agent,
                decision.value,
                json.dumps({
                    "severity": req.severity,
                    "reason_code": req.reason_code,
                    "dedup_key": req.dedup_key,
                }),
                json.dumps({"decision": decision.value}),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("gate_decision log failed (non-fatal): %s", exc)

    @staticmethod
    def _effective_severity(severity: str, decision: GateDecision) -> str:
        if decision == GateDecision.ALLOW:
            return severity
        if decision == GateDecision.DEMOTE_TO_WARN:
            return "warn"
        if decision == GateDecision.DEMOTE_TO_INFO:
            return "info"
        return severity  # SUPPRESS — caller skips

    @staticmethod
    def _today() -> str:
        """UTC date string for daily counters."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
```

- [ ] **Step 5: Run whitelist tests, expect pass**

```bash
pytest tests/services/test_proactive_engine.py -v -k whitelist
```

Expected: 3 passed.

- [ ] **Step 6: Commit progress**

```bash
git add services/proactive_engine.py tests/services/test_proactive_engine.py
git commit -m "feat(sp5): implement ProactiveEngine.allow() — whitelist + counters

Per spec §3.2 steps 1+6. Dedup, cooldown, rate-limit tests follow."
```

---

### Task 2.3: Test dedup, cooldown, rate-limit, and counters

**Files:**
- Modify: `tests/services/test_proactive_engine.py` — exhaustive gate decision matrix

- [ ] **Step 1: Add the dedup tests**

Append:

```python
# ── Dedup tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_first_warn_allows_then_dedup_suppresses(gate, fake_state):
    req = GateRequest(
        agent="x", severity="warn", reason_code=None,
        dedup_key="dup-1", payload={},
        valid_critical_reasons=set(),
    )
    assert await gate.allow(req) == GateDecision.ALLOW
    # Same dedup_key, second call → SUPPRESS
    assert await gate.allow(req) == GateDecision.SUPPRESS


@pytest.mark.asyncio
async def test_different_dedup_keys_both_allow(gate):
    # Different agents to avoid the per-agent cooldown
    req1 = GateRequest(agent="a", severity="warn", reason_code=None,
                       dedup_key="k1", payload={}, valid_critical_reasons=set())
    req2 = GateRequest(agent="b", severity="warn", reason_code=None,
                       dedup_key="k2", payload={}, valid_critical_reasons=set())
    assert await gate.allow(req1) == GateDecision.ALLOW
    assert await gate.allow(req2) == GateDecision.ALLOW


@pytest.mark.asyncio
async def test_dedup_expires_after_window(gate, fake_state):
    req = GateRequest(agent="x", severity="warn", reason_code=None,
                      dedup_key="exp", payload={}, valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.ALLOW
    # Manually expire dedup + cooldown
    fake_state.store.pop(("_gate", "dedup:x:exp"), None)
    fake_state.store.pop(("_gate", "cooldown:x:any"), None)
    assert await gate.allow(req) == GateDecision.ALLOW
```

- [ ] **Step 2: Add cooldown tests**

```python
# ── Cooldown tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_warn_after_cooldown_demotes_to_info(gate, fake_state):
    r1 = GateRequest(agent="x", severity="warn", reason_code=None,
                     dedup_key="k1", payload={}, valid_critical_reasons=set())
    r2 = GateRequest(agent="x", severity="warn", reason_code=None,
                     dedup_key="k2", payload={}, valid_critical_reasons=set())
    assert await gate.allow(r1) == GateDecision.ALLOW
    # Same agent, different dedup, within 1h → DEMOTE_TO_INFO
    assert await gate.allow(r2) == GateDecision.DEMOTE_TO_INFO


@pytest.mark.asyncio
async def test_info_within_cooldown_still_allows(gate):
    """Info isn't rate-limited at agent level."""
    r1 = GateRequest(agent="x", severity="info", reason_code=None,
                     dedup_key="k1", payload={}, valid_critical_reasons=set())
    r2 = GateRequest(agent="x", severity="info", reason_code=None,
                     dedup_key="k2", payload={}, valid_critical_reasons=set())
    assert await gate.allow(r1) == GateDecision.ALLOW
    assert await gate.allow(r2) == GateDecision.ALLOW


@pytest.mark.asyncio
async def test_critical_cooldown_suppresses_second_critical(gate):
    """Two criticals within 24h from same agent → second SUPPRESS."""
    valid = {"reason_a"}
    r1 = GateRequest(agent="x", severity="critical", reason_code="reason_a",
                     dedup_key="k1", payload={}, valid_critical_reasons=valid)
    r2 = GateRequest(agent="x", severity="critical", reason_code="reason_a",
                     dedup_key="k2", payload={}, valid_critical_reasons=valid)
    assert await gate.allow(r1) == GateDecision.ALLOW
    assert await gate.allow(r2) == GateDecision.SUPPRESS
```

- [ ] **Step 3: Add global rate limit + info-cap tests**

```python
# ── Global rate limit ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_global_daily_rate_limit_suppresses_warn(gate, fake_state):
    """8 non-info pings allowed, 9th SUPPRESSED."""
    today = ProactiveEngine._today()
    fake_state.store[("_global", f"daily_count:{today}")] = (8, None)
    req = GateRequest(agent="fresh_agent", severity="warn", reason_code=None,
                      dedup_key="k_overflow", payload={},
                      valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.SUPPRESS


@pytest.mark.asyncio
async def test_global_rate_limit_does_not_suppress_info(gate, fake_state):
    today = ProactiveEngine._today()
    fake_state.store[("_global", f"daily_count:{today}")] = (100, None)
    req = GateRequest(agent="fresh", severity="info", reason_code=None,
                      dedup_key="k_info", payload={},
                      valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.ALLOW


# ── Per-agent info safety cap ───────────────────────────────────

@pytest.mark.asyncio
async def test_info_cap_suppresses_after_20_per_agent_per_day(gate, fake_state):
    today = ProactiveEngine._today()
    fake_state.store[
        ("_global", f"info_count_per_agent:noisy:{today}")] = (20, None)
    req = GateRequest(agent="noisy", severity="info", reason_code=None,
                      dedup_key="k_cap", payload={},
                      valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.SUPPRESS


@pytest.mark.asyncio
async def test_info_cap_does_not_affect_other_agents(gate, fake_state):
    today = ProactiveEngine._today()
    fake_state.store[
        ("_global", f"info_count_per_agent:noisy:{today}")] = (50, None)
    req = GateRequest(agent="quiet", severity="info", reason_code=None,
                      dedup_key="k", payload={},
                      valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.ALLOW
```

- [ ] **Step 4: Add counter-increment tests**

```python
# ── Counter increments ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_allow_increments_global_daily_count(gate, fake_state):
    req = GateRequest(agent="x", severity="warn", reason_code=None,
                      dedup_key="k1", payload={}, valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.ALLOW
    today = ProactiveEngine._today()
    cnt, _ = fake_state.store[("_global", f"daily_count:{today}")]
    assert cnt == 1


@pytest.mark.asyncio
async def test_demote_to_info_increments_info_counter_not_global(gate, fake_state):
    """The EFFECTIVE severity drives the counter."""
    fake_state.store[("_gate", "cooldown:x:any")] = (time.time(), None)
    req = GateRequest(agent="x", severity="warn", reason_code=None,
                      dedup_key="k1", payload={}, valid_critical_reasons=set())
    decision = await gate.allow(req)
    assert decision == GateDecision.DEMOTE_TO_INFO
    today = ProactiveEngine._today()
    info_cnt, _ = fake_state.store.get(
        ("_global", f"info_count_per_agent:x:{today}"), (0, None))
    assert info_cnt == 1
    assert ("_global", f"daily_count:{today}") not in fake_state.store


@pytest.mark.asyncio
async def test_suppress_increments_no_counter(gate, fake_state):
    today = ProactiveEngine._today()
    fake_state.store[("_global", f"daily_count:{today}")] = (8, None)
    req = GateRequest(agent="x", severity="warn", reason_code=None,
                      dedup_key="k", payload={}, valid_critical_reasons=set())
    assert await gate.allow(req) == GateDecision.SUPPRESS
    cnt_after, _ = fake_state.store[("_global", f"daily_count:{today}")]
    assert cnt_after == 8  # unchanged
```

- [ ] **Step 5: Add agent_logs write test**

```python
# ── Logging ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_every_decision_writes_to_agent_logs(gate, fake_db):
    req = GateRequest(agent="x", severity="info", reason_code=None,
                      dedup_key="k1",
                      payload={"trace_id": "trace-1"},
                      valid_critical_reasons=set())
    await gate.allow(req)
    # one INSERT row, action='gate_decision'
    assert len(fake_db.calls) == 1
    sql, args = fake_db.calls[0]
    assert "INSERT INTO agent_logs" in sql
    assert args[0] == "trace-1"
    assert args[1] == "x"
    assert args[2] == "allow"  # decision
```

- [ ] **Step 6: Run all gate tests**

```bash
pytest tests/services/test_proactive_engine.py -v
```

Expected: **20 passed** (3 type + 3 whitelist + 3 dedup + 3 cooldown + 4 global/cap + 3 counter + 1 logging).

- [ ] **Step 7: Commit**

```bash
git add services/proactive_engine.py tests/services/test_proactive_engine.py
git commit -m "test(sp5): exhaustive ProactiveEngine gate decision matrix

Covers all 6 decision steps from spec §3.2 plus counter-increment and
agent_logs write paths."
```

---

### Task 2.4: Add Redis hot-cache wrapper for cooldown/dedup reads

The gate reads `cooldown:*` and `dedup:*` keys on every dispatch. Postgres roundtrip per call is fine in tests but adds 5-10ms per dispatch in production. Per spec §3.1, hot reads cache through Redis with the same key.

**Critical correctness constraint.** Counter reads (`info_count_per_agent:*` and `daily_count:*`) MUST NOT go through the cache. They participate in read-modify-write increments — a 60s-stale cached read would cause silent counter loss, breaking both the global rate limit (`<8/day`) and the SP5 exit-gate measurement of pings/day. Cache only the cooldown/dedup keys that are simple existence/timestamp probes.

**Files:**
- Modify: `services/proactive_engine.py` — add `_cached_get` + `_cache_invalidate`; selectively swap reads
- Modify: `tests/services/test_proactive_engine.py` — add cache test + invalidation test

- [ ] **Step 1: Write failing test for cache-key invocation**

Append to `tests/services/test_proactive_engine.py`:

```python
@pytest.mark.asyncio
async def test_cached_get_called_for_cooldown_and_dedup(monkeypatch, gate):
    """`_decide` reads dedup + cooldown:any through the cache wrapper."""
    calls: list[tuple[str, str]] = []
    original = gate._cached_get
    async def spy(agent: str, key: str, default: Any = None) -> Any:
        calls.append((agent, key))
        return await original(agent, key, default)
    monkeypatch.setattr(gate, "_cached_get", spy)

    req = GateRequest(agent="x", severity="warn", reason_code=None,
                      dedup_key="hot1", payload={},
                      valid_critical_reasons=set())
    await gate.allow(req)
    keys_read = {k for _, k in calls}
    assert "dedup:x:hot1" in keys_read
    assert "cooldown:x:any" in keys_read
```

- [ ] **Step 2: Write failing test confirming counters bypass cache**

```python
@pytest.mark.asyncio
async def test_counter_reads_bypass_cache(monkeypatch, gate):
    """Counter read-modify-write paths MUST stay on uncached state.get
    to avoid 60s-stale cache losing increments."""
    cached_calls: list[str] = []
    state_calls: list[str] = []
    orig_cached = gate._cached_get
    orig_state = gate._state.get

    async def cached_spy(agent, key, default=None):
        cached_calls.append(key)
        return await orig_cached(agent, key, default)

    async def state_spy(agent, key, default=None):
        state_calls.append(key)
        return await orig_state(agent, key, default)

    monkeypatch.setattr(gate, "_cached_get", cached_spy)
    monkeypatch.setattr(gate._state, "get", state_spy)

    today = ProactiveEngine._today()
    req = GateRequest(agent="x", severity="warn", reason_code=None,
                      dedup_key="k_cnt", payload={},
                      valid_critical_reasons=set())
    await gate.allow(req)

    # daily_count read in _decide step 5 AND the read-modify-write in _post_decision
    # must use uncached state.get
    daily_key = f"daily_count:{today}"
    assert daily_key in state_calls, "counter read must bypass cache"
    assert daily_key not in cached_calls, "counter must NOT be cached"
```

- [ ] **Step 3: Write failing test for cache invalidation on set**

```python
@pytest.mark.asyncio
async def test_cache_invalidate_called_after_each_set(monkeypatch, gate):
    invalidated: list[tuple[str, str]] = []
    orig = gate._cache_invalidate
    async def spy(agent, key):
        invalidated.append((agent, key))
        await orig(agent, key)
    monkeypatch.setattr(gate, "_cache_invalidate", spy)

    req = GateRequest(agent="x", severity="critical", reason_code="r1",
                      dedup_key="k_inv", payload={},
                      valid_critical_reasons={"r1"})
    await gate.allow(req)
    invalidated_keys = {k for _, k in invalidated}
    # Every cacheable key written in _post_decision must be invalidated
    assert "cooldown:x:any" in invalidated_keys
    assert "cooldown:x:critical" in invalidated_keys
    assert "dedup:x:k_inv" in invalidated_keys
```

- [ ] **Step 4: Run failing tests**

```bash
pytest tests/services/test_proactive_engine.py::test_cached_get_called_for_cooldown_and_dedup tests/services/test_proactive_engine.py::test_counter_reads_bypass_cache tests/services/test_proactive_engine.py::test_cache_invalidate_called_after_each_set -v
```

Expected: 3 failures with `AttributeError: 'ProactiveEngine' object has no attribute '_cached_get'`.

- [ ] **Step 5: Add `_MISSING` sentinel + `_cached_get` + `_cache_invalidate`**

Append to `ProactiveEngine` class (above the existing helper methods):

```python
    # ── Hot cache wrapper (Redis read-through) ────────────────────
    #
    # Cacheable: cooldown:* and dedup:* keys (existence/timestamp probes).
    # NOT cacheable: counter keys (info_count_per_agent, daily_count) —
    # they participate in read-modify-write increments. A stale read
    # would silently lose counter increments. See spec §3.1, §3.2 step 5.

    CACHE_TTL_SECONDS = 60

    # Sentinel — `is`-comparable, distinct from any user value including 0/None.
    _MISSING = object()

    async def _cached_get(
        self, agent: str, key: str, default: Any = None,
    ) -> Any:
        """Read-through cache. Redis first, then StateService (Postgres)."""
        cache_key = f"cruz:gate:{agent}:{key}"
        try:
            redis = get_redis_service()
            if redis.client is not None:
                raw = await redis.client.get(cache_key)
                if raw is not None:
                    if raw in (b"__MISSING__", "__MISSING__"):
                        return default
                    try:
                        return json.loads(raw)
                    except Exception:
                        return default
        except Exception as exc:  # noqa: BLE001
            logger.debug("redis cache read failed (non-fatal): %s", exc)

        # Cache miss — read source of truth using the sentinel so we can
        # distinguish "absent" from "value happens to equal default".
        value = await self._state.get(agent, key, self._MISSING)
        was_missing = value is self._MISSING
        if was_missing:
            value = default

        try:
            redis = get_redis_service()
            if redis.client is not None:
                payload = "__MISSING__" if was_missing else json.dumps(value, default=str)
                await redis.client.set(cache_key, payload, ex=self.CACHE_TTL_SECONDS)
        except Exception as exc:
            logger.debug("redis cache write failed (non-fatal): %s", exc)
        return value

    async def _cache_invalidate(self, agent: str, key: str) -> None:
        try:
            redis = get_redis_service()
            if redis.client is not None:
                await redis.client.delete(f"cruz:gate:{agent}:{key}")
        except Exception:
            pass
```

- [ ] **Step 6: Selectively swap reads — only cooldown/dedup, NOT counters**

Edit `_decide` exactly as follows. Counter reads (`info_count_per_agent:*`, `daily_count:*`) stay on `self._state.get(...)`. Cooldown/dedup reads switch to `self._cached_get(...)`.

```python
    async def _decide(self, req: GateRequest) -> GateDecision:
        # Step 1: Whitelist (no state read)
        if req.severity == "critical":
            if (req.reason_code is None
                    or req.reason_code not in req.valid_critical_reasons):
                return GateDecision.DEMOTE_TO_WARN

        # Step 2: Dedup — CACHED
        dedup_key = f"dedup:{req.agent}:{req.dedup_key}"
        if await self._cached_get(self.GATE_AGENT, dedup_key) is not None:
            return GateDecision.SUPPRESS

        # Step 3: Critical cooldown — CACHED
        if req.severity == "critical":
            cool_crit = await self._cached_get(
                self.GATE_AGENT, f"cooldown:{req.agent}:critical")
            if cool_crit is not None and time.time() - cool_crit < self.PER_AGENT_COOLDOWN_CRIT:
                return GateDecision.SUPPRESS

        # Step 4: Per-agent cooldown — CACHED
        cool_any = await self._cached_get(
            self.GATE_AGENT, f"cooldown:{req.agent}:any")
        if cool_any is not None and time.time() - cool_any < self.PER_AGENT_COOLDOWN_ANY:
            if req.severity == "info":
                # Step 4a: per-agent info safety cap — UNCACHED counter
                today = self._today()
                cnt = await self._state.get(
                    self.GLOBAL_AGENT,
                    f"info_count_per_agent:{req.agent}:{today}",
                    default=0,
                )
                if cnt >= self.PER_AGENT_INFO_DAILY_CAP:
                    return GateDecision.SUPPRESS
                return GateDecision.ALLOW
            return GateDecision.DEMOTE_TO_INFO

        # Step 5: Global daily rate limit (non-info only) — UNCACHED counter
        if req.severity != "info":
            today = self._today()
            daily = await self._state.get(
                self.GLOBAL_AGENT, f"daily_count:{today}", default=0)
            if daily >= self.GLOBAL_DAILY_RATE_LIMIT:
                return GateDecision.SUPPRESS

        # Step 4a (info path that didn't hit cooldown) — UNCACHED counter.
        # Spec §3.2 step 5: "info still routed up to the per-agent cap from 4a"
        # — required so the cap binds info pings even outside cooldown.
        if req.severity == "info":
            today = self._today()
            cnt = await self._state.get(
                self.GLOBAL_AGENT,
                f"info_count_per_agent:{req.agent}:{today}",
                default=0,
            )
            if cnt >= self.PER_AGENT_INFO_DAILY_CAP:
                return GateDecision.SUPPRESS

        return GateDecision.ALLOW
```

- [ ] **Step 7: Update `_post_decision` to invalidate cache after every set, and keep counter reads uncached**

Replace `_post_decision` body with:

```python
    async def _post_decision(self, req: GateRequest, decision: GateDecision) -> None:
        """Update counters/cooldowns after a non-suppressed decision.

        Counter reads stay on `self._state.get` (uncached) — see Task 2.4
        constraint. Cacheable writes (cooldown/dedup) invalidate the cache
        immediately after the set so the next dispatch sees fresh state.
        """
        if decision == GateDecision.SUPPRESS:
            return

        now_ts = time.time()
        today = self._today()

        # Per-agent any-cooldown
        await self._state.set(
            self.GATE_AGENT, f"cooldown:{req.agent}:any", now_ts,
            ttl_seconds=self.PER_AGENT_COOLDOWN_ANY,
        )
        await self._cache_invalidate(self.GATE_AGENT, f"cooldown:{req.agent}:any")

        # Critical cooldown only when this was actually a critical that ALLOWed
        if decision == GateDecision.ALLOW and req.severity == "critical":
            await self._state.set(
                self.GATE_AGENT, f"cooldown:{req.agent}:critical", now_ts,
                ttl_seconds=self.PER_AGENT_COOLDOWN_CRIT,
            )
            await self._cache_invalidate(
                self.GATE_AGENT, f"cooldown:{req.agent}:critical")

        # Dedup key
        await self._state.set(
            self.GATE_AGENT, f"dedup:{req.agent}:{req.dedup_key}", now_ts,
            ttl_seconds=self.DEDUP_WINDOW,
        )
        await self._cache_invalidate(
            self.GATE_AGENT, f"dedup:{req.agent}:{req.dedup_key}")

        # Counter increment — UNCACHED read + write to avoid stale-cache races.
        # NOTE: not atomic across processes. With one ARQ worker process this
        # is fine. If we ever scale to >1 worker, switch to a SQL atomic
        # increment (e.g. UPDATE ... SET value = ((value::text)::int + 1)::text::jsonb).
        eff_severity = self._effective_severity(req.severity, decision)
        if eff_severity == "info":
            cnt_key = f"info_count_per_agent:{req.agent}:{today}"
            cnt = await self._state.get(self.GLOBAL_AGENT, cnt_key, default=0)
            await self._state.set(
                self.GLOBAL_AGENT, cnt_key, cnt + 1,
                ttl_seconds=86400 * 2,
            )
        else:
            cnt = await self._state.get(
                self.GLOBAL_AGENT, f"daily_count:{today}", default=0)
            await self._state.set(
                self.GLOBAL_AGENT, f"daily_count:{today}", cnt + 1,
                ttl_seconds=86400 * 2,
            )
```

- [ ] **Step 8: Run all proactive_engine tests**

```bash
pytest tests/services/test_proactive_engine.py -v
```

Expected: **23 passed** (the previous 20 + 3 new cache/invalidation tests). Redis is optional in test env — the `redis.client is not None` guards make the cache a no-op when Redis isn't connected, so tests pass with or without Redis running. Tests that depend on the no-Redis fallback (e.g., counter manipulation via `fake_state.store`) will continue to work.

- [ ] **Step 9: Commit**

```bash
git add services/proactive_engine.py tests/services/test_proactive_engine.py
git commit -m "feat(sp5): add Redis hot cache to ProactiveEngine

Per spec §3.1. Cooldown/dedup reads cache through Redis with 60s TTL.
Counter reads (info_count_per_agent, daily_count) deliberately bypass
cache to avoid stale-read races on read-modify-write increments.
Cache invalidated explicitly after every state.set in _post_decision."
```

---

### Task 2.5: Verify Chunk 2 end-to-end

- [ ] **Step 1: Full test run**

```bash
pytest tests/services/test_proactive_engine.py tests/services/test_agent_state.py -v --tb=short
```

Expected: all SP5 service tests pass.

- [ ] **Step 2: Manual smoke (optional but recommended)**

```python
# Drop into ipython:
import asyncio
from services.db import get_db_service
from services.proactive_engine import ProactiveEngine, GateRequest, GateDecision
from services.agent_state import StateService

async def smoke():
    db = get_db_service()
    await db.connect()
    state = StateService(db)
    gate = ProactiveEngine(state, db)
    # Clean
    await db.execute("DELETE FROM agent_state WHERE agent_name LIKE '_g%'")
    req = GateRequest(agent="smoke", severity="critical",
                      reason_code="known", dedup_key="s1",
                      payload={"trace_id": "smoke-1"},
                      valid_critical_reasons={"known"})
    print(await gate.allow(req))   # ALLOW
    print(await gate.allow(req))   # SUPPRESS (dedup)
    await db.execute("DELETE FROM agent_state WHERE agent_name LIKE '_g%'")
    await db.execute("DELETE FROM agent_logs WHERE agent='smoke'")

asyncio.run(smoke())
```

Expected: `GateDecision.ALLOW` then `GateDecision.SUPPRESS`. Verify a `gate_decision` row appeared in `agent_logs`:

```bash
psql "$DATABASE_URL" -c \
  "SELECT trace_id, agent, action, status FROM agent_logs WHERE action='gate_decision' ORDER BY created_at DESC LIMIT 5"
```

- [ ] **Step 3: Tag chunk done**

```bash
git tag claude/sp5-chunk-2-done
```

---

**End of Chunk 2.** Gate is live. `gate.allow(req)` is the structural defense against false-criticals (whitelist enforcement). All 6 decision steps from spec §3.2 implemented and tested. Redis hot cache in place.

---

## Chunk 3: NotificationRouter + TelegramChannel

This chunk lands the pluggable notification surface. After it, anything that calls `router.route(severity, payload)` reaches Telegram. SP3/SP7 channels later register without touching the gate or agents.

### Task 3.1: Define `Channel` protocol and `NotificationRouter`

**Files:**
- Create: `services/notification_router.py`
- Test: `tests/services/test_notification_router.py`

- [ ] **Step 1: Write failing tests for the router**

```python
# tests/services/test_notification_router.py
"""NotificationRouter — pluggable channel registry, per-severity dispatch."""

from __future__ import annotations

from typing import Any

import pytest

from services.notification_router import (
    Channel,
    NotificationRouter,
    get_notification_router,
)


class FakeChannel:
    def __init__(self, name: str, sevs: set[str]) -> None:
        self.name = name
        self.handles_severities = sevs
        self.calls: list[tuple[str, dict]] = []

    async def send(self, severity: str, payload: dict) -> None:
        self.calls.append((severity, payload))


class FailingChannel:
    name = "failing"
    handles_severities = {"info", "warn", "critical"}

    async def send(self, severity: str, payload: dict) -> None:
        raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def _reset_router_singleton():
    import services.notification_router as mod
    mod._instance = None
    yield
    mod._instance = None


@pytest.fixture
def router():
    return NotificationRouter()


@pytest.mark.asyncio
async def test_register_then_route_calls_channel(router):
    ch = FakeChannel("c1", {"warn", "critical"})
    router.register(ch)
    await router.route("warn", {"text": "hi"})
    assert ch.calls == [("warn", {"text": "hi"})]


@pytest.mark.asyncio
async def test_route_skips_channel_for_unhandled_severity(router):
    ch = FakeChannel("crit_only", {"critical"})
    router.register(ch)
    await router.route("info", {"text": "x"})
    assert ch.calls == []


@pytest.mark.asyncio
async def test_route_calls_all_matching_channels(router):
    a = FakeChannel("a", {"info"})
    b = FakeChannel("b", {"info", "warn"})
    router.register(a)
    router.register(b)
    await router.route("info", {"x": 1})
    assert a.calls == [("info", {"x": 1})]
    assert b.calls == [("info", {"x": 1})]


@pytest.mark.asyncio
async def test_failing_channel_does_not_block_others(router, caplog):
    fail = FailingChannel()
    ok = FakeChannel("ok", {"warn"})
    router.register(fail)
    router.register(ok)
    await router.route("warn", {"x": 1})
    assert ok.calls == [("warn", {"x": 1})]
    assert "failing" in caplog.text.lower() or "boom" in caplog.text.lower()


@pytest.mark.asyncio
async def test_register_same_name_replaces_existing(router, caplog):
    """Idempotent registration: re-registering by the same name swaps in
    the new instance (only it receives subsequent route() calls) and
    emits a warning so accidental double-registers are visible."""
    import logging
    caplog.set_level(logging.WARNING, logger="cruz.services.notification_router")
    first = FakeChannel("dup", {"warn"})
    second = FakeChannel("dup", {"warn"})
    router.register(first)
    router.register(second)
    await router.route("warn", {"x": 1})
    assert first.calls == []
    assert second.calls == [("warn", {"x": 1})]
    assert "already registered" in caplog.text.lower()


@pytest.mark.asyncio
async def test_get_notification_router_returns_singleton():
    a = get_notification_router()
    b = get_notification_router()
    assert a is b
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/services/test_notification_router.py -v
```

Expected: all 6 fail with `ImportError`.

- [ ] **Step 3: Implement `NotificationRouter`**

```python
# services/notification_router.py
"""
NotificationRouter — per-severity dispatch over a pluggable channel registry.

SP5 ships exactly one channel: TelegramChannel (built in Task 3.2).
SP3 will register IMessageChannel (criticals only).
SP7 will register FCMChannel (warns + criticals) and VoiceDaemonChannel.

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.3
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger("cruz.services.notification_router")


@runtime_checkable
class Channel(Protocol):
    """One notification target — Telegram, iMessage, FCM, voice daemon."""

    name: str
    handles_severities: set[str]

    async def send(self, severity: str, payload: dict) -> None: ...


class NotificationRouter:
    """Fan-out router. Routes one (severity, payload) to all channels
    that declare they handle that severity. Channel failures are logged
    and do not abort the route — other channels still receive the call."""

    def __init__(self) -> None:
        self._channels: list[Channel] = []

    def register(self, channel: Channel) -> None:
        """Add a channel. Idempotent on `channel.name`."""
        if any(c.name == channel.name for c in self._channels):
            logger.warning("channel %s already registered, replacing", channel.name)
            self._channels = [c for c in self._channels if c.name != channel.name]
        self._channels.append(channel)

    async def route(self, severity: str, payload: dict) -> None:
        """Dispatch one message to every channel that handles `severity`."""
        for ch in self._channels:
            if severity not in ch.handles_severities:
                continue
            try:
                await ch.send(severity, payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "notification channel %s failed (non-fatal): %s",
                    ch.name, exc,
                )


_instance: Optional[NotificationRouter] = None


def get_notification_router() -> NotificationRouter:
    global _instance
    if _instance is None:
        _instance = NotificationRouter()
    return _instance
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/services/test_notification_router.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add services/notification_router.py tests/services/test_notification_router.py
git commit -m "feat(sp5): add NotificationRouter with pluggable channel registry

Per spec §3.3. Channel failures don't block other channels; idempotent
registration by name. SP3/SP7 channels register here without touching
gate or agents."
```

---

### Task 3.2: Implement `TelegramChannel`

**Files:**
- Modify: `services/notification_router.py` — add `TelegramChannel` class
- Modify: `tests/services/test_notification_router.py` — add Telegram tests
- Modify: `.env.example` (or document) — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_FEED_TOPIC_ID` env vars

The channel must:
- Send `info` with `disable_notification=True` (silent), to a `#cruz-feed` topic if the chat is a forum
- Send `warn` as a normal message
- Send `critical` with notification + an inline button `❌ False alarm` whose callback hits `POST /notifications/false-alarm`

- [ ] **Step 1: Write failing tests for Telegram payload assembly**

```python
# Append to tests/services/test_notification_router.py

from unittest.mock import AsyncMock, patch

from services.notification_router import TelegramChannel


@pytest.mark.asyncio
async def test_telegram_info_uses_silent_notification():
    ch = TelegramChannel(bot_token="t", chat_id="123", feed_topic_id="42")
    fake_post = AsyncMock(return_value=AsyncMock(status_code=200, json=lambda: {"ok": True}))
    with patch("services.notification_router._http_post", fake_post):
        await ch.send("info", {"text": "hello", "trace_id": "tr-1"})
    args = fake_post.await_args.kwargs
    body = args["json"]
    assert body["chat_id"] == "123"
    assert body["text"] == "hello"
    assert body["disable_notification"] is True
    assert body["message_thread_id"] == 42


@pytest.mark.asyncio
async def test_telegram_warn_normal_message_no_button():
    ch = TelegramChannel(bot_token="t", chat_id="123")
    fake_post = AsyncMock(return_value=AsyncMock(status_code=200, json=lambda: {"ok": True}))
    with patch("services.notification_router._http_post", fake_post):
        await ch.send("warn", {"text": "alert"})
    body = fake_post.await_args.kwargs["json"]
    assert body["disable_notification"] is False
    assert "reply_markup" not in body


@pytest.mark.asyncio
async def test_telegram_critical_includes_false_alarm_button():
    ch = TelegramChannel(bot_token="t", chat_id="123")
    fake_post = AsyncMock(return_value=AsyncMock(status_code=200, json=lambda: {"ok": True}))
    payload = {
        "text": "URGENT", "trace_id": "tr-2",
        "agent": "reply_triage", "dedup_key": "email:abc",
    }
    with patch("services.notification_router._http_post", fake_post):
        await ch.send("critical", payload)
    body = fake_post.await_args.kwargs["json"]
    assert body["disable_notification"] is False
    markup = body["reply_markup"]
    assert "inline_keyboard" in markup
    btn = markup["inline_keyboard"][0][0]
    assert "False alarm" in btn["text"]
    # callback_data encodes (agent, dedup_key) for the false-alarm endpoint
    assert "reply_triage" in btn["callback_data"]
    assert "email:abc" in btn["callback_data"]


@pytest.mark.asyncio
async def test_telegram_send_swallows_http_error_logs_warning(caplog):
    ch = TelegramChannel(bot_token="t", chat_id="123")
    fake_post = AsyncMock(side_effect=RuntimeError("network down"))
    with patch("services.notification_router._http_post", fake_post):
        # Must not raise — router relies on this to continue with other channels
        await ch.send("warn", {"text": "x"})
    assert "telegram" in caplog.text.lower()


def test_telegram_handles_severities_includes_all_three():
    ch = TelegramChannel(bot_token="t", chat_id="123")
    assert ch.handles_severities == {"info", "warn", "critical"}
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/services/test_notification_router.py -v -k telegram
```

Expected: 5 failures with `ImportError: cannot import TelegramChannel`.

- [ ] **Step 3: Implement `TelegramChannel`**

Append to `services/notification_router.py`:

```python
import json
import os
from typing import Any

import httpx


async def _http_post(url: str, *, json: dict, timeout: float = 10.0) -> Any:
    """Thin httpx wrapper — separated so tests can monkeypatch it."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(url, json=json)


class TelegramChannel:
    """Telegram bot channel — only channel shipped in SP5.

    Severity mapping:
      info     → silent message, posted to feed topic if configured
      warn     → normal message
      critical → notification + inline "False alarm" button

    Env vars:
      TELEGRAM_BOT_TOKEN       — required
      TELEGRAM_CHAT_ID         — required (the user's CRUZ chat)
      TELEGRAM_FEED_TOPIC_ID   — optional; if set, info messages go to that
                                 topic in a forum-mode chat (otherwise main thread)
    """

    name = "telegram"
    handles_severities = {"info", "warn", "critical"}

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        feed_topic_id: str | int | None = None,
    ) -> None:
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        topic = feed_topic_id if feed_topic_id is not None \
                else os.environ.get("TELEGRAM_FEED_TOPIC_ID")
        self.feed_topic_id = int(topic) if topic else None
        if not self.bot_token or not self.chat_id:
            logger.warning(
                "TelegramChannel: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID — "
                "send() will be a no-op until configured"
            )

    async def send(self, severity: str, payload: dict) -> None:
        if not self.bot_token or not self.chat_id:
            logger.debug("telegram not configured — dropping %s message", severity)
            return

        text = payload.get("text", "")
        body: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_notification": severity == "info",
            "parse_mode": "Markdown",
        }

        if severity == "info" and self.feed_topic_id is not None:
            body["message_thread_id"] = self.feed_topic_id

        if severity == "critical":
            agent = payload.get("agent", "?")
            dedup_key = payload.get("dedup_key", "?")
            # Telegram callback_data hard limit: 64 bytes.
            # Format: "fa|<agent>|<key>" (or "fa|<agent>|h:<sha8>" if too long).
            # Hashing keeps the false-alarm endpoint identifying the same
            # logical ping even when dedup_key is long. The bot-server
            # translator (operator config) is responsible for resolving
            # the hash back to the dedup_key it originally sent.
            raw = f"fa|{agent}|{dedup_key}"
            if len(raw.encode("utf-8")) <= 64:
                cb = raw
            else:
                import hashlib
                h = hashlib.sha1(dedup_key.encode("utf-8")).hexdigest()[:8]
                cb = f"fa|{agent}|h:{h}"
                logger.info(
                    "telegram callback_data hashed (raw was %d bytes): %s -> %s",
                    len(raw.encode("utf-8")), dedup_key, cb,
                )
            body["reply_markup"] = {
                "inline_keyboard": [[
                    {"text": "❌ False alarm", "callback_data": cb}
                ]]
            }

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            response = await _http_post(url, json=body)
            # httpx response: a fail-soft check — log non-200 but don't raise
            if hasattr(response, "status_code") and response.status_code >= 400:
                logger.warning(
                    "telegram send returned %s: %s",
                    response.status_code,
                    getattr(response, "text", ""),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram send failed (non-fatal): %s", exc)
```

- [ ] **Step 4: Run Telegram tests, expect pass**

```bash
pytest tests/services/test_notification_router.py -v -k telegram
```

Expected: 5 passed.

- [ ] **Step 5: Run full router suite**

```bash
pytest tests/services/test_notification_router.py -v
```

Expected: 11 passed (6 router + 5 Telegram).

- [ ] **Step 6: Document new env vars**

Append to `.env.example` (or create if missing):

```bash
# SP5 — Notification surface
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_FEED_TOPIC_ID=     # optional — for info-tier silent messages
```

- [ ] **Step 7: Commit**

```bash
git add services/notification_router.py tests/services/test_notification_router.py .env.example
git commit -m "feat(sp5): add TelegramChannel for SP5 notification surface

Per spec §3.3, §7. info=silent in feed topic, warn=normal,
critical=notification + 'False alarm' inline button. HTTP failures
are logged but do not propagate so the router can fan-out to other
channels uninterrupted."
```

---

### Task 3.3: Add `POST /notifications/false-alarm` endpoint

When user taps the inline button, Telegram POSTs to the bot's webhook with `callback_query.data == "fa|<agent>|<dedup_key>"`. We expose a thin endpoint that records this as a false-critical and surfaces it for review.

**Files:**
- Modify: `backend/api/main.py` — add endpoint
- Test: `tests/api/test_false_alarm_endpoint.py`

- [ ] **Step 1: Write failing endpoint test**

```python
# tests/api/test_false_alarm_endpoint.py
"""POST /notifications/false-alarm — Telegram inline-button callback.

Uses fastapi.testclient.TestClient because the endpoint depends on
the FastAPI lifespan (DB pool, Redis pool) being initialised. AsyncClient
+ ASGITransport does NOT run lifespan; existing tests in this dir
(test_health_endpoint.py, test_voice_token.py, test_approvals_endpoint.py)
all use TestClient for the same reason.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app


def test_false_alarm_records_state_for_agent_and_dedup_key():
    with TestClient(app) as client:
        resp = client.post(
            "/notifications/false-alarm",
            json={"agent": "reply_triage", "dedup_key": "email:abc-123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["recorded"] is True

        # Verify state was written. TestClient runs lifespan, so the
        # DB pool is connected — get_state_service() works here.
        import asyncio
        from services.agent_state import get_state_service
        state = get_state_service()
        rec = asyncio.get_event_loop().run_until_complete(
            state.get("reply_triage", "false_critical:email:abc-123")
        )
        assert rec is not None
        assert "ack_at" in rec


def test_false_alarm_rejects_missing_fields():
    with TestClient(app) as client:
        resp = client.post("/notifications/false-alarm", json={"agent": "x"})
    assert resp.status_code in (400, 422)
```

- [ ] **Step 2: Run failing test**

```bash
pytest tests/api/test_false_alarm_endpoint.py -v
```

Expected: 2 failures — endpoint doesn't exist (404) or import error.

- [ ] **Step 3: Add the endpoint to `backend/api/main.py`**

Find a section near the existing webhook endpoints (around the `_verify_hmac` helper) and add:

```python
# ─── Notification callbacks (SP5) ───────────────────────────────────────────

from pydantic import BaseModel
import time

class FalseAlarmRequest(BaseModel):
    agent: str
    dedup_key: str


@app.post("/notifications/false-alarm")
async def notifications_false_alarm(req: FalseAlarmRequest) -> JSONResponse:
    """Record a user-acked false-critical for the SP5 exit-gate measurement.

    Called by Telegram inline button on a `critical` notification, OR by
    any other channel that wants to surface a false-positive ack.
    Writes agent_state(<agent>, "false_critical:<dedup_key>") and stays
    silent — no further action. The SP5 daily briefing handler scans
    these rows for the 7-day measurement window.

    Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §7, §8.2
    """
    from services.agent_state import get_state_service

    state = get_state_service()
    await state.set(
        req.agent,
        f"false_critical:{req.dedup_key}",
        {"ack_at": time.time(), "agent": req.agent, "dedup_key": req.dedup_key},
        ttl_seconds=86400 * 365,
    )
    return JSONResponse(status_code=200, content={"recorded": True})
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/api/test_false_alarm_endpoint.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/api/main.py tests/api/test_false_alarm_endpoint.py
git commit -m "feat(sp5): add POST /notifications/false-alarm endpoint

Per spec §7, §8.2. Records user-acked false-critical to agent_state
for SP5 exit-gate measurement. Telegram inline-button callback target.
1-year TTL keeps audit trail. Telegram → bot → endpoint wiring at
the bot-server side is operator config (not in this commit)."
```

---

### Task 3.4: Verify Chunk 3 end-to-end

- [ ] **Step 1: Full test run**

```bash
pytest tests/services/test_notification_router.py tests/api/test_false_alarm_endpoint.py -v --tb=short
```

Expected: 13 passed (11 router + 2 endpoint).

- [ ] **Step 2: Verify gate + router can co-exist (smoke)**

```python
# ipython:
import asyncio
from services.proactive_engine import ProactiveEngine, GateRequest, GateDecision
from services.notification_router import NotificationRouter, TelegramChannel
from services.agent_state import StateService
from services.db import get_db_service

async def smoke():
    db = get_db_service(); await db.connect()
    state = StateService(db)
    gate = ProactiveEngine(state, db)
    router = NotificationRouter()
    # No Telegram creds in dev → channel is no-op (logs at debug)
    router.register(TelegramChannel())

    req = GateRequest(agent="smoke", severity="warn", reason_code=None,
                      dedup_key="ss1", payload={"text": "smoke warn", "trace_id": "s-1"},
                      valid_critical_reasons=set())
    decision = await gate.allow(req)
    print(decision)
    if decision in (GateDecision.ALLOW, GateDecision.DEMOTE_TO_INFO, GateDecision.DEMOTE_TO_WARN):
        eff = ProactiveEngine._effective_severity(req.severity, decision)
        await router.route(eff, req.payload)
    await db.execute("DELETE FROM agent_state WHERE agent_name LIKE '_g%' OR agent_name='smoke'")
    await db.execute("DELETE FROM agent_logs WHERE agent='smoke'")

asyncio.run(smoke())
```

Expected: prints `GateDecision.ALLOW`. No errors. (Telegram is no-op without creds.)

- [ ] **Step 3: Verify v1 endpoints still work**

```bash
pytest tests/api/ --ignore=tests/api/test_false_alarm_endpoint.py --tb=short
```

Expected: all v1 API tests still pass.

- [ ] **Step 4: Tag chunk done**

```bash
git tag claude/sp5-chunk-3-done
```

---

**End of Chunk 3.** Notification surface live. Router fans out by severity; TelegramChannel composes the right body per severity (silent/normal/critical-with-button). False-alarm endpoint records user acks for the exit-gate measurement.

---

## Chunk 4: EventDrivenAgent base + EVENT_REGISTRY + dispatch + webhook engine

This chunk is the keystone — it links triggers (webhooks/cron) to agents through a registry. After it, agents in Chunks 6–7 are pure subclasses that declare TRIGGERS and inherit dispatch automatically.

### Task 4.1: Implement `EventDrivenAgent` base class

**Files:**
- Create: `agents/event_driven_agent.py`
- Test: `tests/agents/test_event_driven_agent.py`

- [ ] **Step 1: Write failing tests for the base class contract**

```python
# tests/agents/test_event_driven_agent.py
"""EventDrivenAgent — base class for SP5 event-driven agents.

Verifies:
  - Class-level TRIGGERS, CRITICAL_REASONS, KNOWLEDGE_RINGS declarations
  - emit() builds GateRequest from class declarations and routes via gate
  - emit() consults gate decision and routes to NotificationRouter accordingly
  - SUPPRESS does not route
  - DEMOTE_TO_WARN routes at warn severity
  - DEMOTE_TO_INFO routes at info severity
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from agents.event_driven_agent import EventDrivenAgent
from services.proactive_engine import GateDecision, GateRequest


class _FixtureAgent(EventDrivenAgent):
    """Minimal subclass used only by these tests."""

    KNOWLEDGE_RINGS = ["cruz_activities"]
    TRIGGERS = ["cron.test.hourly"]
    CRITICAL_REASONS = {
        "test_critical_reason": "for tests",
    }

    async def process(self, input: AgentInput) -> AgentOutput:
        return AgentOutput(
            success=True, result="ok", agent=self.name,
            duration_ms=0, tokens_used=0, error=None,
            requires_approval=False, approval_prompt=None,
        )


@pytest.fixture
def agent():
    return _FixtureAgent()


def test_subclass_inherits_event_driven_attributes(agent):
    assert agent.KNOWLEDGE_RINGS == ["cruz_activities"]
    assert agent.TRIGGERS == ["cron.test.hourly"]
    assert agent.CRITICAL_REASONS == {"test_critical_reason": "for tests"}


def test_default_class_attributes_are_empty():
    class Empty(EventDrivenAgent):
        async def process(self, input):
            return None
    e = Empty()
    assert e.KNOWLEDGE_RINGS == []
    assert e.TRIGGERS == []
    assert e.CRITICAL_REASONS == {}


@pytest.mark.asyncio
async def test_emit_builds_gate_request_from_class_attrs(agent):
    """emit() passes self.CRITICAL_REASONS.keys() into GateRequest."""
    captured: list[GateRequest] = []
    async def fake_allow(req: GateRequest) -> GateDecision:
        captured.append(req)
        return GateDecision.ALLOW

    fake_router = AsyncMock()

    with patch("agents.event_driven_agent.get_proactive_engine") as eng, \
         patch("agents.event_driven_agent.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=fake_allow)
        router.return_value = fake_router
        await agent.emit("critical", "test_critical_reason",
                         "k1", {"text": "hi"})

    assert len(captured) == 1
    req = captured[0]
    assert req.agent == "_FixtureAgent"
    assert req.severity == "critical"
    assert req.reason_code == "test_critical_reason"
    assert req.dedup_key == "k1"
    assert req.payload == {"text": "hi"}
    assert req.valid_critical_reasons == {"test_critical_reason"}
    fake_router.route.assert_awaited_once_with("critical", {"text": "hi"})


@pytest.mark.asyncio
async def test_emit_allow_routes_at_requested_severity(agent):
    fake_router = AsyncMock()
    with patch("agents.event_driven_agent.get_proactive_engine") as eng, \
         patch("agents.event_driven_agent.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=AsyncMock(return_value=GateDecision.ALLOW))
        router.return_value = fake_router
        decision = await agent.emit("warn", None, "k", {"text": "x"})
    assert decision == GateDecision.ALLOW
    fake_router.route.assert_awaited_once_with("warn", {"text": "x"})


@pytest.mark.asyncio
async def test_emit_demote_to_warn_routes_at_warn(agent):
    fake_router = AsyncMock()
    with patch("agents.event_driven_agent.get_proactive_engine") as eng, \
         patch("agents.event_driven_agent.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=AsyncMock(return_value=GateDecision.DEMOTE_TO_WARN))
        router.return_value = fake_router
        await agent.emit("critical", "wrong_code", "k", {"text": "x"})
    fake_router.route.assert_awaited_once_with("warn", {"text": "x"})


@pytest.mark.asyncio
async def test_emit_demote_to_info_routes_at_info(agent):
    fake_router = AsyncMock()
    with patch("agents.event_driven_agent.get_proactive_engine") as eng, \
         patch("agents.event_driven_agent.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=AsyncMock(return_value=GateDecision.DEMOTE_TO_INFO))
        router.return_value = fake_router
        await agent.emit("warn", None, "k", {"text": "x"})
    fake_router.route.assert_awaited_once_with("info", {"text": "x"})


@pytest.mark.asyncio
async def test_emit_suppress_does_not_route(agent):
    fake_router = AsyncMock()
    with patch("agents.event_driven_agent.get_proactive_engine") as eng, \
         patch("agents.event_driven_agent.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=AsyncMock(return_value=GateDecision.SUPPRESS))
        router.return_value = fake_router
        decision = await agent.emit("warn", None, "k", {"text": "x"})
    assert decision == GateDecision.SUPPRESS
    fake_router.route.assert_not_awaited()


@pytest.mark.asyncio
async def test_emit_payload_carries_agent_and_dedup_key_for_telegram_button(agent):
    """TelegramChannel reads payload['agent'] and payload['dedup_key']
    to build the False-alarm callback. emit() must inject these."""
    captured: list[dict] = []
    async def fake_route(severity, payload):
        captured.append(payload)

    with patch("agents.event_driven_agent.get_proactive_engine") as eng, \
         patch("agents.event_driven_agent.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=AsyncMock(return_value=GateDecision.ALLOW))
        router.return_value = AsyncMock(route=fake_route)
        await agent.emit("critical", "test_critical_reason",
                         "email:abc", {"text": "URGENT"})
    p = captured[0]
    assert p["agent"] == "_FixtureAgent"
    assert p["dedup_key"] == "email:abc"
    assert p["text"] == "URGENT"
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/agents/test_event_driven_agent.py -v
```

Expected: all 8 fail with `ImportError`.

- [ ] **Step 3: Implement `EventDrivenAgent`**

```python
# agents/event_driven_agent.py
"""
EventDrivenAgent — base class for SP5 proactive agents.

Layer on top of BaseAgent. Adds class-level declarations that the
event registry and gate need to know about:

  KNOWLEDGE_RINGS  : list[str]            — Rule 3 (KB participation)
  TRIGGERS         : list[str]            — event types this agent subscribes to
  CRITICAL_REASONS : dict[str, str]       — whitelist for gate criticals (Rule B)

Provides emit() — the canonical way for an event-driven agent to surface
a notification through the gate + router pipeline.

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.4
"""

from __future__ import annotations

import logging
from typing import Literal

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.notification_router import get_notification_router
from services.proactive_engine import (
    GateDecision,
    GateRequest,
    get_proactive_engine,
)

logger = logging.getLogger("cruz.agents.event_driven_agent")


class EventDrivenAgent(BaseAgent):
    """Subclass to make a v2 proactive agent. Implement `process()`
    as usual. Inside it, call `await self.emit(...)` to ship notifications.
    """

    # ── Class-level declarations (override in each subclass) ──────────
    KNOWLEDGE_RINGS: list[str]    = []
    TRIGGERS: list[str]           = []
    CRITICAL_REASONS: dict[str, str] = {}

    DEFAULT_DEDUP_TTL_SECONDS: int = 7 * 86400

    async def emit(
        self,
        severity: Literal["info", "warn", "critical"],
        reason_code: str | None,
        dedup_key: str,
        payload: dict,
    ) -> GateDecision:
        """Build a GateRequest from class declarations, run the gate,
        route notification via NotificationRouter according to decision.

        Returns the GateDecision so callers can branch on it (e.g.,
        log "we tried to fire but were rate-limited").
        """
        # Inject metadata the TelegramChannel uses for the False-alarm button.
        # Idempotent — caller may have already set these.
        payload = {**payload, "agent": self.name, "dedup_key": dedup_key}

        req = GateRequest(
            agent=self.name,
            severity=severity,
            reason_code=reason_code,
            dedup_key=dedup_key,
            payload=payload,
            valid_critical_reasons=set(self.CRITICAL_REASONS.keys()),
        )

        decision = await get_proactive_engine().allow(req)
        router = get_notification_router()

        if decision == GateDecision.ALLOW:
            await router.route(severity, payload)
        elif decision == GateDecision.DEMOTE_TO_WARN:
            await router.route("warn", payload)
        elif decision == GateDecision.DEMOTE_TO_INFO:
            await router.route("info", payload)
        # GateDecision.SUPPRESS: silent — gate already logged the decision

        return decision
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/agents/test_event_driven_agent.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add agents/event_driven_agent.py tests/agents/test_event_driven_agent.py
git commit -m "feat(sp5): add EventDrivenAgent base class

Per spec §3.4. Class-level TRIGGERS/CRITICAL_REASONS/KNOWLEDGE_RINGS
declarations; emit() helper builds GateRequest, runs gate, routes
through NotificationRouter per gate decision."
```

---

### Task 4.2: Build EVENT_REGISTRY with class discovery

**Files:**
- Modify: `agents/event_driven_agent.py` — add `EVENT_REGISTRY` and `register_event_agents()`
- Test: extend `tests/agents/test_event_driven_agent.py` with registry tests

- [ ] **Step 1: Write failing tests for the registry**

Append to test file:

```python
# ── EVENT_REGISTRY tests ────────────────────────────────────────

from agents.event_driven_agent import (
    EVENT_REGISTRY,
    register_event_agent,
    clear_event_registry,
)


@pytest.fixture(autouse=True)
def _isolated_registry():
    clear_event_registry()
    yield
    clear_event_registry()


def test_register_adds_agent_class_to_each_trigger(agent):
    register_event_agent(_FixtureAgent)
    assert _FixtureAgent in EVENT_REGISTRY["cron.test.hourly"]


def test_register_two_agents_for_same_trigger():
    class A(EventDrivenAgent):
        TRIGGERS = ["x"]
        async def process(self, input): return None
    class B(EventDrivenAgent):
        TRIGGERS = ["x"]
        async def process(self, input): return None
    register_event_agent(A)
    register_event_agent(B)
    assert A in EVENT_REGISTRY["x"]
    assert B in EVENT_REGISTRY["x"]
    assert len(EVENT_REGISTRY["x"]) == 2


def test_register_idempotent_does_not_duplicate(agent):
    register_event_agent(_FixtureAgent)
    register_event_agent(_FixtureAgent)
    assert EVENT_REGISTRY["cron.test.hourly"].count(_FixtureAgent) == 1


def test_unknown_trigger_returns_empty_list():
    """Lookup of unsubscribed trigger returns empty list, not KeyError."""
    assert EVENT_REGISTRY.get("never.registered.trigger", []) == []
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/agents/test_event_driven_agent.py -v -k registry
```

Expected: 4 failures with `ImportError`.

- [ ] **Step 3: Implement registry helpers**

Append to `agents/event_driven_agent.py`:

```python
# ── Event registry (built at app boot) ─────────────────────────────────

EVENT_REGISTRY: dict[str, list[type[EventDrivenAgent]]] = {}


def register_event_agent(cls: type[EventDrivenAgent]) -> None:
    """Add an EventDrivenAgent subclass to EVENT_REGISTRY for each
    of its TRIGGERS. Idempotent — registering the same class twice
    is a no-op."""
    for trigger in cls.TRIGGERS:
        agents = EVENT_REGISTRY.setdefault(trigger, [])
        if cls not in agents:
            agents.append(cls)
            logger.debug(
                "registered %s for trigger %s", cls.__name__, trigger
            )


def clear_event_registry() -> None:
    """Test helper — wipe all registrations."""
    EVENT_REGISTRY.clear()
```

- [ ] **Step 4: Run all event-driven tests**

```bash
pytest tests/agents/test_event_driven_agent.py -v
```

Expected: 12 passed (8 emit + 4 registry).

- [ ] **Step 5: Commit**

```bash
git add agents/event_driven_agent.py tests/agents/test_event_driven_agent.py
git commit -m "feat(sp5): add EVENT_REGISTRY with explicit register_event_agent()

Per spec §3.5. Idempotent registration; lookup returns empty list
for unsubscribed triggers. Auto-discovery left as importer
responsibility — Chunk 8 wires every SP5 agent into the registry
on app boot."
```

---

### Task 4.3: Implement `dispatch_event_to_agent` ARQ task

**Files:**
- Create: `workers/tasks/dispatch.py`
- Test: `tests/workers/test_dispatch.py`

The ARQ task receives `(module_path, class_name, event_payload)` and:
1. Imports the agent class dynamically
2. Builds an AgentInput
3. Calls `agent.process(input)`
4. Returns the AgentOutput dict

- [ ] **Step 1: Write failing test**

```python
# tests/workers/test_dispatch.py
"""dispatch_event_to_agent — ARQ task that runs an EventDrivenAgent
in response to a registered trigger event."""

from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest

from workers.tasks.dispatch import dispatch_event_to_agent


@pytest.mark.asyncio
async def test_dispatch_imports_class_and_calls_process():
    """dispatch_event_to_agent dynamically imports the agent class,
    instantiates it, and calls process() with the event payload."""
    fake_process = AsyncMock(return_value={
        "success": True, "result": "did-thing", "agent": "F",
        "duration_ms": 10, "tokens_used": 0, "error": None,
        "requires_approval": False, "approval_prompt": None,
    })
    fake_class = type("F", (), {})
    fake_instance = type("FI", (), {"process": fake_process})()

    with patch("workers.tasks.dispatch._import_class",
               return_value=lambda: fake_instance):
        result = await dispatch_event_to_agent(
            ctx={},
            module_path="agents.fake.fake_agent",
            class_name="FakeAgent",
            event={"trigger": "cron.x", "data": {"y": 1}},
        )
    fake_process.assert_awaited_once()
    call_args = fake_process.await_args.args[0]
    assert call_args["context"]["event"] == {"trigger": "cron.x", "data": {"y": 1}}
    assert call_args["task"].startswith("event:")
    assert "trace_id" in call_args
    assert result["success"] is True


@pytest.mark.asyncio
async def test_dispatch_swallows_agent_errors_returns_failure_dict():
    """Agent exceptions become a failure dict — never raised. ARQ retries
    are surfaced via the after_job_end hook in arq_worker.py."""
    fake_instance = type("X", (), {
        "process": AsyncMock(side_effect=RuntimeError("oops")),
    })()
    with patch("workers.tasks.dispatch._import_class",
               return_value=lambda: fake_instance):
        result = await dispatch_event_to_agent(
            ctx={},
            module_path="agents.fake.fake_agent",
            class_name="FakeAgent",
            event={"trigger": "x", "data": {}},
        )
    assert result["success"] is False
    assert "oops" in result["error"]


@pytest.mark.asyncio
async def test_dispatch_propagates_trace_id_when_present():
    """If event carries a trace_id (from a webhook), reuse it."""
    fake_instance = type("X", (), {
        "process": AsyncMock(return_value={
            "success": True, "result": "ok", "agent": "X", "duration_ms": 0,
            "tokens_used": 0, "error": None, "requires_approval": False,
            "approval_prompt": None,
        }),
    })()
    with patch("workers.tasks.dispatch._import_class",
               return_value=lambda: fake_instance):
        await dispatch_event_to_agent(
            ctx={},
            module_path="m", class_name="C",
            event={"trigger": "t", "trace_id": "given-trace-7", "data": {}},
        )
    call_args = fake_instance.process.await_args.args[0]
    assert call_args["trace_id"] == "given-trace-7"
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/workers/test_dispatch.py -v
```

Expected: 3 failures with `ImportError`.

- [ ] **Step 3: Implement `dispatch_event_to_agent`**

```python
# workers/tasks/dispatch.py
"""
dispatch_event_to_agent — ARQ task entrypoint for event-driven agents.

Webhook tasks (workers/tasks/webhook_tasks.py) and cron triggers enqueue
this task with the agent's module path + class name + event payload. The
task imports the class, instantiates it, and runs process().

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.5
"""

from __future__ import annotations

import importlib
import logging
import uuid
from typing import Any, Callable

logger = logging.getLogger("cruz.workers.dispatch")


def _import_class(module_path: str, class_name: str) -> Callable[[], Any]:
    """Return a callable that, when invoked, returns a fresh agent instance.

    Separated from `dispatch_event_to_agent` so tests can monkey-patch it
    and avoid real imports.
    """
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls   # cls() returns an instance; tests patch _import_class
                 # to return any factory


async def dispatch_event_to_agent(
    ctx: dict,
    module_path: str,
    class_name: str,
    event: dict,
) -> dict:
    """Run an EventDrivenAgent in response to a registered trigger event.

    Args:
        ctx: ARQ context (unused currently — reserved for retry/job_id).
        module_path: e.g. "agents.reply_triage.reply_triage_agent"
        class_name:  e.g. "ReplyTriageAgent"
        event: payload dict — at minimum {"trigger": "<trigger_name>",
               "data": <event-specific dict>}, optionally "trace_id".

    Returns:
        AgentOutput-shaped dict. Errors become success=False entries
        (never raised) so ARQ doesn't loop on the same poisoned event.
    """
    trace_id = event.get("trace_id") or f"sp5-{uuid.uuid4()}"
    try:
        factory = _import_class(module_path, class_name)
        agent = factory()
        agent_input = {
            "task": f"event:{event.get('trigger', 'unknown')}",
            "context": {"event": event},
            "trace_id": trace_id,
            "conversation_id": "",
        }
        output = await agent.process(agent_input)
        return dict(output)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "[%s] dispatch_event_to_agent failed: %s.%s — %s",
            trace_id, module_path, class_name, exc,
        )
        return {
            "success": False,
            "result": None,
            "agent": class_name,
            "duration_ms": 0,
            "tokens_used": 0,
            "error": str(exc),
            "requires_approval": False,
            "approval_prompt": None,
        }
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/workers/test_dispatch.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add workers/tasks/dispatch.py tests/workers/test_dispatch.py
git commit -m "feat(sp5): add dispatch_event_to_agent ARQ task

Per spec §3.5. Imports agent class dynamically, runs process(), swallows
exceptions into failure dict so poisoned events don't loop ARQ retries.
Trace_id propagated from event payload when present."
```

---

### Task 4.4: Extend webhook tasks to dispatch to EVENT_REGISTRY

**Files:**
- Modify: `workers/tasks/webhook_tasks.py` — add trailing dispatch block to each `process_*_webhook`
- Modify: `tests/workers/test_webhook_tasks_dispatch.py` — verify dispatch happens

The existing `process_github_webhook`, `process_vercel_webhook`, `process_google_calendar_webhook` keep their parsing + logging behavior. New behavior: after parsing, look up the trigger in `EVENT_REGISTRY` and enqueue `dispatch_event_to_agent` for each registered class.

- [ ] **Step 1: Write failing test for the additive dispatch**

```python
# tests/workers/test_webhook_tasks_dispatch.py
"""Webhook engine extension — verify existing webhook tasks now also
dispatch to registered EventDrivenAgent classes via EVENT_REGISTRY."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.event_driven_agent import (
    EventDrivenAgent,
    register_event_agent,
    clear_event_registry,
)
from workers.tasks.webhook_tasks import (
    process_github_webhook,
    process_vercel_webhook,
    process_google_calendar_webhook,
)


@pytest.fixture(autouse=True)
def _isolated_registry():
    clear_event_registry()
    yield
    clear_event_registry()


class _GithubAgent(EventDrivenAgent):
    TRIGGERS = ["webhook.github"]
    async def process(self, input):
        return None


@pytest.mark.asyncio
async def test_github_webhook_dispatches_to_registered_agent():
    register_event_agent(_GithubAgent)
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("workers.tasks.webhook_tasks._get_arq_pool",
               return_value=fake_pool):
        await process_github_webhook(
            ctx={},
            event="pull_request",
            payload={"action": "opened", "repository": {"full_name": "x/y"},
                     "pull_request": {"number": 7}},
        )
    fake_pool.enqueue_job.assert_awaited_with(
        "dispatch_event_to_agent",
        # module_path, class_name
        "tests.workers.test_webhook_tasks_dispatch",
        "_GithubAgent",
        # event dict
        {
            "trigger": "webhook.github",
            "data": {"action": "opened",
                     "repository": {"full_name": "x/y"},
                     "pull_request": {"number": 7}},
            "github_event": "pull_request",
        },
    )


@pytest.mark.asyncio
async def test_no_registered_agent_means_no_dispatch_but_logging_still_runs():
    """v1 logging behavior is preserved when no agent is registered."""
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("workers.tasks.webhook_tasks._get_arq_pool",
               return_value=fake_pool):
        result = await process_github_webhook(
            ctx={},
            event="push",
            payload={"action": "push"},
        )
    fake_pool.enqueue_job.assert_not_called()
    # Original return value (logging summary) still produced
    assert result is not None
    assert result.get("event") == "push"


@pytest.mark.asyncio
async def test_calendar_webhook_dispatches_with_trigger_name():
    class _CalAgent(EventDrivenAgent):
        TRIGGERS = ["webhook.google-calendar"]
        async def process(self, input):
            return None

    register_event_agent(_CalAgent)
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("workers.tasks.webhook_tasks._get_arq_pool",
               return_value=fake_pool):
        await process_google_calendar_webhook(
            ctx={},
            headers={"X-Goog-Resource-State": "exists",
                     "X-Goog-Channel-ID": "ch1"},
        )
    args = fake_pool.enqueue_job.await_args.args
    assert args[0] == "dispatch_event_to_agent"
    assert args[1] == _CalAgent.__module__
    assert args[2] == "_CalAgent"
    assert args[3]["trigger"] == "webhook.google-calendar"
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/workers/test_webhook_tasks_dispatch.py -v
```

Expected: 3 failures — `_get_arq_pool` doesn't exist yet, dispatch isn't wired.

- [ ] **Step 3: Extend `workers/tasks/webhook_tasks.py`**

The current file has 3 functions that only log + return a dict. Refactor to extract pool management and add dispatch:

```python
# Replace the entire workers/tasks/webhook_tasks.py with:
"""
ARQ task handlers for inbound webhook payloads.

Each task:
  1. Parses + logs the payload (v1 behavior — unchanged)
  2. Looks up the trigger in EVENT_REGISTRY
  3. Enqueues dispatch_event_to_agent for each registered agent (SP5 addition)

The signature-verification step happens in backend/api/main.py's webhook
endpoints; tasks here trust the payload they receive.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from arq import create_pool
from arq.connections import RedisSettings

from agents.event_driven_agent import EVENT_REGISTRY

logger = logging.getLogger("cruz.workers.webhooks")


async def _get_arq_pool():
    """Open an ARQ Redis pool. Separated so tests can monkey-patch it."""
    return await create_pool(
        RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379"))
    )


async def _dispatch_to_registered(trigger: str, event_payload: Dict[str, Any]) -> None:
    """For every agent registered against `trigger`, enqueue a dispatch."""
    classes = EVENT_REGISTRY.get(trigger, [])
    if not classes:
        return
    pool = await _get_arq_pool()
    for cls in classes:
        await pool.enqueue_job(
            "dispatch_event_to_agent",
            cls.__module__,
            cls.__name__,
            event_payload,
        )


# ─────────────────────────────────────────────────────────────────────────
# v1 webhook tasks — logging behavior preserved; dispatch added at the end.
# ─────────────────────────────────────────────────────────────────────────

async def process_github_webhook(
    ctx: Dict[str, Any], event: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    action = payload.get("action")
    pr_number = (payload.get("pull_request") or {}).get("number")
    repo = (payload.get("repository") or {}).get("full_name")
    logger.info(
        "github webhook event=%s action=%s repo=%s pr=%s",
        event, action, repo, pr_number,
    )
    summary = {
        "event": event,
        "action": action,
        "pr_number": pr_number,
        "repo": repo,
    }
    await _dispatch_to_registered(
        "webhook.github",
        {"trigger": "webhook.github", "data": payload, "github_event": event},
    )
    return summary


async def process_vercel_webhook(
    ctx: Dict[str, Any], payload: Dict[str, Any]
) -> Dict[str, Any]:
    kind = payload.get("type")
    project = (payload.get("payload") or {}).get("project", {}).get("name")
    url = (payload.get("payload") or {}).get("url")
    logger.info("vercel webhook type=%s project=%s url=%s", kind, project, url)
    summary = {"type": kind, "project": project, "url": url}
    await _dispatch_to_registered(
        "webhook.vercel",
        {"trigger": "webhook.vercel", "data": payload},
    )
    return summary


async def process_google_calendar_webhook(
    ctx: Dict[str, Any], headers: Dict[str, str]
) -> Dict[str, Any]:
    state = headers.get("X-Goog-Resource-State") or headers.get("x-goog-resource-state")
    channel_id = headers.get("X-Goog-Channel-ID") or headers.get("x-goog-channel-id")
    logger.info("google-calendar webhook state=%s channel=%s", state, channel_id)
    summary = {"resource_state": state, "channel_id": channel_id}
    await _dispatch_to_registered(
        "webhook.google-calendar",
        {"trigger": "webhook.google-calendar", "data": {"headers": headers,
                                                         "resource_state": state,
                                                         "channel_id": channel_id}},
    )
    return summary
```

> **Note on the duplicate `_get_arq_pool` in `backend/api/main.py`:** the existing API file has its own `get_arq_pool()`. Leave that one alone; it has callers in v1 webhook endpoints. The new `_get_arq_pool()` here is for the worker side.

- [ ] **Step 4: Run failing tests, expect pass**

```bash
pytest tests/workers/test_webhook_tasks_dispatch.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run v1 webhook tests to verify nothing broke**

```bash
pytest tests/workers/ -v --ignore=tests/workers/test_webhook_tasks_dispatch.py --ignore=tests/workers/test_dispatch.py
```

Expected: any pre-existing webhook-task tests still pass. v1 callers receive identical summary dicts (the `_dispatch_to_registered` is fire-and-forget, no return value).

- [ ] **Step 6: Commit**

```bash
git add workers/tasks/webhook_tasks.py tests/workers/test_webhook_tasks_dispatch.py
git commit -m "feat(sp5): extend webhook tasks to dispatch to EVENT_REGISTRY

Per spec §3.5. Each existing process_*_webhook task now looks up its
trigger in EVENT_REGISTRY after logging, and enqueues dispatch_event_
to_agent for every registered agent. v1 logging + return summary are
unchanged so existing callers see no behavior delta when no agent
is registered."
```

---

### Task 4.5: Add Gmail webhook endpoint and Pub/Sub task

Gmail uses Cloud Pub/Sub push notifications. The flow:
1. Gmail watch is registered for the user's mailbox (resubscribed daily by a maintenance cron in Chunk 8).
2. New mail → Gmail publishes to a Pub/Sub topic → Pub/Sub POSTs to `https://cruz.simpleinc.cloud/webhooks/gmail` with a JSON body containing the historyId + an OIDC JWT in the `Authorization` header.
3. Endpoint verifies the JWT against Google's JWKS, enqueues `process_gmail_webhook`.
4. `process_gmail_webhook` resolves historyId → new message IDs (via Gmail History API), then dispatches the trigger `webhook.gmail.new_message` per message.

**Files:**
- Create: `workers/tasks/gmail_webhook_tasks.py`
- Modify: `backend/api/main.py` — add `POST /webhooks/gmail`
- Test: `tests/workers/test_gmail_webhook_tasks.py`
- Test: `tests/api/test_gmail_webhook_endpoint.py`

> **Pub/Sub OIDC verification.** The endpoint validates the JWT signature against Google's JWKS (`https://www.googleapis.com/oauth2/v3/certs`), checks `aud` matches the configured value (`GMAIL_PUBSUB_AUDIENCE` env var, e.g., `https://cruz.simpleinc.cloud/webhooks/gmail`), `iss` is `https://accounts.google.com` or `accounts.google.com`, and `email` matches `GMAIL_PUBSUB_SERVICE_ACCOUNT`. We use the `google-auth` library which is already in the project's transitive deps via google-api-python-client.

- [ ] **Step 1: Write failing test for the endpoint (auth)**

```python
# tests/api/test_gmail_webhook_endpoint.py
"""POST /webhooks/gmail — Pub/Sub push receiver with OIDC JWT verification."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app


def test_gmail_webhook_rejects_missing_auth():
    with TestClient(app) as client:
        resp = client.post("/webhooks/gmail", json={"message": {"data": "abc"}})
    assert resp.status_code == 401


def test_gmail_webhook_rejects_invalid_jwt():
    with TestClient(app) as client:
        resp = client.post(
            "/webhooks/gmail",
            json={"message": {"data": "abc"}},
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )
    assert resp.status_code == 401


def test_gmail_webhook_accepts_valid_jwt_and_enqueues():
    """Valid JWT → 200, enqueues process_gmail_webhook."""
    from unittest.mock import AsyncMock
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock()
    # AsyncMock(return_value=pool) — awaiting get_arq_pool() resolves to pool.
    fake_verify = patch(
        "backend.api.main._verify_pubsub_jwt",
        return_value={"email": "ok"},
    )
    fake_pool = patch(
        "backend.api.main.get_arq_pool",
        new=AsyncMock(return_value=pool),
    )
    with fake_verify, fake_pool, TestClient(app) as client:
        resp = client.post(
            "/webhooks/gmail",
            json={"message": {"data": "eyJoaXN0b3J5SWQiOiAiOTk5In0="}},
            headers={"Authorization": "Bearer x.y.z"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("queued") is True
    pool.enqueue_job.assert_awaited_once()
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/api/test_gmail_webhook_endpoint.py -v
```

Expected: 3 failures (404 on the endpoint).

- [ ] **Step 3: Add the endpoint and JWT verifier to `backend/api/main.py`**

Locate the existing webhook section (after `webhook_google_calendar`) and append:

```python
# ─── Gmail Pub/Sub push receiver (SP5) ──────────────────────────────────────

import base64

# google-auth comes in transitively via google-api-python-client (already
# in v1 for Calendar). If it's not installed in this env, requirements
# need google-auth>=2.0.
try:
    from google.oauth2 import id_token as _g_id_token
    from google.auth.transport import requests as _g_requests
    _GOOGLE_AUTH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _GOOGLE_AUTH_AVAILABLE = False


def _verify_pubsub_jwt(token: str) -> dict | None:
    """Verify a Pub/Sub OIDC token. Returns the decoded claims dict on
    success, None on failure. See Google docs:
      https://cloud.google.com/pubsub/docs/push#authentication
    """
    if not _GOOGLE_AUTH_AVAILABLE:
        return None
    audience = os.environ.get("GMAIL_PUBSUB_AUDIENCE", "")
    expected_email = os.environ.get("GMAIL_PUBSUB_SERVICE_ACCOUNT", "")
    if not audience:
        return None
    try:
        claims = _g_id_token.verify_oauth2_token(
            token, _g_requests.Request(), audience=audience,
        )
        if expected_email and claims.get("email") != expected_email:
            return None
        return claims
    except Exception:
        return None


@app.post("/webhooks/gmail")
async def webhook_gmail(request: Request) -> JSONResponse:
    """Pub/Sub push receiver for Gmail watch notifications.

    Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.5
    """
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth.split(None, 1)[1].strip()
    claims = _verify_pubsub_jwt(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="invalid pubsub jwt")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    pubsub_message = (body or {}).get("message", {})
    pool = await get_arq_pool()
    await pool.enqueue_job("process_gmail_webhook", pubsub_message)
    return JSONResponse(status_code=200, content={"queued": True})
```

- [ ] **Step 4: Run endpoint tests, expect pass**

```bash
pytest tests/api/test_gmail_webhook_endpoint.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Write failing test for the worker task**

```python
# tests/workers/test_gmail_webhook_tasks.py
"""process_gmail_webhook — decode Pub/Sub envelope, resolve historyId
to new messages, dispatch webhook.gmail.new_message per message."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, patch

import pytest

from agents.event_driven_agent import (
    EventDrivenAgent,
    register_event_agent,
    clear_event_registry,
)
from workers.tasks.gmail_webhook_tasks import process_gmail_webhook


@pytest.fixture(autouse=True)
def _isolated_registry():
    clear_event_registry()
    yield
    clear_event_registry()


class _GAgent(EventDrivenAgent):
    TRIGGERS = ["webhook.gmail.new_message"]
    async def process(self, input):
        return None


def _b64(d: dict) -> str:
    return base64.b64encode(json.dumps(d).encode()).decode()


@pytest.mark.asyncio
async def test_dispatches_per_message_id():
    """Pub/Sub envelope contains historyId; we resolve to message IDs
    via Gmail History API and dispatch one trigger per message."""
    register_event_agent(_GAgent)
    fake_history = AsyncMock(return_value=["msg-1", "msg-2"])
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("workers.tasks.gmail_webhook_tasks._fetch_new_message_ids",
               fake_history), \
         patch("workers.tasks.gmail_webhook_tasks._get_arq_pool",
               return_value=fake_pool):
        await process_gmail_webhook(
            ctx={},
            pubsub_message={"data": _b64({"emailAddress": "u@e.com",
                                          "historyId": "12345"})},
        )
    # Two enqueues — one per message
    assert fake_pool.enqueue_job.await_count == 2
    args = [c.args for c in fake_pool.enqueue_job.await_args_list]
    triggers = [a[3]["data"]["message_id"] for a in args]
    assert "msg-1" in triggers and "msg-2" in triggers


@pytest.mark.asyncio
async def test_handles_missing_history_id_gracefully():
    """Malformed Pub/Sub message — log and return without enqueue."""
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("workers.tasks.gmail_webhook_tasks._get_arq_pool",
               return_value=fake_pool):
        result = await process_gmail_webhook(
            ctx={},
            pubsub_message={"data": _b64({})},
        )
    fake_pool.enqueue_job.assert_not_called()
    assert result.get("queued", 0) == 0


@pytest.mark.asyncio
async def test_no_registered_agent_skips_dispatch():
    """Unknown trigger lookup → no enqueue but no error."""
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("workers.tasks.gmail_webhook_tasks._fetch_new_message_ids",
               AsyncMock(return_value=["m1"])), \
         patch("workers.tasks.gmail_webhook_tasks._get_arq_pool",
               return_value=fake_pool):
        await process_gmail_webhook(
            ctx={},
            pubsub_message={"data": _b64({"historyId": "1"})},
        )
    fake_pool.enqueue_job.assert_not_called()
```

- [ ] **Step 6: Run failing tests**

```bash
pytest tests/workers/test_gmail_webhook_tasks.py -v
```

Expected: 3 failures with `ImportError`.

- [ ] **Step 7: Implement `process_gmail_webhook`**

```python
# workers/tasks/gmail_webhook_tasks.py
"""
process_gmail_webhook — Pub/Sub push handler for Gmail new-message
notifications. Decodes the Pub/Sub envelope, resolves historyId to
message IDs via the Gmail History API, then dispatches one
webhook.gmail.new_message event per message.

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.5

Gmail watch resubscription happens in workers/tasks/maintenance_tasks.py
(Chunk 8) on a daily cron — Google requires re-watching every 7 days.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, List

from agents.event_driven_agent import EVENT_REGISTRY
from workers.tasks.webhook_tasks import _get_arq_pool

logger = logging.getLogger("cruz.workers.gmail")


async def _fetch_new_message_ids(history_id: str) -> List[str]:
    """Resolve a Gmail historyId to the list of new message IDs since.

    Implementation note: real impl uses google-api-python-client.
    This stub raises NotImplementedError so tests must monkey-patch it
    explicitly. The real implementation lands in Chunk 6 alongside the
    Reply Triage agent — that's the only agent that reads message bodies
    in SP5, and the gmail-API integration is too large to land here.

    See:
      https://developers.google.com/gmail/api/guides/sync#partial
    """
    raise NotImplementedError(
        "Gmail history fetch lands in Chunk 6 with the gmail client wrapper. "
        "Tests should monkey-patch _fetch_new_message_ids."
    )


async def process_gmail_webhook(
    ctx: Dict[str, Any], pubsub_message: Dict[str, Any]
) -> Dict[str, Any]:
    """Decode Pub/Sub envelope, fetch new message IDs, dispatch each."""
    # Pub/Sub message data is base64-encoded JSON
    raw_data = pubsub_message.get("data", "")
    try:
        payload = json.loads(base64.b64decode(raw_data).decode())
    except Exception as exc:  # noqa: BLE001
        logger.warning("gmail webhook: could not decode pubsub data: %s", exc)
        return {"queued": 0, "error": "decode"}

    history_id = payload.get("historyId")
    if not history_id:
        logger.warning("gmail webhook: missing historyId in payload: %s", payload)
        return {"queued": 0, "error": "no_history_id"}

    try:
        message_ids = await _fetch_new_message_ids(str(history_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("gmail webhook: history fetch failed: %s", exc)
        return {"queued": 0, "error": "history_fetch"}

    classes = EVENT_REGISTRY.get("webhook.gmail.new_message", [])
    if not classes or not message_ids:
        return {"queued": 0}

    pool = await _get_arq_pool()
    queued = 0
    for msg_id in message_ids:
        for cls in classes:
            await pool.enqueue_job(
                "dispatch_event_to_agent",
                cls.__module__,
                cls.__name__,
                {
                    "trigger": "webhook.gmail.new_message",
                    "data": {"message_id": msg_id, "history_id": history_id},
                },
            )
            queued += 1
    return {"queued": queued}
```

- [ ] **Step 8: Run worker tests, expect pass**

```bash
pytest tests/workers/test_gmail_webhook_tasks.py -v
```

Expected: 3 passed.

- [ ] **Step 9: Document new env vars**

Append to `.env.example`:

```bash
# SP5 — Gmail Pub/Sub push notifications
GMAIL_PUBSUB_AUDIENCE=https://cruz.simpleinc.cloud/webhooks/gmail
GMAIL_PUBSUB_SERVICE_ACCOUNT=
```

- [ ] **Step 10: Commit**

```bash
git add workers/tasks/gmail_webhook_tasks.py backend/api/main.py \
        tests/api/test_gmail_webhook_endpoint.py \
        tests/workers/test_gmail_webhook_tasks.py \
        .env.example
git commit -m "feat(sp5): add Gmail Pub/Sub webhook endpoint and task

Per spec §3.5. POST /webhooks/gmail verifies Pub/Sub OIDC JWT,
enqueues process_gmail_webhook. Task decodes envelope, fetches new
message IDs (real gmail history fetch lands in Chunk 6), dispatches
webhook.gmail.new_message per message via EVENT_REGISTRY."
```

---

### Task 4.6: Verify Chunk 4 end-to-end

- [ ] **Step 1: Full test run for Chunk 4 surface**

```bash
pytest tests/agents/test_event_driven_agent.py \
       tests/workers/test_dispatch.py \
       tests/workers/test_webhook_tasks_dispatch.py \
       tests/workers/test_gmail_webhook_tasks.py \
       tests/api/test_gmail_webhook_endpoint.py -v --tb=short
```

Expected: 12 + 3 + 3 + 3 + 3 = **24 passed**.

- [ ] **Step 2: Verify v1 webhook tests still pass**

```bash
pytest tests/workers/ tests/api/ \
  --ignore=tests/workers/test_dispatch.py \
  --ignore=tests/workers/test_webhook_tasks_dispatch.py \
  --ignore=tests/workers/test_gmail_webhook_tasks.py \
  --ignore=tests/api/test_gmail_webhook_endpoint.py \
  --ignore=tests/api/test_false_alarm_endpoint.py \
  --tb=short
```

Expected: all pre-existing webhook + API tests still pass.

- [ ] **Step 3: End-to-end smoke (registry → dispatch → emit)**

```python
# ipython:
import asyncio
from agents.event_driven_agent import (
    EventDrivenAgent, register_event_agent, EVENT_REGISTRY,
)
from services.proactive_engine import GateDecision
from services.notification_router import NotificationRouter

class TestSmoke(EventDrivenAgent):
    TRIGGERS = ["smoke.test"]
    CRITICAL_REASONS = {"smoke_critical": "smoke"}
    async def process(self, input):
        decision = await self.emit("info", None, "k", {"text": "hello smoke"})
        print("emit decision:", decision)
        return None

async def go():
    register_event_agent(TestSmoke)
    print("registry:", dict(EVENT_REGISTRY))
    # Run agent directly (skipping ARQ for the smoke)
    await TestSmoke().process({"task": "smoke", "context": {}, "trace_id": "smk-1", "conversation_id": ""})

asyncio.run(go())
```

Expected: prints registry with TestSmoke under `smoke.test`, then `emit decision: GateDecision.ALLOW`. (TelegramChannel not registered → no actual Telegram call but emit completes.)

- [ ] **Step 4: Tag chunk done**

```bash
git tag claude/sp5-chunk-4-done
```

---

**End of Chunk 4.** Keystone landed. Triggers map to agent classes via `EVENT_REGISTRY`; `dispatch_event_to_agent` runs them; webhook engine extension auto-fires registered agents on inbound webhooks; Gmail Pub/Sub endpoint provides the most important inbound trigger (Reply Triage source). The skeleton is now complete — Chunks 5–7 add concrete handlers and agents on top.

---

## Chunk 5: HandlerContext + 6 handlers

This chunk lands the handler infrastructure (Rule 7 contract) and all six concrete handlers (Daily Briefing, Expense Auditor, Portfolio Watcher, Tax Helper, Relationship Maintenance, Travel Planner). Handlers are info-only, structurally enforced via `HandlerContext.emit_info()`.

### Task 5.1: Implement `HandlerContext`, `HandlerResult`, and base handler infra

**Files:**
- Create: `workers/handlers/__init__.py`
- Create: `workers/handlers/context.py`
- Test: `tests/workers/handlers/__init__.py` (empty)
- Test: `tests/workers/handlers/test_context.py`

- [ ] **Step 1: Write failing tests for HandlerContext**

```python
# tests/workers/handlers/test_context.py
"""HandlerContext — info-only emission surface for SP5 handlers.

Per spec §5: handlers cannot fire warn/critical. The HandlerContext type
deliberately exposes only emit_info(); the full emit() exists only on
EventDrivenAgent. This is structural enforcement, not convention.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services.proactive_engine import GateDecision
from workers.handlers.context import HandlerContext, HandlerResult


@pytest.fixture
def ctx():
    return HandlerContext(trace_id="trace-1", now=datetime.now(timezone.utc))


def test_handler_context_exposes_only_emit_info_method(ctx):
    """The whole point: no emit_warn or emit_critical method exists."""
    assert hasattr(ctx, "emit_info")
    assert not hasattr(ctx, "emit_warn")
    assert not hasattr(ctx, "emit_critical")
    assert not hasattr(ctx, "emit")


@pytest.mark.asyncio
async def test_emit_info_routes_through_gate_at_info_severity(ctx):
    captured = []
    async def fake_allow(req):
        captured.append(req)
        return GateDecision.ALLOW
    fake_router = AsyncMock()
    with patch("workers.handlers.context.get_proactive_engine") as eng, \
         patch("workers.handlers.context.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=fake_allow)
        router.return_value = fake_router
        result = await ctx.emit_info(
            handler_name="daily_briefing",
            reason="daily_summary",
            dedup_key="2026-04-26",
            payload={"text": "hi"},
        )
    assert result == GateDecision.ALLOW
    assert captured[0].severity == "info"
    assert captured[0].agent == "daily_briefing"
    fake_router.route.assert_awaited_once_with("info", {
        "text": "hi", "agent": "daily_briefing", "dedup_key": "2026-04-26",
    })


@pytest.mark.asyncio
async def test_emit_info_suppress_does_not_route(ctx):
    fake_router = AsyncMock()
    with patch("workers.handlers.context.get_proactive_engine") as eng, \
         patch("workers.handlers.context.get_notification_router") as router:
        eng.return_value = AsyncMock(allow=AsyncMock(return_value=GateDecision.SUPPRESS))
        router.return_value = fake_router
        await ctx.emit_info("h", "r", "k", {"text": "x"})
    fake_router.route.assert_not_awaited()


def test_handler_result_dataclass_shape():
    r = HandlerResult(handler_name="x", success=True, summary="done")
    assert r.handler_name == "x"
    assert r.success is True
    assert r.summary == "done"
    assert r.error is None


def test_handler_context_has_kb_and_db_accessors(ctx):
    """kb and db are lazily initialised — verify accessors exist without
    instantiating the real singletons (which would require a live DB)."""
    assert hasattr(ctx, "kb")
    assert hasattr(ctx, "db")
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/workers/handlers/test_context.py -v
```

Expected: all 5 fail with `ImportError`.

- [ ] **Step 3: Implement `HandlerContext` and `HandlerResult`**

```python
# workers/handlers/__init__.py
"""SP5 handlers — scheduled prompt + Claude/Ollama call. Per Rule 7."""
```

```python
# workers/handlers/context.py
"""
HandlerContext — info-only emission surface for SP5 handlers.

Per spec §5 (charter Rule 7), handlers cannot emit warn or critical.
This type structurally enforces that constraint by exposing only
emit_info(). A handler that needs warn/critical semantics is, by
definition, not a handler — it should be promoted to an
EventDrivenAgent and re-checked against Rule 1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from services.knowledge_base import get_kb_service
from services.notification_router import get_notification_router
from services.proactive_engine import (
    GateDecision,
    GateRequest,
    get_proactive_engine,
)

logger = logging.getLogger("cruz.workers.handlers")


@dataclass
class HandlerResult:
    """Standard return shape for a handler invocation."""
    handler_name: str
    success: bool
    summary: str = ""
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class HandlerContext:
    """Per-invocation context object passed to every handler.

    Provides:
      - kb         : KnowledgeBaseService singleton (read-only path: build_agent_context)
      - db         : DatabaseService singleton accessor (lazy)
      - trace_id   : ID for log correlation
      - now        : current UTC time (frozen at HandlerContext construction)
      - emit_info  : the ONLY way for a handler to surface a notification
    """

    def __init__(
        self,
        trace_id: str,
        now: datetime,
    ) -> None:
        self.trace_id = trace_id
        self.now = now
        self._kb = None
        self._db = None

    @property
    def kb(self):
        if self._kb is None:
            self._kb = get_kb_service()
        return self._kb

    @property
    def db(self):
        if self._db is None:
            from services.db import get_db_service
            self._db = get_db_service()
        return self._db

    async def emit_info(
        self,
        handler_name: str,
        reason: str,
        dedup_key: str,
        payload: dict,
    ) -> GateDecision:
        """Route an info-tier notification through the gate.

        Note: handlers are NOT permitted to emit warn or critical. This
        method does not accept a `severity` argument by design.
        """
        payload = {**payload, "agent": handler_name, "dedup_key": dedup_key}
        req = GateRequest(
            agent=handler_name,
            severity="info",
            reason_code=reason,
            dedup_key=dedup_key,
            payload=payload,
            valid_critical_reasons=set(),  # info severity ignores whitelist
        )
        decision = await get_proactive_engine().allow(req)
        if decision == GateDecision.ALLOW:
            await get_notification_router().route("info", payload)
        # Demotions: emit_info already at info, so DEMOTE_TO_INFO is a no-op
        # (still ALLOWed by the gate); SUPPRESS = silent.
        return decision
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/workers/handlers/test_context.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add workers/handlers/__init__.py workers/handlers/context.py \
        tests/workers/handlers/__init__.py \
        tests/workers/handlers/test_context.py
git commit -m "feat(sp5): add HandlerContext with structural info-only enforcement

Per spec §5 (charter Rule 7). HandlerContext exposes only emit_info();
no emit_warn/emit_critical/emit methods exist. Handlers needing
warn/critical must be promoted to EventDrivenAgent."
```

---

### Task 5.2: Build the Daily Briefing handler (canonical pattern)

This is the canonical handler pattern. The other 5 handlers in Task 5.3 follow the same shape with different inputs/outputs.

**Files:**
- Create: `workers/handlers/daily_briefing.py`
- Test: `tests/workers/handlers/test_daily_briefing.py`

The Daily Briefing handler runs at 7am, scans `agent_state` and `agent_logs` from the last 24h, and produces one Telegram info message summarizing yesterday's activity.

- [ ] **Step 1: Write failing test**

```python
# tests/workers/handlers/test_daily_briefing.py
"""Daily Briefing handler — 7am digest of yesterday's agent activity."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from workers.handlers.context import HandlerContext
from workers.handlers.daily_briefing import handle


@pytest.fixture
def ctx():
    return HandlerContext(trace_id="db-trace-1",
                           now=datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_daily_briefing_emits_summary_with_pings_count(ctx):
    """Handler queries agent_logs for last 24h, builds digest, emits info."""
    # Fake DB returns 5 successful agent logs + 1 false_critical ack
    fake_db_rows = [
        {"agent": "reply_triage", "action": "process", "status": "success"},
        {"agent": "reply_triage", "action": "process", "status": "success"},
        {"agent": "followup", "action": "process", "status": "success"},
        {"agent": "health_guardian", "action": "gate_decision", "status": "allow"},
        {"agent": "reply_triage", "action": "gate_decision", "status": "demote_warn"},
    ]
    captured_emit: list[dict] = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured_emit.append({"handler": handler_name, "payload": payload})

    with patch.object(ctx, "_db", AsyncMock(fetch=AsyncMock(return_value=fake_db_rows))), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)

    assert result.success is True
    assert len(captured_emit) == 1
    text = captured_emit[0]["payload"]["text"]
    # Must mention agent breakdown
    assert "reply_triage" in text
    # Must mention gate prevention
    assert "demote" in text.lower() or "prevented" in text.lower()


@pytest.mark.asyncio
async def test_daily_briefing_dedup_key_is_date():
    """Same date = same dedup key — re-running on same day suppresses."""
    ctx = HandlerContext(trace_id="t",
                          now=datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc))
    captured = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(dedup_key)
    with patch.object(ctx, "_db",
                      AsyncMock(fetch=AsyncMock(return_value=[]))), \
         patch.object(ctx, "emit_info", fake_emit):
        await handle({}, ctx)
    assert captured[0] == "daily_briefing:2026-04-26"


@pytest.mark.asyncio
async def test_daily_briefing_handles_empty_window_gracefully(ctx):
    """No agent activity in last 24h → still emits digest saying so."""
    captured: list[str] = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(payload["text"])
    with patch.object(ctx, "_db",
                      AsyncMock(fetch=AsyncMock(return_value=[]))), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
    assert any("no activity" in t.lower() or "0" in t for t in captured)
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/workers/handlers/test_daily_briefing.py -v
```

Expected: 3 failures with `ImportError`.

- [ ] **Step 3: Implement Daily Briefing**

```python
# workers/handlers/daily_briefing.py
"""
Daily Briefing handler — runs at cron.daily.07:00.

Aggregates yesterday's agent activity from agent_logs and emits one
info-tier Telegram digest. Folds info-tier pings from other agents
into a single message so the user doesn't see piecewise spam.

Per spec §5, §10. Replaces the cross-agent synthesis value the cut
Orchestrator agent was reaching for.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict

from workers.handlers.context import HandlerContext, HandlerResult

logger = logging.getLogger("cruz.workers.handlers.daily_briefing")

HANDLER_NAME = "daily_briefing"


async def handle(payload: Dict[str, Any], context: HandlerContext) -> HandlerResult:
    """Run the daily briefing.

    Args:
        payload: ARQ-supplied payload (unused for cron-triggered handlers;
                 reserved for future use)
        context: HandlerContext with kb/db/trace_id/now/emit_info
    """
    today = context.now.strftime("%Y-%m-%d")

    # Pull last-24h agent_logs rows. Note: SQL uses NOW() not context.now
    # — Daily Briefing runs against live time. context.now is used only
    # for dedup-key formatting and labelling.
    # Verified in Chunk 1+: services.db.DatabaseService exposes
    #   async def fetch(query: str, *args) -> list[asyncpg.Record]
    try:
        rows = await context.db.fetch(
            """
            SELECT agent, action, status
            FROM agent_logs
            WHERE created_at >= NOW() - INTERVAL '24 hours'
              AND agent NOT IN ('_gate', '_global')
            """,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("daily_briefing: db query failed: %s", exc)
        rows = []

    by_agent: Counter = Counter()
    by_status: Counter = Counter()
    gate_demotions = 0

    for r in rows:
        by_agent[r["agent"]] += 1
        by_status[r["status"]] += 1
        if r["action"] == "gate_decision" and r["status"] in ("demote_warn", "suppress"):
            gate_demotions += 1

    if not rows:
        text = "📋 *CRUZ daily briefing — " + today + "*\n\nNo agent activity in the last 24h."
    else:
        agent_lines = "\n".join(
            f"  • {agent}: {n}" for agent, n in by_agent.most_common(10)
        )
        text = (
            f"📋 *CRUZ daily briefing — {today}*\n\n"
            f"*Activity by agent*:\n{agent_lines}\n\n"
            f"*Gate stats*: {gate_demotions} pings demoted/suppressed by safety rails."
        )

    decision = await context.emit_info(
        handler_name=HANDLER_NAME,
        reason="daily_summary",
        dedup_key=f"{HANDLER_NAME}:{today}",
        payload={"text": text, "trace_id": context.trace_id},
    )
    return HandlerResult(
        handler_name=HANDLER_NAME,
        success=True,
        summary=f"emitted: {decision.value}, rows={len(rows)}",
        metadata={"row_count": len(rows), "agent_breakdown": dict(by_agent)},
    )
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/workers/handlers/test_daily_briefing.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add workers/handlers/daily_briefing.py tests/workers/handlers/test_daily_briefing.py
git commit -m "feat(sp5): add Daily Briefing handler

Per spec §5, §10. 7am digest of yesterday's agent activity from
agent_logs. Single info-tier Telegram message; date-based dedup
prevents same-day re-fire. Empty windows still emit a 'no activity'
note so the absence is itself observable."
```

---

### Task 5.3: Build the remaining 5 handlers

The other 5 handlers (`expense_auditor`, `portfolio_watcher`, `tax_helper`, `relationship_maintenance`, `travel_planner`) follow the same pattern as Daily Briefing:

1. Module-level `HANDLER_NAME` constant
2. `async def handle(payload, context: HandlerContext) -> HandlerResult:`
3. Read inputs (Notion API, Gmail API, RSS, Calendar, etc.)
4. Optional `kb.build_agent_context()` for context (per Rule 3)
5. Single Claude/Ollama call to compose the digest
6. `await context.emit_info(...)` with a date-based dedup key
7. Return HandlerResult

Each handler gets its own `tests/workers/handlers/test_<name>.py` with at minimum:
- `test_<name>_emits_info_with_dedup_key`
- `test_<name>_handles_empty_input_gracefully`

Use the `ChatResponse` shape from `services.llm` for LLM calls. Default model: Qwen `qwen2.5-coder:14b` (per Rule 2). All handlers route to local Ollama by default; no cloud escalation.

#### 5.3.a — Expense Auditor

**Files:**
- Create: `workers/handlers/expense_auditor.py`
- Test: `tests/workers/handlers/test_expense_auditor.py`

**Behavior:**
- Schedule: `cron.monthly.1st.09:00`
- Inputs: Gmail vendor receipts (last 30d) + Notion expense log
- Output: digest of categorized expenses + missing receipts

**Implementation skeleton:**
```python
# workers/handlers/expense_auditor.py
HANDLER_NAME = "expense_auditor"

async def handle(payload, context: HandlerContext) -> HandlerResult:
    today = context.now.strftime("%Y-%m-%d")
    # 1. Fetch Gmail receipts (label:Receipts in:Inbox newer_than:30d)
    receipts = await _fetch_gmail_receipts(context, days=30)
    # 2. Fetch Notion expense database rows for the same window
    notion_expenses = await _fetch_notion_expenses(context, days=30)
    # 3. Compose Claude prompt: "Categorize these expenses, flag missing receipts"
    summary_text = await _compose_summary(receipts, notion_expenses)
    # 4. Emit
    await context.emit_info(
        handler_name=HANDLER_NAME,
        reason="monthly_expense_summary",
        dedup_key=f"{HANDLER_NAME}:{today[:7]}",  # YYYY-MM dedup
        payload={"text": summary_text, "trace_id": context.trace_id},
    )
    return HandlerResult(handler_name=HANDLER_NAME, success=True,
                         summary=f"reviewed {len(receipts)} receipts")

# Helpers — _fetch_gmail_receipts, _fetch_notion_expenses, _compose_summary
# stub-imp with `raise NotImplementedError("connect Gmail/Notion in Chunk 8 wiring")`
# until Chunk 8 wires them. The test uses monkey-patching to replace them.
```

- [ ] **Step 1: Write failing tests**

```python
# tests/workers/handlers/test_expense_auditor.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest
from workers.handlers.context import HandlerContext
from workers.handlers.expense_auditor import handle


@pytest.fixture
def ctx():
    return HandlerContext(trace_id="ea-1",
                           now=datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_expense_auditor_emits_with_month_dedup(ctx):
    captured = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(dedup_key)
    with patch("workers.handlers.expense_auditor._fetch_gmail_receipts",
               AsyncMock(return_value=[{"id": "r1", "amount": 100}])), \
         patch("workers.handlers.expense_auditor._fetch_notion_expenses",
               AsyncMock(return_value=[])), \
         patch("workers.handlers.expense_auditor._compose_summary",
               AsyncMock(return_value="reviewed")), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
    assert captured[0] == "expense_auditor:2026-05"


@pytest.mark.asyncio
async def test_expense_auditor_handles_no_input(ctx):
    captured = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(payload["text"])
    with patch("workers.handlers.expense_auditor._fetch_gmail_receipts",
               AsyncMock(return_value=[])), \
         patch("workers.handlers.expense_auditor._fetch_notion_expenses",
               AsyncMock(return_value=[])), \
         patch("workers.handlers.expense_auditor._compose_summary",
               AsyncMock(return_value="no expenses found")), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
```

- [ ] **Step 2: Implement (writing-test-first cycle)**

Write the implementation; helpers raise `NotImplementedError` until Chunk 8 wires real Gmail/Notion clients. Tests monkey-patch them. Use `services.llm.chat` with model `"qwen2.5-coder:14b"` for `_compose_summary`.

- [ ] **Step 3: Run + commit**

```bash
pytest tests/workers/handlers/test_expense_auditor.py -v   # 2 passed
git add workers/handlers/expense_auditor.py tests/workers/handlers/test_expense_auditor.py
git commit -m "feat(sp5): add Expense Auditor handler"
```

#### 5.3.b — Portfolio Watcher

**Files:**
- Create: `workers/handlers/portfolio_watcher.py`
- Test: `tests/workers/handlers/test_portfolio_watcher.py`

**Behavior:**
- Schedule: `cron.weekly.friday.17:00`
- Inputs: RSS feeds tagged with each client's tech stack from `projects.tech_stack` (pulled from SP2's `projects` table)
- Output: per-client tech-news digest

**Module-level constants & helpers:**
- `HANDLER_NAME = "portfolio_watcher"`
- `_fetch_rss(stack: list[str]) -> list[dict]` — NotImplementedError until Chunk 8
- `_fetch_active_projects(context) -> list[dict]` — reads `SELECT id, name, slug, tech_stack FROM projects WHERE status='active'` via `context.db.fetch(...)`
- `_compose_digest(client_articles_map: dict) -> str` — Claude/Ollama via `services.llm.chat(model="qwen2.5-coder:14b", ...)`
- Dedup format: `f"portfolio_watcher:{context.now.strftime('%G-W%V')}"` (ISO year-week)

**Tests** (write these explicitly):

```python
# tests/workers/handlers/test_portfolio_watcher.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest
from workers.handlers.context import HandlerContext
from workers.handlers.portfolio_watcher import handle


@pytest.fixture
def ctx():
    # 2026-04-24 is a Friday in ISO week 17
    return HandlerContext(trace_id="pw-1",
                           now=datetime(2026, 4, 24, 17, 0, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_portfolio_watcher_emits_with_week_dedup(ctx):
    captured = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(dedup_key)
    with patch("workers.handlers.portfolio_watcher._fetch_active_projects",
               AsyncMock(return_value=[{"id": "p1", "name": "AMA",
                                        "slug": "ama-solutions",
                                        "tech_stack": ["nextjs"]}])), \
         patch("workers.handlers.portfolio_watcher._fetch_rss",
               AsyncMock(return_value=[{"title": "Next.js 16 released"}])), \
         patch("workers.handlers.portfolio_watcher._compose_digest",
               AsyncMock(return_value="weekly tech")), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
    assert captured[0] == "portfolio_watcher:2026-W17"


@pytest.mark.asyncio
async def test_portfolio_watcher_handles_no_articles(ctx):
    async def fake_emit(*args, **kwargs):
        pass
    with patch("workers.handlers.portfolio_watcher._fetch_active_projects",
               AsyncMock(return_value=[])), \
         patch("workers.handlers.portfolio_watcher._fetch_rss",
               AsyncMock(return_value=[])), \
         patch("workers.handlers.portfolio_watcher._compose_digest",
               AsyncMock(return_value="quiet week")), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
```

```bash
pytest tests/workers/handlers/test_portfolio_watcher.py -v   # 2 passed
git add workers/handlers/portfolio_watcher.py tests/workers/handlers/test_portfolio_watcher.py
git commit -m "feat(sp5): add Portfolio Watcher handler"
```

#### 5.3.c — Tax Helper

**Files:**
- Create: `workers/handlers/tax_helper.py`
- Test: `tests/workers/handlers/test_tax_helper.py`

**Behavior:**
- Schedule: `cron.quarterly.1st.10:00` (Apr/Jul/Oct/Jan)
- Inputs: Gmail + Notion expense log for the just-finished quarter
- Output: GST/income-tax checklist as Telegram message + Notion page draft

**Module-level constants & helpers:**
- `HANDLER_NAME = "tax_helper"`
- `_fetch_quarter_expenses(context, year, quarter) -> list` — NotImplementedError until Chunk 8 (uses Notion + Gmail under the hood; if duplication with `expense_auditor._fetch_*` becomes annoying, refactor into `workers/handlers/_shared.py` then — not now)
- `_compose_tax_checklist(expenses, quarter_label) -> str` — Claude Sonnet 4.6 (see Charter Override note below)
- `_create_notion_page_draft(text, title) -> str` — NotImplementedError until Chunk 8
- Dedup format: `f"tax_helper:{context.now.year}-Q{(context.now.month - 1) // 3 + 1}"`

**Charter override note (Rule 2).** Tax Helper is the only handler that uses Claude Sonnet 4.6 instead of Qwen. Justification: tax-prep accuracy is high-stakes; quarterly frequency keeps cost ≤ ₹4/quarter. This is a per-task override applied within the handler — no `AGENT_MODEL_CONFIG` change needed since handlers don't participate in CRUZ's intelligence-tag escalation pattern. Document this in the handler's docstring with a `# Rule 8 override:` comment.

**Tests** (write these explicitly):

```python
# tests/workers/handlers/test_tax_helper.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest
from workers.handlers.context import HandlerContext
from workers.handlers.tax_helper import handle


@pytest.fixture
def ctx():
    return HandlerContext(trace_id="th-1",
                           now=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_tax_helper_emits_with_quarter_dedup_and_creates_notion_draft(ctx):
    captured_dedup = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured_dedup.append(dedup_key)
    notion_calls = []
    async def fake_notion(text, title):
        notion_calls.append((text, title))
        return "https://notion.so/page-id"

    with patch("workers.handlers.tax_helper._fetch_quarter_expenses",
               AsyncMock(return_value=[{"amount": 1000, "category": "software"}])), \
         patch("workers.handlers.tax_helper._compose_tax_checklist",
               AsyncMock(return_value="checklist...")), \
         patch("workers.handlers.tax_helper._create_notion_page_draft",
               fake_notion), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)

    assert result.success is True
    # Apr 1 → Q2 (since Apr is month 4 → (4-1)//3 + 1 = 2)
    assert captured_dedup[0] == "tax_helper:2026-Q2"
    assert len(notion_calls) == 1


@pytest.mark.asyncio
async def test_tax_helper_handles_no_expenses(ctx):
    async def fake_emit(*args, **kwargs): pass
    async def fake_notion(*args): return "url"
    with patch("workers.handlers.tax_helper._fetch_quarter_expenses",
               AsyncMock(return_value=[])), \
         patch("workers.handlers.tax_helper._compose_tax_checklist",
               AsyncMock(return_value="no expenses")), \
         patch("workers.handlers.tax_helper._create_notion_page_draft",
               fake_notion), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
```

```bash
pytest tests/workers/handlers/test_tax_helper.py -v   # 2 passed
git add workers/handlers/tax_helper.py tests/workers/handlers/test_tax_helper.py
git commit -m "feat(sp5): add Tax Helper handler

Per spec §5. Charter Rule 2 override: uses Claude Sonnet 4.6 (not Qwen)
because tax-prep accuracy is high-stakes and quarterly frequency keeps
cost ≤ ₹4/quarter. Documented inline."
```

#### 5.3.d — Relationship Maintenance

**Files:**
- Create: `workers/handlers/relationship_maintenance.py`
- Test: `tests/workers/handlers/test_relationship_maintenance.py`

**Behavior:**
- Schedule: `cron.weekly.sunday.18:00`
- Inputs: Gmail (last-contact timestamps for known contacts pulled from cumulative thread participants over last 6 months)
- Output: 3 people you haven't messaged in >6w

**Module-level constants & helpers:**
- `HANDLER_NAME = "relationship_maintenance"`
- `STALE_THRESHOLD_DAYS = 42` (6 weeks)
- `MIN_PRIOR_CONTACTS = 3` (excludes one-offs)
- `_compute_last_contact_map(context) -> dict[str, dict]` — NotImplementedError stub; returns `{email: {last_contact_ts, contact_count}}`
- `_filter_stale_contacts(contact_map, now) -> list[dict]` — pure function, applies 6w-stale + ≥3-prior filter; testable without monkey-patching
- `_compose_message(stale_contacts) -> str` — Qwen via `services.llm.chat`; "short + warm tone"
- Dedup format: `f"relationship_maintenance:{context.now.strftime('%G-W%V')}"` (ISO year-week)

**Tests** (write these explicitly):

```python
# tests/workers/handlers/test_relationship_maintenance.py
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
import pytest
from workers.handlers.context import HandlerContext
from workers.handlers.relationship_maintenance import (
    handle, _filter_stale_contacts,
)


@pytest.fixture
def ctx():
    return HandlerContext(trace_id="rm-1",
                           now=datetime(2026, 4, 26, 18, 0, tzinfo=timezone.utc))


def test_filter_excludes_recent_contacts(ctx):
    """Anyone messaged within 42 days is excluded."""
    fresh_ts = (ctx.now - timedelta(days=10)).timestamp()
    contacts = {
        "fresh@x.com": {"last_contact_ts": fresh_ts, "contact_count": 5},
    }
    assert _filter_stale_contacts(contacts, ctx.now) == []


def test_filter_excludes_one_offs(ctx):
    """Less than 3 prior contacts → excluded (avoids spam noise)."""
    stale_ts = (ctx.now - timedelta(days=60)).timestamp()
    contacts = {
        "oneoff@x.com": {"last_contact_ts": stale_ts, "contact_count": 1},
    }
    assert _filter_stale_contacts(contacts, ctx.now) == []


@pytest.mark.asyncio
async def test_relationship_emits_with_week_dedup(ctx):
    captured = []
    async def fake_emit(handler_name, reason, dedup_key, payload):
        captured.append(dedup_key)
    stale_ts = (ctx.now - timedelta(days=60)).timestamp()
    with patch("workers.handlers.relationship_maintenance._compute_last_contact_map",
               AsyncMock(return_value={
                   "x@y.com": {"last_contact_ts": stale_ts, "contact_count": 5},
               })), \
         patch("workers.handlers.relationship_maintenance._compose_message",
               AsyncMock(return_value="ping x@y.com")), \
         patch.object(ctx, "emit_info", fake_emit):
        result = await handle({}, ctx)
    assert result.success is True
    # 2026-04-26 is Sunday in ISO week 17
    assert captured[0] == "relationship_maintenance:2026-W17"
```

```bash
pytest tests/workers/handlers/test_relationship_maintenance.py -v   # 3 passed
git add workers/handlers/relationship_maintenance.py tests/workers/handlers/test_relationship_maintenance.py
git commit -m "feat(sp5): add Relationship Maintenance handler"
```

#### 5.3.e — Travel Planner

**Files:**
- Create: `workers/handlers/travel_planner.py`
- Test: `tests/workers/handlers/test_travel_planner.py`

**Behavior:**
- Trigger: `webhook.google-calendar` event with `location:` field outside the user's home city (filter applied in this handler — not the gate)
- Inputs: the calendar event payload
- Output: travel logistics digest (flights, weather, packing checklist)

**Module-level constants & helpers:**
- `HANDLER_NAME = "travel_planner"`
- `_is_outside_home_city(event_location: str) -> bool` — matches against `HOME_CITY` env var (concrete impl, no stub: case-insensitive substring check)
- `_compose_logistics(event) -> str` — Qwen via `services.llm.chat`; uses title + location + start time
- Dedup format: `f"travel_planner:{event['id']}"` (per-event, not per-day — same trip → same dedup)

**Webhook integration design.** Travel Planner is webhook-triggered, but per Rule 7 handlers are NOT in `EVENT_REGISTRY` (that's agents-only). We need a parallel `HANDLER_REGISTRY` for webhook-triggered handlers. This adds a small `dispatch_event_to_handler` ARQ task (~30 lines) folded into `workers/tasks/dispatch.py`. The `_dispatch_to_registered` helper in `workers/tasks/webhook_tasks.py` is extended to fan out to BOTH registries.

**Note on import-time auto-registration.** Travel Planner self-registers via `register_event_handler(__name__, [...])` at module bottom. This fires on first import. Test isolation requires `clear_handler_registry()` between tests — handled by a new conftest in Step 0 below.

- [ ] **Step 0: Add handler-test conftest for registry isolation**

```python
# tests/workers/handlers/conftest.py
"""Reset HANDLER_REGISTRY around every handler test to insulate from
import-time auto-registration side effects."""

import pytest


@pytest.fixture(autouse=True)
def _reset_handler_registry():
    from workers.tasks.dispatch import clear_handler_registry
    clear_handler_registry()
    yield
    clear_handler_registry()
```

- [ ] **Step 1: Add `HANDLER_REGISTRY` and `dispatch_event_to_handler` to `workers/tasks/dispatch.py`**

```python
# Append to workers/tasks/dispatch.py:

HANDLER_REGISTRY: dict[str, list[str]] = {}  # trigger → list of handler module names


def register_event_handler(module_path: str, triggers: list[str]) -> None:
    """Register a handler module for one or more triggers."""
    for trigger in triggers:
        handlers = HANDLER_REGISTRY.setdefault(trigger, [])
        if module_path not in handlers:
            handlers.append(module_path)


def clear_handler_registry() -> None:
    HANDLER_REGISTRY.clear()


async def dispatch_event_to_handler(
    ctx: dict,
    module_path: str,
    event: dict,
) -> dict:
    """Run a handler in response to a registered trigger event."""
    from datetime import datetime, timezone
    from workers.handlers.context import HandlerContext, HandlerResult

    trace_id = event.get("trace_id") or f"sp5-handler-{uuid.uuid4()}"
    try:
        module = importlib.import_module(module_path)
        handle = getattr(module, "handle")
        context = HandlerContext(trace_id=trace_id,
                                  now=datetime.now(timezone.utc))
        result = await handle(event.get("data", {}), context)
        return {
            "success": result.success,
            "handler": result.handler_name,
            "summary": result.summary,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] dispatch_event_to_handler failed: %s — %s",
                         trace_id, module_path, exc)
        return {"success": False, "handler": module_path, "error": str(exc)}
```

- [ ] **Step 2: Extend webhook task dispatch to also fan out to handlers**

In `workers/tasks/webhook_tasks.py`, modify `_dispatch_to_registered`:

```python
async def _dispatch_to_registered(trigger: str, event_payload: Dict[str, Any]) -> None:
    from workers.tasks.dispatch import HANDLER_REGISTRY

    classes = EVENT_REGISTRY.get(trigger, [])
    handler_modules = HANDLER_REGISTRY.get(trigger, [])
    if not classes and not handler_modules:
        return
    pool = await _get_arq_pool()
    for cls in classes:
        await pool.enqueue_job(
            "dispatch_event_to_agent",
            cls.__module__, cls.__name__, event_payload,
        )
    for mod_path in handler_modules:
        await pool.enqueue_job(
            "dispatch_event_to_handler",
            mod_path, event_payload,
        )
```

- [ ] **Step 3: Update tests**

Add `test_handler_registry_dispatch` to `tests/workers/test_dispatch.py` — verifies handler dispatch via module path. Add `test_webhook_dispatches_to_registered_handler` to `tests/workers/test_webhook_tasks_dispatch.py` — registers a handler module + verifies enqueue.

- [ ] **Step 4: Implement Travel Planner using the handler registry**

The handler module's bottom (after `handle()`) calls:

```python
from workers.tasks.dispatch import register_event_handler

# Auto-register on import — Chunk 8 imports all handlers at app boot
register_event_handler(__name__, ["webhook.google-calendar"])
```

(This is the auto-registration pattern. Cron-triggered handlers don't auto-register here — they're hooked to ARQ cron in Chunk 8.)

```bash
pytest tests/workers/handlers/test_travel_planner.py -v   # 2 passed
git add workers/handlers/travel_planner.py workers/tasks/dispatch.py \
        workers/tasks/webhook_tasks.py \
        tests/workers/handlers/test_travel_planner.py \
        tests/workers/test_dispatch.py \
        tests/workers/test_webhook_tasks_dispatch.py
git commit -m "feat(sp5): add Travel Planner handler + handler registry

Per spec §5, §6. New HANDLER_REGISTRY parallels EVENT_REGISTRY for
webhook-triggered handlers. dispatch_event_to_handler ARQ task runs
handlers in response to events. Travel Planner auto-registers
against webhook.google-calendar on import."
```

---

### Task 5.4: Verify Chunk 5 end-to-end

- [ ] **Step 1: Full handler suite**

```bash
pytest tests/workers/handlers/ -v --tb=short
```

Expected: **19 passed** (5 context + 3 daily_briefing + 2 expense_auditor + 2 portfolio_watcher + 2 tax_helper + 3 relationship_maintenance + 2 travel_planner). Adjust count if you write extra tests during execution.

- [ ] **Step 2: Verify dispatch infrastructure unchanged**

```bash
pytest tests/workers/test_dispatch.py tests/workers/test_webhook_tasks_dispatch.py -v
```

Expected: previous tests + 2 new (handler registry + handler dispatch via webhook).

- [ ] **Step 3: Tag chunk done**

```bash
git tag claude/sp5-chunk-5-done
```

---

**End of Chunk 5.** All 6 handlers implemented. HandlerContext structurally enforces info-only emission. Daily Briefing handler is the canonical pattern; the other 5 mirror it. Travel Planner adds the handler-via-webhook dispatch path (HANDLER_REGISTRY parallel to EVENT_REGISTRY).

---

## Chunk 6: K1-survivor agents (Reply Triage, Followup, Health Guardian) + calibration

This chunk lands the three agents that survive a K1 cut: Reply Triage (gates the SP5 exit), Followup, Health Guardian. Reply Triage gets the most depth — its calibration script is the day-1 gate determining Qwen-vs-Claude.

All three agents follow the canonical EventDrivenAgent pattern from Chunk 4:

```python
class XAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = [...]
    TRIGGERS         = [...]
    CRITICAL_REASONS = {...}

    async def process(self, input: AgentInput) -> AgentOutput:
        # 1. Build KB context (Rule 3)
        kb_context = await get_kb_service().build_agent_context(...)
        # 2. Pull data (event payload, Gmail, journal, ...)
        # 3. LLM tool-use loop (Rule 1 (a))
        # 4. Decide whether to emit
        # 5. await self.emit(severity, reason_code, dedup_key, payload)
        # 6. Record activity (Rule 3)
        await get_kb_service().record_agent_activity(...)
        return AgentOutput(...)
```

### Task 6.1: Reply Triage agent + Gmail history-fetch wrapper + calibration script

**Files:**
- Create: `agents/reply_triage/__init__.py` — exports `ReplyTriageAgent`
- Create: `agents/reply_triage/reply_triage_agent.py` — main class
- Create: `agents/reply_triage/tools.py` — tool schemas + executors
- Create: `agents/reply_triage/gmail_client.py` — Gmail API wrapper (`fetch_message`, `fetch_history_since`, `list_recent_inbound`)
- Create: `scripts/calibrate_reply_triage.py` — day-1 50-email accuracy CLI
- Modify: `workers/tasks/gmail_webhook_tasks.py` — wire `_fetch_new_message_ids` to the real Gmail client
- Test: `tests/agents/test_reply_triage.py`
- Test: `tests/scripts/test_calibrate_reply_triage.py`

#### 6.1.1 — Implement the Gmail client wrapper

The wrapper isolates Gmail API calls so tests monkey-patch one boundary. Uses google-api-python-client (already a v1 dep — used by Calendar agent).

- [ ] **Step 1: Write `agents/reply_triage/gmail_client.py`**

```python
# agents/reply_triage/gmail_client.py
"""
Thin Gmail API wrapper for Reply Triage and gmail-webhook task.

Authentication uses the OAuth credentials at GMAIL_CREDENTIALS_PATH
(already configured in v1 for ECHO/REACH agents). Tests monkey-patch
the public functions; the underlying client is lazily constructed.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger("cruz.agents.reply_triage.gmail_client")

_USER_ID = "me"
_SERVICE_CACHE: Any = None


def _get_service():
    global _SERVICE_CACHE
    if _SERVICE_CACHE is not None:
        return _SERVICE_CACHE
    creds_path = os.environ.get("GMAIL_CREDENTIALS_PATH", "")
    token_path = os.environ.get("GMAIL_TOKEN_PATH", "")
    if not creds_path or not token_path:
        raise RuntimeError(
            "GMAIL_CREDENTIALS_PATH/GMAIL_TOKEN_PATH not set — "
            "Reply Triage cannot read Gmail"
        )
    creds = Credentials.from_authorized_user_file(token_path)
    _SERVICE_CACHE = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return _SERVICE_CACHE


async def fetch_message(message_id: str) -> dict:
    """Return the parsed message envelope: {id, subject, from, date, body, thread_id}."""
    import asyncio
    return await asyncio.to_thread(_fetch_message_sync, message_id)


def _fetch_message_sync(message_id: str) -> dict:
    svc = _get_service()
    msg = svc.users().messages().get(
        userId=_USER_ID, id=message_id, format="full",
    ).execute()
    payload = msg.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    body = _extract_text_body(payload)
    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId"),
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "date": headers.get("date", ""),
        "body": body,
        "labelIds": msg.get("labelIds", []),
    }


def _extract_text_body(payload: dict) -> str:
    """Walk MIME parts, return first text/plain (or text/html stripped) chunk."""
    if payload.get("mimeType", "").startswith("text/"):
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        text = _extract_text_body(part)
        if text:
            return text
    return ""


async def fetch_history_since(history_id: str) -> List[str]:
    """Return list of new message IDs since `history_id`."""
    import asyncio
    return await asyncio.to_thread(_fetch_history_sync, history_id)


def _fetch_history_sync(history_id: str) -> List[str]:
    svc = _get_service()
    try:
        history = svc.users().history().list(
            userId=_USER_ID,
            startHistoryId=history_id,
            historyTypes=["messageAdded"],
        ).execute()
    except Exception as exc:
        logger.warning("gmail history fetch failed: %s", exc)
        return []
    msg_ids: list[str] = []
    for h in history.get("history", []):
        for added in h.get("messagesAdded", []):
            mid = added.get("message", {}).get("id")
            if mid:
                msg_ids.append(mid)
    return msg_ids


async def list_recent_inbound(limit: int = 50) -> List[str]:
    """For the calibration script — returns latest `limit` inbound message IDs."""
    import asyncio
    return await asyncio.to_thread(_list_recent_sync, limit)


def _list_recent_sync(limit: int) -> List[str]:
    svc = _get_service()
    res = svc.users().messages().list(
        userId=_USER_ID, q="-from:me category:primary", maxResults=limit,
    ).execute()
    return [m["id"] for m in res.get("messages", [])]
```

- [ ] **Step 2: Wire `_fetch_new_message_ids` to the real client**

In `workers/tasks/gmail_webhook_tasks.py`, replace the `NotImplementedError` stub:

```python
async def _fetch_new_message_ids(history_id: str) -> List[str]:
    from agents.reply_triage.gmail_client import fetch_history_since
    return await fetch_history_since(history_id)
```

- [ ] **Step 3: Run existing `test_gmail_webhook_tasks.py` to verify Chunk 4 tests still pass**

```bash
pytest tests/workers/test_gmail_webhook_tasks.py -v
```

Expected: 3 passed. (Tests still monkey-patch `_fetch_new_message_ids` directly, so the new real implementation isn't exercised here.)

- [ ] **Step 4: Commit**

```bash
git add agents/reply_triage/__init__.py agents/reply_triage/gmail_client.py \
        workers/tasks/gmail_webhook_tasks.py
git commit -m "feat(sp5): add Gmail client wrapper + wire history fetch

Per spec §3.5. agents/reply_triage/gmail_client.py owns all Gmail API
calls. workers/tasks/gmail_webhook_tasks.py replaces its
NotImplementedError stub with the real fetch_history_since call."
```

#### 6.1.2 — Implement `ReplyTriageAgent`

- [ ] **Step 1: Write failing tests for the agent**

```python
# tests/agents/test_reply_triage.py
"""ReplyTriageAgent — gate-determining agent for SP5 exit gate."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from typing import Any

import pytest

from agents.reply_triage.reply_triage_agent import ReplyTriageAgent
from services.proactive_engine import GateDecision


@pytest.fixture(autouse=True)
def _reset_proactive_engine_singleton():
    import services.proactive_engine as mod
    mod._instance = None
    yield
    mod._instance = None


@pytest.fixture
def agent():
    return ReplyTriageAgent()


def test_class_attrs_match_spec(agent):
    assert agent.KNOWLEDGE_RINGS == ["cruz_activities", "cruz_user_patterns"]
    assert "webhook.gmail.new_message" in agent.TRIGGERS
    assert "cron.5min.gmail_poll" in agent.TRIGGERS
    assert "client_email_unanswered_72h" in agent.CRITICAL_REASONS


@pytest.mark.asyncio
async def test_process_classifies_via_llm_and_caches_result(agent):
    """LLM returns a classification dict; agent stores it in state."""
    fake_msg = {
        "id": "msg-1", "subject": "AMA — production down",
        "from": "ateet@ama.com", "body": "the site is broken",
        "thread_id": "t1", "date": "2026-04-26T10:00:00Z",
    }
    fake_classification = {
        "label": "needs_reply", "urgency": "now",
        "client_match": "ama-uuid", "confidence": 0.9,
        "reason": "explicit production incident",
    }
    fake_state_set = AsyncMock()
    with patch("agents.reply_triage.reply_triage_agent.fetch_message",
               AsyncMock(return_value=fake_msg)), \
         patch("agents.reply_triage.reply_triage_agent._classify_email",
               AsyncMock(return_value=fake_classification)), \
         patch("agents.reply_triage.reply_triage_agent._resolve_client_match",
               AsyncMock(return_value="ama-uuid")), \
         patch("agents.reply_triage.reply_triage_agent._email_age_hours",
               return_value=80), \
         patch("agents.reply_triage.reply_triage_agent.get_state_service",
               return_value=AsyncMock(set=fake_state_set, get=AsyncMock(return_value=None))), \
         patch.object(agent, "emit",
                      AsyncMock(return_value=GateDecision.ALLOW)):
        result = await agent.process({
            "task": "event:webhook.gmail.new_message",
            "context": {"event": {"data": {"message_id": "msg-1"}}},
            "trace_id": "tr-1",
            "conversation_id": "",
        })
    assert result["success"] is True
    fake_state_set.assert_awaited()  # classification cached


@pytest.mark.asyncio
async def test_critical_only_when_all_four_conditions_hold(agent):
    """needs_reply + urgency now/today + client_match + age>72h → critical."""
    fake_msg = {"id": "m1", "subject": "x", "from": "ateet@ama.com",
                "body": "hi", "thread_id": "t", "date": ""}
    cases = [
        # (label, urgency, client_match, age_hours, expected_severity_arg)
        ("needs_reply", "now", "ama-uuid", 80, "critical"),
        ("needs_reply", "now", "ama-uuid", 50, "warn"),  # too young
        ("needs_reply", "now", None,        80, "warn"),  # no client
        ("needs_reply", "this_week", "ama-uuid", 80, "warn"),  # not urgent
        ("fyi",        "now", "ama-uuid", 80, "info"),  # not needs_reply
    ]
    for label, urgency, client, age, expected_sev in cases:
        emit_calls = []
        async def fake_emit(severity, reason, dedup_key, payload):
            emit_calls.append(severity)
            return GateDecision.ALLOW
        with patch("agents.reply_triage.reply_triage_agent.fetch_message",
                   AsyncMock(return_value=fake_msg)), \
             patch("agents.reply_triage.reply_triage_agent._classify_email",
                   AsyncMock(return_value={
                       "label": label, "urgency": urgency,
                       "client_match": client, "confidence": 0.9,
                       "reason": "test",
                   })), \
             patch("agents.reply_triage.reply_triage_agent._resolve_client_match",
                   AsyncMock(return_value=client)), \
             patch("agents.reply_triage.reply_triage_agent._email_age_hours",
                   return_value=age), \
             patch("agents.reply_triage.reply_triage_agent.get_state_service",
                   return_value=AsyncMock(set=AsyncMock(),
                                           get=AsyncMock(return_value=None))), \
             patch.object(agent, "emit", fake_emit):
            await agent.process({
                "task": "event:webhook.gmail.new_message",
                "context": {"event": {"data": {"message_id": "m1"}}},
                "trace_id": "tr", "conversation_id": "",
            })
        assert emit_calls == [expected_sev], (
            f"label={label} urgency={urgency} client={client} age={age}: "
            f"expected emit at {expected_sev!r}, got {emit_calls!r}"
        )


@pytest.mark.asyncio
async def test_dedup_key_uses_message_id(agent):
    fake_msg = {"id": "m-uniq", "subject": "x", "from": "x@y.com",
                "body": "", "thread_id": "t", "date": ""}
    captured_dedup = []
    async def fake_emit(severity, reason, dedup_key, payload):
        captured_dedup.append(dedup_key)
        return GateDecision.ALLOW
    with patch("agents.reply_triage.reply_triage_agent.fetch_message",
               AsyncMock(return_value=fake_msg)), \
         patch("agents.reply_triage.reply_triage_agent._classify_email",
               AsyncMock(return_value={"label": "fyi", "urgency": "later",
                                        "client_match": None, "confidence": 0.5,
                                        "reason": ""})), \
         patch("agents.reply_triage.reply_triage_agent._resolve_client_match",
               AsyncMock(return_value=None)), \
         patch("agents.reply_triage.reply_triage_agent._email_age_hours",
               return_value=10), \
         patch("agents.reply_triage.reply_triage_agent.get_state_service",
               return_value=AsyncMock(set=AsyncMock(),
                                       get=AsyncMock(return_value=None))), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({
            "task": "event", "context": {"event": {"data": {"message_id": "m-uniq"}}},
            "trace_id": "t", "conversation_id": "",
        })
    assert captured_dedup == ["email:m-uniq"]


@pytest.mark.asyncio
async def test_skips_if_already_classified(agent):
    """If state has a prior classification for this message, skip LLM call."""
    cached = {"label": "fyi", "urgency": "later", "client_match": None,
              "confidence": 0.5, "reason": "cached"}
    fake_msg = {"id": "m1", "subject": "x", "from": "x@y.com", "body": "",
                "thread_id": "t", "date": ""}
    classify_mock = AsyncMock()
    with patch("agents.reply_triage.reply_triage_agent.fetch_message",
               AsyncMock(return_value=fake_msg)), \
         patch("agents.reply_triage.reply_triage_agent._classify_email",
               classify_mock), \
         patch("agents.reply_triage.reply_triage_agent.get_state_service",
               return_value=AsyncMock(get=AsyncMock(return_value=cached),
                                       set=AsyncMock())), \
         patch.object(agent, "emit", AsyncMock(return_value=GateDecision.ALLOW)):
        await agent.process({
            "task": "event", "context": {"event": {"data": {"message_id": "m1"}}},
            "trace_id": "t", "conversation_id": "",
        })
    classify_mock.assert_not_awaited()
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/agents/test_reply_triage.py -v
```

Expected: 5 failures with `ImportError`.

- [ ] **Step 3: Implement `ReplyTriageAgent`**

```python
# agents/reply_triage/__init__.py
from agents.reply_triage.reply_triage_agent import ReplyTriageAgent
__all__ = ["ReplyTriageAgent"]
```

```python
# agents/reply_triage/reply_triage_agent.py
"""
ReplyTriageAgent — classifies inbound Gmail messages and fires a critical
alert only when ALL of these conditions hold:
  - label == "needs_reply"
  - urgency in {"now", "today"}
  - client_match is not None
  - email age > 72h

Otherwise emits at info or warn (severity per a small decision matrix).

Default model: Qwen qwen2.5-coder:14b (per Charter Rule 2). Day-1
calibration test (scripts/calibrate_reply_triage.py) determines whether
to keep Qwen or flip to Claude Sonnet 4.6. If flipped, set
AGENT_MODEL_REPLY_TRIAGE env var; agent reads it on each classify call.

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §4.1
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

from agents.base_agent import AgentInput, AgentOutput
from agents.event_driven_agent import EventDrivenAgent
from agents.reply_triage.gmail_client import fetch_message
from services.agent_state import get_state_service
from services.db import get_db_service
from services.knowledge_base import get_kb_service
from services.llm import chat as llm_chat
from services.proactive_engine import GateDecision

logger = logging.getLogger("cruz.agents.reply_triage")

_DEFAULT_MODEL = "qwen2.5-coder:14b"
_CACHE_TTL_DAYS = 30


class ReplyTriageAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_activities", "cruz_user_patterns"]
    TRIGGERS         = ["webhook.gmail.new_message", "cron.5min.gmail_poll"]
    CRITICAL_REASONS = {
        "client_email_unanswered_72h":
            "Email from a known client requires reply, age >72h",
    }

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        trace_id = input["trace_id"]
        try:
            event = input["context"].get("event", {}).get("data", {})
            message_id = event.get("message_id")
            if not message_id:
                return self._fail("no message_id in event", trace_id, start)

            # 1. Cache check
            state = get_state_service()
            cached = await state.get(self.name, f"last_classified:{message_id}")
            if cached:
                logger.debug("[%s] reply_triage: using cached classification for %s",
                             trace_id, message_id)
                classification = cached
                msg = await fetch_message(message_id)  # still fetch for emit metadata
            else:
                # 2. Fetch message
                msg = await fetch_message(message_id)

                # 3. Build KB context (Rule 3)
                kb_context = await get_kb_service().build_agent_context(
                    task=msg.get("subject", "") + "\n\n" + msg.get("body", "")[:500],
                    rings=self.KNOWLEDGE_RINGS,
                    trace_id=trace_id,
                )

                # 4. Classify (LLM call)
                classification = await _classify_email(msg, kb_context)
                # 5. Resolve client_match against projects.email_domains
                classification["client_match"] = await _resolve_client_match(
                    msg.get("from", "")
                )

                # 6. Cache
                await state.set(
                    self.name, f"last_classified:{message_id}",
                    classification, ttl_seconds=_CACHE_TTL_DAYS * 86400,
                )

            # 7. Decide severity (deterministic, NOT a model call)
            age_hours = _email_age_hours(msg.get("date", ""))
            severity, reason_code = _decide_severity(classification, age_hours)

            # 8. Emit
            decision = await self.emit(
                severity=severity,
                reason_code=reason_code,
                dedup_key=f"email:{message_id}",
                payload={
                    "text": _format_telegram_text(msg, classification, age_hours, severity),
                    "trace_id": trace_id,
                },
            )

            # 9. Record activity (Rule 3)
            await get_kb_service().record_agent_activity(
                agent_name=self.name,
                task=f"triage:{msg.get('subject', '')[:80]}",
                result_summary=f"{classification['label']}/{classification['urgency']} "
                               f"→ {severity} ({decision.value})",
                success=True,
                trace_id=trace_id,
                project_id=classification.get("client_match"),
            )

            return AgentOutput(
                success=True, result=classification, agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0, error=None,
                requires_approval=False, approval_prompt=None,
            )
        except Exception as exc:
            return self._fail(str(exc), trace_id, start, exc)

    def _fail(self, reason: str, trace_id: str, start: float,
              exc: Exception | None = None) -> AgentOutput:
        if exc:
            logger.exception("[%s] reply_triage failed: %s", trace_id, reason)
        else:
            logger.warning("[%s] reply_triage skipped: %s", trace_id, reason)
        return AgentOutput(
            success=False, result=None, agent=self.name,
            duration_ms=int((time.monotonic() - start) * 1000),
            tokens_used=0, error=reason,
            requires_approval=False, approval_prompt=None,
        )


# ── Module-level helpers (testable in isolation) ────────────────────────

def _decide_severity(classification: dict, age_hours: int) -> tuple[str, str | None]:
    """Map (classification, age_hours) → (severity, reason_code).

    Critical fires only when ALL conditions hold:
      label == 'needs_reply' AND urgency in {now, today}
      AND client_match is not None AND age_hours > 72.
    Otherwise: needs_reply → warn; everything else → info.
    """
    label = classification.get("label")
    urgency = classification.get("urgency")
    client_match = classification.get("client_match")

    if (label == "needs_reply"
            and urgency in ("now", "today")
            and client_match is not None
            and age_hours > 72):
        return ("critical", "client_email_unanswered_72h")
    if label == "needs_reply":
        return ("warn", None)
    return ("info", None)


def _email_age_hours(date_header: str) -> int:
    """Parse RFC 2822 date header → age in hours from now (UTC)."""
    if not date_header:
        return 0
    try:
        dt = parsedate_to_datetime(date_header)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return max(0, int(delta.total_seconds() / 3600))
    except Exception:
        return 0


async def _classify_email(msg: dict, kb_context: str = "") -> dict:
    """LLM call returning {label, urgency, client_match, confidence, reason}."""
    model = os.environ.get("AGENT_MODEL_REPLY_TRIAGE", _DEFAULT_MODEL)
    prompt = (
        f"{kb_context}\n\n"
        "Classify this email. Return JSON ONLY with fields:\n"
        '  label: "needs_reply" | "fyi" | "spam" | "promo"\n'
        '  urgency: "now" | "today" | "this_week" | "later"\n'
        '  client_match: null (you cannot resolve clients — leave null)\n'
        "  confidence: 0.0-1.0\n"
        "  reason: short explanation (≤15 words)\n\n"
        f"From: {msg.get('from', '')}\n"
        f"Subject: {msg.get('subject', '')}\n"
        f"Body (first 1500 chars):\n{msg.get('body', '')[:1500]}\n"
    )
    response = await llm_chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
    )
    text = ""
    for block in response.content:
        if hasattr(block, "type") and block.type == "text":
            text = block.text
            break
    return _parse_classification_json(text)


def _parse_classification_json(text: str) -> dict:
    """Strip markdown fences if any, parse JSON, fall back to safe default."""
    text = text.strip()
    if text.startswith("```"):
        # strip ```json ... ``` fences
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        d = json.loads(text)
    except Exception:
        return {"label": "fyi", "urgency": "later", "client_match": None,
                "confidence": 0.0, "reason": "parse failed"}
    return {
        "label": d.get("label", "fyi"),
        "urgency": d.get("urgency", "later"),
        "client_match": d.get("client_match"),
        "confidence": float(d.get("confidence", 0.5)),
        "reason": d.get("reason", ""),
    }


async def _resolve_client_match(from_header: str) -> Optional[str]:
    """Match the email's domain against projects.email_domains. Returns
    project_id (UUID) or None.

    Uses the email_domains TEXT[] column added by migration 0006.
    """
    if not from_header or "@" not in from_header:
        return None
    domain = from_header.rsplit("@", 1)[-1].rstrip(">").lower().strip()
    if not domain:
        return None
    db = get_db_service()
    row = await db.fetchrow(
        "SELECT id FROM projects WHERE $1 = ANY(email_domains) AND status='active' LIMIT 1",
        domain,
    )
    return row["id"] if row else None


def _format_telegram_text(msg: dict, classification: dict,
                          age_hours: int, severity: str) -> str:
    """Compose the human-readable Telegram message body."""
    sev_emoji = {"info": "📥", "warn": "⚠️", "critical": "🚨"}[severity]
    return (
        f"{sev_emoji} *{classification['label']}/{classification['urgency']}*\n"
        f"From: `{msg.get('from', '?')}`\n"
        f"Subject: {msg.get('subject', '?')}\n"
        f"Age: {age_hours}h • {classification.get('reason', '')}"
    )
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/agents/test_reply_triage.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add agents/reply_triage/ tests/agents/test_reply_triage.py
git commit -m "feat(sp5): add ReplyTriageAgent

Per spec §4.1. Classifies inbound Gmail messages via Qwen 14B (default,
per Rule 2). Critical fires only when ALL four conditions hold:
needs_reply + urgent + known client + age >72h. Day-1 calibration script
in next task determines if Qwen meets the 80% exit gate; flip to Claude
via AGENT_MODEL_REPLY_TRIAGE env if not."
```

#### 6.1.3 — Calibration script

The script pulls last 50 inbound emails, asks Qwen to classify each, then asks the user to manually confirm/correct. Computes joint-match-rate. Pass = ≥80%.

- [ ] **Step 1: Write calibration script**

```python
# scripts/calibrate_reply_triage.py
"""
Day-1 calibration test for Reply Triage. Pulls 50 most recent inbound
emails, runs the agent's classifier, then asks the user to confirm/correct
each label + urgency. Computes match rate. Pass = ≥80% joint match.

If pass: keep Qwen as default model.
If fail: set AGENT_MODEL_REPLY_TRIAGE=claude-sonnet-4-6 and re-run this
script. If Claude also fails, escalate per spec §8.1 fix-window.

Usage:
  python scripts/calibrate_reply_triage.py
  python scripts/calibrate_reply_triage.py --limit 30  # for a quick smoke
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from agents.reply_triage.gmail_client import fetch_message, list_recent_inbound
from agents.reply_triage.reply_triage_agent import _classify_email


VALID_LABELS = ["needs_reply", "fyi", "spam", "promo"]
VALID_URGENCIES = ["now", "today", "this_week", "later"]


async def main(limit: int) -> int:
    print(f"Fetching last {limit} inbound emails…")
    msg_ids = await list_recent_inbound(limit)
    print(f"Got {len(msg_ids)} message IDs.\n")

    matches_label = 0
    matches_urgency = 0
    matches_joint = 0

    for i, mid in enumerate(msg_ids, 1):
        msg = await fetch_message(mid)
        agent_pred = await _classify_email(msg)
        print(f"\n--- {i}/{len(msg_ids)} ---")
        print(f"From:    {msg['from']}")
        print(f"Subject: {msg['subject'][:80]}")
        print(f"Agent:   label={agent_pred['label']:12s} urgency={agent_pred['urgency']}")
        print("Your label?    [needs_reply / fyi / spam / promo] ", end="", flush=True)
        user_label = input().strip() or agent_pred["label"]
        print("Your urgency?  [now / today / this_week / later] ", end="", flush=True)
        user_urgency = input().strip() or agent_pred["urgency"]

        if user_label not in VALID_LABELS or user_urgency not in VALID_URGENCIES:
            print("invalid input; skipping this email")
            continue

        l_match = (agent_pred["label"] == user_label)
        u_match = (agent_pred["urgency"] == user_urgency)
        matches_label   += int(l_match)
        matches_urgency += int(u_match)
        matches_joint   += int(l_match and u_match)

    n = len(msg_ids)
    if n == 0:
        print("\nNo emails to evaluate. Check Gmail credentials.")
        return 1
    print("\n=== Results ===")
    print(f"Label-only match:    {matches_label}/{n} = {100*matches_label/n:.1f}%")
    print(f"Urgency-only match:  {matches_urgency}/{n} = {100*matches_urgency/n:.1f}%")
    print(f"Joint match:         {matches_joint}/{n} = {100*matches_joint/n:.1f}%")
    joint_rate = matches_joint / n
    if joint_rate >= 0.80:
        print("\n✅ PASSES exit gate (≥80% joint match). Keep current model.")
        return 0
    else:
        print("\n❌ FAILS exit gate. Either (a) flip model to claude-sonnet-4-6:")
        print("     export AGENT_MODEL_REPLY_TRIAGE=claude-sonnet-4-6")
        print("   then re-run this script; or (b) iterate on prompt/schema.")
        return 2


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.limit)))
```

- [ ] **Step 2: Write failing test**

```python
# tests/scripts/test_calibrate_reply_triage.py
"""Smoke test the calibration flow with mocked Gmail + LLM + input()."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_calibration_passes_when_80pct_match(capsys):
    from scripts.calibrate_reply_triage import main

    fake_msg = {"id": "1", "from": "x@y.com", "subject": "hi", "body": "",
                "thread_id": "t", "date": ""}
    with patch("scripts.calibrate_reply_triage.list_recent_inbound",
               AsyncMock(return_value=["1", "2", "3", "4", "5"])), \
         patch("scripts.calibrate_reply_triage.fetch_message",
               AsyncMock(return_value=fake_msg)), \
         patch("scripts.calibrate_reply_triage._classify_email",
               AsyncMock(return_value={"label": "fyi", "urgency": "later",
                                        "client_match": None,
                                        "confidence": 0.5, "reason": ""})), \
         patch("builtins.input", side_effect=["fyi", "later"] * 5):
        rc = await main(limit=5)
    out = capsys.readouterr().out
    assert "PASSES" in out
    assert rc == 0


@pytest.mark.asyncio
async def test_calibration_fails_below_80pct(capsys):
    from scripts.calibrate_reply_triage import main
    fake_msg = {"id": "1", "from": "x@y.com", "subject": "x", "body": "",
                "thread_id": "t", "date": ""}
    with patch("scripts.calibrate_reply_triage.list_recent_inbound",
               AsyncMock(return_value=["1", "2", "3", "4", "5"])), \
         patch("scripts.calibrate_reply_triage.fetch_message",
               AsyncMock(return_value=fake_msg)), \
         patch("scripts.calibrate_reply_triage._classify_email",
               AsyncMock(return_value={"label": "fyi", "urgency": "later",
                                        "client_match": None,
                                        "confidence": 0.5, "reason": ""})), \
         patch("builtins.input",
               side_effect=["needs_reply", "now"] * 5):  # all disagree
        rc = await main(limit=5)
    out = capsys.readouterr().out
    assert "FAILS" in out
    assert rc == 2
```

- [ ] **Step 3: Run tests, expect pass**

```bash
mkdir -p tests/scripts
touch tests/scripts/__init__.py
pytest tests/scripts/test_calibrate_reply_triage.py -v
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add scripts/calibrate_reply_triage.py tests/scripts/__init__.py tests/scripts/test_calibrate_reply_triage.py
git commit -m "feat(sp5): add Reply Triage day-1 calibration script

Per spec §8.1. Pulls 50 inbound emails, classifies via current model,
prompts user to confirm. Pass = ≥80% joint label+urgency match.
Fail → flip to Claude via AGENT_MODEL_REPLY_TRIAGE env var and re-run."
```

---

### Task 6.2: FollowupAgent

**Files:**
- Create: `agents/followup/__init__.py`, `agents/followup/followup_agent.py`
- Test: `tests/agents/test_followup.py`

**Class shape:**
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

**State schema:**
- `agent_state(followup, "queue")` = JSONB array of `{thread_id, client_email, sent_at_ts, project_id, due_date_iso}` records.

**process() flow:**
- If trigger is `webhook.gmail.outbound_sent`: append the new outbound to `queue`.
- If trigger is `cron.daily.10:00`: scan queue:
  - For each entry, check Gmail thread reply state (use `gmail_client.fetch_thread_replied(thread_id)` — add this to `agents/reply_triage/gmail_client.py`).
  - Replied → remove from queue.
  - Unreplied + age ≥ 5d + has client → critical with `followup_due_5d`.
  - Unreplied + age < 5d → no emit (wait).
- Optionally read Plane.so for client_promised_deliverable_overdue (use `services/plane.py` already in v1).

**Tests** (4 minimum). Test bodies follow the Reply Triage pattern — patch `fetch_thread_replied` + `get_state_service` + `agent.emit`, then run `await agent.process(input)`. Skeletons:

```python
# tests/agents/test_followup.py — sketch (4 tests)
import time
from unittest.mock import AsyncMock, patch
import pytest
from agents.followup.followup_agent import FollowupAgent
from services.proactive_engine import GateDecision


@pytest.fixture(autouse=True)
def _reset_proactive_engine_singleton():
    import services.proactive_engine as mod
    mod._instance = None
    yield
    mod._instance = None


@pytest.fixture
def agent():
    return FollowupAgent()


@pytest.mark.asyncio
async def test_outbound_event_appends_to_queue(agent):
    set_calls = []
    async def fake_set(*args, **kwargs):
        set_calls.append(args)
    state = AsyncMock(get=AsyncMock(return_value=[]), set=fake_set)
    with patch("agents.followup.followup_agent.get_state_service",
               return_value=state):
        await agent.process({
            "task": "event:webhook.gmail.outbound_sent",
            "context": {"event": {"trigger": "webhook.gmail.outbound_sent",
                                  "data": {"thread_id": "t1",
                                           "to": "ateet@ama.com"}}},
            "trace_id": "tr", "conversation_id": "",
        })
    # set called with new queue entry appended
    assert set_calls
    queue = set_calls[-1][2]  # 3rd positional arg is value
    assert any(e["thread_id"] == "t1" for e in queue)


@pytest.mark.asyncio
async def test_cron_emits_critical_for_5d_unanswered_client_email(agent):
    six_days_ago = time.time() - 6 * 86400
    queue = [{"thread_id": "t1", "client_email": "ateet@ama.com",
              "sent_at_ts": six_days_ago, "project_id": "ama-uuid",
              "due_date_iso": None}]
    state = AsyncMock(get=AsyncMock(return_value=queue), set=AsyncMock())
    emit_calls = []
    async def fake_emit(severity, reason, dedup_key, payload):
        emit_calls.append((severity, reason))
        return GateDecision.ALLOW
    with patch("agents.followup.followup_agent.get_state_service",
               return_value=state), \
         patch("agents.followup.followup_agent.fetch_thread_replied",
               AsyncMock(return_value=False)), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({
            "task": "event:cron.daily.10:00",
            "context": {"event": {"trigger": "cron.daily.10:00", "data": {}}},
            "trace_id": "tr", "conversation_id": "",
        })
    assert ("critical", "followup_due_5d") in emit_calls


@pytest.mark.asyncio
async def test_cron_skips_already_replied_threads(agent):
    six_days_ago = time.time() - 6 * 86400
    queue = [{"thread_id": "t1", "client_email": "x@y.com",
              "sent_at_ts": six_days_ago, "project_id": "p1"}]
    state = AsyncMock(get=AsyncMock(return_value=queue), set=AsyncMock())
    emit_calls = []
    async def fake_emit(*a, **k): emit_calls.append(a)
    with patch("agents.followup.followup_agent.get_state_service",
               return_value=state), \
         patch("agents.followup.followup_agent.fetch_thread_replied",
               AsyncMock(return_value=True)), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({
            "task": "event", "context": {"event": {"trigger": "cron.daily.10:00", "data": {}}},
            "trace_id": "tr", "conversation_id": "",
        })
    assert emit_calls == []


@pytest.mark.asyncio
async def test_dedup_key_is_per_thread(agent):
    six_days_ago = time.time() - 6 * 86400
    queue = [{"thread_id": "t-X", "client_email": "x@y.com",
              "sent_at_ts": six_days_ago, "project_id": "p1"}]
    state = AsyncMock(get=AsyncMock(return_value=queue), set=AsyncMock())
    captured = []
    async def fake_emit(severity, reason, dedup_key, payload):
        captured.append(dedup_key)
        return GateDecision.ALLOW
    with patch("agents.followup.followup_agent.get_state_service",
               return_value=state), \
         patch("agents.followup.followup_agent.fetch_thread_replied",
               AsyncMock(return_value=False)), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({
            "task": "event", "context": {"event": {"trigger": "cron.daily.10:00", "data": {}}},
            "trace_id": "tr", "conversation_id": "",
        })
    assert captured == ["thread:t-X"]
```

```bash
pytest tests/agents/test_followup.py -v   # 4 passed
git add agents/followup/ tests/agents/test_followup.py
git commit -m "feat(sp5): add FollowupAgent"
```

---

### Task 6.3: HealthGuardianAgent

**Files:**
- Create: `agents/health_guardian/__init__.py`, `agents/health_guardian/health_guardian_agent.py`
- Test: `tests/agents/test_health_guardian.py`

**Class shape:**
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

**Journal format (per charter K3):** one line per day, format:
```
2026-04-26: sleep=Y commitments=Y relationship=N
2026-04-25: sleep=N commitments=Y relationship=Y
```

**State schema:**
- `agent_state(health_guardian, "streak:sleep_n")` = integer
- `agent_state(health_guardian, "streak:commitments_n")` = integer
- `agent_state(health_guardian, "streak:relationship_n")` = integer
- `agent_state(health_guardian, "intervention_history")` = list of `{at_ts, type, dedup_key}`

**process() flow:**
1. Read journal file via `Path(self.JOURNAL_PATH).read_text()` — handle missing file gracefully (info log, return early).
2. Parse the last 7 days of entries.
3. Compute streaks via `_compute_streaks(entries) -> dict[dim, int]`.
4. Persist streaks to agent_state.
5. If any streak ≥ 3:
   - Read `intervention_history`; pick an intervention type that wasn't used in last 7d.
   - LLM call (Claude Sonnet 4.6 — Charter Rule 2 override; intervention quality matters and frequency is rare; document inline) to draft a personalized message.
   - `await self.emit("critical", "health_3n_streak", f"streak:{dim}:{week_iso}", payload)`.
   - Append to `intervention_history`.
6. If no streak ≥ 3: emit `info` summarizing the current streaks (so user can see "everything green").

**Tests** (5 minimum). Skeletons:

```python
# tests/agents/test_health_guardian.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest
from agents.health_guardian.health_guardian_agent import (
    HealthGuardianAgent, _parse_journal, _compute_streaks,
)
from services.proactive_engine import GateDecision


@pytest.fixture(autouse=True)
def _reset_proactive_engine_singleton():
    import services.proactive_engine as mod
    mod._instance = None
    yield
    mod._instance = None


@pytest.fixture
def agent():
    return HealthGuardianAgent()


def test_parses_journal_entries():
    text = (
        "2026-04-26: sleep=Y commitments=N relationship=Y\n"
        "2026-04-25: sleep=N commitments=N relationship=Y\n"
    )
    entries = _parse_journal(text)
    assert len(entries) == 2
    assert entries[0]["sleep"] == "Y"
    assert entries[1]["commitments"] == "N"


def test_compute_streaks_counts_consecutive_ns():
    entries = [
        {"date": "2026-04-26", "sleep": "N", "commitments": "Y", "relationship": "Y"},
        {"date": "2026-04-25", "sleep": "N", "commitments": "Y", "relationship": "Y"},
        {"date": "2026-04-24", "sleep": "N", "commitments": "Y", "relationship": "Y"},
        {"date": "2026-04-23", "sleep": "Y", "commitments": "Y", "relationship": "N"},
    ]
    streaks = _compute_streaks(entries)
    assert streaks["sleep"] == 3
    assert streaks["commitments"] == 0
    assert streaks["relationship"] == 0


@pytest.mark.asyncio
async def test_streak_3_fires_critical_with_whitelisted_reason(agent, tmp_path):
    journal = tmp_path / "h.md"
    journal.write_text(
        "2026-04-26: sleep=N commitments=Y relationship=Y\n"
        "2026-04-25: sleep=N commitments=Y relationship=Y\n"
        "2026-04-24: sleep=N commitments=Y relationship=Y\n"
    )
    agent.JOURNAL_PATH = str(journal)
    emit_calls = []
    async def fake_emit(severity, reason, dedup_key, payload):
        emit_calls.append((severity, reason))
        return GateDecision.ALLOW
    state = AsyncMock(get=AsyncMock(return_value=[]), set=AsyncMock())
    with patch("agents.health_guardian.health_guardian_agent.get_state_service",
               return_value=state), \
         patch("agents.health_guardian.health_guardian_agent._draft_intervention",
               AsyncMock(return_value="rest up")), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({"task": "event", "context": {"event": {}},
                              "trace_id": "tr", "conversation_id": ""})
    assert ("critical", "health_3n_streak") in emit_calls


@pytest.mark.asyncio
async def test_streak_below_3_emits_info_not_critical(agent, tmp_path):
    journal = tmp_path / "h.md"
    journal.write_text(
        "2026-04-26: sleep=N commitments=Y relationship=Y\n"
        "2026-04-25: sleep=N commitments=Y relationship=Y\n"
        "2026-04-24: sleep=Y commitments=Y relationship=Y\n"
    )
    agent.JOURNAL_PATH = str(journal)
    emit_calls = []
    async def fake_emit(severity, reason, dedup_key, payload):
        emit_calls.append((severity, reason))
        return GateDecision.ALLOW
    state = AsyncMock(get=AsyncMock(return_value=[]), set=AsyncMock())
    with patch("agents.health_guardian.health_guardian_agent.get_state_service",
               return_value=state), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({"task": "event", "context": {"event": {}},
                              "trace_id": "tr", "conversation_id": ""})
    assert all(sev != "critical" for sev, _ in emit_calls)


@pytest.mark.asyncio
async def test_dedup_per_week_iso(agent, tmp_path):
    journal = tmp_path / "h.md"
    journal.write_text(
        "2026-04-26: sleep=N commitments=Y relationship=Y\n"
        "2026-04-25: sleep=N commitments=Y relationship=Y\n"
        "2026-04-24: sleep=N commitments=Y relationship=Y\n"
    )
    agent.JOURNAL_PATH = str(journal)
    captured = []
    async def fake_emit(severity, reason, dedup_key, payload):
        captured.append(dedup_key)
        return GateDecision.ALLOW
    state = AsyncMock(get=AsyncMock(return_value=[]), set=AsyncMock())
    with patch("agents.health_guardian.health_guardian_agent.get_state_service",
               return_value=state), \
         patch("agents.health_guardian.health_guardian_agent._draft_intervention",
               AsyncMock(return_value="x")), \
         patch.object(agent, "emit", fake_emit):
        await agent.process({"task": "event", "context": {"event": {}},
                              "trace_id": "tr", "conversation_id": ""})
    # Dedup must be of the form "streak:<dim>:<YYYY-Www>"
    assert any(":W" in k for k in captured)
```

```bash
pytest tests/agents/test_health_guardian.py -v   # 5 passed
git add agents/health_guardian/ tests/agents/test_health_guardian.py
git commit -m "feat(sp5): add HealthGuardianAgent

Per spec §4.6. Journal-only inputs (charter K3 mirrors). 3-N streak
in any dimension fires critical via Claude-drafted intervention.
Charter Rule 2 override (Claude not Qwen) for intervention drafting —
quality matters, frequency is rare."
```

---

### Task 6.4: Verify Chunk 6 end-to-end

- [ ] **Step 1: Full agent + script suite for Chunk 6**

```bash
pytest tests/agents/test_reply_triage.py \
       tests/agents/test_followup.py \
       tests/agents/test_health_guardian.py \
       tests/scripts/test_calibrate_reply_triage.py -v --tb=short
```

Expected: **16 passed** (5 Reply Triage + 4 Followup + 5 Health Guardian + 2 calibration). Adjust if you wrote extra tests.

- [ ] **Step 2: Verify v1 agent tests still pass**

```bash
pytest tests/agents/ \
  --ignore=tests/agents/test_reply_triage.py \
  --ignore=tests/agents/test_followup.py \
  --ignore=tests/agents/test_health_guardian.py \
  --ignore=tests/agents/test_event_driven_agent.py \
  --tb=short
```

Expected: all v1 agent tests still pass.

- [ ] **Step 3: Tag chunk done**

```bash
git tag claude/sp5-chunk-6-done
```

---

**End of Chunk 6.** The 3 K1 survivors are live. Reply Triage gates the SP5 exit; calibration script can be run on day 1 to determine Qwen-vs-Claude. Followup + Health Guardian round out the personal-productivity surface that survives K1.

---

## Chunk 7: Cuttable agents (Meeting Prep, Funded Watcher, Warm Network)

These 3 agents follow the same canonical EventDrivenAgent pattern from Chunks 4 + 6. All three are listed in charter §6 row 6 / row 2 as deletable on K1 fire. Plan format: per-agent class shape + critical implementation notes + 3 mandatory tests each.

### Task 7.1: MeetingPrepAgent

**Files:**
- Create: `agents/meeting_prep/__init__.py`, `agents/meeting_prep/meeting_prep_agent.py`
- Test: `tests/agents/test_meeting_prep.py`

**Class shape:**
```python
class MeetingPrepAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_activities", "cruz_projects_docs"]
    TRIGGERS         = ["webhook.google-calendar"]
    CRITICAL_REASONS = {}   # never fires critical — meeting-prep noise isn't worth interruption
```

**process() flow:**
1. Read `event["data"]` from `input["context"]["event"]["data"]`. Calendar webhook payload contains `headers` and `resource_state` (per Chunk 4 dispatch shape).
2. Call `_fetch_upcoming_events(window_minutes=35)` via `services.google_calendar` (existing v1 module — confirm path; likely `services.calendar`). Returns events starting in 25–35min from now.
3. For each event:
   - Build dedup_key = `f"meeting:{event_id}"`.
   - Read attendee threads via Gmail (use `agents.reply_triage.gmail_client.fetch_recent_with_attendee` — add helper).
   - Read Notion meeting notes via `services.notion` (existing v1).
   - Compose Telegram body via Qwen.
   - `await self.emit("warn", None, dedup_key, payload)`.
4. Record activity per Rule 3.

**Tests** (3 minimum):
1. `test_filters_to_25_to_35min_window` — events outside window aren't emitted.
2. `test_dedup_per_event_id` — same event_id → same dedup.
3. `test_emits_at_warn_never_critical` — even with empty CRITICAL_REASONS, no critical attempted.

```bash
pytest tests/agents/test_meeting_prep.py -v   # 3 passed
git add agents/meeting_prep/ tests/agents/test_meeting_prep.py
git commit -m "feat(sp5): add MeetingPrepAgent

Per spec §4.3. warn-only (CRITICAL_REASONS empty); 25-35min event window;
attendee thread + Notion notes context."
```

---

### Task 7.2: FundedWatcherAgent

**Files:**
- Create: `agents/funded_watcher/__init__.py`, `agents/funded_watcher/funded_watcher_agent.py`
- Test: `tests/agents/test_funded_watcher.py`

**Class shape:**
```python
class FundedWatcherAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_activities", "cruz_domain_knowledge"]
    TRIGGERS         = ["cron.daily.08:00"]
    CRITICAL_REASONS = {}

    RSS_FEEDS = [
        "https://techcrunch.com/feed/",
        "https://yourstory.com/rss",
        "https://inc42.com/feed/",
        "https://hnrss.org/newest?points=100",
    ]
```

**process() flow:**
1. Pull each feed via `feedparser` (add to requirements; small dep). Wrap in `_fetch_rss(url) -> list[dict]` for monkey-patching.
2. Filter out articles whose URL is in `agent_state(funded_watcher, "seen_articles")` (a set with TTL 90d).
3. For new articles: LLM (Qwen) `_match_icp(article, user_offering)` → bool. Skip non-matches.
4. For matches: `await self.emit("warn", None, f"article:{url}", payload_with_summary)`.
5. Update `seen_articles` set with TTL refresh.
6. Record activity per Rule 3.

**Pre-SP4 graceful degradation:** No Crunchbase scrape. RSS-only. If SP4 ships later, add `_scrape_crunchbase()` helper — no agent class change needed.

**Tests** (3 minimum):
1. `test_skips_seen_articles`
2. `test_emits_warn_for_icp_match`
3. `test_dedup_per_url`

```bash
pytest tests/agents/test_funded_watcher.py -v   # 3 passed
git add agents/funded_watcher/ tests/agents/test_funded_watcher.py
git commit -m "feat(sp5): add FundedWatcherAgent (RSS-only pre-SP4)"
```

---

### Task 7.3: WarmNetworkAgent (stub-mode pre-SP4)

**Files:**
- Create: `agents/warm_network/__init__.py`, `agents/warm_network/warm_network_agent.py`
- Test: `tests/agents/test_warm_network.py`

**Class shape:**
```python
class WarmNetworkAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_activities", "cruz_user_patterns"]
    TRIGGERS         = ["cron.weekly.monday.09:00"]
    CRITICAL_REASONS = {}
```

**process() flow:**

*Pre-SP4 (current state):* return AgentOutput(success=True, result="sp4_not_ready", ...) with a single warning log. No emit. No state writes. No external calls.

```python
async def process(self, input):
    if not _sp4_browser_available():
        logger.warning("[%s] WarmNetworkAgent stub-mode: SP4 browser not ready",
                       input["trace_id"])
        return AgentOutput(success=True, result="stub", agent=self.name,
                           duration_ms=0, tokens_used=0, error=None,
                           requires_approval=False, approval_prompt=None)
    # Post-SP4 path — see TODO below
    ...

def _sp4_browser_available() -> bool:
    """Probe whether SP4's services/browser.py exists and exposes get_browser_service()."""
    try:
        from services.browser import get_browser_service  # noqa: F401
        return True
    except ImportError:
        return False
```

*Post-SP4 (TODO when SP4 lands):* full implementation per spec §4.5 — rank LinkedIn contacts by recency-of-activity + signal-of-openness + staleness-of-last-Gmail-contact; emit warn with `last_nudge:<contact_id>` dedup.

**Tests** (3 minimum):
1. `test_stub_mode_returns_success_no_emit` — pre-SP4 path
2. `test_stub_mode_does_not_call_state_or_router`
3. `test_post_sp4_path_marker` — placeholder skipped test (`pytest.mark.skip(reason="SP4 not yet shipped")`) for the real ranking logic. When SP4 ships, unskip + flesh out.

```bash
pytest tests/agents/test_warm_network.py -v   # 2 passed, 1 skipped
git add agents/warm_network/ tests/agents/test_warm_network.py
git commit -m "feat(sp5): add WarmNetworkAgent in stub mode pre-SP4

Per spec §4.5 + §1.2. Pre-SP4: returns success+stub, no state/router
calls. Real LinkedIn-driven ranking lands when SP4 ships."
```

---

### Task 7.4: Verify Chunk 7 end-to-end

- [ ] **Step 1: Full agent suite for Chunk 7**

```bash
pytest tests/agents/test_meeting_prep.py \
       tests/agents/test_funded_watcher.py \
       tests/agents/test_warm_network.py -v --tb=short
```

Expected: **8 passed + 1 skipped** (3 + 3 + 2 + 1 skip).

- [ ] **Step 2: Verify all SP5 agent tests still pass together**

```bash
pytest tests/agents/test_event_driven_agent.py \
       tests/agents/test_reply_triage.py \
       tests/agents/test_followup.py \
       tests/agents/test_health_guardian.py \
       tests/agents/test_meeting_prep.py \
       tests/agents/test_funded_watcher.py \
       tests/agents/test_warm_network.py --tb=short
```

Expected: 12 (event_driven) + 5 (reply_triage) + 4 (followup) + 5 (health_guardian) + 3 + 3 + 2 = **34 passed + 1 skipped**.

- [ ] **Step 3: Tag chunk done**

```bash
git tag claude/sp5-chunk-7-done
```

---

**End of Chunk 7.** All 6 SP5 agents live. Pre-SP4 graceful degradation in place for Funded Watcher (RSS-only) and Warm Network (stub mode). K1 cut surface confirmed — deletion of `agents/meeting_prep/`, `agents/funded_watcher/`, `agents/warm_network/` and their tests reduces SP5 to the 3 K1 survivors with zero refactoring of remaining code.

---

## Chunk 8: ARQ wiring, file watcher, maintenance crons, soak, exit gate execution

This chunk wires every SP5 component into the ARQ worker (cron schedules + dispatch task registration), adds the file watcher for the health journal, the maintenance crons (Gmail watch resubscribe, agent_state cleanup), and runs the SP5 exit gate.

### Task 8.1: Implement file watcher service

**Files:**
- Create: `services/file_watcher.py`
- Test: `tests/services/test_file_watcher.py`

The Health Guardian agent declares trigger `filewatch.health_journal`. We need a watcher that emits this trigger when `docs/personal/health-journal.md` is modified.

**Implementation approach:** use `watchdog` (add to requirements; macOS native `fsevents` backend). Watcher runs as a long-lived task started from `arq_worker.WorkerSettings.on_startup`.

- [ ] **Step 1: Add `watchdog>=3.0` to `requirements.txt`** (verify it's not already present).

- [ ] **Step 2: Implement `services/file_watcher.py`**

```python
# services/file_watcher.py
"""
FileWatcher — emits SP5 file-watch triggers when monitored files change.

Currently monitors:
  docs/personal/health-journal.md → trigger "filewatch.health_journal"

Architecture:
  - Started from arq_worker.WorkerSettings.on_startup
  - Uses watchdog.Observer (fsevents on macOS, inotify on Linux)
  - On modification, enqueues dispatch_event_to_agent for every agent
    registered against the trigger in EVENT_REGISTRY.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from agents.event_driven_agent import EVENT_REGISTRY

logger = logging.getLogger("cruz.services.file_watcher")


WATCH_MAP = {
    "docs/personal/health-journal.md": "filewatch.health_journal",
}


class _Handler(FileSystemEventHandler):
    def __init__(self, path: str, trigger: str, loop: asyncio.AbstractEventLoop) -> None:
        self.path = Path(path).resolve()
        self.trigger = trigger
        self.loop = loop

    def on_modified(self, event):
        if Path(event.src_path).resolve() != self.path:
            return
        # Hop back onto the asyncio loop to enqueue
        asyncio.run_coroutine_threadsafe(
            _enqueue_for_trigger(self.trigger),
            self.loop,
        )


async def _enqueue_for_trigger(trigger: str) -> None:
    classes = EVENT_REGISTRY.get(trigger, [])
    if not classes:
        return
    from workers.tasks.webhook_tasks import _get_arq_pool
    pool = await _get_arq_pool()
    for cls in classes:
        await pool.enqueue_job(
            "dispatch_event_to_agent",
            cls.__module__, cls.__name__,
            {"trigger": trigger, "data": {"source": "filewatch"}},
        )


_observer: Optional[Observer] = None


def start_file_watcher(loop: asyncio.AbstractEventLoop) -> None:
    """Start the watchdog Observer for all WATCH_MAP entries."""
    global _observer
    if _observer is not None:
        return
    _observer = Observer()
    for path_str, trigger in WATCH_MAP.items():
        p = Path(path_str)
        if not p.exists():
            logger.warning("file_watcher: path missing, will watch parent: %s", p)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
        handler = _Handler(str(p), trigger, loop)
        _observer.schedule(handler, str(p.parent), recursive=False)
    _observer.start()
    logger.info("file_watcher started for: %s", list(WATCH_MAP))


def stop_file_watcher() -> None:
    global _observer
    if _observer is not None:
        _observer.stop()
        _observer.join(timeout=2.0)
        _observer = None
```

- [ ] **Step 3: Tests (3 minimum)**

```python
# tests/services/test_file_watcher.py
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from services.file_watcher import (
    start_file_watcher, stop_file_watcher, WATCH_MAP,
)


@pytest.mark.asyncio
async def test_modification_enqueues_dispatch(tmp_path, monkeypatch):
    """Touching the watched file enqueues dispatch_event_to_agent."""
    f = tmp_path / "h.md"
    f.write_text("init\n")
    monkeypatch.setitem(WATCH_MAP, str(f), "filewatch.health_journal")
    # Register a fake agent
    from agents.event_driven_agent import register_event_agent, clear_event_registry, EventDrivenAgent
    clear_event_registry()
    class _FW(EventDrivenAgent):
        TRIGGERS = ["filewatch.health_journal"]
        async def process(self, input): return None
    register_event_agent(_FW)

    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("services.file_watcher._get_arq_pool",
               new=AsyncMock(return_value=fake_pool)):
        loop = asyncio.get_event_loop()
        start_file_watcher(loop)
        try:
            f.write_text("changed\n")
            await asyncio.sleep(0.5)  # let watchdog fire
        finally:
            stop_file_watcher()
            clear_event_registry()
    fake_pool.enqueue_job.assert_awaited()


def test_watch_map_includes_health_journal():
    assert "docs/personal/health-journal.md" in WATCH_MAP
    assert WATCH_MAP["docs/personal/health-journal.md"] == "filewatch.health_journal"


def test_start_is_idempotent(monkeypatch):
    """Calling start_file_watcher twice doesn't crash or double-observe."""
    monkeypatch.setattr("services.file_watcher.WATCH_MAP", {})
    loop = asyncio.new_event_loop()
    try:
        start_file_watcher(loop)
        start_file_watcher(loop)
    finally:
        stop_file_watcher()
        loop.close()
```

- [ ] **Step 4: Commit**

```bash
git add services/file_watcher.py tests/services/test_file_watcher.py requirements.txt
git commit -m "feat(sp5): add FileWatcher for filewatch.health_journal trigger"
```

---

### Task 8.2: Maintenance crons (Gmail watch resubscribe, agent_state cleanup)

**Files:**
- Create: `workers/tasks/maintenance_tasks.py`
- Test: `tests/workers/test_maintenance_tasks.py`

Three maintenance tasks live here:
1. `gmail_watch_resubscribe()` — daily 6am, re-registers Gmail watch (Google requires every 7d).
2. `agent_state_cleanup()` — daily 4:30am, deletes expired rows.
3. `gmail_poll_fallback()` — every 5min, polls Gmail for new messages and dispatches `webhook.gmail.new_message` for IDs not yet seen (covers Gmail-watch expiry windows). Uses `agent_state(_gmail_poll, "last_seen_ids")` (set, TTL 24h) for dedup.

- [ ] **Step 1: Implement**

```python
# workers/tasks/maintenance_tasks.py
"""
SP5 maintenance crons:

  cron.daily.06:00  gmail_watch_resubscribe   — Google requires re-watch /7d
  cron.daily.04:30  agent_state_cleanup       — delete expired rows
  cron.5min.gmail_poll                        — fallback for Gmail-watch lapses
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from agents.event_driven_agent import EVENT_REGISTRY
from agents.reply_triage.gmail_client import list_recent_inbound
from services.agent_state import get_state_service
from workers.tasks.webhook_tasks import _get_arq_pool

logger = logging.getLogger("cruz.workers.maintenance")


async def gmail_watch_resubscribe(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Re-register Gmail watch on the user's mailbox."""
    try:
        from agents.reply_triage.gmail_client import _get_service
        svc = _get_service()
        topic = os.environ.get("GMAIL_PUBSUB_TOPIC", "")
        if not topic:
            logger.warning("GMAIL_PUBSUB_TOPIC not set; skipping resubscribe")
            return {"success": False, "reason": "no_topic"}
        result = svc.users().watch(
            userId="me",
            body={"topicName": topic, "labelIds": ["INBOX"]},
        ).execute()
        return {"success": True, "history_id": result.get("historyId"),
                "expiration": result.get("expiration")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("gmail_watch_resubscribe failed: %s", exc)
        return {"success": False, "error": str(exc)}


async def agent_state_cleanup(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Delete agent_state rows whose expires_at has passed."""
    deleted = await get_state_service().cleanup_expired()
    return {"success": True, "deleted": deleted}


async def gmail_poll_fallback(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Pull last 20 inbound message IDs; dispatch new ones via EVENT_REGISTRY."""
    state = get_state_service()
    seen: list[str] = await state.get("_gmail_poll", "last_seen_ids", default=[])
    seen_set = set(seen)
    try:
        ids = await list_recent_inbound(limit=20)
    except Exception as exc:  # noqa: BLE001
        logger.warning("gmail_poll_fallback list failed: %s", exc)
        return {"success": False, "error": str(exc)}

    new_ids = [i for i in ids if i not in seen_set]
    if not new_ids:
        return {"success": True, "new": 0}

    classes = EVENT_REGISTRY.get("webhook.gmail.new_message", [])
    if classes:
        pool = await _get_arq_pool()
        for msg_id in new_ids:
            for cls in classes:
                await pool.enqueue_job(
                    "dispatch_event_to_agent",
                    cls.__module__, cls.__name__,
                    {"trigger": "webhook.gmail.new_message",
                     "data": {"message_id": msg_id, "source": "poll"}},
                )

    # Store the last 100 IDs (rolling window) with 24h TTL
    merged = (list(new_ids) + list(seen))[:100]
    await state.set("_gmail_poll", "last_seen_ids", merged, ttl_seconds=86400)
    return {"success": True, "new": len(new_ids)}
```

- [ ] **Step 2: Tests (4 minimum)**

```python
# tests/workers/test_maintenance_tasks.py
from unittest.mock import AsyncMock, patch
import pytest
from workers.tasks.maintenance_tasks import (
    gmail_watch_resubscribe, agent_state_cleanup, gmail_poll_fallback,
)


@pytest.mark.asyncio
async def test_state_cleanup_returns_deleted_count():
    fake_state = AsyncMock()
    fake_state.cleanup_expired = AsyncMock(return_value=42)
    with patch("workers.tasks.maintenance_tasks.get_state_service",
               return_value=fake_state):
        result = await agent_state_cleanup({})
    assert result == {"success": True, "deleted": 42}


@pytest.mark.asyncio
async def test_gmail_resubscribe_skips_when_topic_unset(monkeypatch):
    monkeypatch.delenv("GMAIL_PUBSUB_TOPIC", raising=False)
    result = await gmail_watch_resubscribe({})
    assert result["success"] is False
    assert result["reason"] == "no_topic"


@pytest.mark.asyncio
async def test_gmail_poll_dispatches_only_new_ids():
    from agents.event_driven_agent import (
        register_event_agent, clear_event_registry, EventDrivenAgent,
    )
    clear_event_registry()
    class _RT(EventDrivenAgent):
        TRIGGERS = ["webhook.gmail.new_message"]
        async def process(self, input): return None
    register_event_agent(_RT)

    fake_state = AsyncMock()
    fake_state.get = AsyncMock(return_value=["seen-1", "seen-2"])
    fake_state.set = AsyncMock()
    fake_pool = AsyncMock()
    fake_pool.enqueue_job = AsyncMock()
    with patch("workers.tasks.maintenance_tasks.get_state_service",
               return_value=fake_state), \
         patch("workers.tasks.maintenance_tasks.list_recent_inbound",
               AsyncMock(return_value=["seen-1", "new-3", "new-4"])), \
         patch("workers.tasks.maintenance_tasks._get_arq_pool",
               new=AsyncMock(return_value=fake_pool)):
        result = await gmail_poll_fallback({})
    clear_event_registry()
    assert result["new"] == 2
    # Should enqueue exactly twice (new-3, new-4)
    assert fake_pool.enqueue_job.await_count == 2


@pytest.mark.asyncio
async def test_gmail_poll_no_new_returns_zero():
    fake_state = AsyncMock()
    fake_state.get = AsyncMock(return_value=["a", "b"])
    fake_state.set = AsyncMock()
    with patch("workers.tasks.maintenance_tasks.get_state_service",
               return_value=fake_state), \
         patch("workers.tasks.maintenance_tasks.list_recent_inbound",
               AsyncMock(return_value=["a", "b"])):
        result = await gmail_poll_fallback({})
    assert result == {"success": True, "new": 0}
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/workers/test_maintenance_tasks.py -v   # 4 passed
git add workers/tasks/maintenance_tasks.py tests/workers/test_maintenance_tasks.py
git commit -m "feat(sp5): add maintenance crons (gmail resubscribe, state cleanup, gmail poll)"
```

---

### Task 8.3: Wire everything into `workers/arq_worker.py`

This is the integration step that makes SP5 actually run when ARQ starts. Adds:
- `dispatch_event_to_agent`, `dispatch_event_to_handler` to functions
- All maintenance tasks to functions
- All cron schedules per spec §6 trigger inventory
- Auto-import of every SP5 agent + handler module so `EVENT_REGISTRY` and `HANDLER_REGISTRY` populate at boot
- Start the file watcher in `on_startup`

- [ ] **Step 1: Modify `workers/arq_worker.py`**

```python
# workers/arq_worker.py
"""ARQ worker — v1 + SP5 cron schedules and dispatch tasks."""

from __future__ import annotations

import asyncio
import os

from arq import cron
from arq.connections import RedisSettings

from services.alerts import get_alert_service
from workers.tasks.backup_tasks import run_backup
from workers.tasks.pulse_tasks import run_pulse
from workers.tasks.raw_tasks import run_raw
from workers.tasks.reach_tasks import run_reach
from workers.tasks.webhook_tasks import (
    process_github_webhook,
    process_google_calendar_webhook,
    process_vercel_webhook,
)

# ─── SP5 imports ────────────────────────────────────────────────
from workers.tasks.dispatch import (
    dispatch_event_to_agent,
    dispatch_event_to_handler,
    register_event_handler,
)
from workers.tasks.gmail_webhook_tasks import process_gmail_webhook
from workers.tasks.maintenance_tasks import (
    gmail_watch_resubscribe,
    agent_state_cleanup,
    gmail_poll_fallback,
)

# Importing these populates EVENT_REGISTRY via module-level
# register_event_agent calls (added at the bottom of each agent module).
import agents.reply_triage.reply_triage_agent  # noqa: F401
import agents.followup.followup_agent          # noqa: F401
import agents.meeting_prep.meeting_prep_agent  # noqa: F401
import agents.funded_watcher.funded_watcher_agent  # noqa: F401
import agents.warm_network.warm_network_agent  # noqa: F401
import agents.health_guardian.health_guardian_agent  # noqa: F401

# Importing handler modules populates HANDLER_REGISTRY
import workers.handlers.daily_briefing               # noqa: F401
import workers.handlers.expense_auditor              # noqa: F401
import workers.handlers.portfolio_watcher            # noqa: F401
import workers.handlers.tax_helper                   # noqa: F401
import workers.handlers.relationship_maintenance     # noqa: F401
import workers.handlers.travel_planner               # noqa: F401

# Cron-triggered handlers register here (webhook-triggered ones
# self-register at module bottom).
register_event_handler("workers.handlers.daily_briefing",           ["cron.daily.07:00"])
register_event_handler("workers.handlers.expense_auditor",          ["cron.monthly.1st.09:00"])
register_event_handler("workers.handlers.portfolio_watcher",        ["cron.weekly.friday.17:00"])
register_event_handler("workers.handlers.tax_helper",               ["cron.quarterly.1st.10:00"])
register_event_handler("workers.handlers.relationship_maintenance", ["cron.weekly.sunday.18:00"])

# ─── ARQ task wrappers for cron-triggered handlers ──────────────
# ARQ cron jobs need a callable, not a string trigger. Wrap each
# handler dispatch in a tiny coroutine that arq can invoke directly.

async def fire_daily_briefing(ctx):
    return await dispatch_event_to_handler(
        ctx, "workers.handlers.daily_briefing",
        {"trigger": "cron.daily.07:00", "data": {}},
    )

async def fire_expense_auditor(ctx):
    return await dispatch_event_to_handler(
        ctx, "workers.handlers.expense_auditor",
        {"trigger": "cron.monthly.1st.09:00", "data": {}},
    )

async def fire_portfolio_watcher(ctx):
    return await dispatch_event_to_handler(
        ctx, "workers.handlers.portfolio_watcher",
        {"trigger": "cron.weekly.friday.17:00", "data": {}},
    )

async def fire_tax_helper(ctx):
    return await dispatch_event_to_handler(
        ctx, "workers.handlers.tax_helper",
        {"trigger": "cron.quarterly.1st.10:00", "data": {}},
    )

async def fire_relationship_maintenance(ctx):
    return await dispatch_event_to_handler(
        ctx, "workers.handlers.relationship_maintenance",
        {"trigger": "cron.weekly.sunday.18:00", "data": {}},
    )


# ─── ARQ task wrappers for cron-triggered AGENTS ────────────────
# Same pattern — use dispatch_event_to_agent.

from agents.followup.followup_agent import FollowupAgent
from agents.funded_watcher.funded_watcher_agent import FundedWatcherAgent
from agents.warm_network.warm_network_agent import WarmNetworkAgent
from agents.health_guardian.health_guardian_agent import HealthGuardianAgent

async def fire_followup_cron(ctx):
    return await dispatch_event_to_agent(
        ctx, FollowupAgent.__module__, FollowupAgent.__name__,
        {"trigger": "cron.daily.10:00", "data": {}})

async def fire_funded_watcher_cron(ctx):
    return await dispatch_event_to_agent(
        ctx, FundedWatcherAgent.__module__, FundedWatcherAgent.__name__,
        {"trigger": "cron.daily.08:00", "data": {}})

async def fire_warm_network_cron(ctx):
    return await dispatch_event_to_agent(
        ctx, WarmNetworkAgent.__module__, WarmNetworkAgent.__name__,
        {"trigger": "cron.weekly.monday.09:00", "data": {}})

async def fire_health_guardian_cron(ctx):
    return await dispatch_event_to_agent(
        ctx, HealthGuardianAgent.__module__, HealthGuardianAgent.__name__,
        {"trigger": "cron.daily.21:00", "data": {}})


async def on_startup(ctx):
    """ARQ startup hook — start the file watcher."""
    from services.file_watcher import start_file_watcher
    start_file_watcher(asyncio.get_event_loop())


async def on_shutdown(ctx):
    from services.file_watcher import stop_file_watcher
    stop_file_watcher()


async def on_job_end(ctx: dict) -> None:
    if ctx.get("success", True):
        return
    fn = ctx.get("function", "unknown")
    job_id = ctx.get("job_id", "?")
    exc = ctx.get("exception")
    try:
        await get_alert_service().notify(
            "critical",
            f"ARQ job failed: {fn}",
            f"job_id={job_id} function={fn} error={exc}",
        )
    except Exception:
        pass


class WorkerSettings:
    functions = [
        # v1
        run_pulse, run_raw, run_reach, run_backup,
        process_github_webhook, process_vercel_webhook,
        process_google_calendar_webhook,
        # SP5 — dispatch
        dispatch_event_to_agent, dispatch_event_to_handler,
        process_gmail_webhook,
        # SP5 — maintenance
        gmail_watch_resubscribe, agent_state_cleanup, gmail_poll_fallback,
        # SP5 — cron fire wrappers
        fire_daily_briefing, fire_expense_auditor, fire_portfolio_watcher,
        fire_tax_helper, fire_relationship_maintenance,
        fire_followup_cron, fire_funded_watcher_cron,
        fire_warm_network_cron, fire_health_guardian_cron,
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    after_job_end = on_job_end

    cron_jobs = [
        # v1
        cron(run_reach,  hour=2, minute=0),
        cron(run_raw,    hour=3, minute=0),
        cron(run_backup, hour=4, minute=0),
        cron(run_pulse,  hour=6, minute=0),
        # SP5 — agent crons
        cron(fire_funded_watcher_cron,    hour=8,  minute=0),  # daily
        cron(fire_followup_cron,           hour=10, minute=0),  # daily
        cron(fire_health_guardian_cron,    hour=21, minute=0),  # daily
        cron(fire_warm_network_cron,       weekday="mon", hour=9,  minute=0),
        # SP5 — handler crons
        cron(fire_daily_briefing,          hour=7,  minute=0),   # daily
        cron(fire_portfolio_watcher,       weekday="fri", hour=17, minute=0),
        cron(fire_relationship_maintenance, weekday="sun", hour=18, minute=0),
        cron(fire_expense_auditor,         day=1, hour=9,  minute=0),  # monthly
        cron(fire_tax_helper,              month={1, 4, 7, 10}, day=1, hour=10, minute=0),
        # SP5 — maintenance
        cron(gmail_watch_resubscribe,      hour=6,  minute=0),
        cron(agent_state_cleanup,          hour=4,  minute=30),
        cron(gmail_poll_fallback,          minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
    ]

    redis_settings = RedisSettings.from_dsn(
        os.environ.get("REDIS_URL", "redis://localhost:6379")
    )
```

- [ ] **Step 2: Smoke test the worker module loads cleanly**

```bash
python -c "from workers.arq_worker import WorkerSettings; print(len(WorkerSettings.functions), 'functions'); print(len(WorkerSettings.cron_jobs), 'cron jobs')"
```

Expected: prints function/cron counts (no ImportError, no register-time failures).

- [ ] **Step 3: Verify EVENT_REGISTRY + HANDLER_REGISTRY populated**

```bash
python -c "
from workers.arq_worker import WorkerSettings
from agents.event_driven_agent import EVENT_REGISTRY
from workers.tasks.dispatch import HANDLER_REGISTRY
print('EVENT_REGISTRY:', dict(EVENT_REGISTRY))
print('HANDLER_REGISTRY:', dict(HANDLER_REGISTRY))
"
```

Expected: each of the SP5 agent classes appears under its declared TRIGGERS; each handler module path appears under its trigger.

- [ ] **Step 4: Commit**

```bash
git add workers/arq_worker.py
git commit -m "feat(sp5): wire SP5 agents + handlers + crons + file watcher into ARQ worker

Per spec §6 trigger inventory. Imports auto-register every SP5 agent
into EVENT_REGISTRY and every handler into HANDLER_REGISTRY at boot.
File watcher starts via on_startup hook. All cron schedules from spec
§6 wired."
```

---

### Task 8.4: End-to-end integration test

- [ ] **Step 1: Run the entire SP5 test surface**

```bash
pytest tests/services/test_agent_state.py \
       tests/services/test_proactive_engine.py \
       tests/services/test_notification_router.py \
       tests/services/test_file_watcher.py \
       tests/agents/test_event_driven_agent.py \
       tests/agents/test_reply_triage.py \
       tests/agents/test_followup.py \
       tests/agents/test_meeting_prep.py \
       tests/agents/test_funded_watcher.py \
       tests/agents/test_warm_network.py \
       tests/agents/test_health_guardian.py \
       tests/workers/test_dispatch.py \
       tests/workers/test_webhook_tasks_dispatch.py \
       tests/workers/test_gmail_webhook_tasks.py \
       tests/workers/test_maintenance_tasks.py \
       tests/workers/handlers/ \
       tests/api/test_gmail_webhook_endpoint.py \
       tests/api/test_false_alarm_endpoint.py \
       tests/scripts/test_calibrate_reply_triage.py -v --tb=short
```

Expected: all SP5 tests pass. Approximate count: ~110 tests across all chunks. Adjust per actual implementation.

- [ ] **Step 2: Run the full project test suite**

```bash
pytest tests/ --tb=short
```

Expected: 1073 (v1) + ~110 (SP5) ≈ 1183 passed. No v1 regression.

- [ ] **Step 3: Tag chunk done**

```bash
git tag claude/sp5-chunk-8-done
```

---

### Task 8.5: Day-1 calibration + 7-day measurement window

**Day 1 of SP5 execution:**

```bash
# Reply Triage calibration
python scripts/calibrate_reply_triage.py --limit 50
```

Expected:
- ≥80% joint match → ship Qwen, no further action
- <80% → set `AGENT_MODEL_REPLY_TRIAGE=claude-sonnet-4-6` in .env, restart workers, re-run script. If Claude also fails → fix-window per spec §8.1, edit `_classify_email` prompt + schema, re-run.

**Days 2-7: warm-up (no measurement).** Let agents run. Observe Telegram feed. Adjust dedup keys, severity thresholds, prompt phrasing as obvious bugs surface. Commit fixes inline; do not start the formal window during this period.

**Days 8-14: 7-day measurement window** (per spec §8.2):

- [ ] Daily Briefing handler runs every 7am — captures the day's pings_count + false_critical_acks.
- [ ] At end of each day in the window:
  - Verify `count(severity in {info, warn, critical}) >= 3` from `agent_logs` for that day
  - Verify `count(false_critical_acks during window) == 0`
- [ ] If both hold for 7 consecutive days → SP5 exit gate PASSES.
- [ ] If a false-critical fires → reset window from that day; investigate via `agent_state(<agent>, "false_critical:*")`; tighten the agent's CRITICAL_REASONS conjunction or whitelist.

```bash
# Useful query during the window:
psql "$DATABASE_URL" -c "
SELECT
  DATE(created_at) AS day,
  COUNT(*) FILTER (WHERE action='gate_decision' AND status='allow') AS allowed,
  COUNT(*) FILTER (WHERE action='gate_decision' AND status='demote_warn') AS demoted_warn,
  COUNT(*) FILTER (WHERE action='gate_decision' AND status='suppress') AS suppressed
FROM agent_logs
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY day
ORDER BY day DESC;
"
```

```bash
# False-critical count in window:
psql "$DATABASE_URL" -c "
SELECT COUNT(*) FROM agent_state
WHERE key LIKE 'false_critical:%'
  AND updated_at >= NOW() - INTERVAL '7 days';
"
```

**On gate pass:**
- [ ] Tag the SP5 release commit: `git tag sp5-shipped`
- [ ] Move SP5 design doc to `docs/superpowers/specs/shipped/` (or whatever the convention is for completed sub-projects)
- [ ] Brainstorm + plan SP6 (Screen Perception) per charter §2

**On gate fail (7 days don't hold):**
- [ ] Bounded fix window per charter §5.1 (≤25% of original 2-3 week estimate = ≤4 days)
- [ ] If fix window expires → defer SP5 to v2.1 per charter §6 (highly unlikely given the architectural defense — gate is structural)

---

**End of Chunk 8.** SP5 is wired and ready to run. The exit gate is operational; calibration + 7-day window are the final acceptance steps.

---

## Plan complete

**Total scope summary:**

| Chunk | New files | Tests | Production lines (est) |
|---|---|---|---|
| 1 — Foundations | 3 | 9 | ~210 |
| 2 — ProactiveEngine gate | +1 | 23 | ~280 (gate) |
| 3 — Notification router + Telegram + endpoint | +2, modified main.py | 13 | ~270 |
| 4 — EventDrivenAgent + dispatch + Gmail webhook | +5 | 24 | ~430 |
| 5 — Handlers (6) + HandlerContext + handler registry | +9 | 19 | ~830 |
| 6 — K1-survivor agents + calibration | +6 | 16 | ~1090 |
| 7 — Cuttable agents (3) | +3 | 8 + 1 skip | ~600 |
| 8 — File watcher + maintenance + ARQ wiring | +2, modified arq_worker | 11 | ~360 |
| **Total** | **~30 files** | **~123 tests** | **~4,070 LoC** |

This matches the spec's 2–3 week estimate at a sustainable pace. K1 cut surface is ~30 minutes of work (delete 3 agent dirs + 5 handler files + 8 cron registration lines) — exactly as designed.
