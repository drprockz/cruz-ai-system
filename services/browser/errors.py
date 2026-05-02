"""Error hierarchy for the browser primitive layer."""
from __future__ import annotations


class BrowserError(Exception):
    """Base class for all browser layer errors."""


class BrowserTimeoutError(BrowserError):
    """Raised when a page load or wait_for selector times out."""


class BrowserNavigationError(BrowserError):
    """Raised on DNS, connection, SSL, or HTTP >= 500 errors."""


class BrowserCaptchaDetected(BrowserError):
    """Raised when a captcha challenge is detected on a fetched page."""

    def __init__(self, url: str, kind: str) -> None:
        self.url = url
        self.kind = kind
        super().__init__(f"captcha detected on {url}: {kind}")


class BrowserRateLimited(BrowserError):
    """Raised when the per-domain token bucket is exhausted."""

    def __init__(self, domain: str, retry_after_ms: int) -> None:
        self.domain = domain
        self.retry_after_ms = retry_after_ms
        super().__init__(
            f"rate limited at {domain}; retry after {retry_after_ms}ms"
        )


class BrowserProfileError(BrowserError):
    """Raised on invalid profile name or profile directory corruption."""
