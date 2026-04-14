"""Long-running uptime probe for CRUZ.

Polls ``GET /health`` on a fixed interval and appends a JSONL record per
probe. Designed to run for 72h under launchd / cron / systemd-timer;
records are append-only so the file survives restarts.

Records shape::

    {"ts": "2026-04-14T10:00:00Z", "status_code": 200,
     "ok": true, "duration_ms": 12, "body_status": "healthy"}

Exit codes:
    0 — ran for the full window (or one-shot probe returned ok)
    2 — one-shot probe failed (``--once``)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx

DEFAULT_INTERVAL = 300  # 5 minutes
DEFAULT_DURATION = 72 * 3600  # 72 hours


@dataclass(frozen=True)
class Probe:
    ts: str
    status_code: int
    ok: bool
    duration_ms: int
    body_status: str | None
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "ts": self.ts,
                "status_code": self.status_code,
                "ok": self.ok,
                "duration_ms": self.duration_ms,
                "body_status": self.body_status,
                "error": self.error,
            }
        )


def probe_once(url: str, timeout: float = 10.0, *, client: httpx.Client | None = None) -> Probe:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    started = time.perf_counter()
    close = False
    if client is None:
        client = httpx.Client(timeout=timeout)
        close = True
    try:
        resp = client.get(url)
        duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            body_status = resp.json().get("status")
        except Exception:
            body_status = None
        ok = resp.status_code == 200 and body_status in {"healthy", "degraded", None}
        return Probe(ts, resp.status_code, ok, duration_ms, body_status)
    except Exception as exc:  # noqa: BLE001 — record every failure mode
        duration_ms = int((time.perf_counter() - started) * 1000)
        return Probe(ts, 0, False, duration_ms, None, error=str(exc)[:200])
    finally:
        if close:
            client.close()


def run(
    url: str,
    output: Path,
    *,
    interval: int = DEFAULT_INTERVAL,
    duration: int = DEFAULT_DURATION,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    probe: Callable[[str], Probe] = probe_once,
) -> int:
    """Run probes for ``duration`` seconds, returning the probe count."""
    output.parent.mkdir(parents=True, exist_ok=True)
    deadline = clock() + duration
    count = 0
    with output.open("a", encoding="utf-8") as fh:
        while True:
            result = probe(url)
            fh.write(result.to_json() + "\n")
            fh.flush()
            count += 1
            if clock() >= deadline:
                return count
            sleep(interval)


def summarize(records: list[dict]) -> dict:
    total = len(records)
    if total == 0:
        return {"total": 0, "ok": 0, "pct_ok": 0.0}
    ok = sum(1 for r in records if r.get("ok"))
    return {
        "total": total,
        "ok": ok,
        "fail": total - ok,
        "pct_ok": round(100 * ok / total, 2),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CRUZ uptime stability probe")
    p.add_argument("--url", default="http://localhost:3000/health")
    p.add_argument("--output", default="logs/uptime/stability.jsonl")
    p.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    p.add_argument("--duration", type=int, default=DEFAULT_DURATION)
    p.add_argument("--once", action="store_true", help="single probe, print + exit")
    p.add_argument("--summary", action="store_true", help="summarize an existing JSONL")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    out = Path(args.output)
    if args.summary:
        records = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
        print(json.dumps(summarize(records), indent=2))
        return 0
    if args.once:
        result = probe_once(args.url)
        print(result.to_json())
        return 0 if result.ok else 2
    count = run(args.url, out, interval=args.interval, duration=args.duration)
    print(f"Recorded {count} probes → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
