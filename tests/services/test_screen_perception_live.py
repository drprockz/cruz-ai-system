"""
Live tier — runs only on the Mac Mini with CRUZ_LIVE_MAC_TESTS=1.

These tests hit real osascript / screencapture / Claude Vision.
Skipped in CI. Run manually before SP6 sign-off.

⚠️  PRIVACY WARNING: these tests upload a screenshot of the operator's
ACTUAL Mac screen to Anthropic. Before running:
  • Close any browser tab / window with personal or sensitive data
    (banking, password manager, private chats, draft emails).
  • Lock or hide notification banners that may pop in mid-test.
  • Do NOT run on a screen showing client data unless you have
    consent.

Usage:
    CRUZ_LIVE_MAC_TESTS=1 ANTHROPIC_API_KEY=... \\
        pytest tests/services/test_screen_perception_live.py -v
"""

from __future__ import annotations

import os
import platform

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CRUZ_LIVE_MAC_TESTS") != "1" or platform.system() != "Darwin",
    reason="live mac tests require CRUZ_LIVE_MAC_TESTS=1 on macOS",
)


@pytest.mark.asyncio
async def test_live_get_active_window_returns_real_app() -> None:
    """Real osascript: returns a non-empty app name."""
    from services.screen_perception import get_screen_perception_service
    sp = get_screen_perception_service()
    aw = await sp.get_active_window()
    assert aw.app
    assert aw.app != "unknown", "step-1 unexpectedly failed on the real Mac"
    print(f"\nactive app: {aw.app!r} title: {aw.window_title!r}")


@pytest.mark.asyncio
async def test_live_analyze_returns_text() -> None:
    """Real screenshot + real Claude Vision call: non-empty answer."""
    from services.screen_perception import get_screen_perception_service
    sp = get_screen_perception_service()
    result = await sp.analyze()
    assert result.answer, "Vision returned empty text"
    assert len(result.answer) <= 1000  # canonical prompt asks for 2 sentences
    print(f"\nVision answer: {result.answer}")
    print(f"active_window: {result.active_window}")
    print(f"tokens: {result.tokens_used}")


@pytest.mark.asyncio
async def test_live_analyze_with_custom_question() -> None:
    """Real Vision answers a custom question. Open TextEdit and type a
    known string before running this test (or eyeball the answer)."""
    from services.screen_perception import get_screen_perception_service
    sp = get_screen_perception_service()
    result = await sp.analyze(
        question="In one short sentence, name the application that is "
                "currently in focus on this Mac. Do not describe contents."
    )
    assert result.answer
    print(f"\nactive: {result.active_window.app}")
    print(f"vision said: {result.answer}")
