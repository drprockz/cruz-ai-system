"""
Tests for QdrantService — async Qdrant vector DB client.

QdrantService wraps qdrant-client and exposes:
  - connect()                                    → initialise async client
  - health_check()                               → bool
  - ensure_collection(name, vector_size)         → create if not exists
  - upsert(collection, id, vector, payload)      → store vector + metadata
  - search(collection, query_vector, limit)      → list[{score, payload}]

All I/O is mocked — no real Qdrant instance required.

RED phase — must fail before production code exists.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.qdrant import QdrantService, get_qdrant_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_qdrant_client() -> MagicMock:
    """Mock qdrant_client.AsyncQdrantClient."""
    client = MagicMock()

    # collection_exists
    client.collection_exists = AsyncMock(return_value=False)

    # create_collection (no return value needed)
    client.create_collection = AsyncMock(return_value=None)

    # upsert
    client.upsert = AsyncMock(return_value=MagicMock(status="completed"))

    # query_points — qdrant-client >=1.10 returns a QueryResponse with .points
    # (the old .search() method was removed). Each point in .points is a
    # ScoredPoint-like object with .score + .payload.
    hit = MagicMock()
    hit.score = 0.92
    hit.payload = {"role": "user", "content": "My name is Darshan", "conversation_id": "conv-1"}
    query_resp = MagicMock()
    query_resp.points = [hit]
    client.query_points = AsyncMock(return_value=query_resp)

    # health check
    client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))

    return client


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class TestQdrantServiceInterface:
    def test_qdrant_service_can_be_instantiated(self):
        svc = QdrantService()
        assert svc is not None

    def test_has_connect_method(self):
        assert hasattr(QdrantService(), "connect")

    def test_has_health_check_method(self):
        assert hasattr(QdrantService(), "health_check")

    def test_has_ensure_collection_method(self):
        assert hasattr(QdrantService(), "ensure_collection")

    def test_has_upsert_method(self):
        assert hasattr(QdrantService(), "upsert")

    def test_has_search_method(self):
        assert hasattr(QdrantService(), "search")

    def test_get_qdrant_service_returns_instance(self):
        svc = get_qdrant_service()
        assert isinstance(svc, QdrantService)

    def test_get_qdrant_service_returns_same_instance(self):
        assert get_qdrant_service() is get_qdrant_service()


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------

class TestQdrantServiceConnect:
    async def test_connect_creates_async_client(self):
        svc = QdrantService(url="http://localhost:6333")
        mock_client = _make_qdrant_client()

        with patch("services.qdrant.AsyncQdrantClient", return_value=mock_client):
            await svc.connect()

        assert svc.client is mock_client

    async def test_connect_uses_configured_url(self):
        svc = QdrantService(url="http://custom-qdrant:6333")
        mock_client = _make_qdrant_client()

        with patch("services.qdrant.AsyncQdrantClient", return_value=mock_client) as MockClient:
            await svc.connect()

        call_args = MockClient.call_args
        url_used = call_args[1].get("url") or call_args[0][0]
        assert "custom-qdrant" in str(url_used)

    async def test_default_url_is_localhost_6333(self):
        import os
        os.environ.pop("QDRANT_URL", None)
        svc = QdrantService()
        assert "6333" in svc.url or "localhost" in svc.url


# ---------------------------------------------------------------------------
# health_check()
# ---------------------------------------------------------------------------

class TestQdrantServiceHealthCheck:
    async def test_health_check_returns_true_when_reachable(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()

        result = await svc.health_check()

        assert result is True

    async def test_health_check_returns_false_when_unreachable(self):
        svc = QdrantService()
        mock_client = _make_qdrant_client()
        mock_client.get_collections = AsyncMock(side_effect=Exception("connection refused"))
        svc.client = mock_client

        result = await svc.health_check()

        assert result is False

    async def test_health_check_returns_false_when_not_connected(self):
        svc = QdrantService()
        # client never set

        result = await svc.health_check()

        assert result is False


# ---------------------------------------------------------------------------
# ensure_collection()
# ---------------------------------------------------------------------------

class TestQdrantServiceEnsureCollection:
    async def test_creates_collection_if_not_exists(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()
        svc.client.collection_exists = AsyncMock(return_value=False)

        await svc.ensure_collection("test_collection", vector_size=384)

        svc.client.create_collection.assert_called_once()

    async def test_skips_creation_if_collection_exists(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()
        svc.client.collection_exists = AsyncMock(return_value=True)

        await svc.ensure_collection("existing_collection", vector_size=384)

        svc.client.create_collection.assert_not_called()

    async def test_create_collection_uses_provided_name(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()
        svc.client.collection_exists = AsyncMock(return_value=False)

        await svc.ensure_collection("my_special_collection", vector_size=384)

        call_args = str(svc.client.create_collection.call_args)
        assert "my_special_collection" in call_args

    async def test_create_collection_uses_provided_vector_size(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()
        svc.client.collection_exists = AsyncMock(return_value=False)

        await svc.ensure_collection("col", vector_size=768)

        call_args = str(svc.client.create_collection.call_args)
        assert "768" in call_args


# ---------------------------------------------------------------------------
# upsert()
# ---------------------------------------------------------------------------

class TestQdrantServiceUpsert:
    async def test_upsert_calls_client_upsert(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()

        await svc.upsert(
            collection="memories",
            id="msg-001",
            vector=[0.1] * 384,
            payload={"role": "user", "content": "hello"},
        )

        svc.client.upsert.assert_called_once()

    async def test_upsert_passes_collection_name(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()

        await svc.upsert(
            collection="cruz_memories",
            id="msg-001",
            vector=[0.0] * 384,
            payload={},
        )

        call_args = str(svc.client.upsert.call_args)
        assert "cruz_memories" in call_args

    async def test_upsert_passes_payload(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()

        await svc.upsert(
            collection="memories",
            id="msg-42",
            vector=[0.0] * 384,
            payload={"role": "assistant", "content": "unique-payload-content-xyz"},
        )

        call_args = str(svc.client.upsert.call_args)
        assert "unique-payload-content-xyz" in call_args


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------

class TestQdrantServiceSearch:
    async def test_search_returns_list(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()

        results = await svc.search(
            collection="memories",
            query_vector=[0.1] * 384,
            limit=10,
        )

        assert isinstance(results, list)

    async def test_search_result_has_score(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()

        results = await svc.search("memories", [0.1] * 384, limit=5)

        assert "score" in results[0]

    async def test_search_result_has_payload(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()

        results = await svc.search("memories", [0.1] * 384, limit=5)

        assert "payload" in results[0]

    async def test_search_payload_contains_content(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()

        results = await svc.search("memories", [0.1] * 384, limit=5)

        assert results[0]["payload"]["content"] == "My name is Darshan"

    async def test_search_respects_limit(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()

        await svc.search("memories", [0.1] * 384, limit=7)

        call_args = str(svc.client.query_points.call_args)
        assert "7" in call_args

    async def test_search_returns_empty_list_on_no_results(self):
        svc = QdrantService()
        svc.client = _make_qdrant_client()
        empty_resp = MagicMock()
        empty_resp.points = []
        svc.client.query_points = AsyncMock(return_value=empty_resp)

        results = await svc.search("memories", [0.0] * 384, limit=10)

        assert results == []


# ---------------------------------------------------------------------------
# None-guard contract (R5) — methods must raise RuntimeError when not connected,
# never AttributeError. This prevents cryptic crashes when Qdrant is down.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestQdrantServiceNoneGuards:
    async def test_ensure_collection_raises_runtime_error_when_not_connected(self):
        svc = QdrantService()
        # Never called svc.connect(), so svc.client is None
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.ensure_collection("memories", 384)

    async def test_upsert_raises_runtime_error_when_not_connected(self):
        svc = QdrantService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.upsert("memories", "id-1", [0.0] * 384, {"role": "user"})

    async def test_search_raises_runtime_error_when_not_connected(self):
        svc = QdrantService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.search("memories", [0.0] * 384, limit=5)

    async def test_runtime_error_names_the_service(self):
        """The error must mention Qdrant so the operator knows what to start."""
        svc = QdrantService()
        with pytest.raises(RuntimeError, match=r"(?i)qdrant"):
            await svc.ensure_collection("memories", 384)
