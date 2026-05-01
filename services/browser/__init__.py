"""Public API for the browser primitive layer."""
from services.browser.errors import (
    BrowserError,
    BrowserTimeoutError,
    BrowserNavigationError,
    BrowserCaptchaDetected,
    BrowserRateLimited,
    BrowserProfileError,
)
from services.browser.service import BrowserService, get_browser_service

__all__ = [
    "BrowserError",
    "BrowserTimeoutError",
    "BrowserNavigationError",
    "BrowserCaptchaDetected",
    "BrowserRateLimited",
    "BrowserProfileError",
    "BrowserService",
    "get_browser_service",
]
