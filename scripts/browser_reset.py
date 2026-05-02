#!/usr/bin/env python
"""Wipe a named browser profile directory.

Usage:
    python scripts/browser_reset.py <profile>
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main(profile: str) -> None:
    if not profile or not profile.replace("_", "").isalnum():
        sys.exit(f"invalid profile name: {profile!r}")

    profiles_dir = Path(os.path.expanduser(
        os.environ.get("CRUZ_BROWSER_PROFILES_DIR", "~/.cruz/browser-profiles")
    ))
    target = profiles_dir / profile
    if not target.exists():
        print(f"no such profile: {target}")
        return

    confirm = input(f"delete {target}? [y/N] ")
    if confirm.strip().lower() != "y":
        print("aborted.")
        return

    shutil.rmtree(target)
    print(f"deleted {target}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/browser_reset.py <profile>")
    main(sys.argv[1])
