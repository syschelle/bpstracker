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


def test_safe_archive_members_rejects_path_traversal(tmp_path) -> None:
    import io
    import tarfile

    archive_path = tmp_path / 'unsafe.tar.gz'
    with tarfile.open(archive_path, 'w:gz') as archive:
        info = tarfile.TarInfo('../escape.txt')
        payload = b'nope'
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    with tarfile.open(archive_path, 'r:gz') as archive:
        with pytest.raises(HTTPException) as exc:
            backups._safe_archive_members(archive)
    assert exc.value.status_code == 400


def test_encrypt_decrypt_backup_round_trip(tmp_path) -> None:
    source = tmp_path / 'backup.tar.gz'
    encrypted = tmp_path / 'backup.bpsenc'
    restored = tmp_path / 'restored.tar.gz'
    source.write_bytes(b'example encrypted backup payload')

    backups._encrypt_file(source, encrypted, 'correct-horse-battery-staple')
    backups._decrypt_file(encrypted, restored, 'correct-horse-battery-staple')

    assert restored.read_bytes() == source.read_bytes()


def test_decrypt_rejects_wrong_password(tmp_path) -> None:
    source = tmp_path / 'backup.tar.gz'
    encrypted = tmp_path / 'backup.bpsenc'
    restored = tmp_path / 'restored.tar.gz'
    source.write_bytes(b'example encrypted backup payload')

    backups._encrypt_file(source, encrypted, 'correct-horse-battery-staple')
    with pytest.raises(HTTPException) as exc:
        backups._decrypt_file(encrypted, restored, 'wrong-password-123')

    assert exc.value.status_code == 400
