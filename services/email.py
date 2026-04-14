"""
EmailService — SendGrid-backed email sender for CRUZ.

Used by ECHO (client replies, outreach) and REACH (cold outreach) after
the approval gate has cleared. Gmail OAuth is a future provider and
intentionally not implemented here — SendGrid gives us a drop-in API-key
flow without a browser OAuth dance.

Env vars:
    SENDGRID_API_KEY — required to send
    EMAIL_FROM       — default "from" address (e.g. cruz@simpleinc.cloud)

Usage:
    from services.email import EmailService
    svc = EmailService()
    result = await svc.send(
        to="ateet@ama.com",
        subject="Project update",
        body="Shipping tomorrow.",
    )
    # result = {"sent": True, "message_id": "sg-..."}
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("cruz.services.email")

_SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


class EmailService:
    """Thin async wrapper around SendGrid v3 mail/send."""

    def __init__(self) -> None:
        # Read env at send-time (not init-time) so tests can patch os.environ.
        pass

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a single plain-text email via SendGrid.

        Returns {"sent": True, "message_id": str}.
        Raises RuntimeError on missing credentials or non-2xx response.
        """
        api_key = os.environ.get("SENDGRID_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "SENDGRID_API_KEY is not set — cannot send email. "
                "Set it in .env and restart."
            )

        sender = (from_email or os.environ.get("EMAIL_FROM", "")).strip()
        if not sender:
            raise RuntimeError(
                "EMAIL_FROM is not set and no explicit from_email provided. "
                "Configure EMAIL_FROM in .env (e.g. cruz@simpleinc.cloud)."
            )

        payload = {
            "personalizations": [
                {"to": [{"email": to}]},
            ],
            "from": {"email": sender},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": body},
            ],
        }

        async with httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=15.0,
        ) as client:
            resp = await client.post(_SENDGRID_URL, json=payload)

        if resp.status_code >= 300:
            raise RuntimeError(
                f"SendGrid send failed: HTTP {resp.status_code} — {resp.text}"
            )

        message_id = resp.headers.get("X-Message-Id", "")
        logger.info(
            "Email sent via SendGrid: to=%s subject=%s msg_id=%s",
            to, subject, message_id,
        )
        return {"sent": True, "message_id": message_id}
