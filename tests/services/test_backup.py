"""Tests for services/backup.py — BackupService."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_snapshot_postgres_calls_pg_dump():
    from services.backup import BackupService

    svc = BackupService()
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    with patch(
        "asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ) as mock_exec:
        path = await svc.snapshot_postgres()
        assert path.endswith(".dump")
        mock_exec.assert_awaited_once()
        args = mock_exec.await_args.args
        assert args[0] == "pg_dump"
        assert "-Fc" in args


@pytest.mark.asyncio
async def test_snapshot_postgres_raises_on_nonzero_exit():
    from services.backup import BackupService

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"boom"))
    with patch(
        "asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)
    ):
        with pytest.raises(RuntimeError, match="pg_dump"):
            await BackupService().snapshot_postgres()


@pytest.mark.asyncio
async def test_snapshot_redis_calls_redis_cli_rdb():
    from services.backup import BackupService

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    with patch(
        "asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)
    ) as mock_exec:
        path = await BackupService().snapshot_redis()
        assert path.endswith(".rdb")
        args = mock_exec.await_args.args
        assert args[0] == "redis-cli"
        assert "--rdb" in args


@pytest.mark.asyncio
async def test_snapshot_qdrant_tars_storage_dir(tmp_path):
    from services.backup import BackupService

    storage = tmp_path / "qdrant_storage"
    storage.mkdir()
    (storage / "dummy.txt").write_text("x")
    svc = BackupService(qdrant_storage_dir=str(storage))
    path = await svc.snapshot_qdrant()
    assert path.endswith(".tar.gz")
    assert os.path.exists(path)


@pytest.mark.asyncio
async def test_snapshot_qdrant_raises_when_dir_missing():
    from services.backup import BackupService

    svc = BackupService(qdrant_storage_dir="/nonexistent/path")
    with pytest.raises(FileNotFoundError):
        await svc.snapshot_qdrant()


@pytest.mark.asyncio
async def test_upload_to_drive_calls_google_api(tmp_path):
    from services import backup as backup_mod

    f = tmp_path / "snap.dump"
    f.write_bytes(b"data")

    mock_file = MagicMock()
    mock_file.execute = MagicMock(
        return_value={"id": "abc", "webViewLink": "https://drive.google.com/abc"}
    )
    mock_files = MagicMock()
    mock_files.create = MagicMock(return_value=mock_file)
    mock_service = MagicMock()
    mock_service.files = MagicMock(return_value=mock_files)

    import sys
    import types

    fake_http = types.ModuleType("googleapiclient.http")
    fake_http.MediaFileUpload = MagicMock(return_value=MagicMock())
    fake_api = types.ModuleType("googleapiclient")
    sys.modules.setdefault("googleapiclient", fake_api)
    sys.modules["googleapiclient.http"] = fake_http

    with patch.object(
        backup_mod.BackupService, "_drive_service", return_value=mock_service
    ):
        svc = backup_mod.BackupService(drive_folder_id="folder123")
        url = await svc.upload_to_drive(str(f))
        assert "drive.google.com" in url
        create_kwargs = mock_files.create.call_args.kwargs
        assert create_kwargs["body"]["parents"] == ["folder123"]


@pytest.mark.asyncio
async def test_upload_to_drive_raises_without_folder_id(tmp_path):
    from services.backup import BackupService

    f = tmp_path / "x.dump"
    f.write_bytes(b"x")
    svc = BackupService(drive_folder_id=None)
    with pytest.raises(RuntimeError, match="GOOGLE_DRIVE_FOLDER_ID"):
        await svc.upload_to_drive(str(f))
