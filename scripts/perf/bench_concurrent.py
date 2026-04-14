"""
Benchmark 10 concurrent POST /command requests — all must succeed.

Usage:
  python -m scripts.perf.bench_concurrent [--concurrency 10] [--url http://localhost:3000]
"""

from __future__ import annotations

import argparse
import asyncio
import time
from typing import Dict, List

import httpx


async def _one(client: httpx.AsyncClient, url: str, payload: dict) -> Dict:
    t0 = time.perf_counter()
    try:
        resp = await client.post(url, json=payload, timeout=60.0)
        return {
            "status": getattr(resp, "status_code", 500),
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }


async def run_concurrent(
    url: str, payload: dict, concurrency: int = 10
) -> List[Dict]:
    """Fire N concurrent POSTs, return list of per-request results."""
    async with httpx.AsyncClient() as client:
        command_url = f"{url}/command" if not url.endswith("/command") else url
        tasks = [_one(client, command_url, payload) for _ in range(concurrency)]
        return await asyncio.gather(*tasks)


async def main(
    concurrency: int = 10, url: str = "http://localhost:3000"
) -> int:
    async with httpx.AsyncClient() as client:
        try:
            await client.get(f"{url}/health", timeout=2.0)
        except Exception:
            print(
                f"[bench_concurrent] CRUZ server not running at {url}. "
                "start CRUZ first."
            )
            return 2

    payload = {"message": "hi cruz", "stream": False}
    results = await run_concurrent(url, payload, concurrency=concurrency)
    errors = [r for r in results if r.get("status") != 200]
    latencies = [r["elapsed_ms"] for r in results]
    print(
        f"concurrency={concurrency}  ok={concurrency - len(errors)}  errors={len(errors)}  "
        f"min={min(latencies):.1f}ms  max={max(latencies):.1f}ms"
    )
    if errors:
        for e in errors[:3]:
            print(f"  error sample: {e}")
        return 1
    return 0


def _cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--url", type=str, default="http://localhost:3000")
    args = parser.parse_args()
    return asyncio.run(main(concurrency=args.concurrency, url=args.url))


if __name__ == "__main__":
    raise SystemExit(_cli())
