"""
Portfolio Watcher handler — runs at cron.weekly.friday.17:00.

For each active project, fetches RSS feeds tagged with that project's
tech_stack and emits a per-client digest of relevant tech news.

Per spec §5. RSS fetcher + LLM digest composer are stubs until Chunk 8;
the project query is a real implementation against the projects table.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from workers.handlers.context import HandlerContext, HandlerResult

logger = logging.getLogger("cruz.workers.handlers.portfolio_watcher")

HANDLER_NAME = "portfolio_watcher"


async def _fetch_active_projects(context: HandlerContext) -> List[Dict[str, Any]]:
    """Read active projects from the database.

    Returns a list of {id, name, slug, tech_stack} dicts.
    """
    rows = await context.db.fetch(
        "SELECT id, name, slug, tech_stack FROM projects WHERE status='active'"
    )
    return [dict(r) for r in rows]


async def _fetch_rss(stack: List[str]) -> List[Dict[str, Any]]:
    """Fetch RSS articles tagged for the given tech_stack.

    Stubbed until Chunk 8 wiring connects RSS sources.
    """
    raise NotImplementedError("connect RSS sources in Chunk 8 wiring")


async def _compose_digest(client_articles_map: Dict[str, List[Dict[str, Any]]]) -> str:
    """Compose a per-client weekly tech digest from article maps.

    Stubbed until Chunk 8 wiring connects the LLM call.
    """
    raise NotImplementedError("connect LLM digest in Chunk 8 wiring")


async def handle(payload: Dict[str, Any], context: HandlerContext) -> HandlerResult:
    """Run the weekly portfolio watcher.

    Args:
        payload: ARQ-supplied payload (unused for cron-triggered handlers)
        context: HandlerContext with kb/db/trace_id/now/emit_info
    """
    week_label = context.now.strftime("%G-W%V")

    db_failed = False
    rss_failed = False
    compose_failed = False

    try:
        projects = await _fetch_active_projects(context)
    except Exception as exc:  # noqa: BLE001
        logger.warning("portfolio_watcher: project fetch failed: %s", exc)
        projects = []
        db_failed = True

    client_articles_map: Dict[str, List[Dict[str, Any]]] = {}
    for project in projects:
        stack = project.get("tech_stack") or []
        slug = project.get("slug") or str(project.get("id", "unknown"))
        try:
            articles = await _fetch_rss(stack)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "portfolio_watcher: rss fetch failed for %s: %s", slug, exc
            )
            articles = []
            rss_failed = True
        client_articles_map[slug] = articles

    try:
        digest_body = await _compose_digest(client_articles_map)
    except Exception as exc:  # noqa: BLE001
        logger.warning("portfolio_watcher: compose failed: %s", exc)
        digest_body = "Portfolio digest unavailable (compose failed)."
        compose_failed = True

    article_total = sum(len(v) for v in client_articles_map.values())

    text = (
        f"📰 *Portfolio watch — week {week_label}*\n\n"
        f"Projects scanned: {len(projects)}\n"
        f"Articles tagged: {article_total}\n\n"
        f"{digest_body}"
    )

    decision = await context.emit_info(
        handler_name=HANDLER_NAME,
        reason="weekly_portfolio_watch",
        dedup_key=f"{HANDLER_NAME}:{week_label}",
        payload={"text": text, "trace_id": context.trace_id},
    )
    decision_label = getattr(decision, "value", str(decision))

    any_failed = db_failed or rss_failed or compose_failed
    error: Optional[str] = None
    if any_failed:
        failed_parts = []
        if db_failed:
            failed_parts.append("db")
        if rss_failed:
            failed_parts.append("rss")
        if compose_failed:
            failed_parts.append("compose")
        error = f"fetch_failed:{','.join(failed_parts)}"

    result_kwargs: Dict[str, Any] = {
        "handler_name": HANDLER_NAME,
        "success": not any_failed,
        "summary": (
            f"emitted: {decision_label}, "
            f"projects={len(projects)}, articles={article_total}"
        ),
        "metadata": {
            "project_count": len(projects),
            "article_total": article_total,
            "db_failed": db_failed,
            "rss_failed": rss_failed,
            "compose_failed": compose_failed,
        },
    }
    if error:
        result_kwargs["error"] = error
    return HandlerResult(**result_kwargs)
