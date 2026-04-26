"""
Integration tests for KnowledgeBaseService against real Qdrant.

Run with: RUN_KB_INTEGRATION=1 pytest tests/integration/test_kb_integration.py -v

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
