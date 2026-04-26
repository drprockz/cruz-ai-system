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
        import time
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
        import time
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
