"""Tests for the per-domain token-bucket rate limiter."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

import services.browser.service as browser_mod
from services.browser import BrowserRateLimited, get_browser_service


@pytest.mark.asyncio
async def test_burst_exceeding_capacity_raises(monkeypatch):
    """15 calls in <1s; 11th onward should raise BrowserRateLimited."""
    browser_mod._instance = None
    svc = get_browser_service()

    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)
    monkeypatch.setattr(
        svc, "_rate_limit_policy",
        {"example.com": browser_mod.TokenBucketSpec(capacity=10, refill_per_sec=10/60)},
    )

    raised = 0
    for _ in range(15):
        try:
            svc._consume_token("example.com")
        except BrowserRateLimited:
            raised += 1
    assert raised == 5  # 10 succeed, 5 fail


@pytest.mark.asyncio
async def test_bucket_refills_over_time(monkeypatch):
    browser_mod._instance = None
    svc = get_browser_service()

    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)
    monkeypatch.setattr(
        svc, "_rate_limit_policy",
        {"example.com": browser_mod.TokenBucketSpec(capacity=2, refill_per_sec=10.0)},
    )
    # Drain
    svc._consume_token("example.com")
    svc._consume_token("example.com")
    with pytest.raises(BrowserRateLimited):
        svc._consume_token("example.com")
    await asyncio.sleep(0.2)  # 10/sec * 0.2s = 2 tokens refilled
    svc._consume_token("example.com")  # should succeed


def test_per_domain_isolation(monkeypatch):
    browser_mod._instance = None
    svc = get_browser_service()

    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)
    monkeypatch.setattr(
        svc, "_rate_limit_policy",
        {
            "example.com": browser_mod.TokenBucketSpec(capacity=1, refill_per_sec=0.001),
            "other.com":   browser_mod.TokenBucketSpec(capacity=1, refill_per_sec=0.001),
        },
    )
    svc._consume_token("example.com")
    with pytest.raises(BrowserRateLimited):
        svc._consume_token("example.com")
    # other.com still has capacity
    svc._consume_token("other.com")


def test_default_policy_used_for_unknown_domain(monkeypatch):
    browser_mod._instance = None
    svc = get_browser_service()

    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)
    # No per-domain override; default capacity=10
    for _ in range(10):
        svc._consume_token("unknown-domain.com")
    with pytest.raises(BrowserRateLimited):
        svc._consume_token("unknown-domain.com")


def test_env_override_parsing():
    spec = browser_mod._parse_rate_limit_env(
        "duckduckgo.com:30:30/60,techcrunch.com:5:5/60"
    )
    assert spec["duckduckgo.com"].capacity == 30
    assert abs(spec["duckduckgo.com"].refill_per_sec - 30/60) < 1e-9
    assert spec["techcrunch.com"].capacity == 5


@pytest.mark.asyncio
async def test_fetch_raises_when_bucket_drained(monkeypatch):
    browser_mod._instance = None
    svc = get_browser_service()

    monkeypatch.setattr(browser_mod, "BROWSER_PACE_DISABLED", True)
    monkeypatch.setattr(
        svc, "_rate_limit_policy",
        {"example.com": browser_mod.TokenBucketSpec(capacity=0, refill_per_sec=0.001)},
    )
    fake_ctx = MagicMock()
    monkeypatch.setattr(svc, "_get_context", AsyncMock(return_value=fake_ctx))

    with pytest.raises(BrowserRateLimited):
        await svc.fetch("https://example.com")
