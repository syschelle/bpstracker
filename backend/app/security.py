from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import RecoveryCode, User, UserRole, utcnow

# Passwords are stored with Argon2id. A bcrypt verifier remains in place only so
# older BPSTracker test databases keep working; successful legacy logins are
# automatically upgraded by the auth router.
argon2_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19456,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
legacy_pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/api/auth/login')


_ARGON2ID_PREFIX = '$argon2id$'
_RECOVERY_CODE_COUNT = 10
_RECOVERY_CODE_BYTES = 10
_RECOVERY_NORMALIZE_RE = re.compile(r'[^A-Za-z0-9]')


def password_hash(password: str) -> str:
    return argon2_hasher.hash(password)


def is_argon2id_hash(hashed: str | None) -> bool:
    return bool(hashed and hashed.startswith(_ARGON2ID_PREFIX))


def verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    if is_argon2id_hash(hashed):
        try:
            return argon2_hasher.verify(hashed, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    # Very early local test builds and the Growtent reference used plain SHA-256
    # hex hashes. This is kept only as a one-way migration path so users are not
    # locked out; successful logins are re-hashed as Argon2id by the auth router.
    normalized_hash = hashed.strip()
    if re.fullmatch(r'[A-Fa-f0-9]{64}', normalized_hash):
        digest = hashlib.sha256(password.encode('utf-8')).hexdigest()
        return safe_compare(digest.lower(), normalized_hash.lower())

    # Legacy BPSTracker builds used passlib/bcrypt. Keep this path only for
    # migration compatibility.
    try:
        return legacy_pwd_context.verify(password, normalized_hash)
    except Exception:
        return False


def password_needs_rehash(hashed: str | None) -> bool:
    if not hashed:
        return True
    if not is_argon2id_hash(hashed):
        return True
    try:
        return argon2_hasher.check_needs_rehash(hashed)
    except Exception:
        return True


def _jwt_secret() -> str:
    return get_settings().secret_key


def create_access_token(subject: str, extra: dict[str, Any] | None = None, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload: dict[str, Any] = {'sub': subject, 'exp': expire, 'typ': 'access'}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _jwt_secret(), algorithm='HS256')


def create_2fa_challenge_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    return jwt.encode({'sub': subject, 'exp': expire, 'typ': '2fa'}, _jwt_secret(), algorithm='HS256')


def decode_token(token: str, expected_type: str = 'access') -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=['HS256'])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token') from exc
    if payload.get('typ') != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token type')
    return payload


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_token(token, expected_type='access')
    subject = payload.get('sub')
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Inactive or unknown user')
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin and getattr(user.role, 'value', user.role) != UserRole.admin.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin role required')
    return user


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_totp_uri(username: str, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=get_settings().app_name)


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def _fernet() -> Fernet:
    digest = hashlib.sha256(get_settings().secret_key.encode('utf-8')).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode('utf-8')).decode('utf-8')


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        return None


def set_user_totp_secret(user: User, plain_secret: str | None) -> None:
    user.totp_secret = encrypt_secret(plain_secret) if plain_secret else None


def get_user_totp_secret(user: User, db: Session | None = None) -> str | None:
    """Return the plain TOTP secret.

    Old test builds stored the secret in clear text. If such a value is found,
    it is returned and, when a db session is supplied, immediately encrypted in
    place so the migration is automatic.
    """
    if not user.totp_secret:
        return None
    decrypted = decrypt_secret(user.totp_secret)
    if decrypted:
        return decrypted

    # Best-effort legacy migration: pyotp base32 secrets are normally uppercase
    # base32 values. Validate by constructing TOTP; don't log the value.
    candidate = user.totp_secret.strip()
    try:
        pyotp.TOTP(candidate).now()
    except Exception:
        return None
    if db is not None:
        set_user_totp_secret(user, candidate)
        db.add(user)
        db.commit()
        db.refresh(user)
    return candidate


def normalize_recovery_code(code: str) -> str:
    return _RECOVERY_NORMALIZE_RE.sub('', code).upper()


def format_recovery_code(raw: str) -> str:
    normalized = normalize_recovery_code(raw)
    return '-'.join(normalized[i:i + 4] for i in range(0, len(normalized), 4))


def generate_recovery_code() -> str:
    # token_urlsafe may include '-' and '_'; normalize to uppercase alphanumerics
    # so users can enter codes with or without separators.
    raw = secrets.token_urlsafe(_RECOVERY_CODE_BYTES)
    normalized = normalize_recovery_code(raw)
    while len(normalized) < 12:
        normalized += normalize_recovery_code(secrets.token_urlsafe(4))
    return format_recovery_code(normalized[:16])


def replace_recovery_codes(db: Session, user: User, count: int = _RECOVERY_CODE_COUNT) -> list[str]:
    db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id).delete()
    codes = [generate_recovery_code() for _ in range(count)]
    for code in codes:
        db.add(RecoveryCode(user_id=user.id, code_hash=password_hash(normalize_recovery_code(code))))
    return codes


def consume_recovery_code(db: Session, user: User, code: str) -> bool:
    normalized = normalize_recovery_code(code)
    if not normalized:
        return False
    active_codes = db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None)).all()
    for recovery_code in active_codes:
        if verify_password(normalized, recovery_code.code_hash):
            recovery_code.used_at = utcnow()
            db.add(recovery_code)
            db.commit()
            return True
    return False


def delete_recovery_codes(db: Session, user: User) -> None:
    db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id).delete()


def safe_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode('utf-8'), right.encode('utf-8'))
