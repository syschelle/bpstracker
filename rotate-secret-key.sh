#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${BPSTRACKER_APP_DIR:-$SCRIPT_DIR}"
BACKUP_ROOT="${BPSTRACKER_SECURITY_BACKUP_DIR:-$APP_DIR/security-backups}"
BACKEND_CONTAINER="${BPSTRACKER_BACKEND_CONTAINER:-bpstracker-backend}"
POSTGRES_CONTAINER="${BPSTRACKER_POSTGRES_CONTAINER:-bpstracker-postgres}"
MODE="apply"
COMPOSE_FILE=""

usage() {
  cat <<'USAGE'
Usage: sudo ./rotate-secret-key.sh [--backup-only] [--compose-file FILE]

Creates a complete local recovery backup and, unless --backup-only is used,
interactively rotates BPSTracker's SECRET_KEY.

The new SECRET_KEY is entered twice without terminal echo and must contain at
least 32 characters. The script never generates or prints a SECRET_KEY.

Options:
  --backup-only         Create and verify the recovery backup, then stop.
  --compose-file FILE   Override the Compose file used to recreate the backend.
  -h, --help            Show this help.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --backup-only)
      MODE="backup-only"
      shift
      ;;
    --compose-file)
      [ $# -ge 2 ] || { echo "ERROR: --compose-file requires a file." >&2; exit 1; }
      COMPOSE_FILE="$2"
      shift 2
      ;;
    --compose-file=*)
      COMPOSE_FILE="${1#--compose-file=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: Run this script as root, for example: sudo ./rotate-secret-key.sh" >&2
  exit 1
fi

cd "$APP_DIR"

for command in docker tar sha256sum; do
  command -v "$command" >/dev/null 2>&1 || { echo "ERROR: Required command not found: $command" >&2; exit 1; }
done

if [ ! -f .env ]; then
  echo "ERROR: $APP_DIR/.env is missing. Nothing will be changed." >&2
  exit 1
fi
chmod 600 .env
chown root:root .env 2>/dev/null || true

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    echo "ERROR: docker compose or docker-compose is required." >&2
    exit 1
  fi
}

select_compose_file() {
  if [ -n "$COMPOSE_FILE" ]; then
    return
  fi
  local profile=""
  profile="$(sed -n 's/^BPSTRACKER_INSTALL_PROFILE=//p' .env | tail -n1 || true)"
  if [ "$profile" = "zero2w" ] && [ -f docker-compose.zero2w.yml ]; then
    COMPOSE_FILE="docker-compose.zero2w.yml"
  elif [ -f docker-compose.images.yml ]; then
    COMPOSE_FILE="docker-compose.images.yml"
  elif [ -f docker-compose.yml ]; then
    COMPOSE_FILE="docker-compose.yml"
  else
    echo "ERROR: No BPSTracker Compose file found in $APP_DIR." >&2
    exit 1
  fi
}
select_compose_file
[ -f "$COMPOSE_FILE" ] || { echo "ERROR: Compose file not found: $COMPOSE_FILE" >&2; exit 1; }

if ! docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1; then
  echo "ERROR: Backend container not found: $BACKEND_CONTAINER" >&2
  exit 1
fi
if ! docker inspect "$POSTGRES_CONTAINER" >/dev/null 2>&1; then
  echo "ERROR: PostgreSQL container not found: $POSTGRES_CONTAINER" >&2
  exit 1
fi

OLD_SECRET_KEY="$(docker inspect "$BACKEND_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^SECRET_KEY=//p' | head -n1)"
if [ -z "$OLD_SECRET_KEY" ]; then
  echo "ERROR: The running backend container does not expose SECRET_KEY." >&2
  exit 1
fi

ENV_SECRET_KEY="$(sed -n 's/^SECRET_KEY=//p' .env | tail -n1 || true)"
if [ "$ENV_SECRET_KEY" != "$OLD_SECRET_KEY" ]; then
  echo "ERROR: .env SECRET_KEY does not match the running backend container." >&2
  echo "       Reconcile the installation before rotating the key." >&2
  exit 1
fi

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"
mkdir -p "$BACKUP_DIR/config" "$BACKUP_DIR/docker"
chmod 700 "$BACKUP_ROOT" "$BACKUP_DIR" "$BACKUP_DIR/config" "$BACKUP_DIR/docker"

cleanup_on_error() {
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    echo >&2
    echo "ERROR: Secret-key maintenance failed (exit $rc)." >&2
    echo "Recovery backup: $BACKUP_DIR" >&2
  fi
  unset NEW_SECRET_KEY NEW_SECRET_KEY_CONFIRM OLD_SECRET_KEY ENV_SECRET_KEY
  exit "$rc"
}
trap cleanup_on_error EXIT

create_backup() {
  echo "Creating recovery backup in: $BACKUP_DIR"

  cp -a .env "$BACKUP_DIR/config/.env"
  chmod 600 "$BACKUP_DIR/config/.env"

  local file
  for file in docker-compose.yml docker-compose.images.yml docker-compose.zero2w.yml update.sh rotate-secret-key.sh .env.example; do
    if [ -f "$file" ]; then
      cp -a "$file" "$BACKUP_DIR/config/$file"
      chmod 600 "$BACKUP_DIR/config/$file"
    fi
  done

  docker inspect "$BACKEND_CONTAINER" > "$BACKUP_DIR/docker/${BACKEND_CONTAINER}.inspect.json"
  docker inspect "$POSTGRES_CONTAINER" > "$BACKUP_DIR/docker/${POSTGRES_CONTAINER}.inspect.json"
  if docker inspect bpstracker-frontend >/dev/null 2>&1; then
    docker inspect bpstracker-frontend > "$BACKUP_DIR/docker/bpstracker-frontend.inspect.json"
  fi
  chmod 600 "$BACKUP_DIR"/docker/*

  echo "Exporting PostgreSQL database..."
  docker exec "$BACKEND_CONTAINER" sh -lc \
    'db_url="$(printf %s "$DATABASE_URL" | sed "s#^postgresql+psycopg://#postgresql://#")"; pg_dump --no-owner --no-privileges --format=custom "$db_url"' \
    > "$BACKUP_DIR/database.dump"
  chmod 600 "$BACKUP_DIR/database.dump"

  echo "Exporting PostgreSQL globals..."
  local pg_user
  pg_user="$(docker inspect "$POSTGRES_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^POSTGRES_USER=//p' | head -n1)"
  pg_user="${pg_user:-bpstracker}"
  docker exec "$POSTGRES_CONTAINER" pg_dumpall --globals-only -U "$pg_user" > "$BACKUP_DIR/postgres-globals.sql"
  chmod 600 "$BACKUP_DIR/postgres-globals.sql"

  echo "Archiving backend application data..."
  if [ -d "$APP_DIR/data/backend" ]; then
    tar -C "$APP_DIR/data" -czf "$BACKUP_DIR/backend-data.tar.gz" backend
  else
    tar -czf "$BACKUP_DIR/backend-data.tar.gz" --files-from /dev/null
  fi
  chmod 600 "$BACKUP_DIR/backend-data.tar.gz"

  cat > "$BACKUP_DIR/MANIFEST.txt" <<MANIFEST
BPSTracker SECRET_KEY rotation recovery backup
Created: $(date --iso-8601=seconds)
Application directory: $APP_DIR
Compose file: $COMPOSE_FILE
Backend container: $BACKEND_CONTAINER
PostgreSQL container: $POSTGRES_CONTAINER

Contents:
- database.dump: PostgreSQL custom-format logical database backup
- postgres-globals.sql: PostgreSQL roles/globals
- backend-data.tar.gz: /opt/bpstracker/data/backend (or configured application data path)
- config/.env: original environment including the pre-rotation SECRET_KEY
- config/: deployment/configuration files present at backup time
- docker/: docker inspect snapshots
- SHA256SUMS: integrity hashes for all backup files
MANIFEST
  chmod 600 "$BACKUP_DIR/MANIFEST.txt"

  echo "Verifying database dump..."
  docker exec -i "$BACKEND_CONTAINER" pg_restore --list < "$BACKUP_DIR/database.dump" >/dev/null
  [ -s "$BACKUP_DIR/postgres-globals.sql" ] || { echo "ERROR: PostgreSQL globals backup is empty." >&2; return 1; }
  tar -tzf "$BACKUP_DIR/backend-data.tar.gz" >/dev/null
  [ -s "$BACKUP_DIR/config/.env" ] || { echo "ERROR: .env backup is empty." >&2; return 1; }

  (
    cd "$BACKUP_DIR"
    find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
  )
  chmod 600 "$BACKUP_DIR/SHA256SUMS"
  (
    cd "$BACKUP_DIR"
    sha256sum -c SHA256SUMS >/dev/null
  )

  echo "Recovery backup verified successfully."
}

validate_existing_ciphertexts() {
  echo "Validating all currently encrypted BPSTracker secrets..."
  docker exec -i "$BACKEND_CONTAINER" python -c '
import base64, hashlib
from cryptography.fernet import Fernet, InvalidToken
import pyotp
from app.config import get_settings
from app.database import SessionLocal
from app.models import AppSetting, Device, User

key = get_settings().secret_key
digest = hashlib.sha256(key.encode("utf-8")).digest()
fernet = Fernet(base64.urlsafe_b64encode(digest))

def decrypt_required(value, label, allow_totp_plaintext=False):
    if not value:
        return
    try:
        fernet.decrypt(value.encode("utf-8"))
        return
    except InvalidToken:
        if allow_totp_plaintext:
            candidate = value.strip()
            try:
                pyotp.TOTP(candidate).now()
                return
            except Exception:
                pass
        raise RuntimeError(f"Cannot decrypt existing secret: {label}")

def walk(value, label):
    if isinstance(value, dict):
        for key, child in value.items():
            child_label = f"{label}.{key}"
            if key.endswith("_ciphertext") and child:
                decrypt_required(str(child), child_label)
            else:
                walk(child, child_label)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            walk(child, f"{label}[{idx}]")

with SessionLocal() as db:
    for user in db.query(User).all():
        decrypt_required(user.totp_secret, f"users[{user.id}].totp_secret", allow_totp_plaintext=True)
    for device in db.query(Device).all():
        decrypt_required(device.password_ciphertext, f"devices[{device.id}].password_ciphertext")
    for row in db.query(AppSetting).all():
        walk(row.value, f"app_settings[{row.key}]")
print("Encrypted-secret validation passed.")
'
}

prompt_new_secret_key() {
  local min_length=32
  echo
  echo "Enter the new SECRET_KEY. Input is hidden."
  echo "Minimum length: $min_length characters."
  while true; do
    IFS= read -r -s -p "New SECRET_KEY: " NEW_SECRET_KEY </dev/tty
    echo >/dev/tty
    IFS= read -r -s -p "Repeat SECRET_KEY: " NEW_SECRET_KEY_CONFIRM </dev/tty
    echo >/dev/tty

    if [ "${#NEW_SECRET_KEY}" -lt "$min_length" ]; then
      echo "ERROR: SECRET_KEY must contain at least $min_length characters." >&2
      continue
    fi
    if [ "$NEW_SECRET_KEY" != "$NEW_SECRET_KEY_CONFIRM" ]; then
      echo "ERROR: The two SECRET_KEY entries do not match." >&2
      continue
    fi
    if [ "$NEW_SECRET_KEY" = "$OLD_SECRET_KEY" ]; then
      echo "ERROR: The new SECRET_KEY must differ from the current key." >&2
      continue
    fi
    if [[ "$NEW_SECRET_KEY" =~ [[:space:]] ]] || [[ "$NEW_SECRET_KEY" == *"#"* ]] || \
       [[ "$NEW_SECRET_KEY" == *"\""* ]] || [[ "$NEW_SECRET_KEY" == *"'"* ]] || \
       [[ "$NEW_SECRET_KEY" == *\\* ]] || [[ "$NEW_SECRET_KEY" == *'$'* ]]; then
      echo "ERROR: For safe .env handling, SECRET_KEY must not contain whitespace, #, quotes, backslash, or $." >&2
      echo "       Use at least 32 characters made from letters, digits and other safe punctuation." >&2
      continue
    fi
    break
  done
  unset NEW_SECRET_KEY_CONFIRM
}

write_new_env_key() {
  local tmp
  tmp="$(mktemp "$APP_DIR/.env.rotate.XXXXXX")"
  chmod 600 "$tmp"
  local found=0 line
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ "$line" == SECRET_KEY=* ]]; then
      printf 'SECRET_KEY=%s\n' "$NEW_SECRET_KEY" >> "$tmp"
      found=1
    else
      printf '%s\n' "$line" >> "$tmp"
    fi
  done < .env
  if [ "$found" -eq 0 ]; then
    printf '\nSECRET_KEY=%s\n' "$NEW_SECRET_KEY" >> "$tmp"
  fi
  chown root:root "$tmp" 2>/dev/null || true
  mv "$tmp" .env
  chmod 600 .env
}

restore_old_env() {
  echo "Restoring original .env from recovery backup..." >&2
  cp -a "$BACKUP_DIR/config/.env" .env
  chmod 600 .env
  chown root:root .env 2>/dev/null || true
}

wait_backend_health() {
  local attempts=30
  local status=""
  while [ "$attempts" -gt 0 ]; do
    status="$(docker inspect "$BACKEND_CONTAINER" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
    if [ "$status" = "healthy" ] || [ "$status" = "running" ]; then
      return 0
    fi
    sleep 2
    attempts=$((attempts - 1))
  done
  echo "ERROR: Backend did not become healthy after SECRET_KEY change (last status: ${status:-unknown})." >&2
  return 1
}

reencrypt_secrets() {
  echo "Re-encrypting stored BPSTracker secrets with the new SECRET_KEY..."
  printf '%s\n' "$OLD_SECRET_KEY" | docker exec -i "$BACKEND_CONTAINER" python -c '
import base64, hashlib, sys
from cryptography.fernet import Fernet, InvalidToken
import pyotp
from sqlalchemy.orm.attributes import flag_modified
from app.config import get_settings
from app.database import SessionLocal
from app.models import AppSetting, Device, User

old_key = sys.stdin.readline().rstrip("\n")
new_key = get_settings().secret_key
if len(new_key) < 32:
    raise RuntimeError("New SECRET_KEY is shorter than 32 characters")
if old_key == new_key:
    raise RuntimeError("Old and new SECRET_KEY are identical")

def make_fernet(key):
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

old_f = make_fernet(old_key)
new_f = make_fernet(new_key)
counts = {"totp": 0, "device": 0, "setting": 0, "already_new": 0}

def rotate_value(value, label, allow_totp_plaintext=False):
    if not value:
        return value, False
    encoded = value.encode("utf-8")
    try:
        new_f.decrypt(encoded)
        counts["already_new"] += 1
        return value, False
    except InvalidToken:
        pass
    try:
        plain = old_f.decrypt(encoded)
    except InvalidToken:
        if allow_totp_plaintext:
            candidate = value.strip()
            try:
                pyotp.TOTP(candidate).now()
                plain = candidate.encode("utf-8")
            except Exception as exc:
                raise RuntimeError(f"Cannot decrypt existing secret: {label}") from exc
        else:
            raise RuntimeError(f"Cannot decrypt existing secret: {label}")
    return new_f.encrypt(plain).decode("utf-8"), True

def walk(value, label):
    changed = False
    if isinstance(value, dict):
        result = dict(value)
        for key, child in value.items():
            child_label = f"{label}.{key}"
            if key.endswith("_ciphertext") and child:
                rotated, item_changed = rotate_value(str(child), child_label)
                result[key] = rotated
                if item_changed:
                    counts["setting"] += 1
                    changed = True
            else:
                rotated_child, child_changed = walk(child, child_label)
                result[key] = rotated_child
                changed = changed or child_changed
        return result, changed
    if isinstance(value, list):
        result = []
        for idx, child in enumerate(value):
            rotated_child, child_changed = walk(child, f"{label}[{idx}]")
            result.append(rotated_child)
            changed = changed or child_changed
        return result, changed
    return value, False

with SessionLocal() as db:
    try:
        for user in db.query(User).with_for_update().all():
            rotated, changed = rotate_value(user.totp_secret, f"users[{user.id}].totp_secret", allow_totp_plaintext=True)
            if changed:
                user.totp_secret = rotated
                counts["totp"] += 1
        for device in db.query(Device).with_for_update().all():
            rotated, changed = rotate_value(device.password_ciphertext, f"devices[{device.id}].password_ciphertext")
            if changed:
                device.password_ciphertext = rotated
                counts["device"] += 1
        for row in db.query(AppSetting).with_for_update().all():
            rotated_value, changed = walk(row.value, f"app_settings[{row.key}]")
            if changed:
                row.value = rotated_value
                flag_modified(row, "value")
        db.commit()
    except Exception:
        db.rollback()
        raise
print("Secret re-encryption committed successfully: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
'
}


reencrypt_current_key_back_to_old() {
  echo "Rolling encrypted database values back to the previous SECRET_KEY..." >&2
  printf '%s\n' "$OLD_SECRET_KEY" | docker exec -i "$BACKEND_CONTAINER" python -c '
import base64, hashlib, sys
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm.attributes import flag_modified
from app.config import get_settings
from app.database import SessionLocal
from app.models import AppSetting, Device, User

source_key = get_settings().secret_key
target_key = sys.stdin.readline().rstrip("\\n")

def make_fernet(key):
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

source_f = make_fernet(source_key)
target_f = make_fernet(target_key)

def rotate_value(value, label):
    if not value:
        return value, False
    encoded = value.encode("utf-8")
    try:
        target_f.decrypt(encoded)
        return value, False
    except InvalidToken:
        pass
    try:
        plain = source_f.decrypt(encoded)
    except InvalidToken as exc:
        raise RuntimeError(f"Cannot roll back encrypted secret: {label}") from exc
    return target_f.encrypt(plain).decode("utf-8"), True

def walk(value, label):
    changed = False
    if isinstance(value, dict):
        result = dict(value)
        for key, child in value.items():
            child_label = f"{label}.{key}"
            if key.endswith("_ciphertext") and child:
                result[key], item_changed = rotate_value(str(child), child_label)
                changed = changed or item_changed
            else:
                result[key], child_changed = walk(child, child_label)
                changed = changed or child_changed
        return result, changed
    if isinstance(value, list):
        result = []
        for idx, child in enumerate(value):
            rotated_child, child_changed = walk(child, f"{label}[{idx}]")
            result.append(rotated_child)
            changed = changed or child_changed
        return result, changed
    return value, False

with SessionLocal() as db:
    try:
        for user in db.query(User).with_for_update().all():
            if user.totp_secret:
                user.totp_secret, _ = rotate_value(user.totp_secret, f"users[{user.id}].totp_secret")
        for device in db.query(Device).with_for_update().all():
            if device.password_ciphertext:
                device.password_ciphertext, _ = rotate_value(device.password_ciphertext, f"devices[{device.id}].password_ciphertext")
        for row in db.query(AppSetting).with_for_update().all():
            rotated_value, changed = walk(row.value, f"app_settings[{row.key}]")
            if changed:
                row.value = rotated_value
                flag_modified(row, "value")
        db.commit()
    except Exception:
        db.rollback()
        raise
print("Encrypted database values were rolled back to the previous key.")
'
}

verify_new_key() {
  echo "Verifying the new key and all encrypted data..."
  docker exec "$BACKEND_CONTAINER" python -c '
from app.database import SessionLocal
from app.models import AppSetting, Device, User
from app.security import decrypt_secret, get_user_totp_secret

errors = []
def walk(value, label):
    if isinstance(value, dict):
        for key, child in value.items():
            child_label = f"{label}.{key}"
            if key.endswith("_ciphertext") and child and decrypt_secret(str(child)) is None:
                errors.append(child_label)
            else:
                walk(child, child_label)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            walk(child, f"{label}[{idx}]")

with SessionLocal() as db:
    for user in db.query(User).all():
        if user.totp_secret and get_user_totp_secret(user) is None:
            errors.append(f"users[{user.id}].totp_secret")
    for device in db.query(Device).all():
        if device.password_ciphertext and decrypt_secret(device.password_ciphertext) is None:
            errors.append(f"devices[{device.id}].password_ciphertext")
    for row in db.query(AppSetting).all():
        walk(row.value, f"app_settings[{row.key}]")
if errors:
    raise RuntimeError("Secrets that cannot be decrypted with the new key: " + ", ".join(errors))
print("New SECRET_KEY verification passed.")
'
}

create_backup

if [ "$MODE" = "backup-only" ]; then
  echo
  echo "Backup-only mode complete. No configuration or database values were changed."
  trap - EXIT
  unset OLD_SECRET_KEY ENV_SECRET_KEY
  exit 0
fi

validate_existing_ciphertexts
prompt_new_secret_key

echo
read -r -p "A verified backup exists. Rotate SECRET_KEY now? Type YES to continue: " CONFIRM </dev/tty
if [ "$CONFIRM" != "YES" ]; then
  echo "Cancelled. No configuration or database values were changed."
  trap - EXIT
  unset NEW_SECRET_KEY OLD_SECRET_KEY ENV_SECRET_KEY CONFIRM
  exit 0
fi
unset CONFIRM

write_new_env_key

rotation_failed=0
database_rotated=0
if ! compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate backend; then
  rotation_failed=1
elif ! wait_backend_health; then
  rotation_failed=1
elif ! reencrypt_secrets; then
  rotation_failed=1
else
  database_rotated=1
  if ! verify_new_key; then
    rotation_failed=1
  fi
fi

if [ "$rotation_failed" -ne 0 ]; then
  echo "Rotation failed before completion." >&2
  if [ "$database_rotated" -eq 1 ]; then
    if reencrypt_current_key_back_to_old; then
      restore_old_env
      compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate backend || true
      wait_backend_health || true
      echo "Database secrets and .env were rolled back to the previous SECRET_KEY." >&2
    else
      echo "ERROR: Automatic database rollback also failed." >&2
      echo "       The new .env is intentionally being kept to avoid creating a known key/data mismatch." >&2
      echo "       Use the verified recovery backup for manual recovery: $BACKUP_DIR" >&2
    fi
  else
    restore_old_env
    compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate backend || true
    wait_backend_health || true
    echo "The database re-encryption is transactional; no encrypted database values were committed." >&2
  fi
  echo "Recovery backup remains at: $BACKUP_DIR" >&2
  exit 1
fi

chmod 600 .env
chown root:root .env 2>/dev/null || true

# Refresh frontend too so any authentication/session state is cleanly re-established.
compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate frontend >/dev/null 2>&1 || true

NEW_HASH="$(printf '%s' "$NEW_SECRET_KEY" | sha256sum | awk '{print $1}')"
cat > "$BACKUP_DIR/ROTATION_RESULT.txt" <<RESULT
SECRET_KEY rotation completed successfully at $(date --iso-8601=seconds).
New key SHA-256: $NEW_HASH
The new SECRET_KEY itself is intentionally not written here.
The original .env containing the previous key remains in config/.env for recovery.
RESULT
chmod 600 "$BACKUP_DIR/ROTATION_RESULT.txt"
(
  cd "$BACKUP_DIR"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
  sha256sum -c SHA256SUMS >/dev/null
)
chmod 600 "$BACKUP_DIR/SHA256SUMS"

trap - EXIT
unset NEW_SECRET_KEY OLD_SECRET_KEY ENV_SECRET_KEY

echo
echo "SECRET_KEY rotation completed successfully."
echo "Recovery backup: $BACKUP_DIR"
echo "The .env file remains protected with mode 0600."
echo "Existing login sessions are invalid after a SECRET_KEY rotation; sign in again."
