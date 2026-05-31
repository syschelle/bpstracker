from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, User, UserRole
from ..schemas import InstallAdminRequest, InstallCompleteResponse, InstallStatusResponse
from ..security import delete_recovery_codes, password_hash

router = APIRouter(prefix='/api/install', tags=['install'])


def install_required(db: Session) -> bool:
    """Return True only while no active admin account has a stored password hash."""
    configured_admin = (
        db.query(User)
        .filter(
            User.role == UserRole.admin,
            User.is_active.is_(True),
            User.password_hash.is_not(None),
            User.password_hash != '',
        )
        .first()
    )
    return configured_admin is None


@router.get('/status', response_model=InstallStatusResponse)
def get_install_status(db: Session = Depends(get_db)) -> InstallStatusResponse:
    return InstallStatusResponse(install_required=install_required(db))


@router.post('/admin', response_model=InstallCompleteResponse, status_code=status.HTTP_201_CREATED)
def create_initial_admin(payload: InstallAdminRequest, db: Session = Depends(get_db)) -> InstallCompleteResponse:
    if not install_required(db):
        # Behave as a disabled setup endpoint once an admin account exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Install endpoint is disabled')

    username = payload.username.strip()
    password = payload.password
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Passwords do not match')

    existing_admins = db.query(User).filter(User.role == UserRole.admin).order_by(User.id).all()
    admin = existing_admins[0] if existing_admins else None

    username_conflict = (
        db.query(User)
        .filter(func.lower(User.username) == username.lower())
        .first()
    )
    if username_conflict is not None and (admin is None or username_conflict.id != admin.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Username already exists')

    if admin is None:
        admin = User(username=username, password_hash=password_hash(password), role=UserRole.admin, is_active=True)
    else:
        admin.username = username
        admin.password_hash = password_hash(password)
        admin.role = UserRole.admin
        admin.is_active = True
        admin.totp_enabled = False
        admin.totp_secret = None
        delete_recovery_codes(db, admin)

    db.add(admin)
    db.flush()

    # Harden upgraded databases that may contain duplicate admin rows from old builds.
    for duplicate in existing_admins:
        if duplicate.id != admin.id:
            duplicate.is_active = False
            duplicate.totp_enabled = False
            duplicate.totp_secret = None
            delete_recovery_codes(db, duplicate)
            db.add(duplicate)

    db.add(AuditLog(actor_user_id=None, action='install.admin.created', details={'username': username}))
    db.commit()
    return InstallCompleteResponse(ok=True)
