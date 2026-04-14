"""
Benchmark POST /command latency across paths.

Measures p50/p95/p99 for:
  - plain chat (no keyword)
  - RELAY-narrowed forge ("FORGE, fix bug")
  - RELAY-narrowed titan ("deploy to prod")
  - SSE streaming

Usage:
  python -m scripts.perf.bench_command [--n 100] [--url http://localhost:3000]
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from typing import Dict, List, Optional

import httpx


PATHS = [
    ("plain_chat", {"message": "what can you help with?", "stream": False}),
    ("relay_forge", {"message": "FORGE, fix the null check on orders.js", "stream": False}),
    ("relay_titan", {"message": "TITAN, deploy to prod", "stream": False}),
    ("sse_stream", {"message": "hello cruz", "stream": True}),
]


def percentiles(samples: List[float]) -> Dict[str, float]:
    """Return p50/p95/p99 of samples (ms). Empty list → zeros."""
    if not samples:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
    s = sorted(samples)
    n = len(s)

    def pct(p: float) -> float:
        # nearest-rank percentile
        k = max(0, min(n - 1, int(round(p / 100.0 * n)) - 1))
        return s[k]

    return {"p50": pct(50), "p95": pct(95), "p99": pct(99)}


async def run_one(
    client: httpx.AsyncClient, url: str, payload: dict
) -> Optional[float]:
    """POST once; return elapsed ms on success, None on error."""
    t0 = time.perf_counter()
    try:
        resp = await client.post(url, json=payload, timeout=30.0)
        if getattr(resp, "status_code", 500) >= 500:
            return None
    except Exception:
        return None
    return (time.perf_counter() - t0) * 1000.0


async def bench_path(
    client: httpx.AsyncClient, url: str, payload: dict, n: int
) -> List[float]:
    """Run N sequential requests, return the non-None elapsed samples."""
    out: List[float] = []
    for _ in range(n):
        ms = await run_one(client, url, payload)
        if ms is not None:
            out.append(ms)
    return out


async def _server_reachable(client: httpx.AsyncClient, base: str) -> bool:
    try:
        await client.get(f"{base}/health", timeout=2.0)
        return True
    except Exception:
        return False


async def main(n: int = 100, url: str = "http://localhost:3000") -> int:
    async with httpx.AsyncClient() as client:
        if not await _server_reachable(client, url):
            print(
                f"[bench_command] CRUZ server not running at {url}. "
                "start CRUZ first: `pm2 start ecosystem.config.js` "
                "or `python backend/api/main.py`."
            )
            return 2

        command_url = f"{url}/command"
        results: Dict[str, Dict[str, float]] = {}
        for name, payload in PATHS:
            samples = await bench_path(client, command_url, payload, n)
            results[name] = {
                **percentiles(samples),
                "n": len(samples),
                "attempted": n,
            }

    print("path                  n     p50(ms)   p95(ms)   p99(ms)")
    print("-" * 60)
    for name, r in results.items():
        print(
            f"{name:20s}  {int(r['n']):4d}  {r['p50']:8.1f}  {r['p95']:8.1f}  {r['p99']:8.1f}"
        )
    return 0


def _cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--url", type=str, default="http://localhost:3000")
    args = parser.parse_args()
    return asyncio.run(main(n=args.n, url=args.url))


if __name__ == "__main__":
    raise SystemExit(_cli())
