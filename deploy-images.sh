#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/env-setup.sh
source "$SCRIPT_DIR/scripts/env-setup.sh"

PROFILE="${BPSTRACKER_INSTALL_PROFILE:-}"
IMAGE_TAG=""
DEFAULT_IMAGE_TAG="v0.9.11"

while [ $# -gt 0 ]; do
  case "$1" in
    --zero2w|--zero|zero2w)
      PROFILE="zero2w"
      shift
      ;;
    --regular|regular)
      PROFILE="regular"
      shift
      ;;
    --latest|latest)
      IMAGE_TAG="latest"
      shift
      ;;
    --tag)
      if [ $# -lt 2 ]; then
        echo "ERROR: --tag requires a value, for example --tag v0.9.11 or --tag latest." >&2
        exit 1
      fi
      IMAGE_TAG="$2"
      shift 2
      ;;
    --tag=*)
      IMAGE_TAG="${1#--tag=}"
      shift
      ;;
    *)
      echo "ERROR: Unknown option: $1" >&2
      echo "Usage: bash ./deploy-images.sh [--regular|--zero2w] [--latest|--tag TAG]" >&2
      exit 1
      ;;
  esac
done

if [ -z "$PROFILE" ]; then
  PROFILE="$(bpstracker_select_profile)"
fi

if [ -z "$IMAGE_TAG" ]; then
  if [ -t 0 ]; then
    echo ""
    echo "Welchen Docker-Image-Tag möchtest du verwenden?"
    echo "  1) $DEFAULT_IMAGE_TAG (empfohlen für reproduzierbare Releases)"
    echo "  2) latest (immer das aktuellste veröffentlichte Image)"
    printf 'Auswahl [1/2, Standard: 1]: '
    read -r tag_choice || tag_choice=""
    case "$tag_choice" in
      2|l|L|latest|Latest) IMAGE_TAG="latest" ;;
      *) IMAGE_TAG="$DEFAULT_IMAGE_TAG" ;;
    esac
  else
    IMAGE_TAG="${BPSTRACKER_IMAGE_TAG:-$DEFAULT_IMAGE_TAG}"
  fi
fi

bpstracker_prepare_env "$SCRIPT_DIR/.env" "$PROFILE" "$IMAGE_TAG"
bpstracker_env_set "$SCRIPT_DIR/.env" BPSTRACKER_IMAGE_TAG "$IMAGE_TAG"
COMPOSE_FILE="$(bpstracker_compose_file_for_profile "$PROFILE" images)"

mkdir -p /opt/bpstracker/data/postgres /opt/bpstracker/data/backend
BACKEND_UID=10001
BACKEND_GID=10001
if command -v sudo >/dev/null 2>&1; then
  sudo chown -R "${BACKEND_UID}:${BACKEND_GID}" /opt/bpstracker/data/backend
else
  chown -R "${BACKEND_UID}:${BACKEND_GID}" /opt/bpstracker/data/backend 2>/dev/null || true
fi

echo "Using installation profile: $PROFILE"
echo "Using Docker image tag: $IMAGE_TAG"
echo "Using Compose file: $COMPOSE_FILE"
echo "Pulling BPSTracker images from GHCR..."
docker compose -f "$COMPOSE_FILE" pull

echo "Starting BPSTracker..."
echo "Recreating containers so old frontend port mappings are removed..."
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans --force-recreate

echo
echo "Container status:"
docker compose -f "$COMPOSE_FILE" ps

FRONTEND_PORT_DISPLAY="$(bpstracker_env_get "$SCRIPT_DIR/.env" FRONTEND_PORT || true)"
FRONTEND_PORT_DISPLAY="${FRONTEND_PORT_DISPLAY:-5173}"
SECRET_KEY_DISPLAY="$(bpstracker_env_get "$SCRIPT_DIR/.env" SECRET_KEY || true)"

echo
echo "Frontend: http://localhost:${FRONTEND_PORT_DISPLAY}"
if [ -n "$SECRET_KEY_DISPLAY" ]; then
  echo "SECRET_KEY in $SCRIPT_DIR/.env:"
  echo "$SECRET_KEY_DISPLAY"
  echo "Bitte sicher aufbewahren und nach Produktivstart nicht mehr ändern."
fi
