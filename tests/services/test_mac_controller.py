"""Unit tests for services.mac_controller — subprocess mocked, no real osascript."""

from __future__ import annotations

import asyncio
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


# ── clipboard ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clipboard_read_basic() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="hello\n")) as run:
        result = await svc.clipboard_read()
    assert result == "hello"
    script = run.await_args.args[0]
    assert "the clipboard as text" in script


@pytest.mark.asyncio
async def test_clipboard_read_empty() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="\n")):
        assert await svc.clipboard_read() == ""


@pytest.mark.asyncio
async def test_clipboard_write_basic() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc.clipboard_write("paste me")
    script = run.await_args.args[0]
    assert 'set the clipboard to "paste me"' in script


@pytest.mark.asyncio
async def test_clipboard_write_escapes_quotes() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc.clipboard_write('say "hi"')
    script = run.await_args.args[0]
    assert '\\"hi\\"' in script


@pytest.mark.asyncio
async def test_clipboard_write_empty_string_ok() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")):
        await svc.clipboard_write("")  # must not raise


# ── open_app ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_app_basic() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc.open_app("TextEdit")
    script = run.await_args.args[0]
    assert 'tell application "TextEdit" to activate' == script


@pytest.mark.asyncio
async def test_open_app_allows_safe_chars() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")):
        await svc.open_app("Visual Studio Code")
        await svc.open_app("Plane.so")
        await svc.open_app("My_App-1")  # no raise


@pytest.mark.asyncio
async def test_open_app_rejects_injection() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")):
        with pytest.raises(MacControllerError, match="invalid app name"):
            await svc.open_app('TextEdit"; do shell script "rm -rf /')
        with pytest.raises(MacControllerError, match="invalid app name"):
            await svc.open_app("TextEdit\nMail")
        with pytest.raises(MacControllerError, match="invalid app name"):
            await svc.open_app("")


@pytest.mark.asyncio
async def test_open_app_propagates_osascript_error() -> None:
    svc = MacControllerService()
    with patch.object(
        svc, "_run_osascript",
        new=AsyncMock(side_effect=MacControllerError("application not found")),
    ):
        with pytest.raises(MacControllerError, match="application not found"):
            await svc.open_app("NonexistentApp")


# ── screenshot ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_screenshot_full_screen() -> None:
    svc = MacControllerService()
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(fake_png, b""))
    mock_proc.returncode = 0
    with patch(
        "services.mac_controller.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ) as create:
        result = await svc.screenshot()
    assert result == fake_png
    args = create.await_args.args
    assert args[0] == "screencapture"
    assert "-x" in args
    assert "-t" in args and "png" in args
    assert "-" in args  # stdout marker
    assert "-R" not in args  # no region


@pytest.mark.asyncio
async def test_screenshot_with_region() -> None:
    svc = MacControllerService()
    fake_png = b"\x89PNG"
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(fake_png, b""))
    mock_proc.returncode = 0
    with patch(
        "services.mac_controller.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ) as create:
        await svc.screenshot(region=(100, 200, 800, 600))
    args = create.await_args.args
    assert "-R" in args
    r_idx = args.index("-R")
    assert args[r_idx + 1] == "100,200,800,600"


@pytest.mark.asyncio
async def test_screenshot_propagates_error() -> None:
    svc = MacControllerService()
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b"screencapture: error"))
    mock_proc.returncode = 1
    with patch(
        "services.mac_controller.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ):
        with pytest.raises(MacControllerError, match="screencapture: error"):
            await svc.screenshot()


@pytest.mark.asyncio
async def test_screenshot_timeout() -> None:
    svc = MacControllerService()
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_proc.kill = lambda: None
    mock_proc.wait = AsyncMock(return_value=0)
    with patch(
        "services.mac_controller.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ):
        with pytest.raises(MacControllerError, match="timed out"):
            await svc.screenshot()


# ── _calendar_create_local ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calendar_create_local_basic() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc._calendar_create_local(
            title="Deep work",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T12:00:00",
            calendar_name="Calendar",
        )
    script = run.await_args.args[0]
    assert 'tell application "Calendar"' in script
    assert 'tell calendar "Calendar"' in script
    assert "make new event" in script
    assert "Deep work" in script
    # AppleScript date literal — _iso_to_applescript_date converts ISO to MM/DD/YYYY HH:MM:SS
    assert 'date "05/01/2026 10:00:00"' in script
    assert 'date "05/01/2026 12:00:00"' in script


@pytest.mark.asyncio
async def test_calendar_create_local_escapes_title() -> None:
    svc = MacControllerService()
    with patch.object(svc, "_run_osascript", new=AsyncMock(return_value="")) as run:
        await svc._calendar_create_local(
            title='Call "Acme Inc."',
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T11:00:00",
        )
    script = run.await_args.args[0]
    assert '\\"Acme Inc.\\"' in script


@pytest.mark.asyncio
async def test_calendar_create_local_propagates_error() -> None:
    svc = MacControllerService()
    with patch.object(
        svc, "_run_osascript",
        new=AsyncMock(side_effect=MacControllerError("calendar not found")),
    ):
        with pytest.raises(MacControllerError, match="calendar not found"):
            await svc._calendar_create_local(
                title="x",
                start_iso="2026-05-01T10:00:00",
                end_iso="2026-05-01T11:00:00",
            )
