"""
FundedWatcherAgent — surfaces newly-funded startups whose profile matches
the user's ICP (ideal customer profile) so the user can act on warm intent
the same day funding news lands.

Trigger:
  - cron.daily.08:00 — pulls a small set of RSS feeds, dedups against the
    rolling 90d set of seen article URLs, asks Qwen whether each new article
    matches the user's offering, and emits a "warn" Telegram card for each
    match.

Critical reasons (whitelist for the gate):
  - {} — funding-news noise is never worth a critical interruption. All
    emits are at "warn".

Pre-SP4 graceful degradation: RSS-only. When SP4 lands and a Crunchbase
scrape becomes available, add a `_scrape_crunchbase()` helper alongside
`_fetch_rss` — no agent class change needed.

State schema:
  agent_state(funded_watcher, "seen_articles") = JSONB list of URLs
    (capped at _SEEN_CAP entries; TTL 90d).

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §7.2
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import feedparser

from agents.base_agent import AgentInput, AgentOutput
from agents.event_driven_agent import EventDrivenAgent
from services.agent_state import get_state_service
from services.knowledge_base import get_kb_service
from services.llm import chat as llm_chat

logger = logging.getLogger("cruz.agents.funded_watcher")

_SEEN_KEY = "seen_articles"
_SEEN_TTL_SECONDS = 90 * 86400
_SEEN_CAP = 1000
_DEFAULT_USER_OFFERING = "freelance full-stack development services"
_USER_OFFERING_ENV = "FUNDED_WATCHER_USER_OFFERING"
_OFFERING_FALLBACK_ENV = "USER_OFFERING"
_ICP_MODEL_ENV = "AGENT_MODEL_FUNDED_WATCHER"
_ICP_DEFAULT_MODEL = "qwen2.5-coder:14b"


class FundedWatcherAgent(EventDrivenAgent):
    KNOWLEDGE_RINGS  = ["cruz_activities", "cruz_domain_knowledge"]
    TRIGGERS         = ["cron.daily.08:00"]
    CRITICAL_REASONS = {}

    RSS_FEEDS = [
        "https://techcrunch.com/feed/",
        "https://yourstory.com/rss",
        "https://inc42.com/feed/",
        "https://hnrss.org/newest?points=100",
    ]

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        trace_id = input["trace_id"]
        try:
            user_offering = _resolve_user_offering()
            state = get_state_service()
            seen_list: list[str] = await state.get(self.name, _SEEN_KEY) or []
            seen_set: set[str] = set(seen_list)

            emitted: list[str] = []
            considered = 0
            new_urls: list[str] = []

            for feed_url in self.RSS_FEEDS:
                try:
                    articles = await _fetch_rss(feed_url)
                except Exception as exc:
                    logger.warning(
                        "[%s] _fetch_rss(%s) failed: %s",
                        trace_id, feed_url, exc,
                    )
                    continue

                for article in articles or []:
                    url = article.get("url") or article.get("link")
                    if not url:
                        continue
                    considered += 1
                    if url in seen_set:
                        continue
                    # Mark as seen up-front so retries within this run don't
                    # re-process the same URL even if the LLM call later
                    # raises. Also feeds the per-emit dedup key collision.
                    seen_set.add(url)
                    new_urls.append(url)

                    try:
                        is_match = await _match_icp(article, user_offering)
                    except Exception as exc:
                        logger.warning(
                            "[%s] _match_icp(%s) failed: %s",
                            trace_id, url, exc,
                        )
                        continue

                    if not is_match:
                        continue

                    title = article.get("title") or "(no title)"
                    summary = article.get("summary") or ""
                    body = _format_telegram_text(title, url, summary)
                    dedup_key = f"article:{url}"
                    await self.emit(
                        "warn",
                        None,
                        dedup_key,
                        {
                            "text": body,
                            "trace_id": trace_id,
                            "title": title,
                            "url": url,
                            "summary": summary,
                        },
                    )
                    emitted.append(url)

            # Persist updated seen-set (capped, refreshed TTL).
            if new_urls:
                # Most-recent at the end; cap to last _SEEN_CAP.
                merged = [u for u in seen_list if u in seen_set]
                # Append any URLs that were not already in seen_list (preserving
                # the original list's relative order) so we don't churn it.
                existing = set(merged)
                for u in new_urls:
                    if u not in existing:
                        merged.append(u)
                        existing.add(u)
                if len(merged) > _SEEN_CAP:
                    merged = merged[-_SEEN_CAP:]
                await state.set(
                    self.name, _SEEN_KEY, merged,
                    ttl_seconds=_SEEN_TTL_SECONDS,
                )

            # Rule 3: record activity in cruz_activities.
            try:
                await get_kb_service().record_agent_activity(
                    agent_name=self.name,
                    task=f"funded_watcher:scan ({len(self.RSS_FEEDS)} feeds)",
                    result_summary=(
                        f"considered={considered} new={len(new_urls)} "
                        f"emitted={len(emitted)}"
                    ),
                    success=True,
                    trace_id=trace_id,
                )
            except Exception as exc:
                logger.warning(
                    "[%s] record_agent_activity failed (non-fatal): %s",
                    trace_id, exc,
                )

            return AgentOutput(
                success=True,
                result={
                    "considered": considered,
                    "new": len(new_urls),
                    "emitted": emitted,
                },
                agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0,
                error=None,
                requires_approval=False,
                approval_prompt=None,
            )
        except Exception as exc:
            logger.exception("[%s] funded_watcher failed: %s", trace_id, exc)
            return AgentOutput(
                success=False,
                result=None,
                agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0,
                error=str(exc),
                requires_approval=False,
                approval_prompt=None,
            )


# ── Module-level helpers (monkey-patchable from tests) ───────────────────


async def _fetch_rss(url: str) -> list[dict]:
    """Pull `url` via feedparser and return a list of normalised entries.

    Wraps the synchronous ``feedparser.parse`` call in ``asyncio.to_thread``
    to keep the event loop free. Each returned dict has at minimum::

        {"url": str, "title": str, "summary": str, "published": str, "link": str}

    Tests monkey-patch this helper directly, so production wiring is
    deliberately small and side-effect-free.
    """
    parsed = await asyncio.to_thread(feedparser.parse, url)
    entries = getattr(parsed, "entries", None) or []
    out: list[dict] = []
    for e in entries:
        link = e.get("link") if isinstance(e, dict) else getattr(e, "link", None)
        if not link:
            continue
        out.append({
            "url":       link,
            "link":      link,
            "title":     e.get("title", "") if isinstance(e, dict) else getattr(e, "title", "") or "",
            "summary":   e.get("summary", "") if isinstance(e, dict) else getattr(e, "summary", "") or "",
            "published": e.get("published", "") if isinstance(e, dict) else getattr(e, "published", "") or "",
        })
    return out


async def _match_icp(article: dict, user_offering: str) -> bool:
    """Ask Qwen whether `article` is a fit for the user's ICP.

    Strict yes/no prompt — anything that doesn't start with "yes" (case-
    insensitive, after stripping) is treated as a non-match. The LLM call
    is intentionally cheap and short; tests monkey-patch this helper.
    """
    title = (article.get("title") or "").strip()
    summary = (article.get("summary") or "").strip()
    if not title and not summary:
        return False

    system_prompt = (
        "You are a sales analyst. Given a news article and a description of "
        "what a freelancer offers, decide whether the article describes a "
        "company that would plausibly buy that offering in the next 90 days. "
        "Reply with exactly 'yes' or 'no' on the first line — no other text."
    )
    user_prompt = (
        f"Offering: {user_offering}\n\n"
        f"Article title: {title}\n"
        f"Article summary: {summary[:1000]}\n\n"
        "Is this a fit? Reply 'yes' or 'no'."
    )
    response = await llm_chat(
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=8,
        backend="ollama",
        model=os.environ.get(_ICP_MODEL_ENV, _ICP_DEFAULT_MODEL),
    )
    text = ""
    for block in getattr(response, "content", []) or []:
        if hasattr(block, "type") and block.type == "text":
            text = (block.text or "").strip()
            break
    first_token = text.split()[0].lower() if text else ""
    return first_token.startswith("yes")


def _resolve_user_offering() -> str:
    """Return the configured user-offering string, falling back to a default.

    Reads ``FUNDED_WATCHER_USER_OFFERING`` first, then ``USER_OFFERING``.
    If neither is set, logs a one-shot warning and returns a sane default
    so the agent doesn't no-op silently in dev.
    """
    val = (
        os.environ.get(_USER_OFFERING_ENV)
        or os.environ.get(_OFFERING_FALLBACK_ENV)
    )
    if not val:
        logger.warning(
            "FUNDED_WATCHER_USER_OFFERING (and USER_OFFERING) unset; "
            "using default %r — set one for accurate ICP matching",
            _DEFAULT_USER_OFFERING,
        )
        return _DEFAULT_USER_OFFERING
    return val


def _format_telegram_text(title: str, url: str, summary: str) -> str:
    """Compose a short Telegram-friendly card for a matched article."""
    snippet = (summary or "").strip()
    if len(snippet) > 240:
        snippet = snippet[:237].rstrip() + "…"
    lines = [
        "💰 *Funded ICP match*",
        f"*{title}*",
        url,
    ]
    if snippet:
        lines.append("")
        lines.append(snippet)
    return "\n".join(lines)
