"""Unit tests for services.mac_controller — subprocess mocked, no real osascript."""

from __future__ import annotations

import pytest

from services.mac_controller import (
    MacControllerError,
    MacControllerService,
    _escape_applescript_string,
    get_mac_controller_service,
)


# ── Escape helper ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("hello", "hello"),
        ('she said "hi"', 'she said \\"hi\\"'),
        (r"path\to\file", r"path\\to\\file"),
        ("line1\nline2", 'line1" & return & "line2'),
        ("tab\there", 'tab" & tab & "here'),
        ("emoji 🚀 ok", "emoji 🚀 ok"),
        ("", ""),
    ],
)
def test_escape_applescript_string(raw: str, expected: str) -> None:
    assert _escape_applescript_string(raw) == expected


def test_singleton_returns_same_instance() -> None:
    a = get_mac_controller_service()
    b = get_mac_controller_service()
    assert a is b
    assert isinstance(a, MacControllerService)


def test_mac_controller_error_is_runtime_error() -> None:
    err = MacControllerError("boom")
    assert isinstance(err, RuntimeError)
    assert str(err) == "boom"
