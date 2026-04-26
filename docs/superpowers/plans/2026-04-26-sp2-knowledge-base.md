# SP2 Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 4-ring Qdrant knowledge base layer (activities, projects_docs, user_patterns, domain_knowledge) plus two Postgres tables, a unified `KnowledgeBaseService`, a codebase seed script, and retrofit all 13 eligible agents to read/write KB context on every invocation.

**Architecture:** `KnowledgeBaseService` (singleton in `services/knowledge_base.py`) owns all four Qdrant collections and two Postgres tables. Each agent declares `KNOWLEDGE_RINGS: list[str]` as a class variable, calls `build_agent_context()` at the top of `process()`, and calls `record_agent_activity()` after completing. The existing `SemanticMemoryService` / `cruz_memories` collection is untouched.

**Tech Stack:** Python 3.11+, asyncpg (via existing `DatabaseService`), qdrant-client 1.10+ (async, existing `QdrantService`), sentence-transformers all-MiniLM-L6-v2 (existing `EmbeddingService`), Alembic, pytest + unittest.mock

**Spec:** `docs/superpowers/specs/2026-04-26-sp2-knowledge-base-design.md`

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Create | `migrations/versions/0004_kb_tables.py` | Alembic migration: `projects` + `learned_patterns` tables + seed rows |
| Create | `services/knowledge_base.py` | `KnowledgeBaseService` singleton — all read/write methods |
| Create | `scripts/seed_kb.py` | One-shot project codebase indexer |
| Create | `tests/services/test_knowledge_base.py` | Unit tests for every KB service method |
| Create | `tests/integration/test_kb_integration.py` | Full activity write → context read loop |
| Modify | `agents/forge/forge_agent.py` | Add `KNOWLEDGE_RINGS` + 2 KB calls |
| Modify | `agents/echo/echo_agent.py` | Add `KNOWLEDGE_RINGS` + 2 KB calls |
| Modify | `agents/reach/reach_agent.py` | Add `KNOWLEDGE_RINGS` + 2 KB calls |
| Modify | `agents/catch/catch_agent.py` | Add `KNOWLEDGE_RINGS` + 2 KB calls |
| Modify | `agents/pm/pm_agent.py` | Add `KNOWLEDGE_RINGS` + 2 KB calls |
| Modify | `agents/titan/titan_agent.py` | Add `KNOWLEDGE_RINGS` + 2 KB calls |
| Modify | `agents/mark/mark_agent.py` | Add `KNOWLEDGE_RINGS` + 2 KB calls |
| Modify | `agents/qt/qt_agent.py` | Add `KNOWLEDGE_RINGS` + 2 KB calls |
| Modify | `agents/sentinel/sentinel_agent.py` | Add `KNOWLEDGE_RINGS` + 2 KB calls |
| Modify | `agents/raw/raw_agent.py` | Add `KNOWLEDGE_RINGS` + 2 KB calls + `write_domain_knowledge` call |
| Modify | `agents/pulse/pulse_agent.py` | Add `KNOWLEDGE_RINGS` + 2 KB calls |
| Modify | `agents/general/general_agent.py` | Add `KNOWLEDGE_RINGS` + 2 KB calls |
| Modify | `agents/cruz/cruz_agent.py` | Add `KNOWLEDGE_RINGS` + 2 KB calls + `record_pattern_observation` tool |
| Modify | `tests/agents/test_forge_agent.py` | Mock `get_kb_service` |
| Modify | `tests/agents/test_echo_agent.py` | Mock `get_kb_service` |
| Modify | `tests/agents/test_reach_agent.py` | Mock `get_kb_service` |
| Modify | `tests/agents/test_catch_agent.py` | Mock `get_kb_service` |
| Modify | `tests/agents/test_pm_agent.py` | Mock `get_kb_service` |
| Modify | `tests/agents/test_titan_agent.py` | Mock `get_kb_service` |
| Modify | `tests/agents/test_mark_agent.py` | Mock `get_kb_service` |
| Modify | `tests/agents/test_qt_agent.py` | Mock `get_kb_service` |
| Modify | `tests/agents/test_sentinel_agent.py` | Mock `get_kb_service` |
| Modify | `tests/agents/test_raw_agent.py` | Mock `get_kb_service` |
| Modify | `tests/agents/test_pulse_agent.py` | Mock `get_kb_service` |
| Modify | `tests/agents/test_general_agent.py` | Mock `get_kb_service` |
| Modify | `tests/agents/test_cruz_agent.py` | Mock `get_kb_service` |

---

## Chunk 1: Migration + KnowledgeBaseService skeleton

### Task 1: Alembic migration — `projects` and `learned_patterns` tables

**Files:**
- Create: `migrations/versions/0004_kb_tables.py`

- [ ] **Step 1: Write the migration file**

```python
# migrations/versions/0004_kb_tables.py
"""kb_tables

Add projects and learned_patterns tables for SP2 Knowledge Base.

Spec: docs/superpowers/specs/2026-04-26-sp2-knowledge-base-design.md §3.2

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── projects ─────────────────────────────────────────────────���────
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("name",        sa.String(100), nullable=False),
        sa.Column("slug",        sa.String(50),  nullable=False, unique=True),
        sa.Column("type",        sa.String(20),  nullable=False),
        sa.Column("status",      sa.String(20),  nullable=False,
                  server_default=sa.text("'active'")),
        sa.Column("tech_stack",  sa.JSON,         nullable=True),
        sa.Column("github_url",  sa.Text,         nullable=True),
        sa.Column("local_path",  sa.Text,         nullable=True),
        sa.Column("description", sa.Text,         nullable=True),
        sa.Column("metadata",    sa.JSON,         nullable=True),
        sa.Column("created_at",  sa.TIMESTAMP,    nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",  sa.TIMESTAMP,    nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_projects_status", "projects", ["status"])

    # ── learned_patterns ──────────────────────────────────────────────
    op.create_table(
        "learned_patterns",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("pattern_type",      sa.String(50),  nullable=False),
        sa.Column("content",           sa.Text,        nullable=False),
        sa.Column("source",            sa.String(20),  nullable=False),
        sa.Column("agent_name",        sa.String(50),  nullable=True),
        sa.Column("observation_count", sa.Integer,     nullable=False,
                  server_default=sa.text("1")),
        sa.Column("confidence",        sa.Float,       nullable=False,
                  server_default=sa.text("1.0")),
        sa.Column("qdrant_id",         sa.String(36),  nullable=True),
        sa.Column("active",            sa.Boolean,     nullable=False,
                  server_default=sa.text("TRUE")),
        sa.Column("created_at",        sa.TIMESTAMP,   nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",        sa.TIMESTAMP,   nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_learned_patterns_type",
                    "learned_patterns", ["pattern_type", "active"])
    op.create_index("idx_learned_patterns_src",
                    "learned_patterns", ["source", "observation_count"])
    op.create_unique_constraint(
        "uq_learned_patterns_key",
        "learned_patterns",
        ["pattern_type", "content", "source"],
    )

    # ── seed projects ─────────────────────────────────────────────────
    op.execute("""
        INSERT INTO projects (id, name, slug, type, status) VALUES
            (gen_random_uuid()::text, 'AMA Solutions',  'ama-solutions',  'client',   'active'),
            (gen_random_uuid()::text, 'Shooterista',    'shooterista',    'client',   'active'),
            (gen_random_uuid()::text, 'SuiteAdvisors',  'suiteadvisors',  'client',   'active'),
            (gen_random_uuid()::text, 'Asia Capital',   'asia-capital',   'client',   'active'),
            (gen_random_uuid()::text, 'MIDAR',          'midar',          'personal', 'active')
    """)


def downgrade() -> None:
    op.drop_constraint("uq_learned_patterns_key", "learned_patterns", type_="unique")
    op.drop_index("idx_learned_patterns_src",  table_name="learned_patterns")
    op.drop_index("idx_learned_patterns_type", table_name="learned_patterns")
    op.drop_table("learned_patterns")

    op.drop_index("idx_projects_status", table_name="projects")
    op.drop_table("projects")
```

- [ ] **Step 2: Run migration against test DB**

```bash
DATABASE_URL=postgresql://cruz:cruz@localhost:5432/cruz_test alembic upgrade head
```

Expected: `Running upgrade 0003 -> 0004, kb_tables`

- [ ] **Step 3: Verify tables exist**

```bash
psql postgresql://cruz:cruz@localhost:5432/cruz_test \
  -c "\dt projects" \
  -c "\dt learned_patterns" \
  -c "SELECT slug FROM projects ORDER BY slug"
```

Expected: both tables listed; 5 project rows (ama-solutions, asia-capital, midar, shooterista, suiteadvisors).

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/0004_kb_tables.py
git commit -m "feat(db): add projects and learned_patterns tables (SP2)"
```

---

### Task 2: KnowledgeBaseService skeleton + constants

**Files:**
- Create: `services/knowledge_base.py`
- Create: `tests/services/test_knowledge_base.py` (interface tests only)

- [ ] **Step 1: Write the failing interface tests**

```python
# tests/services/test_knowledge_base.py
"""
Tests for KnowledgeBaseService — SP2 Knowledge Base.

Covers: singleton, constants, method signatures, and behaviour of
build_agent_context / record_agent_activity / write_* / observe_interaction.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.knowledge_base import KnowledgeBaseService, get_kb_service


def _make_qdrant():
    q = AsyncMock()
    q.ensure_collection = AsyncMock()
    q.upsert = AsyncMock()
    q.search = AsyncMock(return_value=[])
    return q


def _make_embedding():
    e = MagicMock()
    e.encode = MagicMock(return_value=[0.1] * 384)
    return e


def _make_db():
    db = AsyncMock()
    db.fetch_one = AsyncMock(return_value=None)
    db.fetch_all = AsyncMock(return_value=[])
    db.execute = AsyncMock()
    return db


class TestKnowledgeBaseServiceInterface:
    def test_can_be_instantiated(self):
        kb = KnowledgeBaseService(_make_qdrant(), _make_embedding(), _make_db())
        assert kb is not None

    def test_vector_size_constant(self):
        assert KnowledgeBaseService.VECTOR_SIZE == 384

    def test_collection_names(self):
        assert KnowledgeBaseService.COLLECTION_ACTIVITIES    == "cruz_activities"
        assert KnowledgeBaseService.COLLECTION_PROJECTS_DOCS == "cruz_projects_docs"
        assert KnowledgeBaseService.COLLECTION_USER_PATTERNS == "cruz_user_patterns"
        assert KnowledgeBaseService.COLLECTION_DOMAIN        == "cruz_domain_knowledge"

    def test_observation_threshold_constant(self):
        assert KnowledgeBaseService.PATTERN_THRESHOLD == 5

    def test_context_header_constants_exist(self):
        assert hasattr(KnowledgeBaseService, "HEADER_ACTIVITIES")
        assert hasattr(KnowledgeBaseService, "HEADER_PROJECTS")
        assert hasattr(KnowledgeBaseService, "HEADER_PATTERNS")
        assert hasattr(KnowledgeBaseService, "HEADER_DOMAIN")

    def test_has_required_methods(self):
        kb = KnowledgeBaseService(_make_qdrant(), _make_embedding(), _make_db())
        for method in [
            "build_agent_context", "record_agent_activity",
            "write_project_doc", "write_user_pattern",
            "observe_interaction", "write_domain_knowledge",
        ]:
            assert hasattr(kb, method), f"Missing method: {method}"

    def test_get_kb_service_returns_singleton(self):
        with patch("services.knowledge_base._instance", None):
            with patch("services.knowledge_base.get_qdrant_service", return_value=_make_qdrant()), \
                 patch("services.knowledge_base.get_embedding_service", return_value=_make_embedding()), \
                 patch("services.knowledge_base.get_db_service", return_value=_make_db()):
                svc1 = get_kb_service()
                svc2 = get_kb_service()
                assert svc1 is svc2
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/services/test_knowledge_base.py -v 2>&1 | head -20
```

Expected: `ImportError` or `ModuleNotFoundError` — `services.knowledge_base` does not exist yet.

- [ ] **Step 3: Write the skeleton service**

```python
# services/knowledge_base.py
"""
KnowledgeBaseService — SP2 multi-ring knowledge base for CRUZ agents.

Four Qdrant collections:
  cruz_activities      — what every agent did + outcomes
  cruz_projects_docs   — per-project codebase knowledge
  cruz_user_patterns   — learned preferences and style
  cruz_domain_knowledge — tech / industry research (RAW agent)

Two Postgres tables (migration 0004):
  projects         — known client and personal projects
  learned_patterns — raw observations + inferred preference records

Usage in any agent:
  from services.knowledge_base import get_kb_service

  ctx = await get_kb_service().build_agent_context(task, rings, trace_id)
  # ... do agent work ...
  await get_kb_service().record_agent_activity(agent_name, task, summary,
                                               success, trace_id)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from services.db import get_db_service
from services.embedding import EmbeddingService, get_embedding_service
from services.qdrant import QdrantService, get_qdrant_service

logger = logging.getLogger("cruz.services.knowledge_base")

# Module-level singleton
_instance: Optional["KnowledgeBaseService"] = None


def get_kb_service() -> "KnowledgeBaseService":
    """Return the module-level KnowledgeBaseService singleton."""
    global _instance
    if _instance is None:
        _instance = KnowledgeBaseService(
            get_qdrant_service(),
            get_embedding_service(),
            get_db_service(),
        )
    return _instance


class KnowledgeBaseService:
    """Unified read/write interface for all four KB rings."""

    # ── Constants ────────────────────────────────────────────────────
    VECTOR_SIZE = 384  # all-MiniLM-L6-v2

    COLLECTION_ACTIVITIES    = "cruz_activities"
    COLLECTION_PROJECTS_DOCS = "cruz_projects_docs"
    COLLECTION_USER_PATTERNS = "cruz_user_patterns"
    COLLECTION_DOMAIN        = "cruz_domain_knowledge"

    PATTERN_THRESHOLD = 5  # observations before inferring a pattern

    HEADER_ACTIVITIES = "## Relevant past work"
    HEADER_PROJECTS   = "## Project context"
    HEADER_PATTERNS   = "## Your patterns"
    HEADER_DOMAIN     = "## Domain knowledge"

    def __init__(
        self,
        qdrant: QdrantService,
        embedding: EmbeddingService,
        db: Any,
    ) -> None:
        self._qdrant = qdrant
        self._embedding = embedding
        self._db = db

    # ── READ ─────────────────────────────────────────────────────────

    async def build_agent_context(
        self,
        task: str,
        rings: List[str],
        trace_id: str,
        project_id: Optional[str] = None,
        limit_per_ring: int = 5,
    ) -> str:
        """Return a formatted context string for injection into the agent's system prompt."""
        raise NotImplementedError

    # ── WRITE — activities ────────────────────────────────────────────

    async def record_agent_activity(
        self,
        agent_name: str,
        task: str,
        result_summary: str,
        success: bool,
        trace_id: str,
        project_id: Optional[str] = None,
        tokens_used: Optional[int] = None,
    ) -> None:
        """Embed and upsert one activity record into cruz_activities."""
        raise NotImplementedError

    # ── WRITE — project docs ──────────────────────────────────────────

    async def write_project_doc(
        self,
        project_id: str,
        project_name: str,
        content: str,
        doc_type: str,
        file_path: Optional[str] = None,
        chunk_index: int = 0,
        trace_id: Optional[str] = None,
    ) -> None:
        """
        Upsert a project knowledge chunk.
        Point ID = sha256(project_id + file_path + str(chunk_index))[:32]
        """
        raise NotImplementedError

    # ── WRITE — user patterns (explicit) ─────────────────────────────

    async def write_user_pattern(
        self,
        content: str,
        pattern_type: str,
        source: str = "explicit",
        agent_name: Optional[str] = None,
    ) -> None:
        """Write a pattern immediately. Bypasses the observation threshold."""
        raise NotImplementedError

    # ── WRITE — user patterns (inferred) ─────────────────────────────

    async def observe_interaction(
        self,
        agent_name: str,
        interaction_type: str,
        observed_pattern: str,
    ) -> None:
        """
        Increment observation count. At threshold=5, extract and write pattern
        as a background asyncio task (non-blocking, falls back on API error).
        """
        raise NotImplementedError

    # ── WRITE — domain knowledge ──────────────────────────────────────

    async def write_domain_knowledge(
        self,
        content: str,
        topic: str,
        source: str = "raw_agent",
        trace_id: Optional[str] = None,
    ) -> None:
        """Upsert a domain knowledge chunk into cruz_domain_knowledge."""
        raise NotImplementedError

    # ── Internal helpers ──────────────────────────────────────────────

    def _point_id(self, *parts: str) -> str:
        """Deterministic 32-char hex ID from arbitrary string parts."""
        raw = "".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
```

- [ ] **Step 4: Run interface tests — expect pass**

```bash
pytest tests/services/test_knowledge_base.py -v
```

Expected: all 8 tests PASS (skeleton satisfies the interface).

- [ ] **Step 5: Commit**

```bash
git add services/knowledge_base.py tests/services/test_knowledge_base.py
git commit -m "feat(kb): KnowledgeBaseService skeleton + interface tests"
```

---

## Chunk 2: build_agent_context + record_agent_activity

### Task 3: Implement `record_agent_activity`

**Files:**
- Modify: `services/knowledge_base.py`
- Modify: `tests/services/test_knowledge_base.py`

- [ ] **Step 1: Add tests for `record_agent_activity`**

Append to `tests/services/test_knowledge_base.py`:

```python
class TestRecordAgentActivity:
    @pytest.fixture
    def kb(self):
        return KnowledgeBaseService(_make_qdrant(), _make_embedding(), _make_db())

    @pytest.mark.asyncio
    async def test_calls_qdrant_upsert(self, kb):
        await kb.record_agent_activity(
            "forge", "write a function", "wrote foo()", True, "trace-1"
        )
        kb._qdrant.ensure_collection.assert_awaited_once_with(
            "cruz_activities", 384
        )
        kb._qdrant.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_embed_text_contains_agent_and_task(self, kb):
        await kb.record_agent_activity(
            "echo", "draft email", "drafted subject line", True, "trace-2"
        )
        call_args = kb._embedding.encode.call_args[0][0]
        assert "echo" in call_args
        assert "draft email" in call_args

    @pytest.mark.asyncio
    async def test_payload_fields_present(self, kb):
        await kb.record_agent_activity(
            "forge", "task", "result", False, "trace-3",
            project_id="proj-1", tokens_used=100
        )
        payload = kb._qdrant.upsert.call_args.kwargs["payload"]
        assert payload["agent_name"] == "forge"
        assert payload["success"] is False
        assert payload["project_id"] == "proj-1"
        assert payload["tokens_used"] == 100
        assert payload["trace_id"] == "trace-3"
        assert "timestamp" in payload

    @pytest.mark.asyncio
    async def test_does_not_raise_when_qdrant_fails(self, kb):
        kb._qdrant.upsert = AsyncMock(side_effect=Exception("qdrant down"))
        # Must not propagate — recording is fire-and-forget
        await kb.record_agent_activity("forge", "task", "result", True, "trace-4")
```

- [ ] **Step 2: Run — expect FAIL (NotImplementedError)**

```bash
pytest tests/services/test_knowledge_base.py::TestRecordAgentActivity -v
```

- [ ] **Step 3: Implement `record_agent_activity`**

Replace the `raise NotImplementedError` in `record_agent_activity`:

```python
async def record_agent_activity(
    self,
    agent_name: str,
    task: str,
    result_summary: str,
    success: bool,
    trace_id: str,
    project_id: Optional[str] = None,
    tokens_used: Optional[int] = None,
) -> None:
    try:
        embed_text = f"agent {agent_name}: {task} → {result_summary}"
        vector = self._embedding.encode(embed_text)
        point_id = self._point_id(trace_id, agent_name, str(time.time()))
        payload: Dict[str, Any] = {
            "agent_name":     agent_name,
            "task":           task,
            "result_summary": result_summary,
            "success":        success,
            "project_id":     project_id,
            "trace_id":       trace_id,
            "timestamp":      time.time(),
            "tokens_used":    tokens_used,
        }
        await self._qdrant.ensure_collection(self.COLLECTION_ACTIVITIES, self.VECTOR_SIZE)
        await self._qdrant.upsert(
            collection=self.COLLECTION_ACTIVITIES,
            id=point_id,
            vector=vector,
            payload=payload,
        )
    except Exception as exc:
        logger.warning("[%s] record_agent_activity failed (non-fatal): %s", trace_id, exc)
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/services/test_knowledge_base.py::TestRecordAgentActivity -v
```

- [ ] **Step 5: Commit**

```bash
git add services/knowledge_base.py tests/services/test_knowledge_base.py
git commit -m "feat(kb): implement record_agent_activity"
```

---

### Task 4: Implement `build_agent_context`

**Files:**
- Modify: `services/knowledge_base.py`
- Modify: `tests/services/test_knowledge_base.py`

- [ ] **Step 1: Add tests for `build_agent_context`**

Append to `tests/services/test_knowledge_base.py`:

```python
class TestBuildAgentContext:
    def _make_kb_with_hits(self, hits_by_collection: dict):
        qdrant = _make_qdrant()
        async def _search(collection, query_vector, limit=5):
            return hits_by_collection.get(collection, [])
        qdrant.search = _search
        return KnowledgeBaseService(qdrant, _make_embedding(), _make_db())

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_all_rings_empty(self):
        kb = KnowledgeBaseService(_make_qdrant(), _make_embedding(), _make_db())
        ctx = await kb.build_agent_context("some task", ["cruz_activities"], "t1")
        assert ctx == ""

    @pytest.mark.asyncio
    async def test_only_queries_declared_rings(self):
        kb = KnowledgeBaseService(_make_qdrant(), _make_embedding(), _make_db())
        await kb.build_agent_context("task", ["cruz_activities"], "t1")
        # search called once (for activities), not 4 times
        assert kb._qdrant.search.call_count == 1

    @pytest.mark.asyncio
    async def test_activities_section_included_when_hits_exist(self):
        hits = [{"score": 0.9, "payload": {
            "agent_name": "forge", "task": "wrote foo()",
            "result_summary": "added function", "timestamp": time.time() - 3600
        }}]
        kb = self._make_kb_with_hits({"cruz_activities": hits})
        ctx = await kb.build_agent_context("task", ["cruz_activities"], "t1")
        assert KnowledgeBaseService.HEADER_ACTIVITIES in ctx
        assert "forge" in ctx

    @pytest.mark.asyncio
    async def test_projects_section_included_when_hits_exist(self):
        hits = [{"score": 0.85, "payload": {
            "project_name": "AMA Solutions",
            "content": "Stack: React 18, PostgreSQL",
            "doc_type": "readme"
        }}]
        kb = self._make_kb_with_hits({"cruz_projects_docs": hits})
        ctx = await kb.build_agent_context(
            "task", ["cruz_projects_docs"], "t1", project_id="proj-1"
        )
        assert KnowledgeBaseService.HEADER_PROJECTS in ctx
        assert "AMA Solutions" in ctx

    @pytest.mark.asyncio
    async def test_empty_rings_omit_section_headers(self):
        hits = [{"score": 0.9, "payload": {
            "agent_name": "forge", "task": "t", "result_summary": "r",
            "timestamp": time.time()
        }}]
        kb = self._make_kb_with_hits({"cruz_activities": hits})
        ctx = await kb.build_agent_context(
            "task", ["cruz_activities", "cruz_user_patterns"], "t1"
        )
        assert KnowledgeBaseService.HEADER_ACTIVITIES in ctx
        assert KnowledgeBaseService.HEADER_PATTERNS not in ctx

    @pytest.mark.asyncio
    async def test_returns_empty_string_on_qdrant_error(self):
        kb = KnowledgeBaseService(_make_qdrant(), _make_embedding(), _make_db())
        kb._qdrant.search = AsyncMock(side_effect=Exception("qdrant down"))
        ctx = await kb.build_agent_context("task", ["cruz_activities"], "t1")
        assert ctx == ""
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/services/test_knowledge_base.py::TestBuildAgentContext -v
```

- [ ] **Step 3: Implement `build_agent_context`**

Replace the `raise NotImplementedError` in `build_agent_context`:

```python
async def build_agent_context(
    self,
    task: str,
    rings: List[str],
    trace_id: str,
    project_id: Optional[str] = None,
    limit_per_ring: int = 5,
) -> str:
    try:
        query_vector = self._embedding.encode(task)
        sections: List[str] = []

        for ring in rings:
            try:
                hits = await self._qdrant.search(
                    collection=ring,
                    query_vector=query_vector,
                    limit=limit_per_ring,
                )
            except Exception:
                continue

            if not hits:
                continue

            if ring == self.COLLECTION_ACTIVITIES:
                lines = []
                for h in hits:
                    p = h["payload"]
                    age = int((time.time() - p.get("timestamp", time.time())) / 3600)
                    age_str = f"{age}h ago" if age < 48 else f"{age // 24}d ago"
                    lines.append(
                        f"- {p.get('agent_name','?')}: {p.get('task','')} "
                        f"({age_str})"
                    )
                sections.append(f"{self.HEADER_ACTIVITIES}\n" + "\n".join(lines))

            elif ring == self.COLLECTION_PROJECTS_DOCS:
                proj_name = hits[0]["payload"].get("project_name", "")
                header = f"{self.HEADER_PROJECTS}"
                if proj_name:
                    header += f" — {proj_name}"
                lines = [h["payload"].get("content", "") for h in hits]
                sections.append(header + "\n" + "\n".join(lines))

            elif ring == self.COLLECTION_USER_PATTERNS:
                lines = ["- " + h["payload"].get("content", "") for h in hits]
                sections.append(f"{self.HEADER_PATTERNS}\n" + "\n".join(lines))

            elif ring == self.COLLECTION_DOMAIN:
                lines = [h["payload"].get("content", "") for h in hits]
                sections.append(f"{self.HEADER_DOMAIN}\n" + "\n".join(lines))

        return "\n\n".join(sections)

    except Exception as exc:
        logger.warning("[%s] build_agent_context failed (non-fatal): %s", trace_id, exc)
        return ""
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/services/test_knowledge_base.py::TestBuildAgentContext -v
```

- [ ] **Step 5: Run all KB tests so far**

```bash
pytest tests/services/test_knowledge_base.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add services/knowledge_base.py tests/services/test_knowledge_base.py
git commit -m "feat(kb): implement build_agent_context"
```

---

## Chunk 3: write_project_doc, write_user_pattern, observe_interaction, write_domain_knowledge

### Task 5: Implement `write_project_doc` and `write_domain_knowledge`

**Files:**
- Modify: `services/knowledge_base.py`
- Modify: `tests/services/test_knowledge_base.py`

- [ ] **Step 1: Add tests**

Append to `tests/services/test_knowledge_base.py`:

```python
class TestWriteProjectDoc:
    @pytest.fixture
    def kb(self):
        return KnowledgeBaseService(_make_qdrant(), _make_embedding(), _make_db())

    @pytest.mark.asyncio
    async def test_calls_upsert_with_expected_payload(self, kb):
        await kb.write_project_doc(
            "proj-1", "AMA Solutions", "Stack: React 18", "readme",
            file_path="README.md", chunk_index=0
        )
        kb._qdrant.upsert.assert_awaited_once()
        payload = kb._qdrant.upsert.call_args.kwargs["payload"]
        assert payload["project_id"] == "proj-1"
        assert payload["project_name"] == "AMA Solutions"
        assert payload["doc_type"] == "readme"
        assert payload["file_path"] == "README.md"

    @pytest.mark.asyncio
    async def test_point_id_is_deterministic(self, kb):
        await kb.write_project_doc("p", "Name", "content", "note", chunk_index=0)
        id1 = kb._qdrant.upsert.call_args.kwargs["id"]
        kb._qdrant.upsert.reset_mock()
        await kb.write_project_doc("p", "Name", "content", "note", chunk_index=0)
        id2 = kb._qdrant.upsert.call_args.kwargs["id"]
        assert id1 == id2

    @pytest.mark.asyncio
    async def test_does_not_raise_on_qdrant_error(self, kb):
        kb._qdrant.upsert = AsyncMock(side_effect=Exception("fail"))
        await kb.write_project_doc("p", "N", "c", "note")


class TestWriteDomainKnowledge:
    @pytest.fixture
    def kb(self):
        return KnowledgeBaseService(_make_qdrant(), _make_embedding(), _make_db())

    @pytest.mark.asyncio
    async def test_writes_to_domain_collection(self, kb):
        await kb.write_domain_knowledge("Next.js tip", "Next.js App Router")
        kb._qdrant.ensure_collection.assert_awaited_with("cruz_domain_knowledge", 384)
        payload = kb._qdrant.upsert.call_args.kwargs["payload"]
        assert payload["topic"] == "Next.js App Router"
        assert payload["source"] == "raw_agent"

    @pytest.mark.asyncio
    async def test_accepts_manual_source(self, kb):
        await kb.write_domain_knowledge("note", "topic", source="manual")
        payload = kb._qdrant.upsert.call_args.kwargs["payload"]
        assert payload["source"] == "manual"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/services/test_knowledge_base.py::TestWriteProjectDoc \
       tests/services/test_knowledge_base.py::TestWriteDomainKnowledge -v
```

- [ ] **Step 3: Implement both methods**

Replace `raise NotImplementedError` in `write_project_doc`:

```python
async def write_project_doc(
    self,
    project_id: str,
    project_name: str,
    content: str,
    doc_type: str,
    file_path: Optional[str] = None,
    chunk_index: int = 0,
    trace_id: Optional[str] = None,
) -> None:
    try:
        vector = self._embedding.encode(content)
        point_id = self._point_id(
            project_id, file_path or "", str(chunk_index)
        )
        payload: Dict[str, Any] = {
            "project_id":   project_id,
            "project_name": project_name,
            "doc_type":     doc_type,
            "file_path":    file_path,
            "content":      content,
            "timestamp":    time.time(),
        }
        await self._qdrant.ensure_collection(
            self.COLLECTION_PROJECTS_DOCS, self.VECTOR_SIZE
        )
        await self._qdrant.upsert(
            collection=self.COLLECTION_PROJECTS_DOCS,
            id=point_id,
            vector=vector,
            payload=payload,
        )
    except Exception as exc:
        logger.warning("write_project_doc failed (non-fatal): %s", exc)
```

Replace `raise NotImplementedError` in `write_domain_knowledge`:

```python
async def write_domain_knowledge(
    self,
    content: str,
    topic: str,
    source: str = "raw_agent",
    trace_id: Optional[str] = None,
) -> None:
    try:
        vector = self._embedding.encode(content)
        point_id = self._point_id(topic, content[:50])
        payload: Dict[str, Any] = {
            "topic":     topic,
            "content":   content,
            "source":    source,
            "timestamp": time.time(),
        }
        await self._qdrant.ensure_collection(
            self.COLLECTION_DOMAIN, self.VECTOR_SIZE
        )
        await self._qdrant.upsert(
            collection=self.COLLECTION_DOMAIN,
            id=point_id,
            vector=vector,
            payload=payload,
        )
    except Exception as exc:
        logger.warning("write_domain_knowledge failed (non-fatal): %s", exc)
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/services/test_knowledge_base.py::TestWriteProjectDoc \
       tests/services/test_knowledge_base.py::TestWriteDomainKnowledge -v
```

- [ ] **Step 5: Commit**

```bash
git add services/knowledge_base.py tests/services/test_knowledge_base.py
git commit -m "feat(kb): implement write_project_doc and write_domain_knowledge"
```

---

### Task 6: Implement `write_user_pattern` and `observe_interaction`

**Files:**
- Modify: `services/knowledge_base.py`
- Modify: `tests/services/test_knowledge_base.py`

- [ ] **Step 1: Add tests**

Append to `tests/services/test_knowledge_base.py`:

```python
class TestWriteUserPattern:
    @pytest.fixture
    def kb(self):
        return KnowledgeBaseService(_make_qdrant(), _make_embedding(), _make_db())

    @pytest.mark.asyncio
    async def test_writes_to_user_patterns_collection(self, kb):
        await kb.write_user_pattern("prefer snake_case", "code_style")
        kb._qdrant.ensure_collection.assert_awaited_with(
            "cruz_user_patterns", 384
        )
        payload = kb._qdrant.upsert.call_args.kwargs["payload"]
        assert payload["content"] == "prefer snake_case"
        assert payload["pattern_type"] == "code_style"
        assert payload["source"] == "explicit"
        assert payload["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_also_inserts_into_learned_patterns_db(self, kb):
        await kb.write_user_pattern("formal tone", "comm_style")
        kb._db.execute.assert_awaited()


class TestObserveInteraction:
    def _make_kb(self, observation_count_after=1):
        db = _make_db()
        # fetch_one returns the current count after upsert
        db.fetch_one = AsyncMock(return_value={"observation_count": observation_count_after})
        return KnowledgeBaseService(_make_qdrant(), _make_embedding(), db)

    @pytest.mark.asyncio
    async def test_increments_count_below_threshold(self):
        kb = self._make_kb(observation_count_after=3)
        await kb.observe_interaction("echo", "email_edited", "shortened body")
        kb._db.execute.assert_awaited()  # counter row must be upserted
        # No pattern written yet — count < threshold
        kb._qdrant.upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_writes_pattern_at_threshold(self):
        kb = self._make_kb(observation_count_after=5)
        with patch("services.knowledge_base.asyncio") as mock_asyncio:
            mock_asyncio.create_task = MagicMock()
            await kb.observe_interaction("echo", "email_edited", "shortened body")
            mock_asyncio.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_raise_on_db_error(self):
        kb = KnowledgeBaseService(_make_qdrant(), _make_embedding(), _make_db())
        kb._db.execute = AsyncMock(side_effect=Exception("db down"))
        await kb.observe_interaction("forge", "code_edited", "added type hints")
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/services/test_knowledge_base.py::TestWriteUserPattern \
       tests/services/test_knowledge_base.py::TestObserveInteraction -v
```

- [ ] **Step 3: Implement `write_user_pattern`**

Replace `raise NotImplementedError` in `write_user_pattern`:

```python
async def write_user_pattern(
    self,
    content: str,
    pattern_type: str,
    source: str = "explicit",
    agent_name: Optional[str] = None,
) -> None:
    try:
        vector = self._embedding.encode(content)
        point_id = self._point_id(pattern_type, content[:80])
        payload: Dict[str, Any] = {
            "pattern_type":      pattern_type,
            "content":           content,
            "source":            source,
            "agent_name":        agent_name,
            "observation_count": 1,
            "confidence":        1.0 if source == "explicit" else 0.8,
            "timestamp":         time.time(),
        }
        await self._qdrant.ensure_collection(
            self.COLLECTION_USER_PATTERNS, self.VECTOR_SIZE
        )
        await self._qdrant.upsert(
            collection=self.COLLECTION_USER_PATTERNS,
            id=point_id,
            vector=vector,
            payload=payload,
        )
        row_id = str(uuid.uuid4())
        await self._db.execute(
            """
            INSERT INTO learned_patterns
                (id, pattern_type, content, source, agent_name,
                 observation_count, confidence, qdrant_id, active)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,TRUE)
            ON CONFLICT (pattern_type, content, source)
            DO UPDATE SET
                confidence  = EXCLUDED.confidence,
                qdrant_id   = EXCLUDED.qdrant_id,
                active      = TRUE,
                updated_at  = NOW()
            """,
            row_id, pattern_type, content, source, agent_name,
            1, 1.0 if source == "explicit" else 0.8, point_id,
        )
    except Exception as exc:
        logger.warning("write_user_pattern failed (non-fatal): %s", exc)
```

- [ ] **Step 4: Implement `observe_interaction`**

Replace `raise NotImplementedError` in `observe_interaction`:

```python
async def observe_interaction(
    self,
    agent_name: str,
    interaction_type: str,
    observed_pattern: str,
) -> None:
    try:
        row_id = str(uuid.uuid4())
        # Upsert a counter row keyed on (agent_name, interaction_type, observed_pattern[:80])
        await self._db.execute(
            """
            INSERT INTO learned_patterns
                (id, pattern_type, content, source, agent_name, observation_count,
                 confidence, active)
            VALUES ($1, $2, $3, 'inferred', $4, 1, 0.0, FALSE)
            ON CONFLICT (pattern_type, content, source)
            DO UPDATE SET
                observation_count = learned_patterns.observation_count + 1,
                updated_at = NOW()
            """,
            row_id, interaction_type, observed_pattern[:200], agent_name,
        )
        row = await self._db.fetch_one(
            """
            SELECT observation_count FROM learned_patterns
            WHERE pattern_type = $1 AND content = $2 AND source = 'inferred'
            ORDER BY updated_at DESC LIMIT 1
            """,
            interaction_type, observed_pattern[:200],
        )
        if row and row["observation_count"] >= self.PATTERN_THRESHOLD:
            asyncio.create_task(
                self._extract_and_write_pattern(agent_name, interaction_type, observed_pattern)
            )
    except Exception as exc:
        logger.warning("observe_interaction failed (non-fatal): %s", exc)

async def _extract_and_write_pattern(
    self,
    agent_name: str,
    interaction_type: str,
    observed_pattern: str,
) -> None:
    """Background task: call Claude Sonnet to clean the pattern, then write it."""
    try:
        from services.llm import chat as llm_chat
        messages = [{
            "role": "user",
            "content": (
                f"An agent named {agent_name} has repeatedly observed this pattern "
                f"in user interactions (type: {interaction_type}):\n\n"
                f"{observed_pattern}\n\n"
                "Write a single concise preference rule in plain English "
                "(one sentence, starts with 'Darshan prefers' or 'Darshan always'). "
                "Output only the rule — no explanation, no quotes."
            ),
        }]
        result = await llm_chat(
            model="claude-sonnet-4-6",
            messages=messages,
            system="You extract user preference rules from behavioral observations.",
            max_tokens=100,
        )
        cleaned = result.strip()
        if cleaned:
            await self.write_user_pattern(
                cleaned,
                pattern_type=interaction_type,
                source="inferred",
                agent_name=agent_name,
            )
    except Exception as exc:
        logger.warning("_extract_and_write_pattern failed (non-fatal): %s", exc)
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest tests/services/test_knowledge_base.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add services/knowledge_base.py tests/services/test_knowledge_base.py
git commit -m "feat(kb): implement write_user_pattern and observe_interaction"
```

---

## Chunk 4: Seed script

### Task 7: `scripts/seed_kb.py`

**Files:**
- Create: `scripts/seed_kb.py`
- Create: `tests/scripts/test_seed_kb.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_seed_kb.py
"""Tests for the KB seed script."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.seed_kb import chunk_file, get_priority_files, should_skip


class TestShouldSkip:
    def test_skips_node_modules(self):
        assert should_skip(Path("project/node_modules/foo.js")) is True

    def test_skips_git_dir(self):
        assert should_skip(Path("project/.git/config")) is True

    def test_skips_pycache(self):
        assert should_skip(Path("project/__pycache__/foo.pyc")) is True

    def test_skips_lock_files(self):
        assert should_skip(Path("project/package-lock.json")) is True

    def test_skips_dist(self):
        assert should_skip(Path("project/dist/bundle.js")) is True

    def test_allows_readme(self):
        assert should_skip(Path("project/README.md")) is False

    def test_allows_python_source(self):
        assert should_skip(Path("project/main.py")) is False


class TestChunkFile:
    def test_small_file_is_single_chunk(self):
        content = "line1\nline2\nline3"
        chunks = chunk_file(content, max_tokens=500)
        assert len(chunks) == 1
        assert chunks[0] == content

    def test_large_file_is_split(self):
        # 1000 words → should split at ~500 tokens (≈375 words)
        content = "\n\n".join(["word " * 50] * 20)
        chunks = chunk_file(content, max_tokens=500)
        assert len(chunks) > 1


class TestGetPriorityFiles:
    def test_finds_readme(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "README.md").write_text("# Test")
            Path(tmpdir, "main.py").write_text("print('hi')")
            Path(tmpdir, "node_modules").mkdir()
            Path(tmpdir, "node_modules", "foo.js").write_text("x")
            files = get_priority_files(Path(tmpdir))
            names = [f.name for f in files]
            assert "README.md" in names
            assert "main.py" in names
            assert "foo.js" not in names
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/scripts/test_seed_kb.py -v
```

- [ ] **Step 3: Write the seed script**

```python
#!/usr/bin/env python3
# scripts/seed_kb.py
"""
seed_kb.py — one-shot project codebase indexer for SP2 Knowledge Base.

Usage:
    python scripts/seed_kb.py                          # all active projects with local_path
    python scripts/seed_kb.py --projects ama-solutions # specific projects by slug
    python scripts/seed_kb.py --dry-run               # print what would be indexed

Spec: docs/superpowers/specs/2026-04-26-sp2-knowledge-base-design.md §6
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

# Bootstrap path
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", "postgresql://cruz:cruz@localhost:5432/cruz_db"))

PRIORITY_FILENAMES = {
    "README.md", "CLAUDE.md", ".env.example", "package.json",
    "requirements.txt", "pyproject.toml", "docker-compose.yml",
    "alembic.ini", "main.py", "app.py", "server.ts",
}
PRIORITY_SUFFIXES = {".sql", ".prisma"}
PRIORITY_ENTRY_PATTERNS = {"src/index.ts", "backend/api/main.py"}

SKIP_DIRS  = {"node_modules", ".git", "__pycache__", "dist", "build", ".next", "venv", ".venv"}
SKIP_EXTS  = {".lock", ".min.js", ".min.css", ".pyc", ".map", ".bin", ".whl"}
SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock"}

# Rough tokens-per-character ratio for all-MiniLM-L6-v2 context
_CHARS_PER_TOKEN = 4


def should_skip(path: Path) -> bool:
    """Return True if this file/directory should be excluded from indexing."""
    for part in path.parts:
        if part in SKIP_DIRS:
            return True
    if path.name in SKIP_NAMES:
        return True
    if path.suffix in SKIP_EXTS:
        return True
    return False


def get_priority_files(root: Path) -> List[Path]:
    """Return the list of files worth indexing from a project root."""
    result: List[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if should_skip(path):
            continue
        rel = path.relative_to(root)
        # Priority: exact filename match
        if path.name in PRIORITY_FILENAMES:
            result.insert(0, path)
            continue
        # Priority: suffix match
        if path.suffix in PRIORITY_SUFFIXES:
            result.append(path)
            continue
        # Priority: entry-point patterns
        if str(rel) in PRIORITY_ENTRY_PATTERNS:
            result.append(path)
    return result


def chunk_file(content: str, max_tokens: int = 500) -> List[str]:
    """Split content into chunks of at most max_tokens tokens, splitting on blank lines."""
    max_chars = max_tokens * _CHARS_PER_TOKEN
    if len(content) <= max_chars:
        return [content]

    paragraphs = content.split("\n\n")
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        if len(para) > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            for i in range(0, len(para), max_chars):
                chunks.append(para[i:i + max_chars])
            continue
        if current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


async def seed_project(project: dict, kb, dry_run: bool = False) -> int:
    """Index one project. Returns number of documents written."""
    local_path = project.get("local_path")
    if not local_path:
        print(f"  SKIP {project['name']}: local_path not set")
        return 0

    root = Path(local_path)
    if not root.exists():
        print(f"  SKIP {project['name']}: local_path {local_path} does not exist")
        return 0

    files = get_priority_files(root)
    doc_count = 0
    t0 = time.monotonic()

    for fpath in files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"    WARN: could not read {fpath}: {e}")
            continue

        rel_path = str(fpath.relative_to(root))
        doc_type = "readme" if fpath.name in {"README.md", "CLAUDE.md"} else "file_summary"
        chunks = chunk_file(content)

        for idx, chunk in enumerate(chunks):
            if dry_run:
                print(f"    [dry-run] {rel_path} chunk {idx} ({len(chunk)} chars)")
            else:
                await kb.write_project_doc(
                    project_id=project["id"],
                    project_name=project["name"],
                    content=chunk,
                    doc_type=doc_type,
                    file_path=rel_path,
                    chunk_index=idx,
                )
            doc_count += 1

    elapsed = time.monotonic() - t0
    print(f"  {project['name']}: indexed {doc_count} docs ({len(files)} files) in {elapsed:.1f}s")
    return doc_count


async def main(project_slugs: Optional[List[str]] = None, dry_run: bool = False) -> None:
    from services.db import get_db_service
    from services.knowledge_base import get_kb_service

    db = get_db_service()
    await db.connect()
    kb = get_kb_service()

    query = "SELECT id, name, slug, local_path FROM projects WHERE status = 'active'"
    params: list = []
    if project_slugs:
        placeholders = ", ".join(f"${i+1}" for i in range(len(project_slugs)))
        query += f" AND slug IN ({placeholders})"
        params = project_slugs

    projects = await db.fetch_all(query, *params)
    if not projects:
        print("No matching active projects found.")
        return

    total = 0
    for project in projects:
        total += await seed_project(dict(project), kb, dry_run=dry_run)

    await db.disconnect()
    print(f"\nDone. Total documents indexed: {total}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the CRUZ knowledge base")
    parser.add_argument("--projects", nargs="*", help="Project slugs to seed")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    args = parser.parse_args()
    asyncio.run(main(project_slugs=args.projects, dry_run=args.dry_run))
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/scripts/test_seed_kb.py -v
```

- [ ] **Step 5: Smoke-test dry run**

```bash
python scripts/seed_kb.py --dry-run 2>&1 | head -20
```

Expected: prints projects and "[dry-run]" lines, or "No matching active projects" if DB not running.

- [ ] **Step 6: Commit**

```bash
git add scripts/seed_kb.py tests/scripts/test_seed_kb.py
git commit -m "feat(kb): add seed_kb.py codebase indexer"
```

---

## Chunk 5: Agent retrofit batch 1 (FORGE, ECHO, REACH, CATCH, PM, TITAN, MARK)

**The retrofit pattern is identical for every agent. The steps below use FORGE as the full example; each subsequent agent repeats all 6 steps with its own file paths and ring names.**

### Task 8: Retrofit FORGE

**Files:**
- Modify: `agents/forge/forge_agent.py`
- Modify: `tests/agents/test_forge_agent.py`

- [ ] **Step 1: Add KB mock to the FORGE test file**

Find the test file's top-level fixture or setUp and add:

```python
# At the top of tests/agents/test_forge_agent.py, inside a fixture or as a module patch:
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture(autouse=True)
def mock_kb_service():
    """Mock KnowledgeBaseService for all FORGE tests."""
    mock_kb = MagicMock()
    mock_kb.build_agent_context = AsyncMock(return_value="")
    mock_kb.record_agent_activity = AsyncMock()
    with patch("agents.forge.forge_agent.get_kb_service", return_value=mock_kb):
        yield mock_kb
```

- [ ] **Step 2: Add one regression test**

```python
@pytest.mark.asyncio
async def test_forge_calls_kb_build_context(mock_kb_service):
    """build_agent_context must be called with KNOWLEDGE_RINGS at start of process."""
    agent = ForgeAgent()
    # Use a minimal mock that returns immediately
    with patch("agents.forge.forge_agent.llm_chat") as mock_chat:
        mock_chat.return_value = MagicMock(
            content=[MagicMock(type="text", text="done")],
            stop_reason="end_turn",
        )
        input_data = {
            "task": "write a hello function",
            "context": {},
            "trace_id": "t-forge-kb",
            "conversation_id": "conv-1",
        }
        await agent.process(input_data)
    mock_kb_service.build_agent_context.assert_awaited_once()
    mock_kb_service.record_agent_activity.assert_awaited_once()
```

- [ ] **Step 3: Run — expect FAIL (KB not yet wired)**

```bash
pytest tests/agents/test_forge_agent.py::test_forge_calls_kb_build_context -v
```

- [ ] **Step 4: Add `KNOWLEDGE_RINGS` and KB calls to FORGE**

In `agents/forge/forge_agent.py`, add after the class definition line:

```python
class ForgeAgent(BaseAgent):
    KNOWLEDGE_RINGS: list[str] = ["cruz_activities", "cruz_projects_docs"]
```

At the top of `process()`, before any existing logic, add:

```python
from services.knowledge_base import get_kb_service  # add to imports at top of file

# Inside process(), first two lines:
kb = get_kb_service()
kb_context = await kb.build_agent_context(
    input["task"], self.KNOWLEDGE_RINGS, input["trace_id"],
    project_id=input["context"].get("project_id"),
)
```

Inject `kb_context` into the system prompt (before the existing `_SYSTEM_PROMPT` usage):

```python
system = _SYSTEM_PROMPT
if kb_context:
    system = kb_context + "\n\n" + system
```

At the bottom of `process()`, before `return output`, add:

```python
await kb.record_agent_activity(
    "forge", input["task"],
    str(output.get("result", ""))[:200],
    output["success"], input["trace_id"],
    project_id=input["context"].get("project_id"),
    tokens_used=output.get("tokens_used"),
)
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest tests/agents/test_forge_agent.py -v
```

- [ ] **Step 6: Commit**

```bash
git add agents/forge/forge_agent.py tests/agents/test_forge_agent.py
git commit -m "feat(kb): retrofit FORGE agent with KB reads/writes"
```

---

### Task 9–14: Retrofit ECHO, REACH, CATCH, PM, TITAN, MARK

**Each agent follows the identical 6-step pattern from Task 8. Ring assignments:**

| Agent | File | KNOWLEDGE_RINGS |
|---|---|---|
| ECHO | `agents/echo/echo_agent.py` | `["cruz_activities", "cruz_projects_docs", "cruz_user_patterns"]` |
| REACH | `agents/reach/reach_agent.py` | `["cruz_activities", "cruz_domain_knowledge"]` |
| CATCH | `agents/catch/catch_agent.py` | `["cruz_activities", "cruz_projects_docs"]` |
| PM | `agents/pm/pm_agent.py` | `["cruz_activities", "cruz_projects_docs"]` |
| TITAN | `agents/titan/titan_agent.py` | `["cruz_activities", "cruz_projects_docs"]` |
| MARK | `agents/mark/mark_agent.py` | `["cruz_activities", "cruz_projects_docs"]` |

For each agent:

- [ ] **Add `mock_kb_service` autouse fixture to the agent's test file** (identical code to Task 8 Step 1, with the import path changed to `agents.<name>.<name>_agent.get_kb_service`)
- [ ] **Add `test_<agent>_calls_kb_build_context` regression test**
- [ ] **Run — expect FAIL** — command: `pytest tests/agents/test_<agent>_agent.py::test_<agent>_calls_kb_build_context -v` (substitute lowercase agent name)
- [ ] **Add `KNOWLEDGE_RINGS`, KB calls to the agent file** (same pattern as FORGE, using `agent_name="<lowercase>"`)
- [ ] **Run all agent tests — expect PASS** — command: `pytest tests/agents/test_<agent>_agent.py -v`
- [ ] **Commit** — one commit per agent: `feat(kb): retrofit ECHO agent`, etc.

---

## Chunk 6: Agent retrofit batch 2 (QT, SENTINEL, RAW, PULSE, GENERAL, CRUZ)

### Task 15–18: Retrofit QT, SENTINEL, PULSE, GENERAL

**Ring assignments:**

| Agent | File | KNOWLEDGE_RINGS |
|---|---|---|
| QT | `agents/qt/qt_agent.py` | `["cruz_activities", "cruz_projects_docs"]` |
| SENTINEL | `agents/sentinel/sentinel_agent.py` | `["cruz_activities", "cruz_projects_docs"]` |
| PULSE | `agents/pulse/pulse_agent.py` | `["cruz_activities", "cruz_domain_knowledge"]` |
| GENERAL | `agents/general/general_agent.py` | `["cruz_activities"]` |

Each agent follows the identical 6-step pattern from Task 8. Repeat in order for QT, SENTINEL, PULSE, GENERAL:

- [ ] **Add `mock_kb_service` autouse fixture** to the agent's test file (path: `agents.<name>.<name>_agent.get_kb_service`)
- [ ] **Add `test_<agent>_calls_kb_build_context` regression test**
- [ ] **Run — expect FAIL** — command: `pytest tests/agents/test_<agent>_agent.py::test_<agent>_calls_kb_build_context -v`
- [ ] **Add `KNOWLEDGE_RINGS` + KB calls to agent file** (same pattern as FORGE)
- [ ] **Run all agent tests — expect PASS** — command: `pytest tests/agents/test_<agent>_agent.py -v`
- [ ] **Commit per agent:**

```bash
# QT:
git add agents/qt/qt_agent.py tests/agents/test_qt_agent.py
git commit -m "feat(kb): retrofit QT agent with KB reads/writes"

# SENTINEL:
git add agents/sentinel/sentinel_agent.py tests/agents/test_sentinel_agent.py
git commit -m "feat(kb): retrofit SENTINEL agent with KB reads/writes"

# PULSE:
git add agents/pulse/pulse_agent.py tests/agents/test_pulse_agent.py
git commit -m "feat(kb): retrofit PULSE agent with KB reads/writes"

# GENERAL:
git add agents/general/general_agent.py tests/agents/test_general_agent.py
git commit -m "feat(kb): retrofit GENERAL agent with KB reads/writes"
```

---

### Task 20: Retrofit RAW — with `write_domain_knowledge`

**Files:**
- Modify: `agents/raw/raw_agent.py`
- Modify: `tests/agents/test_raw_agent.py`

RAW is the only agent that also writes to `cruz_domain_knowledge` after completing research.

- [ ] **Add mock fixture and two regression tests to `test_raw_agent.py`**:

```python
@pytest.fixture(autouse=True)
def mock_kb_service():
    mock_kb = MagicMock()
    mock_kb.build_agent_context = AsyncMock(return_value="")
    mock_kb.record_agent_activity = AsyncMock()
    mock_kb.write_domain_knowledge = AsyncMock()
    with patch("agents.raw.raw_agent.get_kb_service", return_value=mock_kb):
        yield mock_kb

@pytest.mark.asyncio
async def test_raw_calls_write_domain_knowledge(mock_kb_service):
    """RAW must write its research result to domain_knowledge ring."""
    agent = RawAgent()
    with patch("agents.raw.raw_agent.llm_chat") as mock_chat:
        mock_chat.return_value = MagicMock(
            content=[MagicMock(type="text", text="research result")],
            stop_reason="end_turn",
        )
        await agent.process({
            "task": "research Playwright selectors",
            "context": {"topic": "Playwright selectors"},
            "trace_id": "t-raw-1",
            "conversation_id": "c1",
        })
    mock_kb_service.write_domain_knowledge.assert_awaited_once()
```

- [ ] **Add KNOWLEDGE_RINGS + KB calls to `raw_agent.py`**:

```python
KNOWLEDGE_RINGS: list[str] = ["cruz_activities", "cruz_domain_knowledge"]
```

After completing research in `process()`, add:

```python
topic = input["context"].get("topic", input["task"][:60])
await kb.write_domain_knowledge(
    content=str(output.get("result", ""))[:1000],
    topic=topic,
    source="raw_agent",
    trace_id=input["trace_id"],
)
```

- [ ] **Run all RAW tests — expect PASS**

```bash
pytest tests/agents/test_raw_agent.py -v
```

- [ ] **Commit**

```bash
git add agents/raw/raw_agent.py tests/agents/test_raw_agent.py
git commit -m "feat(kb): retrofit RAW agent with KB reads/writes + domain knowledge write"
```

---

### Task 21: Retrofit CRUZ — with `record_pattern_observation` tool

**Files:**
- Modify: `agents/cruz/cruz_agent.py`
- Modify: `tests/agents/test_cruz_agent.py`

CRUZ is the only agent that also calls `observe_interaction()` when it detects a behavioral correction in the user's message.

- [ ] **Add mock fixture + regression tests to `test_cruz_agent.py`**:

```python
@pytest.fixture(autouse=True)
def mock_kb_service():
    mock_kb = MagicMock()
    mock_kb.build_agent_context = AsyncMock(return_value="")
    mock_kb.record_agent_activity = AsyncMock()
    mock_kb.observe_interaction = AsyncMock()
    with patch("agents.cruz.cruz_agent.get_kb_service", return_value=mock_kb):
        yield mock_kb

@pytest.mark.asyncio
async def test_cruz_uses_kb_context(mock_kb_service):
    """CRUZ should call build_agent_context on every process() call."""
    agent = CruzAgent()
    with patch("agents.cruz.cruz_agent.llm_chat") as mock_chat:
        mock_chat.return_value = MagicMock(
            content=[MagicMock(type="text", text="response")],
            stop_reason="end_turn",
        )
        await agent.process({
            "task": "what can you do?",
            "context": {},
            "trace_id": "t-cruz-kb",
            "conversation_id": "c1",
        })
    mock_kb_service.build_agent_context.assert_awaited_once()
```

- [ ] **Add `KNOWLEDGE_RINGS` + KB calls to `cruz_agent.py`**:

```python
KNOWLEDGE_RINGS: list[str] = ["cruz_activities", "cruz_user_patterns"]
```

Add `record_pattern_observation` to CRUZ's tool list:

```python
{
    "name": "record_pattern_observation",
    "description": (
        "Call this when the user's message is a behavioral correction — "
        "e.g. 'no, use formal tone', 'always use snake_case', "
        "'stop adding comments'. Records the observation toward learning "
        "Darshan's preferences. agent_name is the agent whose output was corrected."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_name":        {"type": "string"},
            "interaction_type":  {"type": "string",
                                  "description": "e.g. email_draft_edited, code_edited"},
            "observed_pattern":  {"type": "string",
                                  "description": "The preference rule observed"},
        },
        "required": ["agent_name", "interaction_type", "observed_pattern"],
    },
},
```

Handle `record_pattern_observation` in the tool dispatch block:

```python
elif tool_name == "record_pattern_observation":
    await kb.observe_interaction(
        tool_input.get("agent_name", "unknown"),
        tool_input.get("interaction_type", "unknown"),
        tool_input.get("observed_pattern", ""),
    )
    tool_result = {"recorded": True}
```

- [ ] **Run all CRUZ tests — expect PASS**

```bash
pytest tests/agents/test_cruz_agent.py -v
```

- [ ] **Run entire test suite to verify no regressions**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all existing 1,073+ tests passing.

- [ ] **Commit**

```bash
git add agents/cruz/cruz_agent.py tests/agents/test_cruz_agent.py
git commit -m "feat(kb): retrofit CRUZ agent with KB context + record_pattern_observation tool"
```

---

## Chunk 7: Integration tests + exit gate setup

### Task 22: Integration test — full KB loop

**Files:**
- Create: `tests/integration/test_kb_integration.py`

- [ ] **Step 1: Write integration tests**

```python
# tests/integration/test_kb_integration.py
"""
Integration tests for KnowledgeBaseService against real Qdrant.

Run with: DATABASE_URL_TEST=... pytest tests/integration/test_kb_integration.py -v

Requires: Qdrant running on localhost:6333
          PostgreSQL test DB with migration 0004 applied
"""
from __future__ import annotations

import asyncio
import os

import pytest

# Skip unless integration test flag is set
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_KB_INTEGRATION") != "1",
    reason="Set RUN_KB_INTEGRATION=1 to run KB integration tests",
)

from services.embedding import get_embedding_service
from services.knowledge_base import KnowledgeBaseService
from services.qdrant import get_qdrant_service


@pytest.fixture
async def kb():
    from services.db import get_db_service
    qdrant = get_qdrant_service()
    await qdrant.connect()
    db = get_db_service()
    await db.connect()
    svc = KnowledgeBaseService(qdrant, get_embedding_service(), db)
    yield svc
    await qdrant.disconnect()
    await db.disconnect()


@pytest.mark.asyncio
async def test_activity_write_then_read(kb):
    """Write an activity, then verify it appears in build_agent_context."""
    await kb.record_agent_activity(
        "forge", "write endpoint for listing orders",
        "created GET /api/orders endpoint", True, "integ-trace-1",
    )
    ctx = await kb.build_agent_context(
        "add another orders endpoint", ["cruz_activities"], "integ-trace-2"
    )
    assert "forge" in ctx.lower() or "orders" in ctx.lower()


@pytest.mark.asyncio
async def test_project_doc_write_then_read(kb):
    """Write a project doc, then verify it surfaces in context."""
    await kb.write_project_doc(
        "test-proj-id", "Test Project",
        "Stack: FastAPI, PostgreSQL 15, deployed on Railway",
        "readme", file_path="README.md", chunk_index=0,
    )
    ctx = await kb.build_agent_context(
        "add new feature to the project",
        ["cruz_projects_docs"], "integ-trace-3",
        project_id="test-proj-id",
    )
    assert "PostgreSQL" in ctx or "FastAPI" in ctx


@pytest.mark.asyncio
async def test_empty_rings_return_empty_string(kb):
    ctx = await kb.build_agent_context(
        "task", ["cruz_user_patterns"], "integ-trace-4"
    )
    assert ctx == "" or isinstance(ctx, str)
```

- [ ] **Step 2: Run unit tests to verify integration tests are skipped by default**

```bash
pytest tests/integration/test_kb_integration.py -v
```

Expected: `SKIPPED` (3 tests) — `RUN_KB_INTEGRATION` not set.

- [ ] **Step 3: Run against real services (when Qdrant + PG available)**

```bash
RUN_KB_INTEGRATION=1 \
DATABASE_URL=postgresql://cruz:cruz@localhost:5432/cruz_test \
pytest tests/integration/test_kb_integration.py -v
```

Expected: all 3 PASS.

- [ ] **Step 4: Run full test suite one final time**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_kb_integration.py
git commit -m "test(kb): add integration tests for full KB read/write loop"
```

---

### Task 23: Populate `local_path` for all 5 projects

**This is a manual prerequisite for the seed run (Day 4 in the spec).**

- [ ] **Step 1: Update project rows with local_path**

```sql
-- Run against production DB. Replace paths with actual locations on Mac Mini.
UPDATE projects SET local_path = '/Users/darshan/Projects/ama-solutions'  WHERE slug = 'ama-solutions';
UPDATE projects SET local_path = '/Users/darshan/Projects/shooterista'    WHERE slug = 'shooterista';
UPDATE projects SET local_path = '/Users/darshan/Projects/suiteadvisors'  WHERE slug = 'suiteadvisors';
UPDATE projects SET local_path = '/Users/darshan/Projects/asia-capital'   WHERE slug = 'asia-capital';
UPDATE projects SET local_path = '/Users/darshan/Projects/midar'          WHERE slug = 'midar';
```

Or via CRUZ: "Hey CRUZ, remember AMA Solutions is at ~/Projects/ama-solutions"

- [ ] **Step 2: Run seed script**

```bash
python scripts/seed_kb.py
```

Expected: 5 project lines with doc counts, no SKIP lines.

---

### Task 24: Exit gate verification

- [ ] **Step 1: Confirm 13 agents retrofitted**

```bash
grep -l "KNOWLEDGE_RINGS" agents/*/
```

Expected: 13 files (all agents except `relay/relay_agent.py`).

```bash
pytest tests/agents/ -v --tb=short 2>&1 | tail -5
```

Expected: all passing.

- [ ] **Step 2: Check activities count (after daily use)**

```bash
python -c "
import asyncio
from services.qdrant import get_qdrant_service

async def count():
    q = get_qdrant_service()
    await q.connect()
    c = await q.client.count('cruz_activities')
    print('cruz_activities count:', c.count)
    await q.disconnect()

asyncio.run(count())
"
```

Gate requires ≥100. Continue daily use until threshold reached.

- [ ] **Step 3: Look up AMA Solutions project UUID**

```bash
psql "${DATABASE_URL}" -c "SELECT id FROM projects WHERE slug = 'ama-solutions'"
```

Note the UUID. Use it in place of `REPLACE_WITH_AMA_UUID` in the scripts below.

- [ ] **Step 3b: Create `docs/perf/sp2-ab-test.md` with results template**

```bash
mkdir -p docs/perf
cat > docs/perf/sp2-ab-test.md << 'EOF'
# SP2 A/B Test Results

Task: "Add a new REST endpoint to the AMA Solutions backend for listing active orders by client"

## Round 1
- Winner (blind pick — don't label until after): A / B

## Round 2
- Winner (blind pick): A / B

## Round 3
- Winner (blind pick): A / B

## Verdict
KB wins: X/3 rounds — PASS (≥2) / FAIL (<2)
EOF
```

- [ ] **Step 3c: Run 3 paired rounds — record each winner before revealing labels**

For each round (increment trace suffix `-1` → `-2` → `-3`):

```bash
# Run A — KB disabled (build_agent_context patched to return empty string)
python -c "
import asyncio
from unittest.mock import AsyncMock, patch
from agents.forge.forge_agent import ForgeAgent

AMA_UUID = 'REPLACE_WITH_AMA_UUID'

async def run():
    agent = ForgeAgent()
    with patch('agents.forge.forge_agent.get_kb_service') as mock_factory:
        mock_kb = mock_factory.return_value
        mock_kb.build_agent_context = AsyncMock(return_value='')
        mock_kb.record_agent_activity = AsyncMock()
        result = await agent.process({
            'task': 'Add a new REST endpoint to the AMA Solutions backend for listing active orders by client',
            'context': {'project_id': AMA_UUID},
            'trace_id': 'ab-no-kb-1',
            'conversation_id': 'ab-test',
        })
    print(result.get('result', ''))

asyncio.run(run())
"
```

```bash
# Run B — KB enabled (normal execution, no patches)
python -c "
import asyncio
from agents.forge.forge_agent import ForgeAgent

AMA_UUID = 'REPLACE_WITH_AMA_UUID'

async def run():
    agent = ForgeAgent()
    result = await agent.process({
        'task': 'Add a new REST endpoint to the AMA Solutions backend for listing active orders by client',
        'context': {'project_id': AMA_UUID},
        'trace_id': 'ab-with-kb-1',
        'conversation_id': 'ab-test',
    })
    print(result.get('result', ''))

asyncio.run(run())
"
```

Pick the better output without knowing which is A or B. Fill in `docs/perf/sp2-ab-test.md`. Gate passes if KB wins ≥2/3.

- [ ] **Step 4: Run latency comparison**

```bash
./scripts/load/run_scenarios.sh all
```

Record P95 in `docs/perf/load_results.md`. Gate requires regression <20% vs SP1 baseline.

- [ ] **Step 5: Write sign-off to PROGRESS.md**

Append under Phase 6 (or create SP2 section):

```
SP2 sign-off — 2026-MM-DD
  agents_retrofitted:  13/13 retrofitted + 1 exempt (RELAY — charter override §11)
  activities_count:    XXX records
  ab_test:             KB wins X/3 rounds (see docs/perf/sp2-ab-test.md)
  p95_regression:      X% (within 20% limit)
  commit:              <sha>
```

- [ ] **Step 6: Final commit**

```bash
git add PROGRESS.md docs/perf/sp2-ab-test.md docs/perf/load_results.md
git commit -m "chore(sp2): SP2 exit gate sign-off — 13/13 retrofitted + 1 exempt (RELAY)"
```
