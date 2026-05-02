"""Unit tests for services.mac_controller — subprocess mocked, no real osascript."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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


# ── notify ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_basic() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc.notify("Hi", "Body text")
    run.assert_awaited_once()
    script = run.await_args.args[0]
    assert 'display notification "Body text"' in script
    assert 'with title "Hi"' in script
    assert "sound name" not in script


@pytest.mark.asyncio
async def test_notify_with_sound() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc.notify("Hi", "Body", sound=True)
    script = run.await_args.args[0]
    assert 'sound name "Submarine"' in script


@pytest.mark.asyncio
async def test_notify_escapes_quotes_and_newlines() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc.notify('She said "hi"', "line1\nline2")
    script = run.await_args.args[0]
    assert '\\"hi\\"' in script
    assert '" & return & "' in script


@pytest.mark.asyncio
async def test_notify_propagates_error() -> None:
    svc = MacControllerService()
    with patch.object(
        svc, "_run_osascript",
        new=AsyncMock(side_effect=MacControllerError("permission denied")),
    ):
        with pytest.raises(MacControllerError, match="permission denied"):
            await svc.notify("x", "y")
