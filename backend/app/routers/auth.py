from __future__ import annotations

import asyncio
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..models import AuditLog, User, UserRole
from ..login_security import get_login_security_settings, login_failure_guard, resolve_client_ip
from ..notification_service import send_notification
from ..rate_limit import FixedWindowRateLimiter, raise_rate_limited
from ..schemas import (
    LoginRequest,
    TokenResponse,
    TwoFaEnableRequest,
    TwoFaEnableResponse,
    TwoFaVerifyRequest,
    UserRead,
)
from ..security import (
    build_totp_uri,
    consume_recovery_code,
    create_2fa_challenge_token,
    create_access_token,
    clear_auth_cookie,
    decode_token,
    delete_recovery_codes,
    generate_totp_secret,
    get_current_user,
    get_user_totp_secret,
    password_hash,
    password_needs_rehash,
    replace_recovery_codes,
    require_admin,
    set_auth_cookie,
    set_user_totp_secret,
    verify_password,
    verify_totp,
)

router = APIRouter(prefix='/api/auth', tags=['auth'])

LOGIN_IP_LIMIT = FixedWindowRateLimiter(limit=20, window_seconds=60)
LOGIN_ACCOUNT_LIMIT = FixedWindowRateLimiter(limit=5, window_seconds=60)
TWO_FA_IP_LIMIT = FixedWindowRateLimiter(limit=20, window_seconds=60)
TWO_FA_CHALLENGE_LIMIT = FixedWindowRateLimiter(limit=5, window_seconds=60)


def _hash_key(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:32]


def _enforce_limiter(limiter: FixedWindowRateLimiter, key: str) -> None:
    retry_after = limiter.check(key)
    if retry_after is not None:
        raise_rate_limited(retry_after)




async def _send_login_block_notification(source_ip: str, minutes: int) -> None:
    db = SessionLocal()
    try:
        await send_notification(
            db,
            'BPSTracker Security',
            f'Die Source-IP {source_ip} wurde nach fehlgeschlagenen Loginversuchen für {minutes} Minuten gesperrt.',
            priority=1,
        )
    except Exception:
        # Login protection must never fail because the optional notification provider
        # is disabled or temporarily unavailable.
        pass
    finally:
        db.close()


def _user_payload(user: User, recovery_codes: list[str] | None = None) -> dict:
    payload = UserRead.model_validate(user).model_dump()
    if recovery_codes is not None:
        payload['recovery_codes'] = recovery_codes
    return payload


@router.post('/login', response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    # Usernames are stored readable, but login should be forgiving about leading/trailing
    # whitespace and letter case. This prevents lockouts after manual setup edits.
    username = payload.username.strip()
    password = payload.password.strip()

    security_settings = get_login_security_settings(db)
    client_info = resolve_client_ip(request, security_settings.trusted_proxies)
    client_key = client_info.resolved_client_ip
    account_key = f'{client_key}:{username.lower()}'

    if security_settings.enabled:
        retry_after = login_failure_guard.blocked_for(client_key)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail='Source IP is temporarily blocked after failed login attempts.',
                headers={'Retry-After': str(retry_after)},
            )

    _enforce_limiter(LOGIN_IP_LIMIT, client_key)
    _enforce_limiter(LOGIN_ACCOUNT_LIMIT, account_key)
    # Prefer the active account. Older upgraded databases may still contain inactive
    # duplicates from previous test versions; those must not shadow the real viewer.
    user = (
        db.query(User)
        .filter(User.username == username, User.is_active.is_(True))
        .order_by(User.id)
        .first()
    )
    if user is None:
        user = (
            db.query(User)
            .filter(func.lower(User.username) == username.lower(), User.is_active.is_(True))
            .order_by(User.id)
            .first()
        )
    if not user or not verify_password(password, user.password_hash):
        attempt = 1
        newly_blocked = False
        retry_after = None
        if security_settings.enabled:
            attempt, newly_blocked, retry_after = login_failure_guard.record_failure(client_key, security_settings)
        db.add(AuditLog(actor_user_id=user.id if user else None, action='auth.login.failed', details={
            'username': username,
            'source_ip': client_key,
            'direct_ip': client_info.direct_ip,
            'attempt': attempt,
            'max_failed_attempts': security_settings.max_failed_attempts if security_settings.enabled else None,
        }))
        if newly_blocked:
            db.add(AuditLog(actor_user_id=user.id if user else None, action='auth.login.blocked', details={
                'username': username,
                'source_ip': client_key,
                'block_minutes': security_settings.block_minutes,
            }))
        db.commit()
        if newly_blocked:
            if security_settings.notify_on_block:
                asyncio.create_task(_send_login_block_notification(client_key, security_settings.block_minutes))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail='Source IP is temporarily blocked after failed login attempts.',
                headers={'Retry-After': str(retry_after or security_settings.block_minutes * 60)},
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')

    login_failure_guard.clear(client_key)
    if password_needs_rehash(user.password_hash):
        user.password_hash = password_hash(password)
        db.add(AuditLog(actor_user_id=user.id, action='auth.password_hash.upgraded', details={'algorithm': 'argon2id'}))
        db.commit()
        db.refresh(user)

    LOGIN_ACCOUNT_LIMIT.clear(account_key)

    if user.role == UserRole.admin and user.totp_enabled:
        return TokenResponse(requires_2fa=True, challenge_token=create_2fa_challenge_token(str(user.id)))

    set_auth_cookie(response, create_access_token(str(user.id)))
    return TokenResponse(requires_2fa=False)


@router.post('/2fa/verify', response_model=TokenResponse)
def verify_2fa(payload: TwoFaVerifyRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    security_settings = get_login_security_settings(db)
    client_key = resolve_client_ip(request, security_settings.trusted_proxies).resolved_client_ip
    challenge_key = _hash_key(payload.challenge_token)
    _enforce_limiter(TWO_FA_IP_LIMIT, client_key)
    _enforce_limiter(TWO_FA_CHALLENGE_LIMIT, challenge_key)

    decoded = decode_token(payload.challenge_token, expected_type='2fa')

    try:
        user_id = int(decoded.get('sub'))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid 2FA code')

    user = db.get(User, user_id)
    if not user or user.role != UserRole.admin or not user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid 2FA code')

    secret = get_user_totp_secret(user, db)
    totp_ok = bool(secret and verify_totp(secret, payload.code))
    recovery_ok = False if totp_ok else consume_recovery_code(db, user, payload.code)
    if not totp_ok and not recovery_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid 2FA code')

    TWO_FA_CHALLENGE_LIMIT.clear(challenge_key)

    if recovery_ok:
        db.add(AuditLog(actor_user_id=user.id, action='auth.2fa.recovery_code.used', details={}))
        db.commit()

    set_auth_cookie(response, create_access_token(str(user.id)))
    return TokenResponse(requires_2fa=False)


@router.post('/logout')
def logout(response: Response) -> Response:
    clear_auth_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get('/me', response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post('/2fa/setup')
def setup_2fa(user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, str]:
    secret = generate_totp_secret()
    set_user_totp_secret(user, secret)
    user.totp_enabled = False
    delete_recovery_codes(db, user)
    db.add(AuditLog(actor_user_id=user.id, action='auth.2fa.setup.started', details={}))
    db.commit()
    return {'secret': secret, 'provisioning_uri': build_totp_uri(user.username, secret)}


@router.post('/2fa/enable', response_model=TwoFaEnableResponse)
def enable_2fa(payload: TwoFaEnableRequest, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    secret = get_user_totp_secret(user, db)
    if not secret or not verify_totp(secret, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid 2FA code')
    user.totp_enabled = True
    recovery_codes = replace_recovery_codes(db, user)
    db.add(user)
    db.add(AuditLog(actor_user_id=user.id, action='auth.2fa.enabled', details={'recovery_code_count': len(recovery_codes)}))
    db.commit()
    db.refresh(user)
    return _user_payload(user, recovery_codes)

