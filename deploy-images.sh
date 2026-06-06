#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/env-setup.sh
source "$SCRIPT_DIR/scripts/env-setup.sh"

PROFILE="${BPSTRACKER_INSTALL_PROFILE:-}"
case "${1:-}" in
  --zero2w|--zero|zero2w)
    PROFILE="zero2w"
    shift || true
    ;;
  --regular|regular)
    PROFILE="regular"
    shift || true
    ;;
esac
if [ -z "$PROFILE" ]; then
  PROFILE="$(bpstracker_select_profile)"
fi

bpstracker_prepare_env "$SCRIPT_DIR/.env" "$PROFILE" "v0.9.9"
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
