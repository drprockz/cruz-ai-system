#!/usr/bin/env python3
"""
CRUZ AI System — end-to-end smoke test.

Runs a fixed battery of probes against a running CRUZ server and reports
pass/fail per path. Intended as the "did I actually wire this up right?"
check after local setup (Session A of Phase 6 hardening).

Usage:
    # Start CRUZ first:
    pm2 start ecosystem.config.js        # or: python backend/api/main.py

    # Then run this:
    python scripts/smoke/smoke_test.py
    python scripts/smoke/smoke_test.py --host http://localhost:3000
    python scripts/smoke/smoke_test.py --skip-llm    # probe /health only

Exit code:
    0 — all probes passed
    1 — one or more failed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

# ── Output helpers ────────────────────────────────────────────────────────

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
BOLD = "\033[1m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}!{RESET} {msg}")


def dim(msg: str) -> None:
    print(f"    {DIM}{msg}{RESET}")


def header(msg: str) -> None:
    print(f"\n{BOLD}{msg}{RESET}")


# ── Probe definitions ─────────────────────────────────────────────────────

@dataclass
class ProbeResult:
    name: str
    passed: bool
    duration_ms: int
    detail: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


async def probe_health(client: httpx.AsyncClient, host: str) -> ProbeResult:
    start = time.monotonic()
    try:
        r = await client.get(f"{host}/health", timeout=15.0)
        elapsed = int((time.monotonic() - start) * 1000)
        if r.status_code != 200:
            return ProbeResult("health", False, elapsed,
                               f"HTTP {r.status_code}", {"body": r.text[:300]})
        body = r.json()
        status = body.get("status")
        return ProbeResult(
            "health", status == "healthy", elapsed,
            f"status={status}", body,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return ProbeResult("health", False, elapsed, f"connection error: {exc}")


async def probe_command(
    client: httpx.AsyncClient,
    host: str,
    name: str,
    command: str,
    expect_agent: Optional[str] = None,
    timeout: float = 60.0,
) -> ProbeResult:
    start = time.monotonic()
    try:
        r = await client.post(
            f"{host}/command",
            json={"command": command, "device": "mac_mini", "stream": False},
            timeout=timeout,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        body = r.json()
        if r.status_code >= 500:
            return ProbeResult(name, False, elapsed,
                               f"HTTP {r.status_code}: {body.get('error', '?')[:150]}", body)
        # 202 (approval required) is still a pass — it means the agent ran
        if r.status_code not in (200, 202):
            return ProbeResult(name, False, elapsed,
                               f"unexpected HTTP {r.status_code}", body)

        actual_agent = body.get("agent", "?")
        agent_ok = expect_agent is None or actual_agent == expect_agent.upper()
        success = bool(body.get("success")) and agent_ok
        detail = (
            f"agent={actual_agent} "
            f"tokens={body.get('tokens_used', 0)} "
            f"duration={body.get('duration_ms', 0)}ms"
        )
        if not agent_ok:
            detail = f"expected agent={expect_agent} — {detail}"
        return ProbeResult(name, success, elapsed, detail, body)
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return ProbeResult(name, False, elapsed, f"error: {exc}")


async def probe_conversations_post(client: httpx.AsyncClient, host: str) -> ProbeResult:
    start = time.monotonic()
    try:
        r = await client.post(f"{host}/conversations", json={"device": "smoke"},
                              timeout=15.0)
        elapsed = int((time.monotonic() - start) * 1000)
        if r.status_code != 201:
            return ProbeResult("post-conversations", False, elapsed,
                               f"HTTP {r.status_code}", {"body": r.text[:200]})
        body = r.json()
        cid = body.get("conversation_id", "")
        if len(cid) != 36:
            return ProbeResult("post-conversations", False, elapsed,
                               f"bad uuid: {cid}", body)
        return ProbeResult("post-conversations", True, elapsed,
                           f"conversation_id={cid[:12]}…", body)
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return ProbeResult("post-conversations", False, elapsed, f"error: {exc}")


async def probe_agents_status(client: httpx.AsyncClient, host: str) -> ProbeResult:
    start = time.monotonic()
    try:
        r = await client.get(f"{host}/agents/status", timeout=10.0)
        elapsed = int((time.monotonic() - start) * 1000)
        if r.status_code != 200:
            return ProbeResult("agents-status", False, elapsed,
                               f"HTTP {r.status_code}")
        body = r.json()
        return ProbeResult("agents-status", isinstance(body, list), elapsed,
                           f"{len(body)} agent rows recorded", {"rows": body})
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return ProbeResult("agents-status", False, elapsed, f"error: {exc}")


# ── Orchestrator ──────────────────────────────────────────────────────────

async def run(host: str, skip_llm: bool) -> int:
    print(f"{BOLD}CRUZ smoke test — target: {host}{RESET}")

    async with httpx.AsyncClient() as client:
        # 1. Health
        header("1. /health")
        h = await probe_health(client, host)
        if h.passed:
            ok(f"{h.duration_ms}ms — {h.detail}")
        else:
            fail(f"{h.duration_ms}ms — {h.detail}")
            # Show which services are down
            for key in ("postgresql", "redis", "qdrant", "claude_api"):
                val = h.data.get(key, "?")
                if val not in ("connected", "reachable"):
                    dim(f"{key}: {val}")
            ollama = h.data.get("ollama", {})
            if isinstance(ollama, dict):
                missing = ollama.get("missing", [])
                if missing:
                    dim(f"ollama.missing: {missing}")
            # Without healthy dependencies, later probes will cascade-fail.
            warn("Dependencies degraded — later probes may also fail.")

        results: List[ProbeResult] = [h]

        # 2. Endpoint surface (no LLM)
        header("2. API endpoints")
        c = await probe_conversations_post(client, host)
        (ok if c.passed else fail)(f"POST /conversations — {c.duration_ms}ms — {c.detail}")
        results.append(c)

        a = await probe_agents_status(client, host)
        (ok if a.passed else fail)(f"GET /agents/status — {a.duration_ms}ms — {a.detail}")
        results.append(a)

        if skip_llm:
            warn("--skip-llm set; skipping LLM command probes.")
        else:
            # 3. Command paths — exercise each orchestration flow once
            header("3. POST /command (exercises Claude + RELAY + tool_use)")

            probes = [
                # Plain chat: no keyword → RELAY passes all tools, Claude likely end_turn
                ("plain-chat", "What can you help me with?", None),
                # FORGE: keyword match → RELAY narrows → tool_use → FORGE drafts code
                ("forge-write", "Write a Python function that parses CSV", "CRUZ"),
                # ECHO: "draft an email" keyword → narrow → ECHO drafts
                ("echo-draft", "Draft an email to test@example.com about deploy timing", "CRUZ"),
            ]
            for name, cmd, expect in probes:
                p = await probe_command(client, host, name, cmd, expect_agent=expect)
                (ok if p.passed else fail)(
                    f"{name:<14} — {p.duration_ms}ms — {p.detail}"
                )
                if not p.passed:
                    data = p.data if isinstance(p.data, dict) else {}
                    if data.get("error"):
                        dim(f"server error: {str(data['error'])[:200]}")
                results.append(p)

    # ── Summary ──
    header("Summary")
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    for r in results:
        marker = f"{GREEN}PASS{RESET}" if r.passed else f"{RED}FAIL{RESET}"
        print(f"  [{marker}] {r.name:<22} {r.duration_ms:>6}ms  {r.detail}")
    color = GREEN if passed == total else RED
    print(f"\n{color}{passed}/{total} probes passed{RESET}")
    return 0 if passed == total else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="http://localhost:3000",
                        help="CRUZ base URL")
    parser.add_argument("--skip-llm", action="store_true",
                        help="Skip POST /command probes (useful when Claude API is down)")
    args = parser.parse_args()
    return asyncio.run(run(args.host, args.skip_llm))


if __name__ == "__main__":
    sys.exit(main())
