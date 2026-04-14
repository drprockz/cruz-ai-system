"""
RelayAgent — deterministic keyword classifier.

RELAY makes ZERO LLM calls.  It matches the task string against a
keyword table and returns the name of the agent that should handle
the request.  If no keyword matches the task falls through to GENERAL.

Design principles:
- No imports of anthropic, ollama, or any ML library
- Pure string operations only
- Must complete in <100ms for any input
- Single source of truth for agent routing — AGENT_KEYWORDS

Adding a new routing rule: add one entry to AGENT_KEYWORDS.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from agents.base_agent import AgentInput, AgentOutput, BaseAgent

# --------------------------------------------------------------------------
# Routing table — order matters: first match wins (most-specific first)
# --------------------------------------------------------------------------
# Format: {keyword_substring: agent_name}
# Keyword matching is case-insensitive substring search on the task string.
AGENT_KEYWORDS: Dict[str, str] = {
    # FORGE — code generation (specific patterns first)
    "write a function": "FORGE",
    "write a script": "FORGE",
    "write a test": "FORGE",
    "write code": "FORGE",
    "write a python": "FORGE",
    "write a typescript": "FORGE",
    "create a function": "FORGE",
    "create a script": "FORGE",
    "create a component": "FORGE",
    "create a react": "FORGE",
    "generate code": "FORGE",
    "implement": "FORGE",
    "refactor": "FORGE",
    "debug this": "FORGE",
    "fix the bug": "FORGE",
    # ECHO — email / communication
    "send an email": "ECHO",
    "send email": "ECHO",
    "draft an email": "ECHO",
    "draft a reply": "ECHO",
    "draft email": "ECHO",
    "write an email": "ECHO",
    "reply to": "ECHO",
    "compose email": "ECHO",
    # REACH — lead generation / outreach
    "find leads": "REACH",
    "generate leads": "REACH",
    "prospect ": "REACH",
    "outreach": "REACH",
    "apollo": "REACH",
    # CATCH — meeting / transcription
    "transcribe": "CATCH",
    "meeting notes": "CATCH",
    "summarize the meeting": "CATCH",
    # PM — project management
    "create a task": "PM",
    "add a task": "PM",
    "update the ticket": "PM",
    "linear ticket": "PM",
    "project status": "PM",
    # TITAN — deployment / infrastructure
    "deploy": "TITAN",
    "push to production": "TITAN",
    "run migrations": "TITAN",
    "infrastructure": "TITAN",
    # MARK — documentation
    "write docs": "MARK",
    "generate documentation": "MARK",
    "update the readme": "MARK",
    # QT — testing automation
    "write tests": "FORGE",  # QT uses FORGE's code generation, alias for now
    "generate tests": "FORGE",
    # SENTINEL — code review
    "code review": "SENTINEL",
    "security review": "SENTINEL",
    "review my code": "SENTINEL",
    # RAW — research / web scraping
    "research": "RAW",
    "scrape": "RAW",
    "find information about": "RAW",
    # PULSE — briefings
    "daily briefing": "PULSE",
    "morning briefing": "PULSE",
    "what happened today": "PULSE",
}


def classify(task: str) -> Optional[str]:
    """
    Lightweight keyword classifier used by CruzAgent as a tool-list pre-filter.

    Returns the LOWERCASE agent name (e.g. "forge", "titan") if any keyword
    in AGENT_KEYWORDS matches the task, or None when there's no match.

    Unlike RelayAgent.process(), this function never returns a "GENERAL"
    fallback — None tells the caller "no keyword hit, let Claude decide
    from the full tool list." Zero LLM calls, zero I/O.
    """
    if not task:
        return None
    task_lower = task.lower()
    for keyword, agent_name in AGENT_KEYWORDS.items():
        if keyword.lower() in task_lower:
            return agent_name.lower()
    return None


class RelayAgent(BaseAgent):
    """
    Deterministic keyword router.

    process() never calls any external service. It scans the task string
    for keyword matches and returns the winning agent name plus the
    original task so the downstream agent has full context.
    """

    name: str = "RELAY"

    def __init__(self) -> None:
        super().__init__()
        self.name = "RELAY"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        task_lower = input["task"].lower()

        routed_to = "GENERAL"
        for keyword, agent_name in AGENT_KEYWORDS.items():
            if keyword.lower() in task_lower:
                routed_to = agent_name
                break

        duration_ms = int((time.monotonic() - start) * 1000)

        return AgentOutput(
            success=True,
            result={
                "agent": routed_to,
                "task": input["task"],
                "trace_id": input["trace_id"],
                "conversation_id": input["conversation_id"],
            },
            agent=self.name,
            duration_ms=duration_ms,
            tokens_used=0,  # Zero LLM calls — always 0
            error=None,
            requires_approval=False,
            approval_prompt=None,
        )
