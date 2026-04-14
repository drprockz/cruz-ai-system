"""
AlertService — Telegram + Sentry notification wrapper.

Used by CruzAgent (unhandled exceptions), TITAN (deploy failures),
and ARQ workers (scheduled task failures) to surface problems to the
operator in real time.

Env vars:
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID — Telegram destination
    SENTRY_DSN                           — Sentry project DSN

Contract:
    await AlertService().notify(severity, title, message) -> dict
        severity ∈ {"critical", "warning", "info"}
    Returns {"telegram": bool, "sentry": bool, "error"?: str}.
    Never raises — failures are logged and reported in the return value.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

import httpx

logger = logging.getLogger("cruz.services.alerts")


_SEVERITY_EMOJI = {"critical": "🔴", "warning": "🟠", "info": "🔵"}
_SENTRY_LEVEL = {"critical": "error", "warning": "warning", "info": "info"}


class AlertService:
    """Fire-and-forget Telegram + Sentry alert fan-out."""

    async def notify(self, severity: str, title: str, message: str) -> Dict[str, Any]:
        severity = severity.lower()
        result: Dict[str, Any] = {"telegram": False, "sentry": False}

        tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        sentry_dsn = os.environ.get("SENTRY_DSN", "").strip()

        if tg_token and tg_chat:
            try:
                emoji = _SEVERITY_EMOJI.get(severity, "")
                text = f"{emoji} [{severity.upper()}] {title}\n\n{message}"
                url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(
                        url,
                        json={"chat_id": tg_chat, "text": text},
                    )
                if 200 <= resp.status_code < 300:
                    result["telegram"] = True
                else:
                    result["error"] = f"telegram http {resp.status_code}"
                    logger.warning("telegram alert failed: %s", resp.text)
            except Exception as exc:
                result["error"] = f"telegram: {exc}"
                logger.warning("telegram alert error: %s", exc)

        if sentry_dsn:
            try:
                import sentry_sdk  # type: ignore

                sentry_sdk.capture_message(
                    f"{title}: {message}",
                    level=_SENTRY_LEVEL.get(severity, "info"),
                )
                result["sentry"] = True
            except Exception as exc:
                result["error"] = result.get("error") or f"sentry: {exc}"
                logger.warning("sentry alert error: %s", exc)

        return result


_default: AlertService | None = None


def get_alert_service() -> AlertService:
    global _default
    if _default is None:
        _default = AlertService()
    return _default


# ---------------------------------------------------------------------------
# Loki log shipping
# ---------------------------------------------------------------------------

import time
from typing import Optional


class LokiHandler(logging.Handler):
    """
    Ship log records to a Grafana Loki instance via /loki/api/v1/push.

    Synchronous POST with a short timeout. Failures never raise — Loki
    being down must not take CRUZ down with it.
    """

    def __init__(
        self,
        url: str,
        labels: Optional[Dict[str, str]] = None,
        timeout: float = 2.0,
    ):
        super().__init__()
        self.url = url.rstrip("/") + "/loki/api/v1/push"
        self.labels = labels or {"app": "cruz"}
        self.timeout = timeout

    def emit(self, record: logging.LogRecord) -> None:
        try:
            ts_ns = str(int(time.time() * 1_000_000_000))
            line = self.format(record) if self.formatter else record.getMessage()
            stream_labels = {
                **self.labels,
                "level": record.levelname.lower(),
                "logger": record.name,
            }
            body = {
                "streams": [
                    {"stream": stream_labels, "values": [[ts_ns, line]]},
                ]
            }
            httpx.post(self.url, json=body, timeout=self.timeout)
        except Exception:
            # Never let logging crash the process.
            pass


def install_loki_logging(
    logger: Optional[logging.Logger] = None,
    labels: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Attach a LokiHandler to `logger` (or root) if LOKI_URL is set.

    Returns True if installed, False if skipped.
    """
    url = os.environ.get("LOKI_URL", "").strip()
    if not url:
        return False
    target = logger if logger is not None else logging.getLogger()
    target.addHandler(LokiHandler(url=url, labels=labels))
    return True
