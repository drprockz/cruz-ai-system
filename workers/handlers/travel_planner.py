"""
Travel Planner handler — webhook-triggered logistics digest.

Triggered by `webhook.google-calendar` events. When the calendar event's
`location` is outside the user's home city, surface a single info-tier
notification with travel logistics (flight reminder, weather, packing
suggestions). Dedup-keyed by event id so the same trip doesn't fan out
multiple times if the calendar event is updated.

Per spec §5, §6. Auto-registers against `webhook.google-calendar` on
import; Chunk 8 imports all handler modules at app boot.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from workers.handlers.context import HandlerContext, HandlerResult

logger = logging.getLogger("cruz.workers.handlers.travel_planner")

HANDLER_NAME = "travel_planner"


def _is_outside_home_city(event_location: str) -> bool:
    """Return True iff event_location is set, HOME_CITY env var is set,
    and HOME_CITY is NOT a case-insensitive substring of event_location.

    Conservative defaults: empty location or unset HOME_CITY → False
    ("not travel"). Avoids false positives that would spam the user.
    """
    home_city = os.environ.get("HOME_CITY", "")
    if not home_city or not event_location:
        return False
    return home_city.lower() not in event_location.lower()


async def _compose_logistics(event: Dict[str, Any]) -> str:
    """Compose the logistics digest body (flight + weather + packing).

    Stubbed until Chunk 8 wiring connects the LLM client.
    """
    raise NotImplementedError("connect Ollama in Chunk 8")


async def handle(payload: Dict[str, Any], context: HandlerContext) -> HandlerResult:
    """Run the travel-planner check for an inbound calendar event.

    NOTE (Chunk 8 wiring): This handler expects `payload` to be a calendar
    event dict with at minimum {"id", "location", "summary", "start"}.
    The current `process_google_calendar_webhook` only forwards Pub/Sub
    headers — Chunk 8 must enrich the payload with the resolved event
    via the Calendar API before this handler can fire. Until then,
    every webhook → "skipped (not travel)".

    Args:
        payload: The calendar event dict (data sub-dict from webhook
                 envelope), shape:
                   {"id": str, "location": str, "summary": str, ...}
        context: HandlerContext with kb/db/trace_id/now/emit_info
    """
    event_id = payload.get("id", "unknown")
    location = payload.get("location", "") or ""

    if not _is_outside_home_city(location):
        return HandlerResult(
            handler_name=HANDLER_NAME,
            success=True,
            summary=f"skipped (not travel): id={event_id} location={location!r}",
            metadata={"skipped": True, "event_id": event_id, "location": location},
        )

    compose_failed = False
    try:
        body = await _compose_logistics(payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("travel_planner: compose failed: %s", exc)
        body = "Travel logistics body unavailable (compose failed)."
        compose_failed = True

    text = (
        f"✈️ *Travel reminder — {payload.get('summary', '(no title)')}*\n\n"
        f"Location: {location}\n\n"
        f"{body}"
    )

    decision = await context.emit_info(
        handler_name=HANDLER_NAME,
        reason="travel_logistics",
        dedup_key=f"{HANDLER_NAME}:{event_id}",
        payload={
            "text": text,
            "trace_id": context.trace_id,
            "event_id": event_id,
            "location": location,
        },
    )
    decision_label = getattr(decision, "value", str(decision))

    error: Optional[str] = "compose_failed" if compose_failed else None

    result_kwargs: Dict[str, Any] = {
        "handler_name": HANDLER_NAME,
        "success": not compose_failed,
        "summary": (
            f"emitted: {decision_label}, event_id={event_id}, "
            f"location={location!r}"
        ),
        "metadata": {
            "event_id": event_id,
            "location": location,
            "compose_failed": compose_failed,
        },
    }
    if error:
        result_kwargs["error"] = error
    return HandlerResult(**result_kwargs)


# Auto-register on import (load-bearing): Chunk 8 imports all handlers at
# app boot; removing this line silently disables Travel Planner in production.
from workers.tasks.dispatch import register_event_handler  # noqa: E402

register_event_handler(__name__, ["webhook.google-calendar"])
