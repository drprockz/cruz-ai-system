"""
RAW worker task — 3 AM tech research and dependency update scan.

Stub implementation for Phase 3. The RAW agent (Llama 3.1 8B) that
scrapes Hacker News, checks npm/pip for outdated dependencies, and
stores findings in Qdrant is built in Phase 5.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("cruz.workers.raw")


async def run_raw(ctx: dict) -> None:
    """
    3 AM research update task.

    Phase 5: will call RawAgent to scan dependency updates,
    research relevant tech news, and store findings in Qdrant.
    """
    logger.info("[RAW] 3 AM research update — Phase 5 agent not yet built, skipping")
