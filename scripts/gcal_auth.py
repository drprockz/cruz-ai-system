# scripts/gcal_auth.py
"""
One-time Google Calendar OAuth bootstrap.

Run on the Mac Mini:
    python scripts/gcal_auth.py

Requires GCAL_CLIENT_ID + GCAL_CLIENT_SECRET in environment (or .env).

Opens a browser for consent, writes the refresh token to
GCAL_TOKEN_PATH (default ~/.config/cruz/gcal-token.json), then
prints the user's primary calendar to confirm.

Spec: docs/superpowers/specs/2026-04-26-sp3-mac-controller-design.md §4
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
DEFAULT_TOKEN_PATH = "~/.config/cruz/gcal-token.json"


def main() -> int:
    client_id = os.environ.get("GCAL_CLIENT_ID")
    client_secret = os.environ.get("GCAL_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("ERROR: GCAL_CLIENT_ID and GCAL_CLIENT_SECRET must be set in env.")
        print()
        print("Get them from https://console.cloud.google.com/apis/credentials")
        print("(create an OAuth 2.0 Client ID, type 'Desktop app').")
        return 1

    token_path = Path(
        os.path.expanduser(os.environ.get("GCAL_TOKEN_PATH", DEFAULT_TOKEN_PATH))
    )
    token_path.parent.mkdir(parents=True, exist_ok=True)

    if token_path.exists():
        resp = input(f"Token already exists at {token_path}. Overwrite? [y/N] ")
        if resp.strip().lower() != "y":
            print("Aborted. Existing token kept.")
            return 0

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    print("Opening browser for Google consent...")
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }
    token_path.write_text(json.dumps(payload, indent=2))
    token_path.chmod(0o600)
    print(f"\n✓ Refresh token written to {token_path} (mode 0600)")

    # Verify by listing the primary calendar.
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    cal = service.calendars().get(calendarId="primary").execute()
    print(f"✓ Authenticated as: {cal.get('summary')} ({cal.get('id')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
