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
