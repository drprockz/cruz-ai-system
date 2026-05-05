"""Unit tests for services.screen_perception — subprocess + LLM mocked."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from services.mac_controller import MacControllerError
from services.screen_perception import (
    ActiveWindow,
    ScreenAnalysis,
    ScreenPerceptionError,
    ScreenPerceptionService,
    WINDOW_TITLE_ALLOWLIST,
    get_screen_perception_service,
)


def test_singleton_returns_same_instance() -> None:
    a = get_screen_perception_service()
    b = get_screen_perception_service()
    assert a is b
    assert isinstance(a, ScreenPerceptionService)


def test_screen_perception_error_is_runtime_error() -> None:
    err = ScreenPerceptionError("boom")
    assert isinstance(err, RuntimeError)
    assert str(err) == "boom"


def test_window_title_allowlist_contains_dev_tools() -> None:
    """Sanity: the allowlist is the set the spec §4 defines, no extras."""
    expected = {
        "Code", "Cursor", "Xcode", "Terminal", "iTerm2",
        "PyCharm", "WebStorm", "Sublime Text", "Zed", "Ghostty",
    }
    assert WINDOW_TITLE_ALLOWLIST == expected


def test_active_window_to_context_line_app_only() -> None:
    aw = ActiveWindow(app="Mail", window_title=None, captured_at=0.0)
    assert aw.to_context_line() == "- Active app: Mail"


def test_active_window_to_context_line_with_title() -> None:
    aw = ActiveWindow(
        app="Code",
        window_title="orders.js — ama-solutions",
        captured_at=0.0,
    )
    assert aw.to_context_line() == "- Active app: Code — orders.js — ama-solutions"


def test_screen_analysis_dataclass_fields() -> None:
    """Confirm the dataclass shape the dispatch path depends on."""
    aw = ActiveWindow(app="Code", window_title="x", captured_at=1.0)
    sa = ScreenAnalysis(
        answer="hello",
        active_window=aw,
        image_bytes_len=42,
        duration_ms=100,
        tokens_used=200,
    )
    assert sa.answer == "hello"
    assert sa.active_window is aw
    assert sa.image_bytes_len == 42
    assert sa.duration_ms == 100
    assert sa.tokens_used == 200


@pytest.mark.asyncio
async def test_get_active_window_app_only_non_allowlisted() -> None:
    """Non-allowlisted app: only app name is captured, no window title."""
    svc = ScreenPerceptionService()
    # Patch the helper that runs osascript so step-1 returns "Mail".
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Mail"),
    ) as step1, patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value=""),
    ) as step2:
        aw = await svc.get_active_window()
    assert aw.app == "Mail"
    assert aw.window_title is None
    step1.assert_awaited_once()
    # Step-2 must NOT be called for non-allowlisted apps.
    step2.assert_not_called()


@pytest.mark.asyncio
async def test_get_active_window_with_title_allowlisted() -> None:
    """Allowlisted app: window title captured."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Code"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value="orders.js — ama-solutions"),
    ) as step2:
        aw = await svc.get_active_window()
    assert aw.app == "Code"
    assert aw.window_title == "orders.js — ama-solutions"
    step2.assert_awaited_once_with("Code")


@pytest.mark.asyncio
async def test_get_active_window_blocks_title_for_non_allowlisted() -> None:
    """Safari is NOT in the allowlist — step-2 must not be called."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Safari"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value="should-not-appear"),
    ) as step2:
        aw = await svc.get_active_window()
    assert aw.app == "Safari"
    assert aw.window_title is None
    step2.assert_not_called()


@pytest.mark.asyncio
async def test_get_active_window_allowlist_is_case_sensitive() -> None:
    """Lowercase 'code' (vs allowlisted 'Code') falls through to app-only."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="code"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value="should-not-appear"),
    ) as step2:
        aw = await svc.get_active_window()
    assert aw.app == "code"
    assert aw.window_title is None
    step2.assert_not_called()


@pytest.mark.asyncio
async def test_get_active_window_step1_failure_returns_unknown() -> None:
    """Step-1 raising → returns ActiveWindow(app='unknown', ...); never raises."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(side_effect=MacControllerError("osascript not found")),
    ):
        aw = await svc.get_active_window()
    assert aw.app == "unknown"
    assert aw.window_title is None


@pytest.mark.asyncio
async def test_get_active_window_step1_empty_returns_unknown() -> None:
    """Step-1 returning '' → ActiveWindow(app='unknown', ...)."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value=""),
    ):
        aw = await svc.get_active_window()
    assert aw.app == "unknown"
    assert aw.window_title is None


@pytest.mark.asyncio
async def test_get_active_window_step2_failure_returns_app_only() -> None:
    """Step-2 raising → app preserved, window_title=None."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Code"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(side_effect=MacControllerError("window not found")),
    ):
        aw = await svc.get_active_window()
    assert aw.app == "Code"
    assert aw.window_title is None


@pytest.mark.asyncio
async def test_get_active_window_step2_empty_string_becomes_none() -> None:
    """Step-2 returning '' (no front window) → window_title=None, not ''."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Terminal"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value=""),
    ):
        aw = await svc.get_active_window()
    assert aw.app == "Terminal"
    assert aw.window_title is None


@pytest.mark.asyncio
async def test_get_active_window_app_name_regex_rejects_injection() -> None:
    """If step-1 somehow returns a string that fails APP_NAME_RE,
    step-2 must not be called even if the name is in the allowlist."""
    svc = ScreenPerceptionService()
    # Construct a string that isn't in the allowlist by exact match
    # but would also fail the regex. Tests defense-in-depth: allowlist
    # is the primary block, regex is the secondary one for any future
    # allowlist entry that contains unsafe characters.
    # We monkeypatch the allowlist to include the malicious string so
    # we exercise the regex check specifically.
    import services.screen_perception as sp_mod
    original = sp_mod.WINDOW_TITLE_ALLOWLIST
    sp_mod.WINDOW_TITLE_ALLOWLIST = frozenset({'Bad"; rm -rf /'})
    try:
        with patch.object(
            svc, "_run_osascript_for_step1",
            new=AsyncMock(return_value='Bad"; rm -rf /'),
        ), patch.object(
            svc, "_run_osascript_for_step2",
            new=AsyncMock(return_value="should-not-appear"),
        ) as step2:
            aw = await svc.get_active_window()
        assert aw.app == 'Bad"; rm -rf /'
        assert aw.window_title is None
        step2.assert_not_called()
    finally:
        sp_mod.WINDOW_TITLE_ALLOWLIST = original
