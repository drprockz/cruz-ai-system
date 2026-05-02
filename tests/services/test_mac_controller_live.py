# tests/services/test_mac_controller_live.py
"""Live-tier MacControllerService tests — real osascript / screencapture.

Run on the Mac Mini only:
    CRUZ_LIVE_MAC_TESTS=1 pytest tests/services/test_mac_controller_live.py -v

Skipped automatically on Linux / CI / when env var is unset.
"""

from __future__ import annotations

import asyncio
import io
import os
import platform
import sys

import pytest

from services.mac_controller import (
    MacControllerError,
    get_mac_controller_service,
)

LIVE = os.environ.get("CRUZ_LIVE_MAC_TESTS") == "1"
IS_MAC = platform.system() == "Darwin"

pytestmark = pytest.mark.skipif(
    not (LIVE and IS_MAC),
    reason="Live mac tests require CRUZ_LIVE_MAC_TESTS=1 on macOS",
)


@pytest.mark.asyncio
async def test_live_clipboard_round_trip() -> None:
    svc = get_mac_controller_service()
    sentinel = "CRUZ-test-clipboard-7f3a9c2e"
    original = ""
    try:
        original = await svc.clipboard_read()
    except MacControllerError:
        pass  # empty clipboard is fine

    await svc.clipboard_write(sentinel)
    read_back = await svc.clipboard_read()
    assert read_back == sentinel

    # Restore
    await svc.clipboard_write(original)


@pytest.mark.asyncio
async def test_live_notify_does_not_raise() -> None:
    svc = get_mac_controller_service()
    await svc.notify("CRUZ test", "If you see this, ignore — automated test.")


@pytest.mark.asyncio
async def test_live_open_app_textedit() -> None:
    svc = get_mac_controller_service()
    await svc.open_app("TextEdit")
    # Give it a moment to actually launch.
    await asyncio.sleep(1.0)
    # Confirm it's running via pgrep.
    proc = await asyncio.create_subprocess_exec(
        "pgrep", "-x", "TextEdit",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    assert proc.returncode == 0, "TextEdit should be running"

    # Cleanup — quit TextEdit politely.
    quit_proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", 'tell application "TextEdit" to quit',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await quit_proc.communicate()


@pytest.mark.asyncio
async def test_live_open_app_rejects_invalid_name() -> None:
    svc = get_mac_controller_service()
    with pytest.raises(MacControllerError, match="invalid app name"):
        await svc.open_app("TextEdit; do shell script")


@pytest.mark.asyncio
async def test_live_screenshot_returns_valid_png() -> None:
    svc = get_mac_controller_service()
    png = await svc.screenshot()
    assert png.startswith(b"\x89PNG\r\n\x1a\n"), "should be PNG magic"
    assert len(png) > 1000, "PNG should be more than 1 KB"

    # Optional richer parse if Pillow is installed.
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.size[0] > 0 and img.size[1] > 0


@pytest.mark.asyncio
async def test_live_screenshot_with_region() -> None:
    svc = get_mac_controller_service()
    png = await svc.screenshot(region=(0, 0, 200, 200))
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_live_open_app_unknown_raises() -> None:
    svc = get_mac_controller_service()
    with pytest.raises(MacControllerError):
        await svc.open_app("CRUZ-nonexistent-app-zzz")
