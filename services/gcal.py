"""
GCalService — Google Calendar API wrapper for the Calendar agent.

OAuth 2.0 with stored refresh token. Token lives at GCAL_TOKEN_PATH
(default ~/.config/cruz/gcal-token.json) and is provisioned by
scripts/gcal_auth.py once per machine.

Public surface used by agents/calendar/calendar_agent.py:
  - create_event(title, start_iso, end_iso, attendees=None, **kw) -> dict
  - list_events(start_iso, end_iso, calendar_id=None) -> list[dict]
  - delete_event(event_id, calendar_id=None) -> None  (used by test cleanup)

Spec: docs/superpowers/specs/2026-04-26-sp3-mac-controller-design.md §4
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cruz.services.gcal")

_DEFAULT_TOKEN_PATH = "~/.config/cruz/gcal-token.json"
_DEFAULT_CALENDAR_ID = "primary"
_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class GCalError(RuntimeError):
    """Raised on Google Calendar API failures."""


class GCalAuthError(GCalError):
    """Raised when the OAuth token is missing, malformed, or refresh fails."""


_instance: Optional["GCalService"] = None


def get_gcal_service() -> "GCalService":
    """Return the module-level GCalService singleton."""
    global _instance
    if _instance is None:
        _instance = GCalService()
    return _instance


class GCalService:
    """Async wrapper around the synchronous google-api-python-client.

    The Google client is sync — we offload calls to a thread via asyncio.to_thread
    so we don't block the event loop.
    """

    def __init__(self) -> None:
        self._token_path = Path(
            os.path.expanduser(
                os.environ.get("GCAL_TOKEN_PATH", _DEFAULT_TOKEN_PATH)
            )
        )
        self._default_calendar_id = os.environ.get(
            "GCAL_DEFAULT_CALENDAR_ID", _DEFAULT_CALENDAR_ID
        )
        self._refresh_lock = threading.Lock()

    # ── Auth ───────────────────────────────────────────────────────────

    def _load_credentials(self):
        """Load Credentials from GCAL_TOKEN_PATH. Raise GCalAuthError on failure."""
        from google.oauth2.credentials import Credentials

        if not self._token_path.exists():
            raise GCalAuthError(f"token file not found at {self._token_path}")
        try:
            data = json.loads(self._token_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise GCalAuthError(f"failed to read token file: {exc}") from exc

        try:
            creds = Credentials(
                token=data.get("token"),
                refresh_token=data["refresh_token"],
                token_uri=data["token_uri"],
                client_id=data["client_id"],
                client_secret=data["client_secret"],
                scopes=data.get("scopes", _SCOPES),
            )
        except KeyError as exc:
            raise GCalAuthError(f"token file missing key: {exc}") from exc

        # Refresh if needed.
        if not creds.valid:
            with self._refresh_lock:
                if not creds.valid:
                    from google.auth.transport.requests import Request
                    try:
                        creds.refresh(Request())
                    except Exception as exc:
                        raise GCalAuthError(f"token refresh failed: {exc}") from exc
                    data["token"] = creds.token
                    self._token_path.write_text(json.dumps(data, indent=2))

        return creds

    def _build_service(self):
        """Build a Google Calendar service object. Cached per call (cheap)."""
        from googleapiclient.discovery import build
        creds = self._load_credentials()
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    # ── create_event ──────────────────────────────────────────────────

    async def create_event(
        self,
        title: str,
        start_iso: str,
        end_iso: str,
        attendees: Optional[List[str]] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        calendar_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert one event. Returns Google's event resource on success."""
        cal = calendar_id or self._default_calendar_id
        body: Dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
        }
        if attendees:
            body["attendees"] = [{"email": e} for e in attendees]
        if description:
            body["description"] = description
        if location:
            body["location"] = location

        return await asyncio.to_thread(self._sync_create_event, cal, body)

    def _sync_create_event(self, cal: str, body: Dict[str, Any]) -> Dict[str, Any]:
        from googleapiclient.errors import HttpError
        try:
            return self._build_service().events().insert(
                calendarId=cal,
                body=body,
                sendUpdates="all" if "attendees" in body else "none",
            ).execute()
        except HttpError as exc:
            raise GCalError(f"Google API error {exc.resp.status}: {exc}") from exc

    # ── list_events ───────────────────────────────────────────────────

    async def list_events(
        self,
        start_iso: str,
        end_iso: str,
        calendar_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List events in [start, end). Returns a flat list of event resources."""
        cal = calendar_id or self._default_calendar_id
        return await asyncio.to_thread(
            self._sync_list_events, cal, _ensure_z(start_iso), _ensure_z(end_iso)
        )

    def _sync_list_events(self, cal: str, time_min: str, time_max: str) -> List[Dict[str, Any]]:
        from googleapiclient.errors import HttpError
        try:
            response = self._build_service().events().list(
                calendarId=cal,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=2500,
            ).execute()
            return response.get("items", [])
        except HttpError as exc:
            raise GCalError(f"Google API error {exc.resp.status}: {exc}") from exc

    # ── delete_event (test cleanup only) ──────────────────────────────

    async def delete_event(
        self,
        event_id: str,
        calendar_id: Optional[str] = None,
    ) -> None:
        """Delete an event by ID."""
        cal = calendar_id or self._default_calendar_id
        await asyncio.to_thread(self._sync_delete_event, cal, event_id)

    def _sync_delete_event(self, cal: str, event_id: str) -> None:
        from googleapiclient.errors import HttpError
        try:
            self._build_service().events().delete(
                calendarId=cal, eventId=event_id
            ).execute()
        except HttpError as exc:
            raise GCalError(f"Google API error {exc.resp.status}: {exc}") from exc


def _ensure_z(iso: str) -> str:
    """Append 'Z' UTC marker if the ISO string has no offset.

    Returns date-only strings (length < 11) unchanged — they are not
    datetimes and the caller is responsible for using `date` rather than
    `dateTime` in the event body.
    """
    if len(iso) < 11:
        return iso
    if iso.endswith("Z") or "+" in iso[10:] or "-" in iso[10:]:
        return iso
    return iso + "Z"
