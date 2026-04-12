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

import anthropic

from agents.base_agent import AgentInput, AgentOutput, BaseAgent

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

    def __init__(self) -> None:
        super().__init__()
        self.name = "GENERAL"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()

        try:
            client = anthropic.AsyncAnthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY")
            )

            messages: List[Dict[str, str]] = [
                {"role": "user", "content": input["task"]}
            ]

            response = await client.messages.create(
                model=_MODEL,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                messages=messages,
            )

            result_text: str = response.content[0].text
            tokens_used: int = response.usage.input_tokens + response.usage.output_tokens
            duration_ms = int((time.monotonic() - start) * 1000)

            return AgentOutput(
                success=True,
                result=result_text,
                agent=self.name,
                duration_ms=duration_ms,
                tokens_used=tokens_used,
                error=None,
                requires_approval=False,
                approval_prompt=None,
            )

        except Exception as exc:
            return self.handle_error(exc, input["trace_id"])
