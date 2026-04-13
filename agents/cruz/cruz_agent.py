"""
CruzAgent — main orchestrator. The user always talks to CRUZ.

Flow:
  1. Build messages list (conversation history + new user task)
  2. Call Claude with CRUZ_TOOLS enabled
  3. If Claude returns tool_use blocks: dispatch to specialist agents
  4. Feed tool results back to Claude for a final text response
  5. Return the final text (or surface a requires_approval gate)

CruzAgent deliberately does NOT call RELAY. RELAY is for future
API-layer routing. Claude's native tool_use is the real orchestration.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import anthropic

import uuid as _uuid

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from agents.forge.forge_agent import ForgeAgent
from agents.echo.echo_agent import EchoAgent
from agents.pm.pm_agent import PMAgent
from agents.catch.catch_agent import CatchAgent
from agents.reach.reach_agent import ReachAgent
from services.conversation import ConversationService
from services.db import get_db_service
from services.semantic_memory import SemanticMemoryService
from services.qdrant import get_qdrant_service
from services.embedding import get_embedding_service

logger = logging.getLogger("cruz.agents.CRUZ")

_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You are CRUZ, a world-class personal AI assistant — the FRIDAY to a developer's Tony Stark.

You have access to specialist tools for specific tasks:
- **forge**: Write, review, or modify code
- **echo**: Draft or send emails and messages
- **reach**: Find leads or prospect new clients
- **titan**: Deploy applications or run infrastructure tasks
- **catch**: Transcribe or summarise meetings
- **pm**: Create or update tasks and project management tickets

For simple questions, answer directly without using tools.
For tasks that match a specialist, use the appropriate tool.
Always be concise, direct, and professional."""

# --------------------------------------------------------------------------
# Tool definitions passed to Claude's API
# --------------------------------------------------------------------------
CRUZ_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "forge",
        "description": (
            "Generate, review, refactor, or debug code. Use for any programming task: "
            "writing functions, creating components, fixing bugs, or writing tests."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The coding task to perform, with full context.",
                }
            },
            "required": ["task"],
        },
    },
    {
        "name": "echo",
        "description": (
            "Draft or send emails and messages. Use for any communication task: "
            "replying to clients, drafting outreach, or composing professional messages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The communication task, including recipient and context.",
                }
            },
            "required": ["task"],
        },
    },
    {
        "name": "reach",
        "description": "Find leads, prospect clients, or run outreach campaigns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The outreach or lead-gen task."}
            },
            "required": ["task"],
        },
    },
    {
        "name": "titan",
        "description": "Deploy applications, run migrations, or manage infrastructure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The deployment or infra task."}
            },
            "required": ["task"],
        },
    },
    {
        "name": "catch",
        "description": "Transcribe or summarise meeting recordings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The transcription or summary task."}
            },
            "required": ["task"],
        },
    },
    {
        "name": "pm",
        "description": "Create, update, or query tasks and project management tickets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The project management task."}
            },
            "required": ["task"],
        },
    },
]

# Map tool name → agent class
# Add entries here as specialist agents are implemented
_TOOL_AGENT_MAP: Dict[str, Any] = {
    "forge": ForgeAgent,
    "echo": EchoAgent,
    "pm": PMAgent,
    "catch": CatchAgent,
    "reach": ReachAgent,
}


class CruzAgent(BaseAgent):
    """
    Main CRUZ orchestrator.

    Calls Claude with tool_use enabled, dispatches tool calls to
    specialist agents, and returns the final response to the caller.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = "CRUZ"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        total_tokens = 0

        try:
            client = anthropic.AsyncAnthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY")
            )

            # ── Conversation persistence ──────────────────────────────────
            db = get_db_service()
            conv_service = ConversationService(db)
            conversation_id: str = input["conversation_id"]
            await conv_service.get_or_create_conversation(conversation_id)
            history = await conv_service.load_history(conversation_id)

            # ── Semantic memory — retrieve relevant past exchanges ────────
            sem_service = SemanticMemoryService(get_qdrant_service(), get_embedding_service())
            semantic_hits = await sem_service.search_similar(input["task"], limit=10)

            # Order: [semantic context] [session history] [new user message]
            messages: List[Dict[str, Any]] = [
                *semantic_hits,
                *history,
                {"role": "user", "content": input["task"]},
            ]

            # Agentic loop: continue until end_turn or approval gate hit
            while True:
                response = await client.messages.create(
                    model=_MODEL,
                    max_tokens=8096,
                    system=_SYSTEM_PROMPT,
                    tools=CRUZ_TOOLS,
                    messages=messages,
                )

                total_tokens += response.usage.input_tokens + response.usage.output_tokens

                # --------------------------------------------------------
                # Plain text response — we're done
                # --------------------------------------------------------
                if response.stop_reason == "end_turn":
                    text = _extract_text(response.content)
                    duration = int((time.monotonic() - start) * 1000)
                    await conv_service.save_exchange(
                        conversation_id=conversation_id,
                        user_task=input["task"],
                        assistant_result=text,
                    )
                    # Store both turns in semantic memory for future retrieval
                    await sem_service.store(
                        id=str(_uuid.uuid4()),
                        role="user",
                        content=input["task"],
                        conversation_id=conversation_id,
                    )
                    await sem_service.store(
                        id=str(_uuid.uuid4()),
                        role="assistant",
                        content=text,
                        conversation_id=conversation_id,
                    )
                    await self.log(
                        db=db,
                        trace_id=input["trace_id"],
                        status="success",
                        input_data={"task": input["task"]},
                        output_data={"result": text},
                        tokens_used=total_tokens,
                        duration_ms=duration,
                    )
                    return AgentOutput(
                        success=True,
                        result=text,
                        agent=self.name,
                        duration_ms=duration,
                        tokens_used=total_tokens,
                        error=None,
                        requires_approval=False,
                        approval_prompt=None,
                    )

                # --------------------------------------------------------
                # Tool use — dispatch and collect results
                # --------------------------------------------------------
                if response.stop_reason == "tool_use":
                    tool_results: List[Dict[str, Any]] = []
                    approval_gate: Optional[AgentOutput] = None

                    for block in response.content:
                        if block.type != "tool_use":
                            continue

                        agent_output = await self._dispatch_tool(
                            tool_name=block.name,
                            tool_input=block.input,
                            trace_id=input["trace_id"],
                            conversation_id=input["conversation_id"],
                        )
                        total_tokens += agent_output.get("tokens_used", 0)

                        if agent_output.get("requires_approval"):
                            # Surface approval gate immediately — do not continue loop
                            approval_gate = agent_output
                            break

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": str(agent_output.get("result", "")),
                            }
                        )

                    if approval_gate is not None:
                        return AgentOutput(
                            success=True,
                            result=approval_gate.get("result"),
                            agent=self.name,
                            duration_ms=int((time.monotonic() - start) * 1000),
                            tokens_used=total_tokens,
                            error=None,
                            requires_approval=True,
                            approval_prompt=approval_gate.get("approval_prompt"),
                        )

                    # Feed tool results back to Claude for the final response
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({"role": "user", "content": tool_results})
                    continue

                # Unexpected stop_reason — treat as end of loop
                text = _extract_text(response.content)
                return AgentOutput(
                    success=True,
                    result=text or "",
                    agent=self.name,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    tokens_used=total_tokens,
                    error=None,
                    requires_approval=False,
                    approval_prompt=None,
                )

        except Exception as exc:
            output = self.handle_error(exc, input["trace_id"])
            try:
                await self.log(
                    db=get_db_service(),
                    trace_id=input["trace_id"],
                    status="error",
                    input_data={"task": input["task"]},
                    output_data={"error": str(exc)},
                    tokens_used=0,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            except Exception:
                pass  # log() already swallows, but guard against db init failure
            return output

    async def _dispatch_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        trace_id: str,
        conversation_id: str,
    ) -> AgentOutput:
        """
        Instantiate the agent matching tool_name and call process().

        Returns an error AgentOutput if the tool name is unrecognised.
        """
        agent_cls = _TOOL_AGENT_MAP.get(tool_name)
        if agent_cls is None:
            logger.warning(
                "[%s] Unknown tool requested: %s — returning error", trace_id, tool_name
            )
            return AgentOutput(
                success=False,
                result=None,
                agent=self.name,
                duration_ms=0,
                tokens_used=0,
                error=f"Unknown tool: '{tool_name}'. Not yet implemented.",
                requires_approval=False,
                approval_prompt=None,
            )

        specialist_agent = agent_cls()
        agent_input: AgentInput = {
            "task": tool_input.get("task", ""),
            "context": tool_input,
            "trace_id": trace_id,
            "conversation_id": conversation_id,
        }
        return await specialist_agent.process(agent_input)


def _extract_text(content: List[Any]) -> str:
    """Pull plain text out of an Anthropic content block list."""
    for block in content:
        if hasattr(block, "type") and block.type == "text":
            return block.text
    return ""
