"""Per-domain token-bucket rate limiter for browser primitives."""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("cruz.services.browser.rate_limit")


@dataclass(frozen=True)
class TokenBucketSpec:
    """Specification for a token bucket: capacity and refill rate."""
    capacity: int
    refill_per_sec: float


_DEFAULT_BUCKET = TokenBucketSpec(capacity=10, refill_per_sec=10 / 60)


def _parse_rate_limit_env(raw: str) -> dict[str, TokenBucketSpec]:
    """Parse `domain:cap:N/D,...` into a policy dict.

    Example: "duckduckgo.com:30:30/60,techcrunch.com:5:5/60"
    """
    out: dict[str, TokenBucketSpec] = {}
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            domain, cap_s, rate_s = entry.split(":")
            num, denom = rate_s.split("/")
            out[domain] = TokenBucketSpec(
                capacity=int(cap_s),
                refill_per_sec=float(num) / float(denom),
            )
        except Exception:
            logger.warning("ignoring malformed rate-limit entry: %r", entry)
    return out
