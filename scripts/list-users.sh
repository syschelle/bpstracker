#!/usr/bin/env bash
set -euo pipefail
cd /opt/bpstracker

docker compose -p bpstracker exec -T backend python - <<'PY'
from app.database import SessionLocal
from app.models import User

with SessionLocal() as db:
    users = db.query(User).order_by(User.role, User.id).all()
    print('ID | Rolle  | Aktiv | 2FA | Benutzername | Hash')
    print('---|--------|-------|-----|--------------|----------------')
    for u in users:
        h = u.password_hash or ''
        if h.startswith('$argon2id$'):
            hp = 'argon2id'
        elif h.startswith('$2'):
            hp = 'bcrypt'
        elif len(h) == 64 and all(c in '0123456789abcdefABCDEF' for c in h):
            hp = 'sha256-legacy'
        else:
            hp = (h[:18] + '...') if h else '<leer>'
        role = getattr(u.role, 'value', u.role)
        print(f'{u.id} | {role:<6} | {str(u.is_active):<5} | {str(u.totp_enabled):<3} | {u.username} | {hp}')
PY
