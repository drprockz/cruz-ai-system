"""
Daily 4 AM backup task — snapshot Postgres + Redis + Qdrant, write to backup target.

Wired via workers/arq_worker.py cron. Failures of one snapshot are recorded
but do not stop the others: a partial backup is better than none.

Target selection: when BACKUP_LOCAL_DIR is set, snapshots are moved there;
otherwise they're uploaded to Google Drive.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from services.backup import BackupService

logger = logging.getLogger("cruz.workers.backup")


async def run_backup(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Snapshot all three stores, then write each to the configured target."""
    svc = BackupService()
    uploaded: list[str] = []
    errors: Dict[str, str] = {}
    use_local = bool(svc.local_dir)

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
            if use_local:
                target = await svc.save_local(path)
                uploaded.append(f"file://{target}")
                logger.info("[backup] %s → %s", name, target)
            else:
                url = await svc.upload_to_drive(path)
                uploaded.append(url)
                logger.info("[backup] %s → %s", name, url)
        except Exception as exc:
            logger.error("[backup] %s write failed: %s", name, exc)
            errors[name] = str(exc)

    return {"uploaded": uploaded, "errors": errors}
