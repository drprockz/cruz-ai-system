"""
GeneralAgent — Claude-backed catch-all for tasks no specialist handles.

GeneralAgent is always RELAY's fallback.  It calls Claude Sonnet 4 with
the user's raw task and returns the plain-text response.  No tool_use,
no agentic loop — just a single-turn Claude call.

More complex multi-turn orchestration with tool_use lives in CruzAgent.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List

import anthropic  # kept for legacy tests that patch this attribute

from services.llm import chat as llm_chat

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.db import get_db_service
from services.knowledge_base import get_kb_service

_MODEL = "claude-sonnet-4-6"
_SYSTEM_PROMPT = (
    "You are CRUZ, a world-class AI assistant. "
    "Answer the user's request clearly and concisely. "
    "If you need to write code, format it in markdown code blocks."
)


class GeneralAgent(BaseAgent):
    """
    Single-turn Claude Sonnet 4 call for general Q&A and simple tasks.

    Tokens consumed are tracked in the returned AgentOutput so callers
    can accumulate cost across the full request pipeline.
    """

    KNOWLEDGE_RINGS: list[str] = ["cruz_activities"]

    def __init__(self) -> None:
        super().__init__()
        self.name = "GENERAL"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        db = get_db_service()
        output: AgentOutput | None = None

        # ── KB context (fire-and-forget; never raises) ───────────────────
        kb = get_kb_service()
        kb_context = await kb.build_agent_context(
            input["task"],
            self.KNOWLEDGE_RINGS,
            input["trace_id"],
            project_id=input["context"].get("project_id"),
        )
        system = _SYSTEM_PROMPT
        if kb_context:
            system = kb_context + "\n\n" + system

        try:
            try:
                messages: List[Dict[str, str]] = [
                    {"role": "user", "content": input["task"]}
                ]

                response = await llm_chat(
                    system=system,
                    messages=messages,
                    max_tokens=4096,
                )

                result_text: str = response.content[0].text
                tokens_used: int = response.usage.input_tokens + response.usage.output_tokens
                duration_ms = int((time.monotonic() - start) * 1000)

                try:
                    await self.log(
                        db=db,
                        trace_id=input["trace_id"],
                        status="success",
                        input_data={"task": input["task"]},
                        output_data={"result": result_text},
                        tokens_used=tokens_used,
                        duration_ms=duration_ms,
                    )
                except Exception:
                    pass

                output = AgentOutput(
                    success=True,
                    result=result_text,
                    agent=self.name,
                    duration_ms=duration_ms,
                    tokens_used=tokens_used,
                    error=None,
                    requires_approval=False,
                    approval_prompt=None,
                )
                return output

            except Exception as exc:
                output = self.handle_error(exc, input["trace_id"])
                try:
                    await self.log(
                        db=db,
                        trace_id=input["trace_id"],
                        status="error",
                        input_data={"task": input["task"]},
                        output_data={"error": str(exc)},
                        tokens_used=0,
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )
                except Exception:
                    pass
                return output

        finally:
            # ── KB activity record (fire-and-forget; never raises) ────────
            try:
                if output is not None:
                    await kb.record_agent_activity(
                        "general",
                        input["task"],
                        str(output.get("result", ""))[:200],
                        output["success"],
                        input["trace_id"],
                        project_id=input["context"].get("project_id"),
                        tokens_used=output.get("tokens_used"),
                    )
            except Exception:
                pass
