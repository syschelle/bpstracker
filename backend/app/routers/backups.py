from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import stat as stat_module
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from ..database import SessionLocal, engine, get_db
from ..models import AuditLog, User
from ..schemas import BackupCreateRequest, BackupInfo
from ..security import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/backups', tags=['backups'])

# Kept only for backwards compatibility with backups created by older releases.
# New backups are created in /tmp and deleted immediately after the HTTP download.
BACKUP_DIR = Path('/app/data/backups')
BACKUP_MAGIC = b'BPSTrackerBackupV1\n'
PBKDF2_ITERATIONS = 390_000
BACKUP_FILENAME_RE = re.compile(r'^bpstracker-backup-\d{8}-\d{6}\.tar\.gz\.bpsenc$')
MAX_BACKUP_UPLOAD_BYTES = 256 * 1024 * 1024
MAX_EXTRACTED_BYTES = 1024 * 1024 * 1024


def _database_url() -> str:
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise HTTPException(status_code=500, detail='DATABASE_URL is not configured')
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
        shutil.copytree(
            source,
            target,
            ignore=shutil.ignore_patterns('backups', '*.tar.gz', '*.bpsenc'),
            dirs_exist_ok=True,
        )
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


def _decrypt_file(input_path: Path, output_path: Path, password: str) -> None:
    try:
        with input_path.open('rb') as fh:
            if fh.read(len(BACKUP_MAGIC)) != BACKUP_MAGIC:
                raise HTTPException(status_code=400, detail='Invalid BPSTracker backup file')
            header_length_raw = fh.read(4)
            if len(header_length_raw) != 4:
                raise HTTPException(status_code=400, detail='Invalid BPSTracker backup header')
            header_length = int.from_bytes(header_length_raw, 'big')
            if header_length < 2 or header_length > 64 * 1024:
                raise HTTPException(status_code=400, detail='Invalid BPSTracker backup header')
            header_raw = fh.read(header_length)
            if len(header_raw) != header_length:
                raise HTTPException(status_code=400, detail='Invalid BPSTracker backup header')
            ciphertext = fh.read()
        header = json.loads(header_raw.decode('utf-8'))
    except HTTPException:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail='Invalid BPSTracker backup file') from exc

    if (
        header.get('format') != 'bpstracker-backup-encrypted-v1'
        or header.get('cipher') != 'AES-256-GCM'
        or header.get('kdf') != 'PBKDF2-HMAC-SHA256'
        or header.get('iterations') != PBKDF2_ITERATIONS
        or header.get('aad') != 'BPSTracker encrypted backup v1'
    ):
        raise HTTPException(status_code=400, detail='Unsupported BPSTracker backup format')

    try:
        salt = bytes.fromhex(str(header['salt']))
        nonce = bytes.fromhex(str(header['nonce']))
        if len(salt) != 16 or len(nonce) != 12:
            raise ValueError('invalid salt or nonce length')
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        key = kdf.derive(password.encode('utf-8'))
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, b'BPSTracker encrypted backup v1')
    except (KeyError, ValueError, InvalidTag) as exc:
        raise HTTPException(status_code=400, detail='Backup password is incorrect or the backup file is damaged') from exc

    output_path.write_bytes(plaintext)


def _create_database_dump(output_file: Path) -> None:
    command = ['pg_dump', '--no-owner', '--no-privileges', '--format=plain', '--file', str(output_file), _database_url()]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
    except FileNotFoundError as exc:
        logger.exception('Backup creation failed because pg_dump is not installed')
        raise HTTPException(status_code=500, detail='Backup failed: PostgreSQL pg_dump is not installed in the backend container') from exc
    except subprocess.TimeoutExpired as exc:
        logger.exception('Backup creation timed out while running pg_dump')
        raise HTTPException(status_code=500, detail='Backup failed: database dump timed out after 180 seconds') from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f'pg_dump exited with status {result.returncode}'
        logger.error('Backup database dump failed: %s', detail)
        raise HTTPException(status_code=500, detail=f'Backup failed while exporting PostgreSQL: {detail}')


def _create_encrypted_backup(output_path: Path, password: str) -> None:
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
        _encrypt_file(archive_path, output_path, password)


def _safe_archive_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    total_size = 0
    for member in members:
        member_path = Path(member.name)
        if member_path.is_absolute() or '..' in member_path.parts:
            raise HTTPException(status_code=400, detail='Backup archive contains an unsafe path')
        if not member.name.startswith('backup/') and member.name != 'backup':
            raise HTTPException(status_code=400, detail='Backup archive has an invalid structure')
        if member.issym() or member.islnk() or member.isdev() or member.isfifo():
            raise HTTPException(status_code=400, detail='Backup archive contains an unsupported file type')
        if member.isfile():
            total_size += member.size
            if total_size > MAX_EXTRACTED_BYTES:
                raise HTTPException(status_code=413, detail='Backup archive is too large after extraction')
    return members


def _extract_and_validate_backup(archive_path: Path, target_dir: Path) -> Path:
    try:
        with tarfile.open(archive_path, 'r:gz') as archive:
            members = _safe_archive_members(archive)
            archive.extractall(target_dir, members=members)
    except HTTPException:
        raise
    except (tarfile.TarError, OSError) as exc:
        raise HTTPException(status_code=400, detail='Invalid BPSTracker backup archive') from exc

    root = target_dir / 'backup'
    manifest_path = root / 'manifest.json'
    database_dump = root / 'database.sql'
    if not manifest_path.is_file() or not database_dump.is_file():
        raise HTTPException(status_code=400, detail='Backup is missing manifest.json or database.sql')
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail='Backup manifest is invalid') from exc
    if manifest.get('app') != 'BPSTracker' or manifest.get('format') != 'bpstracker-backup-v1':
        raise HTTPException(status_code=400, detail='Unsupported BPSTracker backup manifest')
    return root


def _restore_database_dump(database_dump: Path, work_dir: Path) -> None:
    restore_script = work_dir / 'restore.sql'
    with restore_script.open('wb') as output:
        output.write(b'DROP SCHEMA IF EXISTS public CASCADE;\nCREATE SCHEMA public;\n')
        with database_dump.open('rb') as source:
            shutil.copyfileobj(source, output)

    command = [
        'psql',
        '--no-psqlrc',
        '--set', 'ON_ERROR_STOP=1',
        '--single-transaction',
        '--file', str(restore_script),
        _database_url(),
    ]
    engine.dispose()
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail='Restore failed: PostgreSQL psql is not installed in the backend container') from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail='Restore failed: database restore timed out after 300 seconds') from exc
    finally:
        engine.dispose()
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f'psql exited with status {result.returncode}'
        logger.error('Backup restore failed: %s', detail)
        raise HTTPException(status_code=500, detail=f'Restore failed while importing PostgreSQL: {detail}')


def _restore_backend_data(source: Path) -> None:
    if not source.is_dir():
        return
    target = Path('/app/data')
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns('backups', '*.tar.gz', '*.bpsenc'),
        dirs_exist_ok=True,
    )


def _restore_uploaded_backup(encrypted_path: Path, password: str, work_dir: Path) -> None:
    archive_path = work_dir / 'backup.tar.gz'
    extracted_path = work_dir / 'extracted'
    extracted_path.mkdir()
    _decrypt_file(encrypted_path, archive_path, password)
    backup_root = _extract_and_validate_backup(archive_path, extracted_path)
    _restore_database_dump(backup_root / 'database.sql', work_dir)
    _restore_backend_data(backup_root / 'backend_data')


def _cleanup_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning('Could not remove temporary backup file %s', path)


def _validate_passwords(payload: BackupCreateRequest) -> None:
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail='Backup passwords do not match')
    if len(payload.password) < 12:
        raise HTTPException(status_code=400, detail='Backup password must be at least 12 characters long')


@router.post('/create-download')
def create_and_download_backup(
    payload: BackupCreateRequest,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FileResponse:
    _validate_passwords(payload)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    filename = f'bpstracker-backup-{timestamp}.tar.gz.bpsenc'
    fd, temp_name = tempfile.mkstemp(prefix='bpstracker-download-', suffix='.bpsenc', dir='/tmp')
    os.close(fd)
    output_path = Path(temp_name)
    try:
        _create_encrypted_backup(output_path, payload.password)
        size_bytes = output_path.stat().st_size
        db.add(AuditLog(actor_user_id=actor.id, action='backup.download_create', details={'filename': filename, 'size_bytes': size_bytes}))
        db.commit()
        logger.info('Encrypted backup created for direct download: %s (%d bytes)', filename, size_bytes)
        return FileResponse(
            output_path,
            media_type='application/octet-stream',
            filename=filename,
            headers={'Cache-Control': 'no-store'},
            background=BackgroundTask(_cleanup_file, output_path),
        )
    except Exception:
        _cleanup_file(output_path)
        raise


@router.post('/restore')
async def restore_backup(
    file: UploadFile = File(...),
    password: str = Form(...),
    actor: User = Depends(require_admin),
) -> dict[str, object]:
    if len(password) < 12:
        raise HTTPException(status_code=400, detail='Backup password must be at least 12 characters long')
    if file.filename and not file.filename.lower().endswith('.bpsenc'):
        raise HTTPException(status_code=400, detail='Please select a BPSTracker .bpsenc backup file')

    with tempfile.TemporaryDirectory(prefix='bpstracker-restore-') as tmp_name:
        tmp = Path(tmp_name)
        encrypted_path = tmp / 'upload.bpsenc'
        size = 0
        with encrypted_path.open('wb') as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BACKUP_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail='Backup file is larger than 256 MiB')
                output.write(chunk)
        await file.close()
        if size == 0:
            raise HTTPException(status_code=400, detail='Backup file is empty')

        await asyncio.to_thread(_restore_uploaded_backup, encrypted_path, password, tmp)

    # The restored database may contain a different audit history/user set, so do not
    # write an AuditLog row after replacing the schema. Keep an operational log instead.
    logger.warning('BPSTracker backup restore completed by admin user id=%s', actor.id)
    return {
        'ok': True,
        'message': 'Backup restored successfully.',
        'restart_recommended': True,
    }


# Legacy endpoints for backups created by BPSTracker <= 0.9.68. New versions no
# longer create persistent server-side backup files.
def _is_safe_backup_file(path: Path) -> bool:
    if not BACKUP_FILENAME_RE.fullmatch(path.name):
        return False
    try:
        file_stat = path.lstat()
    except FileNotFoundError:
        return False
    return stat_module.S_ISREG(file_stat.st_mode)


def _safe_backup_path(filename: str) -> Path:
    if not BACKUP_FILENAME_RE.fullmatch(filename):
        raise HTTPException(status_code=400, detail='Invalid backup filename')
    if not BACKUP_DIR.is_dir():
        raise HTTPException(status_code=404, detail='Backup not found')
    backup_dir = BACKUP_DIR.resolve()
    for candidate in backup_dir.iterdir():
        if candidate.name != filename:
            continue
        resolved = candidate.resolve(strict=False)
        if resolved.parent != backup_dir:
            raise HTTPException(status_code=400, detail='Invalid backup filename')
        if not _is_safe_backup_file(candidate):
            raise HTTPException(status_code=404, detail='Backup not found')
        return candidate
    raise HTTPException(status_code=404, detail='Backup not found')


@router.get('', response_model=list[BackupInfo])
@router.get('/', include_in_schema=False)
def list_backups(_: User = Depends(require_admin)) -> list[BackupInfo]:
    if not BACKUP_DIR.is_dir():
        return []
    try:
        paths = [p for p in BACKUP_DIR.iterdir() if _is_safe_backup_file(p)]
    except PermissionError:
        logger.warning('Legacy backup directory is not readable; returning an empty legacy backup list')
        return []
    backups: list[BackupInfo] = []
    for path in sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True):
        stat = path.stat()
        backups.append(BackupInfo(
            filename=path.name,
            size_bytes=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        ))
    return backups


@router.get('/download/{filename}')
def download_legacy_backup(filename: str, _: User = Depends(require_admin)) -> FileResponse:
    path = _safe_backup_path(filename)
    return FileResponse(path, media_type='application/octet-stream', filename=path.name)


@router.delete('/{filename}')
def delete_legacy_backup(filename: str, actor: User = Depends(require_admin)) -> dict[str, bool]:
    path = _safe_backup_path(filename)
    path.unlink()
    try:
        with SessionLocal() as db:
            db.add(AuditLog(actor_user_id=actor.id, action='backup.delete', details={'filename': filename}))
            db.commit()
    except Exception:
        logger.exception('Could not write audit entry for legacy backup deletion')
    return {'ok': True}
