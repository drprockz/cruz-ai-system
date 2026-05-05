"""Unit tests for services.screen_perception — subprocess + LLM mocked."""

from __future__ import annotations

import pytest

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
