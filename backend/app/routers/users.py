from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, User, UserRole
from ..schemas import UserCredentialUpdate, UserRead
from ..security import delete_recovery_codes, password_hash, require_admin

router = APIRouter(prefix='/api/users', tags=['users'])


@router.get('', response_model=list[UserRead])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[User]:
    return db.query(User).order_by(User.role).all()


@router.patch('/{role}', response_model=UserRead)
def update_role_credentials(
    role: UserRole,
    payload: UserCredentialUpdate,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    # Older MVP databases may contain duplicate users for one role because the
    # singleton role constraint was added later. Always update the first active
    # account for the role and disable duplicates so the Setup tab is deterministic.
    role_users = db.query(User).filter(User.role == role).order_by(User.id).all()
    user = next((candidate for candidate in role_users if candidate.is_active), None) or (role_users[0] if role_users else None)

    username = payload.username.strip()
    password = payload.password.strip() if payload.password else None
    if not user and not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Password is required when creating a user role')
    # If an inactive duplicate with this username exists from an older test build,
    # rename it instead of blocking the intended admin/setup change. Active users
    # with another role still conflict as expected.
    current_user_id = user.id if user is not None else -1
    username_conflicts = (
        db.query(User)
        .filter(func.lower(User.username) == username.lower(), User.id != current_user_id)
        .order_by(User.id)
        .all()
    )
    for conflict in username_conflicts:
        if conflict.is_active:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Username already exists')
        conflict.username = f'{conflict.username}_disabled_{conflict.id}'
        db.add(conflict)

    if user is None:
        user = User(username=username, password_hash=password_hash(password or ''), role=role, is_active=True)
    else:
        user.username = username
        if password:
            user.password_hash = password_hash(password)
        user.is_active = True

    # Disable duplicate accounts with the same role from old test deployments.
    for duplicate in role_users:
        if duplicate.id != user.id:
            duplicate.is_active = False
            if role == UserRole.viewer:
                duplicate.totp_enabled = False
                duplicate.totp_secret = None
                delete_recovery_codes(db, duplicate)
            db.add(duplicate)

    # Only the admin account may use 2FA. Make sure the viewer cannot inherit
    # legacy 2FA settings or recovery codes.
    if role == UserRole.viewer:
        user.totp_enabled = False
        user.totp_secret = None
        delete_recovery_codes(db, user)

    db.add(user)
    db.add(AuditLog(actor_user_id=actor.id, action='user.credentials.update', details={'role': role.value, 'password_changed': bool(password)}))
    db.commit()
    db.refresh(user)
    return user
