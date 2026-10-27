#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DEFAULT_IMAGE_TAG="v0.9.77"
IMAGE_TAG="${BPSTRACKER_IMAGE_TAG:-$DEFAULT_IMAGE_TAG}"
COMPOSE_FILE="docker-compose.images.yml"
MAINTENANCE_FILE="rotate-secret-key.sh"
REPO_RAW_BASE="https://raw.githubusercontent.com/syschelle/bpstracker"

usage() {
  cat <<'USAGE'
Usage: bash ./update.sh [--latest|--tag TAG]

Updates an image-based BPSTracker installation in /opt/bpstracker.
The matching Compose file and maintenance scripts are downloaded and validated
before containers are updated. An existing .env is required and is backed up;
this updater never creates a replacement .env from defaults.

Options:
  --latest       Use the latest GHCR image and files from branch main.
  --tag TAG      Use a specific release tag, for example v0.9.77.
  -h, --help     Show this help.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --latest|latest)
      IMAGE_TAG="latest"
      shift
      ;;
    --tag)
      if [ $# -lt 2 ]; then
        echo "ERROR: --tag requires a value, for example --tag v0.9.77 or --tag latest." >&2
        exit 1
      fi
      IMAGE_TAG="$2"
      shift 2
      ;;
    --tag=*)
      IMAGE_TAG="${1#--tag=}"
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

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed or not in PATH." >&2
  exit 1
fi

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

download_file() {
  local url="$1"
  local target="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --connect-timeout 15 --retry 2 "$url" -o "$target"
  elif command -v wget >/dev/null 2>&1; then
    wget -q --timeout=15 -O "$target" "$url"
  else
    echo "ERROR: curl or wget is required to refresh deployment files." >&2
    exit 1
  fi
}

if [ ! -f .env ]; then
  echo "ERROR: $SCRIPT_DIR/.env is missing." >&2
  echo "       The updater will not create or replace a production .env from defaults." >&2
  exit 1
fi
chmod 600 .env
chown root:root .env 2>/dev/null || true

if [ "$IMAGE_TAG" = "latest" ]; then
  COMPOSE_REF="main"
else
  COMPOSE_REF="$IMAGE_TAG"
fi

COMPOSE_TMP=".${COMPOSE_FILE}.tmp"
MAINTENANCE_TMP=".${MAINTENANCE_FILE}.tmp"
SELF_TMP=".update.sh.tmp"
COMPOSE_BACKUP="${COMPOSE_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
ENV_BACKUP_DIR="security-backups/update-env-$(date +%Y%m%d-%H%M%S)"

cleanup() {
  rm -f "$COMPOSE_TMP" "$MAINTENANCE_TMP" "$SELF_TMP"
}
trap cleanup EXIT

echo "Using BPSTracker image tag: $IMAGE_TAG"
echo "Downloading deployment files from $COMPOSE_REF..."
download_file "$REPO_RAW_BASE/$COMPOSE_REF/$COMPOSE_FILE" "$COMPOSE_TMP"
download_file "$REPO_RAW_BASE/$COMPOSE_REF/$MAINTENANCE_FILE" "$MAINTENANCE_TMP"
download_file "$REPO_RAW_BASE/$COMPOSE_REF/update.sh" "$SELF_TMP"

if [ ! -s "$COMPOSE_TMP" ]; then
  echo "ERROR: Downloaded Compose file is empty." >&2
  exit 1
fi
if ! grep -q '^  backend:' "$COMPOSE_TMP" || ! grep -q '^  frontend:' "$COMPOSE_TMP"; then
  echo "ERROR: Downloaded Compose file does not look like a BPSTracker image Compose file." >&2
  exit 1
fi
if [ ! -s "$MAINTENANCE_TMP" ] || ! grep -q 'SECRET_KEY' "$MAINTENANCE_TMP"; then
  echo "ERROR: Downloaded maintenance script is invalid." >&2
  exit 1
fi

bash -n "$MAINTENANCE_TMP"
bash -n "$SELF_TMP"
export BPSTRACKER_IMAGE_TAG="$IMAGE_TAG"
compose -f "$COMPOSE_TMP" config >/dev/null

mkdir -p "$ENV_BACKUP_DIR"
chmod 700 security-backups "$ENV_BACKUP_DIR"
cp -a .env "$ENV_BACKUP_DIR/.env"
chmod 600 "$ENV_BACKUP_DIR/.env"
chown root:root "$ENV_BACKUP_DIR/.env" 2>/dev/null || true
printf 'Original .env saved automatically before BPSTracker update to %s at %s\n' \
  "$IMAGE_TAG" "$(date --iso-8601=seconds)" > "$ENV_BACKUP_DIR/README.txt"
chmod 600 "$ENV_BACKUP_DIR/README.txt"
echo "Saved protected .env backup in $ENV_BACKUP_DIR"

if [ -f "$COMPOSE_FILE" ]; then
  cp -a "$COMPOSE_FILE" "$COMPOSE_BACKUP"
  echo "Saved previous Compose file as $COMPOSE_BACKUP"
fi
mv "$COMPOSE_TMP" "$COMPOSE_FILE"

# Keep compatibility with older fixed-tag Compose files while new releases use
# BPSTRACKER_IMAGE_TAG interpolation.
if grep -Eq 'ghcr\.io/syschelle/bpstracker-(backend|frontend):' "$COMPOSE_FILE"; then
  sed -i -E "s#ghcr\\.io/syschelle/bpstracker-backend:[^[:space:]]+#ghcr.io/syschelle/bpstracker-backend:$IMAGE_TAG#" "$COMPOSE_FILE"
  sed -i -E "s#ghcr\\.io/syschelle/bpstracker-frontend:[^[:space:]]+#ghcr.io/syschelle/bpstracker-frontend:$IMAGE_TAG#" "$COMPOSE_FILE"
fi

echo "Pulling images..."
compose -f "$COMPOSE_FILE" pull

echo "Recreating containers..."
compose -f "$COMPOSE_FILE" up -d --remove-orphans --force-recreate

# Only persist the new image tag after the container update completed.
ENV_TMP="$(mktemp "$SCRIPT_DIR/.env.update.XXXXXX")"
chmod 600 "$ENV_TMP"
found=0
while IFS= read -r line || [ -n "$line" ]; do
  if [[ "$line" == BPSTRACKER_IMAGE_TAG=* ]]; then
    printf 'BPSTRACKER_IMAGE_TAG=%s\n' "$IMAGE_TAG" >> "$ENV_TMP"
    found=1
  else
    printf '%s\n' "$line" >> "$ENV_TMP"
  fi
done < .env
if [ "$found" -eq 0 ]; then
  printf '\nBPSTRACKER_IMAGE_TAG=%s\n' "$IMAGE_TAG" >> "$ENV_TMP"
fi
chown root:root "$ENV_TMP" 2>/dev/null || true
mv "$ENV_TMP" .env
chmod 600 .env

mv "$MAINTENANCE_TMP" "$MAINTENANCE_FILE"
chmod 750 "$MAINTENANCE_FILE"
chown root:root "$MAINTENANCE_FILE" 2>/dev/null || true

# Install the just-downloaded updater last. Replacing the running script is safe;
# the current process has already parsed/executed the earlier content.
mv "$SELF_TMP" update.sh
chmod 750 update.sh
chown root:root update.sh 2>/dev/null || true

trap - EXIT
cleanup

echo
echo "Container status:"
compose -f "$COMPOSE_FILE" ps

echo
echo "Update complete."
echo "Protected .env backup: $ENV_BACKUP_DIR/.env"
echo "SECRET_KEY maintenance script: $SCRIPT_DIR/$MAINTENANCE_FILE"
