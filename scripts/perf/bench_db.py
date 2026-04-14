"""
Benchmark P95 for hot SQL queries.

Measures:
  1. ConversationService.load_history (SELECT messages LIMIT 50)
  2. BaseAgent.log INSERT into agent_logs
  3. agent_logs SELECT by trace_id

Usage:
  python -m scripts.perf.bench_db [--n 100]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from typing import Awaitable, List

from scripts.perf.bench_command import percentiles


async def time_coro(coro: Awaitable) -> float:
    t0 = time.perf_counter()
    await coro
    return (time.perf_counter() - t0) * 1000.0


async def bench_load_history(db, conversation_id: str, n: int) -> List[float]:
    samples: List[float] = []
    for _ in range(n):
        samples.append(
            await time_coro(
                db.fetch(
                    """
                    SELECT role, content FROM messages
                    WHERE conversation_id = $1
                    ORDER BY created_at ASC
                    LIMIT 50
                    """,
                    conversation_id,
                )
            )
        )
    return samples


async def bench_agent_log_insert(db, n: int) -> List[float]:
    samples: List[float] = []
    for _ in range(n):
        tid = str(uuid.uuid4())
        samples.append(
            await time_coro(
                db.execute(
                    """
                    INSERT INTO agent_logs
                      (trace_id, agent, action, status, input_data, output_data,
                       tokens_used, duration_ms)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    """,
                    tid,
                    "bench",
                    "bench",
                    "success",
                    json.dumps({}),
                    json.dumps({}),
                    0,
                    1,
                )
            )
        )
    return samples


async def bench_logs_by_trace(db, trace_id: str, n: int) -> List[float]:
    samples: List[float] = []
    for _ in range(n):
        samples.append(
            await time_coro(
                db.fetch(
                    """
                    SELECT agent, action, status, duration_ms, created_at
                    FROM agent_logs
                    WHERE trace_id = $1
                    ORDER BY created_at ASC
                    """,
                    trace_id,
                )
            )
        )
    return samples


async def _connect():
    import asyncpg

    dsn = os.environ.get(
        "DATABASE_URL",
        "postgresql://cruz:password@localhost:5432/cruz_db",
    )
    return await asyncpg.connect(dsn)


async def main(n: int = 100) -> int:
    try:
        db = await _connect()
    except Exception as exc:
        print(
            f"[bench_db] PostgreSQL not running or DATABASE_URL misconfigured: {exc}. "
            "start postgres first: `brew services start postgresql@16`."
        )
        return 2

    try:
        conv_id = str(uuid.uuid4())
        await db.execute("INSERT INTO conversations (id) VALUES ($1)", conv_id)
        trace_id = str(uuid.uuid4())
        # seed a row for the by-trace query
        await db.execute(
            """
            INSERT INTO agent_logs
              (trace_id, agent, action, status, input_data, output_data,
               tokens_used, duration_ms)
            VALUES ($1,'seed','seed','success','{}','{}',0,1)
            """,
            trace_id,
        )

        hist = await bench_load_history(db, conv_id, n)
        ins = await bench_agent_log_insert(db, n)
        byt = await bench_logs_by_trace(db, trace_id, n)
    finally:
        await db.close()

    print("query                       n     p50(ms)   p95(ms)   p99(ms)")
    print("-" * 64)
    for label, s in (
        ("load_history", hist),
        ("agent_log_insert", ins),
        ("logs_by_trace_id", byt),
    ):
        p = percentiles(s)
        print(
            f"{label:26s}  {len(s):4d}  {p['p50']:8.2f}  {p['p95']:8.2f}  {p['p99']:8.2f}"
        )
    return 0


def _cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    args = parser.parse_args()
    return asyncio.run(main(n=args.n))


if __name__ == "__main__":
    raise SystemExit(_cli())
