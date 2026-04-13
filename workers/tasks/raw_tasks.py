"""
RAW worker task — 3 AM tech research and dependency update scan.

Runs two jobs in sequence:
  1. Dependency scan (pip list --outdated → Llama analysis → Qdrant)
  2. Tech research on topics from RESEARCH_TOPICS env var (comma-separated)

Uses RawAgent which calls Llama 3.1 8B locally (zero token cost).
"""

from __future__ import annotations

import logging
import os
import uuid

from agents.raw.raw_agent import RawAgent
from agents.base_agent import AgentInput

logger = logging.getLogger("cruz.workers.raw")

_DEFAULT_TOPICS = [
    "Python async frameworks 2026",
    "FastAPI latest security advisories",
    "Docker and containerisation best practices",
]


async def run_raw(ctx: dict) -> None:
    """
    3 AM research update task.

    Scans pip dependencies for outdated packages, then researches a
    rotating list of tech topics. All findings stored in Qdrant.
    """
    agent = RawAgent()

    # ── 1. Dependency scan ────────────────────────────────────────────
    trace_id = str(uuid.uuid4())
    dep_input: AgentInput = {
        "task": "Scan pip dependencies for outdated packages",
        "context": {"mode": "dependencies"},
        "trace_id": trace_id,
        "conversation_id": f"cron-raw-deps-{trace_id}",
    }
    try:
        result = await agent.process(dep_input)
        if result["success"]:
            items = result["result"].get("items", [])
            logger.info("[RAW] Dependency scan complete — %d outdated packages", len(items))
        else:
            logger.warning("[RAW] Dependency scan failed: %s", result["error"])
    except Exception as exc:
        logger.error("[RAW] Dependency scan unexpected error: %s", exc)

    # ── 2. Tech research topics ───────────────────────────────────────
    topics_env = os.environ.get("RAW_RESEARCH_TOPICS", "")
    topics = [t.strip() for t in topics_env.split(",") if t.strip()] or _DEFAULT_TOPICS

    for topic in topics:
        trace_id = str(uuid.uuid4())
        research_input: AgentInput = {
            "task": topic,
            "context": {"mode": "research", "topic": topic},
            "trace_id": trace_id,
            "conversation_id": f"cron-raw-research-{trace_id}",
        }
        try:
            result = await agent.process(research_input)
            if result["success"]:
                logger.info("[RAW] Research complete — topic: %s", topic)
            else:
                logger.warning("[RAW] Research failed for '%s': %s", topic, result["error"])
        except Exception as exc:
            logger.error("[RAW] Research unexpected error for '%s': %s", topic, exc)
