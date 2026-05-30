from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, User
from ..schemas import BackupCreateRequest, BackupCreateResponse, BackupInfo
from ..security import require_admin

router = APIRouter(prefix='/api/backups', tags=['backups'])

BACKUP_DIR = Path('/app/data/backups')
BACKUP_MAGIC = b'BPSTrackerBackupV1\n'
PBKDF2_ITERATIONS = 390_000


def _backup_dir() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def _safe_backup_path(filename: str) -> Path:
    if not filename.endswith('.tar.gz.bpsenc'):
        raise HTTPException(status_code=400, detail='Invalid backup filename')
    if '/' in filename or '\\' in filename or filename.startswith('.'):
        raise HTTPException(status_code=400, detail='Invalid backup filename')
    path = _backup_dir() / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail='Backup not found')
    return path


def _database_url() -> str:
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise HTTPException(status_code=500, detail='DATABASE_URL is not configured')
    # pg_dump does not understand SQLAlchemy's postgresql+psycopg scheme.
    return url.replace('postgresql+psycopg://', 'postgresql://', 1)


def _write_env_snapshot(path: Path) -> None:
    keys = [
        'APP_NAME',
        'FRONTEND_PORT',
        'VITE_API_BASE_URL',
        'POSTGRES_DB',
        'POSTGRES_USER',
        'POSTGRES_PASSWORD',
        'DATABASE_URL',
        'JWT_SECRET',
        'SECRET_KEY',
    ]
    with path.open('w', encoding='utf-8') as fh:
        fh.write('# Environment snapshot created by BPSTracker backup\n')
        fh.write('# Review before restoring on another system.\n')
        for key in keys:
            if key in os.environ:
                value = str(os.environ.get(key, ''))
                escaped = value.replace('\\', '\\\\').replace('\n', '\\n')
                fh.write(f'{key}={escaped}\n')


def _copy_if_exists(source: Path, target: Path) -> None:
    if not source.exists():
        return
    if source.is_dir():
        shutil.copytree(source, target, ignore=shutil.ignore_patterns('backups', '*.tar.gz', '*.bpsenc'), dirs_exist_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _encrypt_file(input_path: Path, output_path: Path, password: str) -> None:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    key = kdf.derive(password.encode('utf-8'))
    aesgcm = AESGCM(key)
    plaintext = input_path.read_bytes()
    aad = b'BPSTracker encrypted backup v1'
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    header = {
        'format': 'bpstracker-backup-encrypted-v1',
        'cipher': 'AES-256-GCM',
        'kdf': 'PBKDF2-HMAC-SHA256',
        'iterations': PBKDF2_ITERATIONS,
        'salt': salt.hex(),
        'nonce': nonce.hex(),
        'aad': aad.decode('ascii'),
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    header_bytes = json.dumps(header, separators=(',', ':')).encode('utf-8')
    with output_path.open('wb') as fh:
        fh.write(BACKUP_MAGIC)
        fh.write(len(header_bytes).to_bytes(4, 'big'))
        fh.write(header_bytes)
        fh.write(ciphertext)


def _create_database_dump(output_file: Path) -> None:
    command = ['pg_dump', '--no-owner', '--no-privileges', '--format=plain', '--file', str(output_file), _database_url()]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f'pg_dump failed: {result.stderr.strip() or result.stdout.strip()}')


@router.get('', response_model=list[BackupInfo])
@router.get('/', include_in_schema=False)
def list_backups(_: User = Depends(require_admin)) -> list[BackupInfo]:
    backups: list[BackupInfo] = []
    for path in sorted(_backup_dir().glob('*.tar.gz.bpsenc'), key=lambda item: item.stat().st_mtime, reverse=True):
        stat = path.stat()
        backups.append(BackupInfo(
            filename=path.name,
            size_bytes=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        ))
    return backups


@router.post('/create', response_model=BackupCreateResponse)
def create_backup(
    payload: BackupCreateRequest,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> BackupCreateResponse:
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail='Backup passwords do not match')
    if len(payload.password) < 12:
        raise HTTPException(status_code=400, detail='Backup password must be at least 12 characters long')

    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    filename = f'bpstracker-backup-{timestamp}.tar.gz.bpsenc'
    output_path = _backup_dir() / filename

    with tempfile.TemporaryDirectory(prefix='bpstracker-backup-') as tmp_name:
        tmp = Path(tmp_name)
        content = tmp / 'backup'
        content.mkdir()

        manifest = {
            'app': 'BPSTracker',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'format': 'bpstracker-backup-v1',
            'encrypted': True,
            'contains': ['database.sql', 'environment.env', 'backend_data'],
        }
        (content / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

        _create_database_dump(content / 'database.sql')
        _write_env_snapshot(content / 'environment.env')
        _copy_if_exists(Path('/app/data'), content / 'backend_data')

        archive_path = tmp / 'backup.tar.gz'
        with tarfile.open(archive_path, 'w:gz') as tar:
            tar.add(content, arcname='backup')

        _encrypt_file(archive_path, output_path, payload.password)
        try:
            archive_path.unlink(missing_ok=True)
        except Exception:
            pass

    stat = output_path.stat()
    db.add(AuditLog(actor_user_id=actor.id, action='backup.create', details={'filename': filename, 'size_bytes': stat.st_size}))
    db.commit()

    return BackupCreateResponse(
        filename=filename,
        size_bytes=stat.st_size,
        download_url=f'/api/backups/download/{filename}',
    )


@router.get('/download/{filename}')
def download_backup(filename: str, _: User = Depends(require_admin)) -> FileResponse:
    path = _safe_backup_path(filename)
    return FileResponse(
        path,
        media_type='application/octet-stream',
        filename=filename,
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@router.delete('/{filename}')
def delete_backup(filename: str, actor: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, bool]:
    path = _safe_backup_path(filename)
    path.unlink()
    db.add(AuditLog(actor_user_id=actor.id, action='backup.delete', details={'filename': filename}))
    db.commit()
    return {'ok': True}
