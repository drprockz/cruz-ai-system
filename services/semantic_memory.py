"""
SemanticMemoryService — vector-backed long-term memory for CRUZ.

Combines EmbeddingService + QdrantService to give CRUZ the ability to
recall relevant past exchanges across conversation sessions.

Usage pattern:
  # On each CRUZ request — retrieve context
  hits = await semantic_memory.search_similar(user_task, limit=10)
  messages = [*hits, *session_history, {"role": "user", "content": task}]

  # After a successful response — store both turns
  await semantic_memory.store(id=uuid, role="user",    content=task,     conversation_id=cid)
  await semantic_memory.store(id=uuid, role="assistant", content=response, conversation_id=cid)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from services.embedding import EmbeddingService
from services.qdrant import QdrantService

logger = logging.getLogger("cruz.services.semantic_memory")


class SemanticMemoryService:
    """Stores and retrieves conversation exchanges as vector embeddings."""

    COLLECTION = "cruz_memories"
    VECTOR_SIZE = 384  # all-MiniLM-L6-v2 output dimensions

    def __init__(self, qdrant: QdrantService, embedding: EmbeddingService) -> None:
        self._qdrant = qdrant
        self._embedding = embedding

    async def store(
        self,
        id: str,
        role: str,
        content: str,
        conversation_id: str,
    ) -> None:
        """
        Encode `content` and upsert the vector into Qdrant.

        Args:
            id:              Stable unique ID (use PostgreSQL message UUID).
            role:            "user" or "assistant".
            content:         The message text to embed and store.
            conversation_id: Source conversation — stored in payload for filtering.
        """
        vector = self._embedding.encode(content)
        await self._qdrant.ensure_collection(self.COLLECTION, self.VECTOR_SIZE)
        await self._qdrant.upsert(
            collection=self.COLLECTION,
            id=id,
            vector=vector,
            payload={
                "role": role,
                "content": content,
                "conversation_id": conversation_id,
            },
        )

    async def search_similar(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, str]]:
        """
        Return the top-`limit` most semantically similar past exchanges.

        Returns a list of {role, content} dicts ready to prepend to
        Claude's messages array.
        """
        query_vector = self._embedding.encode(query)
        hits = await self._qdrant.search(
            collection=self.COLLECTION,
            query_vector=query_vector,
            limit=limit,
        )
        return [
            {"role": hit["payload"]["role"], "content": hit["payload"]["content"]}
            for hit in hits
        ]
