"""
PrivacyEngine — regex-based PII redaction for text that's about to be
stored in long-term memory (Qdrant) or written to agent_logs.

Deliberately conservative. We'd rather mask an over-broad match than leak
a real credential. Tune patterns as real false-positives surface.
"""
from __future__ import annotations

import re
from typing import List, Tuple

# Each tuple: (label, compiled_regex, replacement)
_PATTERNS: List[Tuple[str, re.Pattern, str]] = [
    # Credit card-ish (13-19 digits, allow spaces/dashes)
    ("CC", re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), "[REDACTED_CC]"),
    # US SSN
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    # Anthropic / OpenAI / Deepgram-style API keys
    (
        "API_KEY",
        re.compile(r"\b(sk-[A-Za-z0-9_-]{20,}|dg-[A-Za-z0-9_-]{20,}|ak-[A-Za-z0-9_-]{20,})\b"),
        "[REDACTED_API_KEY]",
    ),
    # Generic bearer-token patterns (40+ char alphanumeric + dashes)
    (
        "BEARER",
        re.compile(
            r"\b(?:bearer\s+)[A-Za-z0-9._-]{40,}\b",
            flags=re.IGNORECASE,
        ),
        "[REDACTED_BEARER]",
    ),
    # AWS-style access keys
    ("AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    # Private keys
    (
        "PRIVATE_KEY",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH |)PRIVATE KEY-----",
            flags=re.MULTILINE,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # Passwords in URL auth: postgres://user:pass@host/db  → keep user, mask pass
    (
        "URL_PASSWORD",
        re.compile(r"(://[^:/\s]+):([^@/\s]+)(@)"),
        r"\1:[REDACTED_PW]\3",
    ),
    # Bank-account-ish 8-17 contiguous digits (only when preceded by "account" word)
    (
        "BANK_ACCT",
        re.compile(
            r"\b(account\s+(?:number|#|no\.?)\s*:?\s*)(\d{8,17})\b",
            flags=re.IGNORECASE,
        ),
        r"\1[REDACTED_ACCT]",
    ),
]


def sanitize(text: str) -> str:
    """Return text with PII patterns masked. Safe to call on empty/None."""
    if not text:
        return text
    out = text
    for _label, pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    return out


def find(text: str) -> List[Tuple[str, str]]:
    """Return a list of (label, matched_text) for audit/debug."""
    if not text:
        return []
    hits: List[Tuple[str, str]] = []
    for label, pattern, _repl in _PATTERNS:
        for m in pattern.finditer(text):
            hits.append((label, m.group(0)))
    return hits
