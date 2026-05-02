"""Daily browser health probe — runs a stable DDG search and alerts on failure."""
from __future__ import annotations

import logging

from services.alerts import get_alert_service
from services.browser import get_browser_service

logger = logging.getLogger("cruz.workers.browser_health")

_PROBE_QUERY = "anthropic claude"
_MIN_EXPECTED_RESULTS = 3


async def browser_health_probe(ctx: dict) -> dict:
    """Run a tiny DDG search; alert on zero results or exceptions."""
    try:
        results = await get_browser_service().search(
            _PROBE_QUERY, limit=10, trace_id="browser_health_probe",
        )
    except Exception as exc:
        logger.warning("browser_health_probe failed: %s", exc)
        try:
            await get_alert_service().notify(
                "warning",
                "Browser layer probe failed",
                f"DDG search raised: {exc}",
            )
        except Exception:
            pass
        return {"status": "error", "reason": str(exc)}

    if len(results) < _MIN_EXPECTED_RESULTS:
        logger.warning(
            "browser_health_probe returned %d results (expected >= %d)",
            len(results), _MIN_EXPECTED_RESULTS,
        )
        try:
            await get_alert_service().notify(
                "warning",
                "Browser layer degraded",
                f"DDG search returned {len(results)} results "
                f"(expected >= {_MIN_EXPECTED_RESULTS}); parser may be broken.",
            )
        except Exception:
            pass
        return {"status": "degraded", "result_count": len(results)}

    return {"status": "ok", "result_count": len(results)}
