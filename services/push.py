# services/push.py
"""FCM push notification dispatch.

PushService is a singleton constructed in lifespan() with the path to a
Firebase service-account JSON. Public API:

    push = get_push_service()  # may be None in degraded mode
    if push:
        await push.send_to_user(user_id, PushPayload(title="...", body="..."))

Auto-prunes UNREGISTERED / Invalid / SenderIdMismatch tokens on send.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

import firebase_admin
from firebase_admin import credentials, initialize_app, messaging

logger = logging.getLogger("cruz.services.push")


@dataclass
class PushPayload:
    title: str
    body: str
    url: Optional[str] = None
    trace_id: Optional[str] = None


@dataclass
class SendResult:
    token: str
    ok: bool
    msg_id: Optional[str] = None
    reason: Optional[str] = None


class PushService:
    def __init__(self, sa_path: str, project_id: str, db: Any = None) -> None:
        cred = credentials.Certificate(sa_path)
        # Reuse the default app if already initialized (lifespan called twice
        # in tests). firebase_admin._apps is the registry.
        if "[DEFAULT]" not in firebase_admin._apps:
            initialize_app(cred, {"projectId": project_id})
        self._db = db

    async def send_to_user(self, user_id: int, payload: PushPayload) -> list[SendResult]:
        raise NotImplementedError("Task 1.4")
