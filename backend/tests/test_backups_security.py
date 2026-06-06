from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routers import backups


def test_safe_backup_path_accepts_only_regular_backup_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(backups, 'BACKUP_DIR', tmp_path)
    backup = tmp_path / 'bpstracker-backup-20260604-091500.tar.gz.bpsenc'
    backup.write_bytes(b'backup')

    assert backups._safe_backup_path(backup.name) == backup


@pytest.mark.parametrize('filename', [
    '../bpstracker-backup-20260604-091500.tar.gz.bpsenc',
    'subdir/bpstracker-backup-20260604-091500.tar.gz.bpsenc',
    '.bpstracker-backup-20260604-091500.tar.gz.bpsenc',
    'bpstracker-backup-20260604.tar.gz.bpsenc',
    'backup.tar.gz.bpsenc',
    'bpstracker-backup-20260604-091500.tar.gz',
])
def test_safe_backup_path_rejects_untrusted_filenames(tmp_path, monkeypatch, filename: str) -> None:
    monkeypatch.setattr(backups, 'BACKUP_DIR', tmp_path)

    with pytest.raises(HTTPException) as exc:
        backups._safe_backup_path(filename)

    assert exc.value.status_code == 400


def test_safe_backup_path_rejects_symlinks(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(backups, 'BACKUP_DIR', tmp_path)
    target = tmp_path / 'target.tar.gz.bpsenc'
    target.write_bytes(b'not selected directly')
    link = tmp_path / 'bpstracker-backup-20260604-091500.tar.gz.bpsenc'
    link.symlink_to(target)

    with pytest.raises(HTTPException) as exc:
        backups._safe_backup_path(link.name)

    assert exc.value.status_code == 404
