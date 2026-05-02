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
from datetime import datetime
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
from agents.calendar.calendar_agent import CalendarAgent
from agents.relay.relay_agent import classify
from services.alerts import get_alert_service
from services.conversation import ConversationService
from services.db import get_db_service
from services.device_handoff import DeviceHandoffService
from services.knowledge_base import get_kb_service
from services.mac_controller import MacControllerError, get_mac_controller_service
from services.redis_client import get_redis_service
from services.semantic_memory import SemanticMemoryService
from services.qdrant import get_qdrant_service
from services.embedding import get_embedding_service
from services.llm.router import chat_stream as llm_chat_stream
from services.sentence_stream import sentence_stream as _sentence_stream
from services.llm.stream_events import (
    TextDeltaEvent, ToolUseEvent, DoneEvent as _LLMDone,
)
from agents.cruz.stream_events import (
    Text, ToolStart, ToolFinish, ApprovalRequired, Done,
)

logger = logging.getLogger("cruz.agents.CRUZ")

_MODEL = "claude-sonnet-4-6"

# Human-friendly "I'm working on it" phrasing per tool.
_TOOL_INTRO = {
    "forge": "Let me write that code.",
    "echo": "Drafting the message.",
    "reach": "Finding leads now.",
    "pm": "Updating tasks.",
    "catch": "Transcribing that for you.",
    "qt": "Running tests.",
    "sentinel": "Reviewing the code.",
    "titan": "Starting the deploy.",
    "mark": "Generating the docs.",
    "raw": "Researching.",
    "pulse": "Gathering your briefing.",
}

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
    {
        "name": "record_pattern_observation",
        "description": (
            "Call this when the user's message is a behavioral correction — "
            "e.g. 'no, use formal tone', 'always use snake_case', "
            "'stop adding comments'. Records the observation toward learning "
            "Darshan's preferences. agent_name is the agent whose output was corrected."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name":        {"type": "string"},
                "interaction_type":  {"type": "string",
                                      "description": "e.g. email_draft_edited, code_edited"},
                "observed_pattern":  {"type": "string",
                                      "description": "The preference rule observed"},
            },
            "required": ["agent_name", "interaction_type", "observed_pattern"],
        },
    },
    # ── Mac Controller (Layer 2 — services/mac_controller.py) ─────────
    {
        "name": "mac_screenshot",
        "description": (
            "Capture the screen on the Mac Mini and return PNG bytes. "
            "Optional region [x, y, width, height] in screen pixels. "
            "Use for 'what's on my screen' or grabbing visual context for vision tasks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 4,
                    "maxItems": 4,
                    "description": "Optional [x, y, width, height] sub-rectangle.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "mac_clipboard_read",
        "description": "Read the current macOS clipboard contents as text.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "mac_clipboard_write",
        "description": (
            "Replace the macOS clipboard with the given text. "
            "Use for 'copy this for me' or staging text the user will paste."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to place on the clipboard."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "mac_open_app",
        "description": (
            "Launch (or bring to front) a macOS app by name. "
            "Examples: 'TextEdit', 'Visual Studio Code', 'Mail'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Exact app name as it appears in /Applications."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "mac_notify",
        "description": (
            "Fire a macOS Notification Center banner. "
            "Use for reminders, soft alerts, or confirming background work."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body":  {"type": "string"},
                "sound": {"type": "boolean", "description": "Play Submarine sound (default false)."},
            },
            "required": ["title", "body"],
        },
    },
    # ── Calendar (Layer 2 — agents/calendar/calendar_agent.py) ────────
    {
        "name": "calendar_create_event",
        "description": (
            "Create a calendar event in Google Calendar (auto-mirrors to Calendar.app). "
            "Self-only events (no attendees) are created immediately. "
            "Events with attendees require user approval before sending invites."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title":       {"type": "string"},
                "start_iso":   {"type": "string",
                                "description": "ISO 8601 datetime, e.g. 2026-05-01T10:00:00"},
                "end_iso":     {"type": "string"},
                "attendees":   {"type": "array", "items": {"type": "string"},
                                "description": "Optional list of attendee email addresses."},
                "description": {"type": "string"},
                "location":    {"type": "string"},
                "calendar_id": {"type": "string",
                                "description": "Optional non-primary calendar ID."},
            },
            "required": ["title", "start_iso", "end_iso"],
        },
    },
    {
        "name": "calendar_list_events",
        "description": "List Google Calendar events in a time range. Read-only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_iso":   {"type": "string"},
                "end_iso":     {"type": "string"},
                "calendar_id": {"type": "string"},
            },
            "required": ["start_iso", "end_iso"],
        },
    },
    {
        "name": "calendar_find_free_slot",
        "description": (
            "Find the first free slot of `duration_minutes` in [earliest_iso, latest_iso]. "
            "Reads busy events from Google Calendar. Read-only — does not create anything."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_minutes": {"type": "integer", "minimum": 5},
                "earliest_iso":     {"type": "string"},
                "latest_iso":       {"type": "string"},
                "working_hours":    {"type": "array", "items": {"type": "integer"},
                                     "minItems": 2, "maxItems": 2,
                                     "description": "Optional [start_hour, end_hour], 24h."},
            },
            "required": ["duration_minutes", "earliest_iso", "latest_iso"],
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
    "calendar_create_event":   CalendarAgent,
    "calendar_list_events":    CalendarAgent,
    "calendar_find_free_slot": CalendarAgent,
}


class CruzAgent(BaseAgent):
    """
    Main CRUZ orchestrator.

    Calls Claude with tool_use enabled, dispatches tool calls to
    specialist agents, and returns the final response to the caller.
    """

    KNOWLEDGE_RINGS: List[str] = ["cruz_activities", "cruz_user_patterns"]

    def __init__(self) -> None:
        super().__init__()
        self.name = "CRUZ"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        total_tokens = 0
        output: Optional[AgentOutput] = None

        # ── KB context (fire-and-forget; never raises) ───────────────────
        kb = get_kb_service()
        kb_context = await kb.build_agent_context(
            input["task"],
            self.KNOWLEDGE_RINGS,
            input["trace_id"],
            project_id=input["context"].get("project_id"),
        )

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
            try:
                semantic_hits = await sem_service.search_similar(input["task"], limit=10)
            except Exception as exc:
                logger.warning(
                    "[%s] semantic memory unavailable (continuing without): %s",
                    input["trace_id"], exc,
                )
                semantic_hits = []

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
            now = datetime.now().astimezone()
            runtime_context = (
                f"\n\n## Runtime context (authoritative — use this, ignore any prior replies that contradict it)\n"
                f"- Current datetime: {now.strftime('%A, %B %d, %Y %I:%M %p %Z')}\n"
                f"- User: Darshan Parmar (freelance full-stack developer)\n"
                f"- Host: Mac Mini M4, accessed from phone/ipad/thinkpad/mac\n"
                f"- When asked the time or date, answer directly from the datetime above. "
                f"Never say you 'can't access real-time data' — this runtime context IS real-time."
            )
            system_prompt = _SYSTEM_PROMPT + runtime_context
            if kb_context:
                system_prompt = kb_context + "\n\n" + system_prompt
            max_reply_tokens = 8096
            if device in ("mac_mini", "phone", "ipad"):
                system_prompt = system_prompt + (
                    "\n\nIMPORTANT: The user is speaking via voice. Your reply will be "
                    "read aloud by a TTS engine. Answer in 1-2 plain sentences, under "
                    "40 words. No bullet points, no markdown, no code blocks, no lists. "
                    "Be conversational, direct, and brief."
                )
                max_reply_tokens = 512

            # Persona v1 augmentation — wraps the base prompt with identity,
            # response-style hint, humor permission and (if available) user
            # profile summary.  Fully wrapped in try/except: if persona fails
            # for any reason, we fall back to the raw prompt.
            try:
                from agents.cruz.persona import PersonaLayer
                from agents.cruz.persona.relationship_memory import quick_profile
                try:
                    profile = await quick_profile(db, user_id="darshan")
                except Exception:
                    profile = None
                system_prompt = PersonaLayer.get().augment_system_prompt(
                    base=system_prompt,
                    task=input["task"],
                    device=device,
                    now=now,
                    profile=profile,
                )
            except Exception as exc:
                logger.warning(
                    "[%s] persona augmentation skipped (non-fatal): %s",
                    input["trace_id"], exc,
                )

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
                    try:
                        # PII redaction before long-term memory. Non-fatal if missing.
                        try:
                            from agents.cruz.persona import PersonaLayer as _PL
                            _p = _PL.get()
                            _u = _p.sanitize_for_memory(input["task"])
                            _t = _p.sanitize_for_memory(text)
                        except Exception:
                            _u, _t = input["task"], text
                        await sem_service.store(
                            id=str(_uuid.uuid4()),
                            role="user",
                            content=_u,
                            conversation_id=conversation_id,
                        )
                        await sem_service.store(
                            id=str(_uuid.uuid4()),
                            role="assistant",
                            content=_t,
                            conversation_id=conversation_id,
                        )
                    except Exception as exc:
                        logger.warning(
                            "[%s] semantic memory store failed (non-fatal): %s",
                            input["trace_id"], exc,
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
                    output = AgentOutput(
                        success=True,
                        result=text,
                        agent=self.name,
                        duration_ms=duration,
                        tokens_used=total_tokens,
                        error=None,
                        requires_approval=False,
                        approval_prompt=None,
                    )
                    return output

                # --------------------------------------------------------
                # Tool use — dispatch and collect results
                # --------------------------------------------------------
                if response.stop_reason == "tool_use":
                    tool_results: List[Dict[str, Any]] = []
                    approval_gate: Optional[AgentOutput] = None

                    for block in response.content:
                        if block.type != "tool_use":
                            continue

                        # ── Built-in tool: record pattern observation ────
                        if block.name == "record_pattern_observation":
                            tool_input = block.input or {}
                            await kb.observe_interaction(
                                tool_input.get("agent_name", "unknown"),
                                tool_input.get("interaction_type", "unknown"),
                                tool_input.get("observed_pattern", ""),
                            )
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": str({"recorded": True}),
                                }
                            )
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
                        output = AgentOutput(
                            success=True,
                            result=approval_gate.get("result"),
                            agent=self.name,
                            duration_ms=int((time.monotonic() - start) * 1000),
                            tokens_used=total_tokens,
                            error=None,
                            requires_approval=True,
                            approval_prompt=approval_gate.get("approval_prompt"),
                        )
                        return output

                    # Feed tool results back to Claude for the final response
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({"role": "user", "content": tool_results})
                    continue

                # Unexpected stop_reason — treat as end of loop
                text = _extract_text(response.content)
                output = AgentOutput(
                    success=True,
                    result=text or "",
                    agent=self.name,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    tokens_used=total_tokens,
                    error=None,
                    requires_approval=False,
                    approval_prompt=None,
                )
                return output

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

        finally:
            # ── KB activity record (fire-and-forget; never raises) ────────
            try:
                if output is not None:
                    await kb.record_agent_activity(
                        "cruz",
                        input["task"],
                        str(output.get("result", ""))[:200],
                        output["success"],
                        input["trace_id"],
                        project_id=input["context"].get("project_id"),
                        tokens_used=output.get("tokens_used"),
                    )
            except Exception:
                pass

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
        # ── Mac Controller dispatch (services, not agents) ─────────────
        if tool_name.startswith("mac_"):
            return await self._dispatch_mac_tool(tool_name, tool_input, trace_id)

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
        # Inject tool name into context so dispatcher-style agents (Calendar)
        # know which operation to run. Existing agents ignore the extra key.
        context: Dict[str, Any] = dict(tool_input)
        context["tool"] = tool_name
        agent_input: AgentInput = {
            "task": tool_input.get("task", ""),
            "context": context,
            "trace_id": trace_id,
            "conversation_id": conversation_id,
        }
        return await specialist_agent.process(agent_input)

    async def _dispatch_mac_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        trace_id: str,
    ) -> AgentOutput:
        """Route mac_* tools directly to MacControllerService."""
        start = time.monotonic()
        mac = get_mac_controller_service()
        try:
            if tool_name == "mac_screenshot":
                region = tool_input.get("region")
                region_t = tuple(region) if region else None
                png = await mac.screenshot(region=region_t)
                result: Any = {
                    "bytes_len": len(png),
                    "mime_type": "image/png",
                    # Note: raw bytes are NOT included in result to keep
                    # tool_result text size manageable. Caller (e.g. SP6)
                    # invokes mac.screenshot() directly when bytes are needed.
                }
            elif tool_name == "mac_clipboard_read":
                result = await mac.clipboard_read()
            elif tool_name == "mac_clipboard_write":
                await mac.clipboard_write(tool_input["text"])
                result = {"written": True, "chars": len(tool_input["text"])}
            elif tool_name == "mac_open_app":
                await mac.open_app(tool_input["name"])
                result = {"opened": tool_input["name"]}
            elif tool_name == "mac_notify":
                await mac.notify(
                    tool_input["title"],
                    tool_input["body"],
                    sound=tool_input.get("sound", False),
                )
                result = {"notified": True}
            else:
                return AgentOutput(
                    success=False, result=None, agent=self.name,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    tokens_used=0,
                    error=f"Unknown mac tool: {tool_name!r}",
                    requires_approval=False, approval_prompt=None,
                )
        except MacControllerError as exc:
            return AgentOutput(
                success=False, result=None, agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0,
                error=str(exc),
                requires_approval=False, approval_prompt=None,
            )

        return AgentOutput(
            success=True, result=result, agent=self.name,
            duration_ms=int((time.monotonic() - start) * 1000),
            tokens_used=0,
            error=None,
            requires_approval=False, approval_prompt=None,
        )

    async def stream_response(
        self,
        *,
        task: str,
        conversation_id: str,
        trace_id: str,
        device: Optional[str] = None,
    ):
        """
        Async iterator for voice + SSE paths. Yields:
          Text / ToolStart / ToolFinish / ApprovalRequired / Done
        Persists conversation + semantic memory identically to process().
        """
        import time as _time
        import uuid as _uuid
        start = _time.monotonic()
        total_tokens = 0
        success: bool = False
        final_text: str = ""

        # ── KB context (fire-and-forget; never raises) ───────────────────
        kb = get_kb_service()
        kb_context = await kb.build_agent_context(
            task,
            self.KNOWLEDGE_RINGS,
            trace_id,
        )

        try:
            db = get_db_service()
            conv_service = ConversationService(db)
            await conv_service.get_or_create_conversation(conversation_id)
            history = await conv_service.load_history(conversation_id)

            sem_service = SemanticMemoryService(
                get_qdrant_service(), get_embedding_service()
            )
            try:
                semantic_hits = await sem_service.search_similar(task, limit=10)
            except Exception as exc:
                logger.warning(
                    "semantic memory unavailable (continuing without): %s", exc
                )
                semantic_hits = []

            messages: List[Dict[str, Any]] = [
                *semantic_hits, *history, {"role": "user", "content": task},
            ]

            tools = CRUZ_TOOLS
            hint = classify(task)
            if hint:
                f = [t for t in CRUZ_TOOLS if t["name"] == hint]
                if f:
                    tools = f

            now = datetime.now().astimezone()
            runtime_context = (
                f"\n\n## Runtime context (authoritative — use this, ignore any prior replies that contradict it)\n"
                f"- Current datetime: {now.strftime('%A, %B %d, %Y %I:%M %p %Z')}\n"
                f"- User: Darshan Parmar (freelance full-stack developer)\n"
                f"- Host: Mac Mini M4, accessed from phone/ipad/thinkpad/mac\n"
                f"- When asked the time or date, answer directly from the datetime above. "
                f"Never say you 'can't access real-time data' — this runtime context IS real-time."
            )
            system_prompt = _SYSTEM_PROMPT + runtime_context
            if kb_context:
                system_prompt = kb_context + "\n\n" + system_prompt
            max_reply_tokens = 512 if device in ("mac_mini", "phone", "ipad") else 4096
            if device in ("mac_mini", "phone", "ipad"):
                system_prompt += (
                    "\n\nIMPORTANT: Voice mode — reply in 1-2 plain sentences under 40 words. "
                    "No markdown, no lists."
                )

            # Persona v1 augmentation — same pattern as process(). Fail-soft.
            try:
                from agents.cruz.persona import PersonaLayer
                from agents.cruz.persona.relationship_memory import quick_profile
                try:
                    profile = await quick_profile(db, user_id="darshan")
                except Exception:
                    profile = None
                system_prompt = PersonaLayer.get().augment_system_prompt(
                    base=system_prompt,
                    task=task,
                    device=device,
                    now=now,
                    profile=profile,
                )
            except Exception as exc:
                logger.warning(
                    "[%s] persona augmentation skipped in stream_response: %s",
                    trace_id, exc,
                )

            # Buffer all sentences for persistence + faithful history rebuild.
            final_text_parts: List[str] = []

            while True:
                pending_tools: List[ToolUseEvent] = []
                turn_text_parts: List[str] = []

                async def _text_token_stream():
                    nonlocal total_tokens
                    async for ev in llm_chat_stream(
                        system=system_prompt, messages=messages,
                        tools=tools, max_tokens=max_reply_tokens,
                    ):
                        if isinstance(ev, TextDeltaEvent):
                            turn_text_parts.append(ev.delta)
                            yield ev.delta
                        elif isinstance(ev, ToolUseEvent):
                            pending_tools.append(ev)
                        elif isinstance(ev, _LLMDone):
                            total_tokens += ev.usage.input_tokens + ev.usage.output_tokens

                async for sentence in _sentence_stream(_text_token_stream()):
                    final_text_parts.append(sentence)
                    yield Text(content=sentence)

                if not pending_tools:
                    break

                # Dispatch tools
                tool_result_blocks = []
                approval_hit = False
                for tu in pending_tools:
                    # ── Built-in tool: record pattern observation ────
                    if tu.name == "record_pattern_observation":
                        ti = tu.input or {}
                        await kb.observe_interaction(
                            ti.get("agent_name", "unknown"),
                            ti.get("interaction_type", "unknown"),
                            ti.get("observed_pattern", ""),
                        )
                        tool_result_blocks.append({
                            "type": "tool_result",
                            "tool_use_id": tu.tool_use_id,
                            "content": str({"recorded": True}),
                        })
                        continue

                    yield ToolStart(
                        agent=tu.name,
                        summary=_TOOL_INTRO.get(tu.name, f"Running {tu.name}."),
                    )
                    out = await self._dispatch_tool(
                        tool_name=tu.name, tool_input=tu.input,
                        trace_id=trace_id, conversation_id=conversation_id,
                    )
                    if out.get("requires_approval"):
                        yield ApprovalRequired(
                            agent=tu.name,
                            prompt=out.get("approval_prompt") or "",
                            payload=tu.input,
                        )
                        yield Done(
                            tokens_used=total_tokens,
                            duration_ms=int((_time.monotonic() - start) * 1000),
                        )
                        success = True
                        approval_hit = True
                        break
                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": tu.tool_use_id,
                        "content": str(out.get("result", "")),
                    })
                    yield ToolFinish(
                        agent=tu.name,
                        result_preview=str(out.get("result", ""))[:200],
                    )

                if approval_hit:
                    return

                # Reconstruct assistant turn (include any pre-tool text)
                assistant_content: List[Dict[str, Any]] = []
                joined_turn_text = "".join(turn_text_parts).strip()
                if joined_turn_text:
                    assistant_content.append({"type": "text", "text": joined_turn_text})
                for tu in pending_tools:
                    assistant_content.append({
                        "type": "tool_use", "id": tu.tool_use_id,
                        "name": tu.name, "input": tu.input,
                    })
                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({"role": "user", "content": tool_result_blocks})

            # Persist — matches process() parity
            final_text = " ".join(final_text_parts).strip()
            if final_text:
                await conv_service.save_exchange(
                    conversation_id=conversation_id,
                    user_task=task,
                    assistant_result=final_text,
                )
                try:
                    try:
                        from agents.cruz.persona import PersonaLayer as _PL
                        _p = _PL.get()
                        _u = _p.sanitize_for_memory(task)
                        _t = _p.sanitize_for_memory(final_text)
                    except Exception:
                        _u, _t = task, final_text
                    await sem_service.store(
                        id=str(_uuid.uuid4()), role="user",
                        content=_u, conversation_id=conversation_id,
                    )
                    await sem_service.store(
                        id=str(_uuid.uuid4()), role="assistant",
                        content=_t, conversation_id=conversation_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "semantic memory store failed (non-fatal): %s", exc
                    )

            success = True
            yield Done(
                tokens_used=total_tokens,
                duration_ms=int((_time.monotonic() - start) * 1000),
            )

        finally:
            # ── KB activity record (fire-and-forget; never raises) ────────
            try:
                await kb.record_agent_activity(
                    "cruz",
                    task,
                    final_text[:200],
                    success,
                    trace_id,
                    tokens_used=total_tokens,
                )
            except Exception:
                pass


def _extract_text(content: List[Any]) -> str:
    """Pull plain text out of an Anthropic content block list."""
    for block in content:
        if hasattr(block, "type") and block.type == "text":
            return block.text
    return ""
