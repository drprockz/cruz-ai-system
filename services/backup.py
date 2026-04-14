"""
BackupService — snapshots Postgres, Redis, Qdrant and uploads to Google Drive.

Run by workers/tasks/backup_tasks.py on a 4 AM daily ARQ cron.

Env vars:
  DATABASE_URL                     — parsed for pg_dump connection
  REDIS_URL                        — parsed for redis-cli connection (default: redis://localhost:6379)
  QDRANT_STORAGE_DIR               — on-disk path to qdrant_storage (default: ./qdrant_storage)
  GOOGLE_DRIVE_FOLDER_ID           — destination folder (required for upload)
  GOOGLE_APPLICATION_CREDENTIALS   — path to service-account JSON (Google auth)
"""

from __future__ import annotations

import asyncio
import os
import tarfile
import tempfile
import time
from typing import Optional
from urllib.parse import urlparse


def _ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


class BackupService:
    """Wraps pg_dump, redis-cli, qdrant tar, and Google Drive upload."""

    def __init__(
        self,
        database_url: Optional[str] = None,
        redis_url: Optional[str] = None,
        qdrant_storage_dir: Optional[str] = None,
        drive_folder_id: Optional[str] = None,
        tmp_dir: Optional[str] = None,
    ) -> None:
        self.database_url = database_url or os.environ.get(
            "DATABASE_URL",
            "postgresql://cruz:password@localhost:5432/cruz_db",
        )
        self.redis_url = redis_url or os.environ.get(
            "REDIS_URL", "redis://localhost:6379"
        )
        self.qdrant_storage_dir = qdrant_storage_dir or os.environ.get(
            "QDRANT_STORAGE_DIR", "qdrant_storage"
        )
        self.drive_folder_id = drive_folder_id or os.environ.get(
            "GOOGLE_DRIVE_FOLDER_ID"
        )
        self.tmp_dir = tmp_dir or tempfile.gettempdir()

    async def snapshot_postgres(self) -> str:
        """pg_dump -Fc to /tmp/cruz-pg-<ts>.dump. Returns the path."""
        out = os.path.join(self.tmp_dir, f"cruz-pg-{_ts()}.dump")
        proc = await asyncio.create_subprocess_exec(
            "pg_dump",
            "-Fc",
            "-f",
            out,
            self.database_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"pg_dump failed (exit={proc.returncode}): {stderr.decode(errors='ignore')}"
            )
        return out

    async def snapshot_redis(self) -> str:
        """redis-cli --rdb to /tmp/cruz-redis-<ts>.rdb. Returns the path."""
        out = os.path.join(self.tmp_dir, f"cruz-redis-{_ts()}.rdb")
        parsed = urlparse(self.redis_url)
        host = parsed.hostname or "localhost"
        port = str(parsed.port or 6379)

        proc = await asyncio.create_subprocess_exec(
            "redis-cli",
            "-h",
            host,
            "-p",
            port,
            "--rdb",
            out,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"redis-cli --rdb failed (exit={proc.returncode}): "
                f"{stderr.decode(errors='ignore')}"
            )
        return out

    async def snapshot_qdrant(self) -> str:
        """tar.gz the qdrant_storage dir. Returns the tarball path."""
        src = self.qdrant_storage_dir
        if not os.path.isdir(src):
            raise FileNotFoundError(f"qdrant storage dir missing: {src}")
        out = os.path.join(self.tmp_dir, f"cruz-qdrant-{_ts()}.tar.gz")

        def _tar():
            with tarfile.open(out, "w:gz") as tf:
                tf.add(src, arcname=os.path.basename(src.rstrip(os.sep)))

        await asyncio.get_event_loop().run_in_executor(None, _tar)
        return out

    def _drive_service(self):
        """Build the Google Drive v3 service (isolated for test patching)."""
        from google.oauth2 import service_account  # type: ignore
        from googleapiclient.discovery import build  # type: ignore

        creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path:
            raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS not set")
        creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    async def upload_to_drive(self, path: str) -> str:
        """Upload a snapshot to Drive; return its webViewLink."""
        if not self.drive_folder_id:
            raise RuntimeError("GOOGLE_DRIVE_FOLDER_ID not set")

        from googleapiclient.http import MediaFileUpload  # type: ignore

        service = self._drive_service()
        body = {
            "name": os.path.basename(path),
            "parents": [self.drive_folder_id],
        }
        media = MediaFileUpload(path, resumable=True)

        def _upload():
            return (
                service.files()
                .create(body=body, media_body=media, fields="id,webViewLink")
                .execute()
            )

        result = await asyncio.get_event_loop().run_in_executor(None, _upload)
        return result.get("webViewLink") or f"drive://file/{result.get('id')}"
