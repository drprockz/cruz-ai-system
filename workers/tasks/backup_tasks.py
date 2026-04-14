"""
Daily 4 AM backup task — snapshot Postgres + Redis + Qdrant, upload to Drive.

Wired via workers/arq_worker.py cron. Failures of one snapshot are recorded
but do not stop the others: a partial backup is better than none.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from services.backup import BackupService

logger = logging.getLogger("cruz.workers.backup")


async def run_backup(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Snapshot all three stores in parallel-ish, then upload each."""
    svc = BackupService()
    uploaded: list[str] = []
    errors: Dict[str, str] = {}

    targets = [
        ("postgres", svc.snapshot_postgres),
        ("redis", svc.snapshot_redis),
        ("qdrant", svc.snapshot_qdrant),
    ]

    for name, snapshot in targets:
        try:
            path = await snapshot()
        except Exception as exc:
            logger.error("[backup] %s snapshot failed: %s", name, exc)
            errors[name] = str(exc)
            continue

        try:
            url = await svc.upload_to_drive(path)
            uploaded.append(url)
            logger.info("[backup] %s → %s", name, url)
        except Exception as exc:
            logger.error("[backup] %s upload failed: %s", name, exc)
            errors[name] = str(exc)

    return {"uploaded": uploaded, "errors": errors}
