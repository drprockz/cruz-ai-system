#!/usr/bin/env python
"""Open a headed Chromium window pointed at a named profile.

Usage:
    python scripts/browser_login.py <profile>

The window stays open until you close it. Use this once per profile to log
into sites manually — cookies persist for headless reuse.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


async def main(profile: str) -> None:
    if not profile or not profile.replace("_", "").isalnum():
        sys.exit(f"invalid profile name: {profile!r}")

    from playwright.async_api import async_playwright

    profiles_dir = Path(os.path.expanduser(
        os.environ.get("CRUZ_BROWSER_PROFILES_DIR", "~/.cruz/browser-profiles")
    ))
    profile_dir = profiles_dir / profile
    profile_dir.mkdir(parents=True, exist_ok=True)

    print(f"opening headed Chromium against {profile_dir}")
    print("log in as needed; close the window when done.")

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = await ctx.new_page()
        await page.goto("about:blank")
        # Block until the user closes the context (all pages).
        try:
            while ctx.pages:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        await ctx.close()
    print(f"done. profile saved to {profile_dir}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/browser_login.py <profile>")
    asyncio.run(main(sys.argv[1]))
