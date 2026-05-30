#!/usr/bin/env bash
set -euo pipefail

cd /opt/bpstracker
ROLE="${1:-}"
USERNAME="${2:-}"
PASSWORD="${3:-}"

if [[ "$ROLE" != "admin" && "$ROLE" != "viewer" || -z "$USERNAME" || -z "$PASSWORD" ]]; then
  echo "Nutzung: $0 <admin|viewer> <benutzername> <neues-passwort>"
  echo "Beispiel: $0 viewer viewer 'MeinPasswort123!'"
  exit 1
fi

docker compose -p bpstracker exec -T backend python - <<PY
from app.database import SessionLocal
from app.models import User, UserRole
from app.security import delete_recovery_codes, password_hash, verify_password

role = UserRole(${ROLE@Q})
username = ${USERNAME@Q}.strip()
password = ${PASSWORD@Q}.strip()
if len(password) < 8:
    raise SystemExit('FEHLER: Passwort muss mindestens 8 Zeichen haben.')

with SessionLocal() as db:
    role_users = db.query(User).filter(User.role == role).order_by(User.id).all()
    user = next((u for u in role_users if u.is_active), None) or (role_users[0] if role_users else None)

    for u in db.query(User).order_by(User.id).all():
        if u.id != (user.id if user else None) and (u.username or '').lower() == username.lower():
            u.is_active = False
            u.username = f'{u.username}_disabled_{u.id}'
            db.add(u)

    if user is None:
        user = User(username=username, password_hash=password_hash(password), role=role, is_active=True)
        db.add(user)
        db.flush()
    else:
        user.username = username
        user.password_hash = password_hash(password)
        user.is_active = True
        db.add(user)

    if role == UserRole.viewer:
        user.totp_enabled = False
        user.totp_secret = None
        delete_recovery_codes(db, user)

    for duplicate in role_users:
        if duplicate.id != user.id:
            duplicate.is_active = False
            if duplicate.role == UserRole.viewer:
                duplicate.totp_enabled = False
                duplicate.totp_secret = None
                delete_recovery_codes(db, duplicate)
            db.add(duplicate)

    db.commit()
    db.refresh(user)
    ok = verify_password(password, user.password_hash)
    print(f'{role.value}-Zugang gesetzt: username={user.username!r}, id={user.id}, verify={ok}')
    if not ok:
        raise SystemExit('FEHLER: Passwort-Hash konnte direkt nach dem Speichern nicht verifiziert werden.')
PY
