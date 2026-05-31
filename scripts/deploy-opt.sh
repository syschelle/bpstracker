#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/bpstracker"
PROJECT_NAME="bpstracker"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR_REAL="$(readlink -m "$APP_DIR")"
SRC_DIR_REAL="$(readlink -m "$SRC_DIR")"

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

sudo mkdir -p "$APP_DIR"
sudo chown -R "$USER:$USER" "$APP_DIR"
mkdir -p "$APP_DIR/data/postgres" "$APP_DIR/data/backend" "$APP_DIR/backups"

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

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "Created $APP_DIR/.env"
  echo "Bitte prüfe $APP_DIR/.env, setze einen starken SECRET_KEY und lege den initialen Admin anschließend in der Weboberfläche an."
fi

cd "$APP_DIR"

echo "Prüfe, dass der Frontend-Docker-Build garantiert ohne npm/node läuft ..."
bash "$APP_DIR/scripts/verify-no-npm-build.sh"

echo "Stoppe alte BPSTracker-Container, damit alte Host-Port-Mappings sicher entfernt werden ..."
docker compose -p "$PROJECT_NAME" down --remove-orphans || true

echo "Baue BPSTracker-Images immer aus $APP_DIR ..."
echo "Frontend: nginx + vorhandenes frontend/dist, KEIN npm install, KEIN npm ci."
docker compose -p "$PROJECT_NAME" build --progress=plain

echo "Starte PostgreSQL und Backend zuerst ..."
docker compose -p "$PROJECT_NAME" up -d --remove-orphans postgres backend || true

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

  # Alle 20 Sekunden schon einmal die letzten Backend-Zeilen zeigen, damit es nicht wie ein Hänger wirkt.
  if [ $((NOW_TS - LAST_LOG_TS)) -ge 20 ]; then
    LAST_LOG_TS="$NOW_TS"
    echo "--- letzte Backend-Logs ---"
    docker compose -p "$PROJECT_NAME" logs --tail=40 backend || true
    echo "--- Ende Backend-Logs ---"
  fi

  sleep 5
done

if [ "$BACKEND_HEALTH" != "healthy" ]; then
  echo
  echo "ERROR: Backend ist nicht healthy. Status: $BACKEND_HEALTH, Container-State: ${BACKEND_STATE:-unknown}"
  echo
  echo "Container-Status:"
  docker compose -p "$PROJECT_NAME" ps || true
  echo
  echo "Letzte Backend-Logs:"
  docker compose -p "$PROJECT_NAME" logs --tail=250 backend || true
  echo
  echo "Letzte PostgreSQL-Logs:"
  docker compose -p "$PROJECT_NAME" logs --tail=120 postgres || true
  echo
  echo "Schnelldiagnose:"
  echo "  cd $APP_DIR"
  echo "  docker compose -p $PROJECT_NAME ps"
  echo "  docker compose -p $PROJECT_NAME logs --tail=250 backend"
  echo
  echo "Wenn dies eine Testinstallation ohne wichtige Messdaten ist, kannst du mit frischer Datenbank neu starten:"
  echo "  cd $APP_DIR"
  echo "  docker compose -p $PROJECT_NAME down"
  echo "  mv data/postgres data/postgres.backup.$(date +%Y%m%d-%H%M%S)"
  echo "  bash ./deploy.sh"
  exit 1
fi

echo "Backend ist healthy. Starte Frontend ..."
docker compose -p "$PROJECT_NAME" up -d --remove-orphans frontend

echo "Container-Status:"
docker compose -p "$PROJECT_NAME" ps

FRONTEND_PORT_DISPLAY="$(grep -E '^FRONTEND_PORT=' .env 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
FRONTEND_PORT_DISPLAY="${FRONTEND_PORT_DISPLAY:-5173}"

echo
printf 'BPSTracker wurde nach %s deployt und gestartet.\n' "$APP_DIR"
echo "Frontend: http://localhost:${FRONTEND_PORT_DISPLAY}"
echo "Backend und PostgreSQL sind nicht von außen veröffentlicht; Zugriff nur intern über das Docker-Netzwerk."
echo "API-Aufrufe laufen über den Frontend-Proxy: http://localhost:${FRONTEND_PORT_DISPLAY}/api/..."
echo
