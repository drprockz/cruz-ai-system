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

import anthropic  # kept for legacy tests that patch agents.cruz.cruz_agent.anthropic

from services.llm import chat as llm_chat

import uuid as _uuid

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from agents.forge.forge_agent import ForgeAgent
from agents.echo.echo_agent import EchoAgent
from agents.pm.pm_agent import PMAgent
from agents.catch.catch_agent import CatchAgent
from agents.reach.reach_agent import ReachAgent
from agents.qt.qt_agent import QTAgent
from agents.sentinel.sentinel_agent import SentinelAgent
from agents.titan.titan_agent import TitanAgent
from agents.mark.mark_agent import MarkAgent
from agents.raw.raw_agent import RawAgent
from agents.pulse.pulse_agent import PulseAgent
from agents.relay.relay_agent import classify
from services.alerts import get_alert_service
from services.conversation import ConversationService
from services.db import get_db_service
from services.device_handoff import DeviceHandoffService
from services.redis_client import get_redis_service
from services.semantic_memory import SemanticMemoryService
from services.qdrant import get_qdrant_service
from services.embedding import get_embedding_service

logger = logging.getLogger("cruz.agents.CRUZ")

_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You are CRUZ, a world-class personal AI assistant — the FRIDAY to a developer's Tony Stark.

You have access to specialist tools for specific tasks:
- **forge**: Write, review, or modify code — functions, components, fixes, tests
- **echo**: Draft or send emails and messages — client replies, outreach
- **reach**: Find leads or prospect new clients — discovery + personalised cold email
- **pm**: Create or update tasks and project management tickets (Plane.so)
- **catch**: Transcribe meetings, extract action items, save notes
- **qt**: Run tests and quality gates — pytest, Playwright, Lighthouse, npm audit
- **sentinel**: Review pull requests for bugs and security issues
- **titan**: Deploy applications — Vercel, Railway, SSH — with rollback on failure
- **mark**: Generate docs — OpenAPI, JSDoc, README, CHANGELOG; publish to GitHub/Notion
- **raw**: Research tech topics or scan for dependency updates; store in Qdrant
- **pulse**: Compile a morning briefing from calendar + overnight research + pending tasks

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
    {
        "name": "qt",
        "description": (
            "Run tests, security scans, and quality gates. Use for: running "
            "pytest / Playwright / Lighthouse, auditing npm dependencies for "
            "vulnerabilities, or generating new unit tests for given code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "What to test or scan. Include test_type in context "
                        "(pytest | npm_audit | playwright | lighthouse | generate)."
                    ),
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "sentinel",
        "description": (
            "Review a pull request for bugs, security issues, or style. "
            "Fetches the PR diff from GitHub and returns structured review "
            "findings. Can optionally post inline comments back to the PR."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "The review task. Include repo ('owner/name') and "
                        "pr_number in context."
                    ),
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "mark",
        "description": (
            "Generate documentation: OpenAPI specs, JSDoc comments, README "
            "files, or CHANGELOG entries from commit messages. Can publish "
            "to GitHub and/or Notion after approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "Docs to generate. Include doc_type (openapi | jsdoc | "
                        "readme | changelog) and project in context."
                    ),
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "raw",
        "description": (
            "Research tech topics or scan dependencies for updates. Writes "
            "findings into Qdrant semantic memory so later agents (PULSE, "
            "CRUZ) can retrieve them. Use for 'research X', 'check for pip "
            "outdated', dependency update digests."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "Topic to research, or 'dependencies' for a pip-"
                        "outdated scan. Include mode (research | dependencies) "
                        "in context."
                    ),
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "pulse",
        "description": (
            "Generate a morning briefing combining today's calendar events, "
            "overnight RAW research from Qdrant, recent agent activity, and "
            "pending tasks. Read-only; no approval required."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "Briefing focus (e.g. 'today' or a specific date). "
                        "Defaults to current day."
                    ),
                },
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
    "qt": QTAgent,
    "sentinel": SentinelAgent,
    "titan": TitanAgent,
    "mark": MarkAgent,
    "raw": RawAgent,
    "pulse": PulseAgent,
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
            # LLM routing happens via services.llm — backend chosen by
            # LLM_BACKEND env var (anthropic | ollama | gemini). The
            # response shape is duck-typed to match Anthropic's SDK so
            # the agentic loop below is backend-agnostic.

            # ── Conversation persistence ──────────────────────────────────
            db = get_db_service()
            conv_service = ConversationService(db)
            conversation_id: str = input["conversation_id"]
            await conv_service.get_or_create_conversation(conversation_id)
            history = await conv_service.load_history(conversation_id)

            # ── Semantic memory — retrieve relevant past exchanges ────────
            sem_service = SemanticMemoryService(get_qdrant_service(), get_embedding_service())
            semantic_hits = await sem_service.search_similar(input["task"], limit=10)

            # Order: [semantic context] [session history] [handoff note?] [new user message]
            messages: List[Dict[str, Any]] = [
                *semantic_hits,
                *history,
            ]

            # ── Cross-device handoff detection ────────────────────────────
            device = input["context"].get("device")
            if device:
                try:
                    handoff = DeviceHandoffService(get_redis_service())
                    switched, last_device = await handoff.detect_switch(
                        conversation_id, device
                    )
                    if switched and last_device:
                        await handoff.publish_switch(
                            conversation_id, last_device, device
                        )
                        messages.append({
                            "role": "user",
                            "content": (
                                f"[System: User switched from {last_device} to {device}. "
                                f"Acknowledge the device switch briefly and continue naturally.]"
                            ),
                        })
                        messages.append({
                            "role": "assistant",
                            "content": (
                                f"Welcome back on {device}. Picking up where you left off."
                            ),
                        })
                except Exception as handoff_exc:
                    logger.warning(
                        "[%s] Device handoff check failed (non-fatal): %s",
                        input["trace_id"],
                        handoff_exc,
                    )

            messages.append({"role": "user", "content": input["task"]})

            # ── RELAY pre-filter ──────────────────────────────────────────
            # Deterministic keyword hit → narrow Claude's tool list to that
            # one tool. No match → pass all tools (existing behavior).
            # Unknown hint (e.g. "qt" not in CRUZ_TOOLS yet) → full list.
            tools = CRUZ_TOOLS
            relay_hint = classify(input["task"])
            if relay_hint:
                filtered = [t for t in CRUZ_TOOLS if t["name"] == relay_hint]
                if filtered:
                    tools = filtered
                    logger.info(
                        "[%s] RELAY pre-filter: narrowed tools to '%s'",
                        input["trace_id"], relay_hint,
                    )

            # Voice-mode brevity: when the request came from a voice device,
            # append an instruction so CRUZ gives a short, spoken-style reply
            # instead of a multi-paragraph answer with bullet points.
            system_prompt = _SYSTEM_PROMPT
            max_reply_tokens = 8096
            if device in ("mac_mini", "phone", "ipad"):
                system_prompt = _SYSTEM_PROMPT + (
                    "\n\nIMPORTANT: The user is speaking via voice. Your reply will be "
                    "read aloud by a TTS engine. Answer in 1-2 plain sentences, under "
                    "40 words. No bullet points, no markdown, no code blocks, no lists. "
                    "Be conversational, direct, and brief."
                )
                max_reply_tokens = 512

            # Agentic loop: continue until end_turn or approval gate hit
            while True:
                response = await llm_chat(
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                    max_tokens=max_reply_tokens,
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
                await get_alert_service().notify(
                    "critical",
                    "CRUZ unhandled exception",
                    f"trace_id={input['trace_id']} task={input.get('task','')[:200]} error={exc}",
                )
            except Exception:
                pass
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
