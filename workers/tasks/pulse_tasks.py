"""
PULSE worker task — 6 AM daily morning briefing.

Calls PulseAgent to compile:
  - Today's Google Calendar events
  - Overnight RAW research from Qdrant
  - Overnight agent activity from agent_logs
  - Pending tasks from tasks table

The generated briefing is logged and available for CRUZ to serve
when Darshan first speaks to the system in the morning.
"""

from __future__ import annotations

import logging
import uuid

from agents.pulse.pulse_agent import PulseAgent
from agents.base_agent import AgentInput

logger = logging.getLogger("cruz.workers.pulse")


async def run_pulse(ctx: dict) -> None:
    """6 AM daily briefing task — compiles and logs the morning brief."""
    trace_id = str(uuid.uuid4())
    agent = PulseAgent()
    agent_input: AgentInput = {
        "task": "Generate 6 AM morning briefing",
        "context": {"mode": "briefing"},
        "trace_id": trace_id,
        "conversation_id": f"cron-pulse-{trace_id}",
    }
    try:
        result = await agent.process(agent_input)
        if result["success"]:
            date = result["result"].get("date", "")
            events = len(result["result"].get("calendar_events", []))
            tasks = len(result["result"].get("pending_tasks", []))
            logger.info(
                "[PULSE] Briefing ready — %s | %d events | %d pending tasks",
                date, events, tasks,
            )
        else:
            logger.warning("[PULSE] Briefing failed: %s", result["error"])
    except Exception as exc:
        logger.error("[PULSE] Unexpected error: %s", exc)
