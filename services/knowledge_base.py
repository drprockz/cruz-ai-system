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
from services.llm import chat as llm_chat
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

    # ── WRITE — user patterns (explicit) ─────────────────────────────

    async def write_user_pattern(
        self,
        content: str,
        pattern_type: str,
        source: str = "explicit",
        agent_name: Optional[str] = None,
    ) -> None:
        """Write a pattern immediately. Bypasses the observation threshold."""
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
        try:
            row_id = str(uuid.uuid4())
            # Upsert a counter row keyed on (pattern_type, content, source)
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
            row = await self._db.fetchrow(
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

    # ── WRITE — domain knowledge ──────────────────────────────────────

    async def write_domain_knowledge(
        self,
        content: str,
        topic: str,
        source: str = "raw_agent",
        trace_id: Optional[str] = None,
    ) -> None:
        """Upsert a domain knowledge chunk into cruz_domain_knowledge."""
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

    # ── Internal helpers ──────────────────────────────────────────────

    def _point_id(self, *parts: str) -> str:
        """Deterministic 32-char hex ID from arbitrary string parts."""
        raw = "".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
