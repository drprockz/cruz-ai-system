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
