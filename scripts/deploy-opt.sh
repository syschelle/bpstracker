#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/bpstracker"
PROJECT_NAME="bpstracker"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR_REAL="$(readlink -m "$APP_DIR")"
SRC_DIR_REAL="$(readlink -m "$SRC_DIR")"

# shellcheck source=scripts/env-setup.sh
source "$SCRIPT_DIR/env-setup.sh"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker wurde nicht gefunden." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose wurde nicht gefunden." >&2
  exit 1
fi

if [ "$SRC_DIR_REAL" != "$APP_DIR_REAL" ] && ! command -v rsync >/dev/null 2>&1; then
  echo "ERROR: rsync wurde nicht gefunden. Bitte installiere rsync oder kopiere das Projekt manuell nach $APP_DIR." >&2
  exit 1
fi

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

sudo mkdir -p "$APP_DIR"
sudo chown -R "$USER:$USER" "$APP_DIR"
mkdir -p "$APP_DIR/data/postgres" "$APP_DIR/data/backend" "$APP_DIR/backups"
BACKEND_UID=10001
BACKEND_GID=10001
sudo chown -R "${BACKEND_UID}:${BACKEND_GID}" "$APP_DIR/data/backend"

if [ "$SRC_DIR_REAL" != "$APP_DIR_REAL" ]; then
  echo "Deploye BPSTracker von $SRC_DIR nach $APP_DIR ..."
  rsync -a --delete \
    --exclude='.git' \
    --exclude='.env' \
    --exclude='data/postgres' \
    --exclude='data/backend' \
    --exclude='backups' \
    "$SRC_DIR"/ "$APP_DIR"/
else
  echo "BPSTracker liegt bereits in $APP_DIR. Kopieren wird übersprungen."
fi

mkdir -p "$APP_DIR/data/postgres" "$APP_DIR/data/backend" "$APP_DIR/backups"
sudo chown -R "${BACKEND_UID}:${BACKEND_GID}" "$APP_DIR/data/backend"

# Re-source the copied helper from the target directory so future deploys use the installed version.
# shellcheck source=scripts/env-setup.sh
source "$APP_DIR/scripts/env-setup.sh"
bpstracker_prepare_env "$APP_DIR/.env" "$PROFILE" "v0.9.11"

cd "$APP_DIR"
COMPOSE_FILE="$(bpstracker_compose_file_for_profile "$PROFILE" local)"

echo "Verwende Installationsprofil: $PROFILE"
echo "Verwende Compose-Datei: $COMPOSE_FILE"

if [ "$PROFILE" = "zero2w" ]; then
  echo "Pi Zero 2 W Profil: verwende vorgebaute GHCR-Images statt lokalem Build."
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" pull
else
  echo "Prüfe, dass der Frontend-Docker-Build garantiert ohne npm/node läuft ..."
  bash "$APP_DIR/scripts/verify-no-npm-build.sh"
fi

echo "Stoppe alte BPSTracker-Container, damit alte Host-Port-Mappings sicher entfernt werden ..."
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" down --remove-orphans || true

if [ "$PROFILE" != "zero2w" ]; then
  echo "Baue BPSTracker-Images immer aus $APP_DIR ..."
  echo "Frontend: nginx + vorhandenes frontend/dist, KEIN npm install, KEIN npm ci."
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" build --progress=plain
fi

echo "Starte PostgreSQL und Backend zuerst ..."
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" up -d --remove-orphans postgres backend || true

# Warte auf Backend-Health und zeige regelmäßig Status/Logs.
echo "Warte auf Backend-Healthcheck ..."
echo "Hinweis: Wenn dies fehlschlägt, werden direkt Backend- und PostgreSQL-Logs ausgegeben."
BACKEND_HEALTH="unknown"
MAX_SECONDS="${BACKEND_HEALTH_TIMEOUT_SECONDS:-75}"
START_TS="$(date +%s)"
LAST_LOG_TS=0

while true; do
  NOW_TS="$(date +%s)"
  ELAPSED=$((NOW_TS - START_TS))
  BACKEND_HEALTH="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' bpstracker-backend 2>/dev/null || echo missing)"
  BACKEND_STATE="$(docker inspect --format='{{.State.Status}}' bpstracker-backend 2>/dev/null || echo missing)"
  POSTGRES_HEALTH="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' bpstracker-postgres 2>/dev/null || echo missing)"

  printf '  [%3ss/%ss] postgres=%s backend_state=%s backend_health=%s\n' "$ELAPSED" "$MAX_SECONDS" "$POSTGRES_HEALTH" "$BACKEND_STATE" "$BACKEND_HEALTH"

  if [ "$BACKEND_HEALTH" = "healthy" ]; then
    break
  fi

  if [ "$BACKEND_STATE" = "exited" ] || [ "$BACKEND_STATE" = "dead" ] || [ "$BACKEND_STATE" = "missing" ]; then
    break
  fi

  if [ "$ELAPSED" -ge "$MAX_SECONDS" ]; then
    break
  fi

  if [ $((NOW_TS - LAST_LOG_TS)) -ge 20 ]; then
    LAST_LOG_TS="$NOW_TS"
    echo "--- letzte Backend-Logs ---"
    docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" logs --tail=40 backend || true
    echo "--- Ende Backend-Logs ---"
  fi

  sleep 5
done

if [ "$BACKEND_HEALTH" != "healthy" ]; then
  echo
  echo "ERROR: Backend ist nicht healthy. Status: $BACKEND_HEALTH, Container-State: ${BACKEND_STATE:-unknown}"
  echo
  echo "Container-Status:"
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" ps || true
  echo
  echo "Letzte Backend-Logs:"
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" logs --tail=250 backend || true
  echo
  echo "Letzte PostgreSQL-Logs:"
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" logs --tail=120 postgres || true
  echo
  echo "Schnelldiagnose:"
  echo "  cd $APP_DIR"
  echo "  docker compose -p $PROJECT_NAME -f $COMPOSE_FILE ps"
  echo "  docker compose -p $PROJECT_NAME -f $COMPOSE_FILE logs --tail=250 backend"
  echo
  echo "Wenn dies eine Testinstallation ohne wichtige Messdaten ist, kannst du mit frischer Datenbank neu starten:"
  echo "  cd $APP_DIR"
  echo "  docker compose -p $PROJECT_NAME -f $COMPOSE_FILE down"
  echo "  mv data/postgres data/postgres.backup.$(date +%Y%m%d-%H%M%S)"
  echo "  bash ./deploy.sh"
  exit 1
fi

echo "Backend ist healthy. Starte Frontend ..."
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" up -d --remove-orphans frontend

echo "Container-Status:"
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" ps

FRONTEND_PORT_DISPLAY="$(bpstracker_env_get .env FRONTEND_PORT || true)"
FRONTEND_PORT_DISPLAY="${FRONTEND_PORT_DISPLAY:-5173}"
SECRET_KEY_DISPLAY="$(bpstracker_env_get .env SECRET_KEY || true)"

echo
printf 'BPSTracker wurde nach %s deployt und gestartet.\n' "$APP_DIR"
echo "Frontend: http://localhost:${FRONTEND_PORT_DISPLAY}"
echo "Backend und PostgreSQL sind nicht von außen veröffentlicht; Zugriff nur intern über das Docker-Netzwerk."
echo "API-Aufrufe laufen über den Frontend-Proxy: http://localhost:${FRONTEND_PORT_DISPLAY}/api/..."
echo
if [ -n "$SECRET_KEY_DISPLAY" ]; then
  echo "SECRET_KEY in $APP_DIR/.env:"
  echo "$SECRET_KEY_DISPLAY"
  echo "Bitte sicher aufbewahren und nach Produktivstart nicht mehr ändern."
  echo
fi
