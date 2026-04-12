"""
BaseAgent — mandatory abstract foundation for all 12 CRUZ agents.

Every agent (RELAY, FORGE, ECHO, REACH, CATCH, PM, TITAN, MARK, QT,
SENTINEL, RAW, PULSE) must subclass BaseAgent and implement process().
This enforces a uniform AgentInput → AgentOutput contract across the
entire system and provides shared logging and error handling.
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from typing_extensions import TypedDict


class AgentInput(TypedDict):
    """Structured input passed to every agent."""

    task: str
    """Natural-language task description from CRUZ or the user."""

    context: Dict[str, Any]
    """Arbitrary key-value context (conversation history, user prefs, etc.)."""

    trace_id: str
    """Unique ID threaded through every log row for this request."""

    conversation_id: str
    """ID of the active conversation session in PostgreSQL."""


class AgentOutput(TypedDict):
    """Structured output returned by every agent."""

    success: bool
    """True if the agent completed the task without a fatal error."""

    result: Any
    """Task result — str, dict, or None."""

    agent: str
    """Name of the agent that produced this output (e.g. 'FORGE')."""

    duration_ms: int
    """Wall-clock time the agent spent processing, in milliseconds."""

    tokens_used: int
    """Total LLM tokens consumed (input + output). 0 for non-LLM agents."""

    error: Optional[str]
    """Human-readable error message, or None on success."""

    requires_approval: bool
    """True when the action is irreversible and needs human sign-off."""

    approval_prompt: Optional[str]
    """Question shown to the user when requires_approval is True."""


class BaseAgent(ABC):
    """
    Abstract base class that every CRUZ agent must subclass.

    Subclasses must implement:
        async def process(self, input: AgentInput) -> AgentOutput

    Subclasses inherit:
        self.name       — class name, used in all logs and AgentOutput
        self.logger     — pre-configured logger with agent name
        handle_error()  — builds a failure AgentOutput from any exception
    """

    def __init__(self) -> None:
        self.name: str = self.__class__.__name__
        self.logger: logging.Logger = logging.getLogger(f"cruz.agents.{self.name}")

    @abstractmethod
    async def process(self, input: AgentInput) -> AgentOutput:
        """
        Execute the agent's core task.

        Args:
            input: Validated AgentInput with task, context, trace_id, conversation_id.

        Returns:
            AgentOutput describing the result, duration, and any approval gate.
        """

    async def log(
        self,
        db: Any,
        trace_id: str,
        status: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        tokens_used: int,
        duration_ms: int,
    ) -> None:
        """
        Persist one row to agent_logs — fire-and-forget.

        DB errors are swallowed: logging must never crash an agent.

        Args:
            db:          DatabaseService instance.
            trace_id:    Links this row to the originating request.
            status:      "success" or "error".
            input_data:  Serialisable dict of agent inputs.
            output_data: Serialisable dict of agent outputs.
            tokens_used: Total LLM tokens consumed.
            duration_ms: Processing time in milliseconds.
        """
        try:
            await db.execute(
                """
                INSERT INTO agent_logs
                    (trace_id, agent, action, status, input_data, output_data,
                     tokens_used, duration_ms)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8)
                """,
                trace_id,
                self.name,
                "process",
                status,
                json.dumps(input_data),
                json.dumps(output_data),
                tokens_used,
                duration_ms,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "[%s] agent_logs write failed (non-fatal): %s", trace_id, exc
            )

    def handle_error(self, error: Exception, trace_id: str) -> AgentOutput:
        """
        Build a failure AgentOutput from an unexpected exception.

        Logs the error at ERROR level (trace_id in the message for grep-ability)
        and returns a well-formed AgentOutput so callers never see a bare exception.

        Args:
            error:    The caught exception.
            trace_id: Trace ID for this request, included in the log line.

        Returns:
            AgentOutput with success=False and the error message populated.
        """
        self.logger.error(
            "[%s] %s failed: %s",
            trace_id,
            self.name,
            str(error),
            exc_info=True,
        )
        return AgentOutput(
            success=False,
            result=None,
            agent=self.name,
            duration_ms=0,
            tokens_used=0,
            error=str(error),
            requires_approval=False,
            approval_prompt=None,
        )
