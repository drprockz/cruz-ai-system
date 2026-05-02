"""Pure HTML parsers for the browser primitive layer.

Selectors are constants defined here. When DDG (or any other engine) changes
markup, update only this file.
"""
from __future__ import annotations

import re as _re_captcha
import urllib.parse
from typing import List, Optional, TypedDict


class SearchResult(TypedDict):
    title: str
    url: str
    snippet: str
    rank: int


class PageResult(TypedDict):
    url: str
    final_url: str
    status: int
    title: str
    html: str
    text: str
    byte_size: int


_CAPTCHA_TEXT_PATTERN = _re_captcha.compile(
    r"please verify you are (a )?human|are you a robot|press and hold to confirm",
    _re_captcha.IGNORECASE,
)

# Patterns indicating documentation or discussion about captchas, not an actual challenge
_CAPTCHA_META_PATTERN = _re_captcha.compile(
    r"how (captcha|recaptcha|hcaptcha|turnstile) works|explains?.*(captcha|challenge)",
    _re_captcha.IGNORECASE,
)


def _parse_ddg_html(html: str) -> List[SearchResult]:
    """Parse DuckDuckGo HTML response.

    Returns ranked results; returns an empty list on structural change so
    callers can detect a parser break without crashing.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results: List[SearchResult] = []
    for rank, item in enumerate(
        soup.select("div.result, div.web-result"),
        start=1,
    ):
        a = item.select_one("a.result__a")
        snippet_el = item.select_one(".result__snippet")
        if not a or not a.get("href"):
            continue
        # DDG sometimes wraps in /l/?uddg= redirector — strip if present
        href = a["href"]
        parsed = urllib.parse.urlparse(href)
        if parsed.path == "/l/":
            qs = urllib.parse.parse_qs(parsed.query)
            href = qs.get("uddg", [href])[0]
        results.append(
            SearchResult(
                title=a.get_text(strip=True),
                url=href,
                snippet=snippet_el.get_text(" ", strip=True) if snippet_el else "",
                rank=rank,
            )
        )
    return results


def _detect_captcha(html: str, url: str) -> Optional[str]:
    """Return the captcha kind if a challenge is detected on the page, else None.

    Heuristic — over-detects deliberately. False positives surface to caller as
    BrowserCaptchaDetected; caller decides how to fall back. Pure function over
    HTML, fully testable.
    """
    if not html:
        return None
    lower = html.lower()
    # Iframe-based challenges
    if 'src="https://www.google.com/recaptcha/' in lower:
        return "recaptcha"
    if 'src="https://newassets.hcaptcha.com/' in lower or 'class="h-captcha"' in lower:
        return "hcaptcha"
    if 'src="https://challenges.cloudflare.com/turnstile/' in lower:
        return "turnstile"
    # Text heuristic — body content asks the user to prove they're human
    # But exclude documentation pages that explain captchas in general
    if _CAPTCHA_TEXT_PATTERN.search(html):
        if _CAPTCHA_META_PATTERN.search(html):
            return None
        return "text_heuristic"
    return None
