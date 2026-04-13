"""
REACH worker task — 2 AM nightly lead discovery and outreach drafting.

Calls ReachAgent with a configurable criteria string from the REACH_CRITERIA
env var. The generated leads and outreach drafts are stored as the agent result
(requires_approval=True — sending is always gated behind human confirmation).
"""

from __future__ import annotations

import logging
import os
import uuid

from agents.reach.reach_agent import ReachAgent
from agents.base_agent import AgentInput

logger = logging.getLogger("cruz.workers.reach")

_DEFAULT_CRITERIA = (
    "Find SaaS founders or CTOs at early-stage startups in India "
    "who may need freelance full-stack development help"
)


async def run_reach(ctx: dict) -> None:
    """
    2 AM nightly lead generation task.

    Discovers leads matching REACH_CRITERIA and drafts personalised
    outreach emails for each. Results are logged and stored — human
    approval is required before any emails are actually sent.
    """
    criteria = os.environ.get("REACH_CRITERIA", _DEFAULT_CRITERIA)
    trace_id = str(uuid.uuid4())

    logger.info("[REACH] Starting nightly lead generation (trace=%s)", trace_id)

    agent = ReachAgent()
    agent_input: AgentInput = {
        "task": criteria,
        "context": {},
        "trace_id": trace_id,
        "conversation_id": f"cron-reach-{trace_id}",
    }

    try:
        result = await agent.process(agent_input)
        if result["success"]:
            total = result["result"]["total"]
            logger.info(
                "[REACH] Completed — %d lead%s discovered (trace=%s)",
                total,
                "s" if total != 1 else "",
                trace_id,
            )
        else:
            logger.warning(
                "[REACH] Run failed: %s (trace=%s)",
                result.get("error"),
                trace_id,
            )
    except Exception as exc:
        logger.error("[REACH] Unexpected error: %s (trace=%s)", exc, trace_id)
