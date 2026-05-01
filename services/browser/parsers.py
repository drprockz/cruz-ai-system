"""Pure HTML parsers for the browser primitive layer.

Selectors are constants defined here. When DDG (or any other engine) changes
markup, update only this file.
"""
from __future__ import annotations

import urllib.parse
from typing import List, TypedDict


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
