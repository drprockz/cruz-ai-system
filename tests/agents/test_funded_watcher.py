"""FundedWatcherAgent — SP5 §7.2.

warn-only; daily 08:00 cron; RSS-only (Crunchbase scrape lands with SP4);
LLM ICP filter; per-URL dedup with 90d seen-set TTL.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.funded_watcher.funded_watcher_agent import FundedWatcherAgent
from services.proactive_engine import GateDecision


@pytest.fixture(autouse=True)
def _reset_proactive_engine_singleton():
    import services.proactive_engine as mod

    mod._instance = None
    yield
    mod._instance = None


@pytest.fixture
def agent():
    return FundedWatcherAgent()


def _article(url: str, title: str = "Acme raises $10M", summary: str = "Series A") -> dict:
    return {
        "url": url,
        "link": url,
        "title": title,
        "summary": summary,
        "published": "Sun, 03 May 2026 09:00:00 GMT",
    }


@pytest.mark.asyncio
async def test_skips_seen_articles(agent):
    """URLs already in agent_state(seen_articles) are NOT re-emitted and
    do NOT trigger a _match_icp call (no LLM expense)."""
    seen_url = "https://example.com/already-seen"
    state = AsyncMock(get=AsyncMock(return_value=[seen_url]), set=AsyncMock())

    fetch_calls: list[str] = []

    async def fake_fetch(url: str) -> list[dict]:
        fetch_calls.append(url)
        # First feed returns the already-seen URL; others empty.
        if url == FundedWatcherAgent.RSS_FEEDS[0]:
            return [_article(seen_url)]
        return []

    match_calls: list[str] = []

    async def fake_match(article: dict, offering: str) -> bool:
        match_calls.append(article["url"])
        return True

    emit_calls: list[tuple] = []

    async def fake_emit(severity, reason, dedup_key, payload):
        emit_calls.append((severity, reason, dedup_key))
        return GateDecision.ALLOW

    with patch(
        "agents.funded_watcher.funded_watcher_agent.get_state_service",
        return_value=state,
    ), patch(
        "agents.funded_watcher.funded_watcher_agent._fetch_rss",
        AsyncMock(side_effect=fake_fetch),
    ), patch(
        "agents.funded_watcher.funded_watcher_agent._match_icp",
        AsyncMock(side_effect=fake_match),
    ), patch(
        "agents.funded_watcher.funded_watcher_agent.get_kb_service",
        return_value=MagicMock(record_agent_activity=AsyncMock()),
    ), patch.object(agent, "emit", fake_emit):
        result = await agent.process({
            "task": "event:cron.daily.08:00",
            "context": {"event": {"trigger": "cron.daily.08:00", "data": {}}},
            "trace_id": "tr-skip",
            "conversation_id": "",
        })

    assert result["success"] is True
    assert emit_calls == [], f"expected no emits for seen URL; got {emit_calls!r}"
    assert match_calls == [], (
        f"expected no _match_icp calls for seen URL (saves LLM tokens); "
        f"got {match_calls!r}"
    )
    # All feeds were attempted.
    assert len(fetch_calls) == len(FundedWatcherAgent.RSS_FEEDS)


@pytest.mark.asyncio
async def test_emits_warn_for_icp_match(agent):
    """A new article whose _match_icp returns True must trigger exactly one
    emit at severity='warn' with dedup_key 'article:<url>' and reason=None."""
    state = AsyncMock(get=AsyncMock(return_value=[]), set=AsyncMock())
    target_url = "https://techcrunch.com/2026/05/03/acme-series-a"

    async def fake_fetch(url: str) -> list[dict]:
        if url == FundedWatcherAgent.RSS_FEEDS[0]:
            return [_article(target_url)]
        return []

    captured: list[tuple] = []

    async def fake_emit(severity, reason, dedup_key, payload):
        captured.append((severity, reason, dedup_key, payload))
        return GateDecision.ALLOW

    with patch(
        "agents.funded_watcher.funded_watcher_agent.get_state_service",
        return_value=state,
    ), patch(
        "agents.funded_watcher.funded_watcher_agent._fetch_rss",
        AsyncMock(side_effect=fake_fetch),
    ), patch(
        "agents.funded_watcher.funded_watcher_agent._match_icp",
        AsyncMock(return_value=True),
    ), patch(
        "agents.funded_watcher.funded_watcher_agent.get_kb_service",
        return_value=MagicMock(record_agent_activity=AsyncMock()),
    ), patch.object(agent, "emit", fake_emit):
        result = await agent.process({
            "task": "event:cron.daily.08:00",
            "context": {"event": {"trigger": "cron.daily.08:00", "data": {}}},
            "trace_id": "tr-emit",
            "conversation_id": "",
        })

    assert result["success"] is True
    assert len(captured) == 1, f"expected exactly 1 emit; got {captured!r}"
    severity, reason, dedup_key, payload = captured[0]
    assert severity == "warn"
    assert reason is None
    assert dedup_key == f"article:{target_url}"
    # Payload carries the article context the Telegram body needs.
    assert payload["url"] == target_url
    assert payload["title"]
    assert "text" in payload
    # Seen-set was persisted with the new URL and a 90d TTL.
    state.set.assert_awaited()
    set_args, set_kwargs = state.set.await_args
    assert set_args[0] == agent.name
    assert set_args[1] == "seen_articles"
    persisted_urls = set_args[2]
    assert target_url in persisted_urls
    assert set_kwargs.get("ttl_seconds") == 90 * 86400


@pytest.mark.asyncio
async def test_dedup_per_url(agent):
    """Same URL appearing in multiple feeds must only fire one emit per run
    (per-URL dedup) and the dedup key uses 'article:<url>' so that across
    runs, the gate's own dedup layer would also collide."""
    state = AsyncMock(get=AsyncMock(return_value=[]), set=AsyncMock())
    shared_url = "https://yourstory.com/2026/05/03/acme-funding"

    async def fake_fetch(url: str) -> list[dict]:
        # Return the SAME article from EVERY feed — simulates a story
        # syndicated across the watched RSS sources.
        return [_article(shared_url)]

    captured_keys: list[str] = []

    async def fake_emit(severity, reason, dedup_key, payload):
        captured_keys.append(dedup_key)
        return GateDecision.ALLOW

    with patch(
        "agents.funded_watcher.funded_watcher_agent.get_state_service",
        return_value=state,
    ), patch(
        "agents.funded_watcher.funded_watcher_agent._fetch_rss",
        AsyncMock(side_effect=fake_fetch),
    ), patch(
        "agents.funded_watcher.funded_watcher_agent._match_icp",
        AsyncMock(return_value=True),
    ), patch(
        "agents.funded_watcher.funded_watcher_agent.get_kb_service",
        return_value=MagicMock(record_agent_activity=AsyncMock()),
    ), patch.object(agent, "emit", fake_emit):
        await agent.process({
            "task": "event:cron.daily.08:00",
            "context": {"event": {"trigger": "cron.daily.08:00", "data": {}}},
            "trace_id": "tr-dedup",
            "conversation_id": "",
        })

    # Same URL across N feeds → exactly 1 emit, with the canonical dedup key.
    assert captured_keys == [f"article:{shared_url}"], (
        f"expected dedup to collapse cross-feed duplicates to 1 emit; "
        f"got {captured_keys!r}"
    )
