"""
QdrantService — async Qdrant vector database client.

Used by CRUZ's semantic memory layer to store and retrieve
embeddings of past conversation exchanges.

Collection layout (semantic_memory):
  vector  : float[384]  — all-MiniLM-L6-v2 embedding of the exchange text
  payload : {
      role            : "user" | "assistant",
      content         : str,
      conversation_id : str,
      trace_id        : str,
  }
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

logger = logging.getLogger("cruz.services.qdrant")

_QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

# Module-level singleton
_instance: Optional["QdrantService"] = None


def get_qdrant_service() -> "QdrantService":
    """Return the module-level QdrantService singleton."""
    global _instance
    if _instance is None:
        _instance = QdrantService()
    return _instance


class QdrantService:
    """Async wrapper around qdrant-client for CRUZ semantic memory."""

    def __init__(self, url: Optional[str] = None) -> None:
        self.url: str = url or _QDRANT_URL
        self.client: Optional[AsyncQdrantClient] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Initialise the async Qdrant client."""
        self.client = AsyncQdrantClient(url=self.url)
        logger.info("QdrantService connected to %s", self.url)

    async def disconnect(self) -> None:
        """Close the async Qdrant client."""
        if self.client is not None:
            await self.client.close()
            self.client = None
            logger.info("QdrantService disconnected")

    def _require_client(self) -> AsyncQdrantClient:
        """Raise a clear error if connect() was never called."""
        if self.client is None:
            raise RuntimeError(
                "QdrantService is not connected. Call await qdrant.connect() "
                "first (or verify Qdrant is running at "
                f"{self.url})."
            )
        return self.client

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Return True if Qdrant is reachable, False otherwise."""
        if self.client is None:
            return False
        try:
            await self.client.get_collections()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    async def ensure_collection(self, name: str, vector_size: int) -> None:
        """
        Create the named collection if it does not already exist.

        Uses cosine distance — appropriate for sentence-transformer embeddings.
        """
        client = self._require_client()
        exists = await client.collection_exists(name)
        if exists:
            return

        await client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s' (dim=%d)", name, vector_size)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def upsert(
        self,
        collection: str,
        id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        """
        Insert or overwrite a single vector point.

        Args:
            collection: Target collection name.
            id:         Stable string ID (e.g. message UUID from PostgreSQL).
            vector:     Dense embedding (must match collection vector_size).
            payload:    Arbitrary metadata stored alongside the vector.
        """
        client = self._require_client()
        await client.upsert(
            collection_name=collection,
            points=[PointStruct(id=id, vector=vector, payload=payload)],
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def search(
        self,
        collection: str,
        query_vector: List[float],
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Return the top-`limit` most similar vectors to `query_vector`.

        Each result is a dict with:
          score   : float  — cosine similarity (higher = more similar)
          payload : dict   — the metadata stored at upsert time
        """
        client = self._require_client()
        # qdrant-client 1.10+ replaced `.search()` with `.query_points()`
        # which returns a QueryResponse object exposing `.points`. Older
        # `.search()` is gone in the 1.16+ SDK shipped here.
        resp = await client.query_points(
            collection_name=collection,
            query=query_vector,
            limit=limit,
        )
        hits = getattr(resp, "points", resp)
        return [{"score": hit.score, "payload": hit.payload} for hit in hits]
