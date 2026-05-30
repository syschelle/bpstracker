#!/usr/bin/env bash
set -euo pipefail

cd /opt/bpstracker
USERNAME="${1:-viewer}"
PASSWORD="${2:-}"

if [[ -z "$PASSWORD" ]]; then
  echo "Nutzung: $0 <viewer-benutzername> <neues-passwort>"
  echo "Beispiel: $0 viewer 'MeinPasswort123!'"
  exit 1
fi

# Use the same backend code that the login endpoint uses, then verify the hash immediately.
docker compose -p bpstracker exec -T backend python - <<PY
from app.database import SessionLocal
from app.models import User, UserRole
from app.security import delete_recovery_codes, password_hash, verify_password

username = ${USERNAME@Q}.strip() or 'viewer'
password = ${PASSWORD@Q}.strip()

if len(password) < 8:
    raise SystemExit('FEHLER: Viewer-Passwort muss mindestens 8 Zeichen haben.')

with SessionLocal() as db:
    viewers = db.query(User).filter(User.role == UserRole.viewer).order_by(User.id).all()
    viewer = next((u for u in viewers if u.is_active), None) or (viewers[0] if viewers else None)

    # Rename inactive duplicate users with the desired username so they cannot confuse login/setup.
    for u in db.query(User).order_by(User.id).all():
        if u.id != (viewer.id if viewer else None) and (u.username or '').lower() == username.lower():
            u.is_active = False
            u.username = f'{u.username}_disabled_{u.id}'
            db.add(u)

    if viewer is None:
        viewer = User(username=username, password_hash=password_hash(password), role=UserRole.viewer, is_active=True, totp_enabled=False, totp_secret=None)
        db.add(viewer)
        db.flush()
    else:
        viewer.username = username
        viewer.password_hash = password_hash(password)
        viewer.is_active = True
        viewer.totp_enabled = False
        viewer.totp_secret = None
        delete_recovery_codes(db, viewer)
        db.add(viewer)

    for duplicate in viewers:
        if duplicate.id != viewer.id:
            duplicate.is_active = False
            duplicate.totp_enabled = False
            duplicate.totp_secret = None
            delete_recovery_codes(db, duplicate)
            db.add(duplicate)

    db.commit()
    db.refresh(viewer)
    ok = verify_password(password, viewer.password_hash)
    print(f'Viewer-Zugang gesetzt: username={viewer.username!r}, id={viewer.id}, verify={ok}')
    if not ok:
        raise SystemExit('FEHLER: Passwort-Hash konnte direkt nach dem Speichern nicht verifiziert werden.')

    print('\nAktive Benutzer:')
    for u in db.query(User).filter(User.is_active.is_(True)).order_by(User.role, User.id).all():
        role = getattr(u.role, 'value', u.role)
        print(f'- {role}: {u.username}')
PY
