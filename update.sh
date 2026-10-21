#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DEFAULT_IMAGE_TAG="v0.9.64"
IMAGE_TAG="${BPSTRACKER_IMAGE_TAG:-$DEFAULT_IMAGE_TAG}"
COMPOSE_FILE="docker-compose.images.yml"

usage() {
  cat <<'EOF'
Usage: bash ./update.sh [--latest|--tag TAG]

Updates an image-based BPSTracker installation in /opt/bpstracker.

Options:
  --latest       Use the latest GHCR image tag.
  --tag TAG      Use a specific GHCR image tag, for example v0.9.64.
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
        echo "ERROR: --tag requires a value, for example --tag v0.9.64 or --tag latest." >&2
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

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "ERROR: $COMPOSE_FILE not found. Run this script in the BPSTracker install directory." >&2
  exit 1
fi

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

touch .env
if grep -q '^BPSTRACKER_IMAGE_TAG=' .env; then
  sed -i "s/^BPSTRACKER_IMAGE_TAG=.*/BPSTRACKER_IMAGE_TAG=$IMAGE_TAG/" .env
else
  printf '\nBPSTRACKER_IMAGE_TAG=%s\n' "$IMAGE_TAG" >> .env
fi
export BPSTRACKER_IMAGE_TAG="$IMAGE_TAG"

if grep -Eq 'ghcr\.io/syschelle/bpstracker-(backend|frontend):' "$COMPOSE_FILE"; then
  sed -i -E "s#ghcr\\.io/syschelle/bpstracker-backend:[^[:space:]]+#ghcr.io/syschelle/bpstracker-backend:$IMAGE_TAG#" "$COMPOSE_FILE"
  sed -i -E "s#ghcr\\.io/syschelle/bpstracker-frontend:[^[:space:]]+#ghcr.io/syschelle/bpstracker-frontend:$IMAGE_TAG#" "$COMPOSE_FILE"
fi

echo "Using BPSTracker image tag: $IMAGE_TAG"
echo "Pulling images..."
compose -f "$COMPOSE_FILE" pull

echo "Recreating containers..."
compose -f "$COMPOSE_FILE" up -d --remove-orphans --force-recreate

echo
echo "Container status:"
compose -f "$COMPOSE_FILE" ps
