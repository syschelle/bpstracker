#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DEFAULT_IMAGE_TAG="v0.9.71"
IMAGE_TAG="${BPSTRACKER_IMAGE_TAG:-$DEFAULT_IMAGE_TAG}"
COMPOSE_FILE="docker-compose.images.yml"
REPO_RAW_BASE="https://raw.githubusercontent.com/syschelle/bpstracker"

usage() {
  cat <<'EOF'
Usage: bash ./update.sh [--latest|--tag TAG]

Updates an image-based BPSTracker installation in /opt/bpstracker.
The matching docker-compose.images.yml is downloaded and validated before images are updated.

Options:
  --latest       Use the latest GHCR image and the compose file from branch main.
  --tag TAG      Use a specific release tag, for example v0.9.71.
  -h, --help     Show this help.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --latest|latest)
      IMAGE_TAG="latest"
      shift
      ;;
    --tag)
      if [ $# -lt 2 ]; then
        echo "ERROR: --tag requires a value, for example --tag v0.9.71 or --tag latest." >&2
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
    echo "ERROR: curl or wget is required to refresh $COMPOSE_FILE." >&2
    exit 1
  fi
}

touch .env
if grep -q '^BPSTRACKER_IMAGE_TAG=' .env; then
  sed -i "s/^BPSTRACKER_IMAGE_TAG=.*/BPSTRACKER_IMAGE_TAG=$IMAGE_TAG/" .env
else
  printf '\nBPSTRACKER_IMAGE_TAG=%s\n' "$IMAGE_TAG" >> .env
fi
export BPSTRACKER_IMAGE_TAG="$IMAGE_TAG"

if [ "$IMAGE_TAG" = "latest" ]; then
  COMPOSE_REF="main"
else
  COMPOSE_REF="$IMAGE_TAG"
fi
COMPOSE_URL="$REPO_RAW_BASE/$COMPOSE_REF/docker-compose.images.yml"
COMPOSE_TMP=".${COMPOSE_FILE}.tmp"
COMPOSE_BACKUP="${COMPOSE_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
trap 'rm -f "$COMPOSE_TMP"' EXIT

echo "Using BPSTracker image tag: $IMAGE_TAG"
echo "Refreshing $COMPOSE_FILE from $COMPOSE_REF..."
download_file "$COMPOSE_URL" "$COMPOSE_TMP"

if [ ! -s "$COMPOSE_TMP" ]; then
  echo "ERROR: Downloaded compose file is empty." >&2
  exit 1
fi
if ! grep -q '^  backend:' "$COMPOSE_TMP" || ! grep -q '^  frontend:' "$COMPOSE_TMP"; then
  echo "ERROR: Downloaded compose file does not look like a BPSTracker image compose file." >&2
  exit 1
fi

# Validate the new file before replacing the working copy. The current .env and
# exported image tag are intentionally used for interpolation during validation.
compose -f "$COMPOSE_TMP" config >/dev/null

if [ -f "$COMPOSE_FILE" ]; then
  cp -a "$COMPOSE_FILE" "$COMPOSE_BACKUP"
  echo "Saved previous compose file as $COMPOSE_BACKUP"
fi
mv "$COMPOSE_TMP" "$COMPOSE_FILE"
trap - EXIT

# Keep compatibility with older fixed-tag compose files while new releases use
# BPSTRACKER_IMAGE_TAG interpolation.
if grep -Eq 'ghcr\.io/syschelle/bpstracker-(backend|frontend):' "$COMPOSE_FILE"; then
  sed -i -E "s#ghcr\\.io/syschelle/bpstracker-backend:[^[:space:]]+#ghcr.io/syschelle/bpstracker-backend:$IMAGE_TAG#" "$COMPOSE_FILE"
  sed -i -E "s#ghcr\\.io/syschelle/bpstracker-frontend:[^[:space:]]+#ghcr.io/syschelle/bpstracker-frontend:$IMAGE_TAG#" "$COMPOSE_FILE"
fi

echo "Pulling images..."
compose -f "$COMPOSE_FILE" pull

echo "Recreating containers..."
compose -f "$COMPOSE_FILE" up -d --remove-orphans --force-recreate

echo
echo "Container status:"
compose -f "$COMPOSE_FILE" ps
