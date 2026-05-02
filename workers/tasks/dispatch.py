"""
dispatch_event_to_agent — ARQ task entrypoint for event-driven agents.

Webhook tasks (workers/tasks/webhook_tasks.py) and cron triggers enqueue
this task with the agent's module path + class name + event payload. The
task imports the class, instantiates it, and runs process().

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.5
"""

from __future__ import annotations

import importlib
import logging
import uuid
from typing import Any, Callable

from agents.base_agent import AgentInput

logger = logging.getLogger("cruz.workers.dispatch")


def _import_class(module_path: str, class_name: str) -> Callable[[], Any]:
    """Return a callable that, when invoked, returns a fresh agent instance.

    Separated from `dispatch_event_to_agent` so tests can monkey-patch it
    and avoid real imports.
    """
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls   # cls() returns an instance; tests patch _import_class
                 # to return any factory


async def dispatch_event_to_agent(
    ctx: dict,
    module_path: str,
    class_name: str,
    event: dict,
) -> dict:
    """Run an EventDrivenAgent in response to a registered trigger event.

    Args:
        ctx: ARQ context (unused currently — reserved for retry/job_id).
        module_path: e.g. "agents.reply_triage.reply_triage_agent"
        class_name:  e.g. "ReplyTriageAgent"
        event: payload dict — at minimum {"trigger": "<trigger_name>",
               "data": <event-specific dict>}, optionally "trace_id".

    Returns:
        AgentOutput-shaped dict. Errors become success=False entries
        (never raised) so ARQ doesn't loop on the same poisoned event.
    """
    trace_id = event.get("trace_id") or f"sp5-{uuid.uuid4()}"
    try:
        factory = _import_class(module_path, class_name)
        agent = factory()
        agent_input: AgentInput = {
            "task": f"event:{event.get('trigger', 'unknown')}",
            "context": {"event": event},
            "trace_id": trace_id,
            "conversation_id": "",
        }
        output = await agent.process(agent_input)
        return dict(output)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "[%s] dispatch_event_to_agent failed: %s.%s — %s",
            trace_id, module_path, class_name, exc,
        )
        return {
            "success": False,
            "result": None,
            "agent": class_name,
            "duration_ms": 0,
            "tokens_used": 0,
            "error": str(exc),
            "requires_approval": False,
            "approval_prompt": None,
        }


# ─── Handler registry (parallel to EVENT_REGISTRY for webhook-triggered handlers) ──

HANDLER_REGISTRY: dict[str, list[str]] = {}  # trigger → list of handler module paths


def register_event_handler(module_path: str, triggers: list[str]) -> None:
    """Register a handler module for one or more triggers. Idempotent."""
    for trigger in triggers:
        handlers = HANDLER_REGISTRY.setdefault(trigger, [])
        if module_path not in handlers:
            handlers.append(module_path)
            logger.debug(
                "registered handler %s for trigger %s", module_path, trigger
            )


def clear_handler_registry() -> None:
    """Test helper — wipe all handler registrations."""
    HANDLER_REGISTRY.clear()


async def dispatch_event_to_handler(
    ctx: dict,
    module_path: str,
    event: dict,
) -> dict:
    """Run a handler in response to a registered trigger event.

    Imports the handler module (which has a module-level `handle` function),
    builds a HandlerContext, calls handle() with the event payload.
    """
    from datetime import datetime, timezone
    from workers.handlers.context import HandlerContext

    trace_id = event.get("trace_id") or f"sp5-handler-{uuid.uuid4()}"
    try:
        module = importlib.import_module(module_path)
        handle = getattr(module, "handle")
        context = HandlerContext(
            trace_id=trace_id,
            now=datetime.now(timezone.utc),
        )
        result = await handle(event.get("data", {}), context)
        return {
            "success": result.success,
            "handler": result.handler_name,
            "summary": result.summary,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "[%s] dispatch_event_to_handler failed: %s — %s",
            trace_id, module_path, exc,
        )
        return {"success": False, "handler": module_path, "error": str(exc)}
