"""
Tests for SemanticMemoryService — Qdrant-backed vector memory.

SemanticMemoryService combines EmbeddingService + QdrantService to:
  - store(id, role, content, conversation_id) → encode text, upsert to Qdrant
  - search_similar(query, limit) → encode query, search Qdrant, return [{role, content}]

The COLLECTION constant must be "cruz_memories".
The VECTOR_SIZE constant must be 384 (all-MiniLM-L6-v2).

RED phase — must fail before production code exists.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.semantic_memory import SemanticMemoryService


def _make_embedding_svc(vector=None):
    svc = MagicMock()
    svc.encode = MagicMock(return_value=vector or [0.1] * 384)
    return svc


def _make_qdrant_svc(hits=None):
    svc = AsyncMock()
    svc.ensure_collection = AsyncMock()
    svc.upsert = AsyncMock()
    default_hits = [
        {"score": 0.9, "payload": {"role": "user", "content": "prior question", "conversation_id": "conv-old"}},
        {"score": 0.8, "payload": {"role": "assistant", "content": "prior answer", "conversation_id": "conv-old"}},
    ]
    svc.search = AsyncMock(return_value=hits if hits is not None else default_hits)
    return svc


class TestSemanticMemoryServiceInterface:
    def test_can_be_instantiated(self):
        svc = SemanticMemoryService(_make_qdrant_svc(), _make_embedding_svc())
        assert svc is not None

    def test_has_store_method(self):
        svc = SemanticMemoryService(_make_qdrant_svc(), _make_embedding_svc())
        assert hasattr(svc, "store")

    def test_has_search_similar_method(self):
        svc = SemanticMemoryService(_make_qdrant_svc(), _make_embedding_svc())
        assert hasattr(svc, "search_similar")

    def test_collection_name_is_cruz_memories(self):
        assert SemanticMemoryService.COLLECTION == "cruz_memories"

    def test_vector_size_is_384(self):
        assert SemanticMemoryService.VECTOR_SIZE == 384


class TestSemanticMemoryStore:
    async def test_store_encodes_content(self):
        emb = _make_embedding_svc()
        svc = SemanticMemoryService(_make_qdrant_svc(), emb)

        await svc.store(
            id="msg-001",
            role="user",
            content="unique-content-to-encode",
            conversation_id="conv-1",
        )

        emb.encode.assert_called_once_with("unique-content-to-encode")

    async def test_store_calls_ensure_collection(self):
        qdrant = _make_qdrant_svc()
        svc = SemanticMemoryService(qdrant, _make_embedding_svc())

        await svc.store(id="msg-001", role="user", content="hello", conversation_id="conv-1")

        qdrant.ensure_collection.assert_called_once_with("cruz_memories", 384)

    async def test_store_upserts_to_qdrant(self):
        qdrant = _make_qdrant_svc()
        svc = SemanticMemoryService(qdrant, _make_embedding_svc())

        await svc.store(id="msg-abc", role="user", content="text", conversation_id="conv-1")

        qdrant.upsert.assert_called_once()

    async def test_store_upsert_includes_id(self):
        qdrant = _make_qdrant_svc()
        svc = SemanticMemoryService(qdrant, _make_embedding_svc())

        await svc.store(id="unique-msg-id-xyz", role="user", content="text", conversation_id="c1")

        call = str(qdrant.upsert.call_args)
        assert "unique-msg-id-xyz" in call

    async def test_store_payload_includes_role(self):
        qdrant = _make_qdrant_svc()
        svc = SemanticMemoryService(qdrant, _make_embedding_svc())

        await svc.store(id="m1", role="assistant", content="text", conversation_id="c1")

        call = str(qdrant.upsert.call_args)
        assert "assistant" in call

    async def test_store_payload_includes_content(self):
        qdrant = _make_qdrant_svc()
        svc = SemanticMemoryService(qdrant, _make_embedding_svc())

        await svc.store(id="m1", role="user", content="unique-stored-content-abc", conversation_id="c1")

        call = str(qdrant.upsert.call_args)
        assert "unique-stored-content-abc" in call

    async def test_store_payload_includes_conversation_id(self):
        qdrant = _make_qdrant_svc()
        svc = SemanticMemoryService(qdrant, _make_embedding_svc())

        await svc.store(id="m1", role="user", content="text", conversation_id="unique-conv-id-456")

        call = str(qdrant.upsert.call_args)
        assert "unique-conv-id-456" in call


class TestSemanticMemorySearchSimilar:
    async def test_search_similar_returns_list(self):
        svc = SemanticMemoryService(_make_qdrant_svc(), _make_embedding_svc())

        results = await svc.search_similar("what did we discuss?", limit=10)

        assert isinstance(results, list)

    async def test_search_similar_encodes_query(self):
        emb = _make_embedding_svc()
        svc = SemanticMemoryService(_make_qdrant_svc(), emb)

        await svc.search_similar("unique-query-text-xyz", limit=5)

        emb.encode.assert_called_once_with("unique-query-text-xyz")

    async def test_search_similar_calls_qdrant_search(self):
        qdrant = _make_qdrant_svc()
        svc = SemanticMemoryService(qdrant, _make_embedding_svc())

        await svc.search_similar("query", limit=10)

        qdrant.search.assert_called_once()

    async def test_search_similar_passes_limit(self):
        qdrant = _make_qdrant_svc()
        svc = SemanticMemoryService(qdrant, _make_embedding_svc())

        await svc.search_similar("query", limit=7)

        call = str(qdrant.search.call_args)
        assert "7" in call

    async def test_search_similar_result_has_role_and_content(self):
        svc = SemanticMemoryService(_make_qdrant_svc(), _make_embedding_svc())

        results = await svc.search_similar("anything", limit=5)

        assert "role" in results[0]
        assert "content" in results[0]

    async def test_search_similar_strips_qdrant_metadata(self):
        """Only role + content returned — no score, conversation_id, etc."""
        svc = SemanticMemoryService(_make_qdrant_svc(), _make_embedding_svc())

        results = await svc.search_similar("anything", limit=5)

        assert "score" not in results[0]
        assert "conversation_id" not in results[0]

    async def test_search_similar_returns_empty_on_no_hits(self):
        svc = SemanticMemoryService(_make_qdrant_svc(hits=[]), _make_embedding_svc())

        results = await svc.search_similar("query", limit=10)

        assert results == []
