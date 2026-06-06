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

PROFILE="${BPSTRACKER_INSTALL_PROFILE:-}"
LANGUAGE_OPTION=""
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
    --language|--lang)
      if [ $# -lt 2 ]; then
        echo "ERROR: --language requires de or en." >&2
        exit 1
      fi
      LANGUAGE_OPTION="$(bpstracker_normalize_language "$2")"
      shift 2
      ;;
    --language=*|--lang=*)
      LANGUAGE_OPTION="$(bpstracker_normalize_language "${1#*=}")"
      shift
      ;;
    *)
      echo "ERROR: Unknown option: $1" >&2
      echo "Usage: bash ./deploy.sh [--regular|--zero2w] [--language de|en]" >&2
      exit 1
      ;;
  esac
done

if [ -n "$LANGUAGE_OPTION" ]; then
  BPSTRACKER_LANGUAGE="$LANGUAGE_OPTION"
else
  BPSTRACKER_LANGUAGE="$(bpstracker_select_language "$SRC_DIR/.env")"
fi
export BPSTRACKER_LANGUAGE

err() {
  echo "$*" >&2
}

if ! command -v docker >/dev/null 2>&1; then
  if bpstracker_is_english; then err "ERROR: docker was not found."; else err "ERROR: docker wurde nicht gefunden."; fi
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  if bpstracker_is_english; then err "ERROR: docker compose was not found."; else err "ERROR: docker compose wurde nicht gefunden."; fi
  exit 1
fi

if [ "$SRC_DIR_REAL" != "$APP_DIR_REAL" ] && ! command -v rsync >/dev/null 2>&1; then
  if bpstracker_is_english; then
    err "ERROR: rsync was not found. Please install rsync or copy the project manually to $APP_DIR."
  else
    err "ERROR: rsync wurde nicht gefunden. Bitte installiere rsync oder kopiere das Projekt manuell nach $APP_DIR."
  fi
  exit 1
fi

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
  if bpstracker_is_english; then
    echo "Deploying BPSTracker from $SRC_DIR to $APP_DIR ..."
  else
    echo "Deploye BPSTracker von $SRC_DIR nach $APP_DIR ..."
  fi
  rsync -a --delete \
    --exclude='.git' \
    --exclude='.env' \
    --exclude='data/postgres' \
    --exclude='data/backend' \
    --exclude='backups' \
    "$SRC_DIR"/ "$APP_DIR"/
else
  if bpstracker_is_english; then
    echo "BPSTracker is already located in $APP_DIR. Copy step skipped."
  else
    echo "BPSTracker liegt bereits in $APP_DIR. Kopieren wird übersprungen."
  fi
fi

mkdir -p "$APP_DIR/data/postgres" "$APP_DIR/data/backend" "$APP_DIR/backups"
sudo chown -R "${BACKEND_UID}:${BACKEND_GID}" "$APP_DIR/data/backend"

# Re-source the copied helper from the target directory so future deploys use the installed version.
# shellcheck source=scripts/env-setup.sh
source "$APP_DIR/scripts/env-setup.sh"
export BPSTRACKER_LANGUAGE
bpstracker_prepare_env "$APP_DIR/.env" "$PROFILE" "v0.9.15" "$BPSTRACKER_LANGUAGE"

cd "$APP_DIR"
COMPOSE_FILE="$(bpstracker_compose_file_for_profile "$PROFILE" local)"

if bpstracker_is_english; then
  echo "Using script language: English"
  echo "Using installation profile: $(bpstracker_profile_label "$PROFILE")"
  echo "Using Compose file: $COMPOSE_FILE"
else
  echo "Verwende Skriptsprache: Deutsch"
  echo "Verwende Installationsprofil: $(bpstracker_profile_label "$PROFILE")"
  echo "Verwende Compose-Datei: $COMPOSE_FILE"
fi

if [ "$PROFILE" = "zero2w" ]; then
  if bpstracker_is_english; then
    echo "Pi Zero 2 W profile: using prebuilt GHCR images instead of a local build."
  else
    echo "Pi Zero 2 W Profil: verwende vorgebaute GHCR-Images statt lokalem Build."
  fi
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" pull
else
  if bpstracker_is_english; then
    echo "Checking that the frontend Docker build is guaranteed to run without npm/node ..."
  else
    echo "Prüfe, dass der Frontend-Docker-Build garantiert ohne npm/node läuft ..."
  fi
  bash "$APP_DIR/scripts/verify-no-npm-build.sh"
fi

if bpstracker_is_english; then
  echo "Stopping old BPSTracker containers so old host port mappings are removed safely ..."
else
  echo "Stoppe alte BPSTracker-Container, damit alte Host-Port-Mappings sicher entfernt werden ..."
fi
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" down --remove-orphans || true

if [ "$PROFILE" != "zero2w" ]; then
  if bpstracker_is_english; then
    echo "Building BPSTracker images from $APP_DIR ..."
    echo "Frontend: nginx + existing frontend/dist, NO npm install, NO npm ci."
  else
    echo "Baue BPSTracker-Images immer aus $APP_DIR ..."
    echo "Frontend: nginx + vorhandenes frontend/dist, KEIN npm install, KEIN npm ci."
  fi
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" build --progress=plain
fi

if bpstracker_is_english; then
  echo "Starting PostgreSQL and backend first ..."
else
  echo "Starte PostgreSQL und Backend zuerst ..."
fi
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" up -d --remove-orphans postgres backend || true

if bpstracker_is_english; then
  echo "Waiting for backend healthcheck ..."
  echo "Hint: if this fails, backend and PostgreSQL logs will be shown immediately."
else
  echo "Warte auf Backend-Healthcheck ..."
  echo "Hinweis: Wenn dies fehlschlägt, werden direkt Backend- und PostgreSQL-Logs ausgegeben."
fi
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
    if bpstracker_is_english; then echo "--- latest backend logs ---"; else echo "--- letzte Backend-Logs ---"; fi
    docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" logs --tail=40 backend || true
    if bpstracker_is_english; then echo "--- end backend logs ---"; else echo "--- Ende Backend-Logs ---"; fi
  fi

  sleep 5
done

if [ "$BACKEND_HEALTH" != "healthy" ]; then
  echo
  if bpstracker_is_english; then
    echo "ERROR: backend is not healthy. Health: $BACKEND_HEALTH, container state: ${BACKEND_STATE:-unknown}"
    echo
    echo "Container status:"
    docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" ps || true
    echo
    echo "Latest backend logs:"
    docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" logs --tail=250 backend || true
    echo
    echo "Latest PostgreSQL logs:"
    docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" logs --tail=120 postgres || true
    echo
    echo "Quick diagnosis:"
    echo "  cd $APP_DIR"
    echo "  docker compose -p $PROJECT_NAME -f $COMPOSE_FILE ps"
    echo "  docker compose -p $PROJECT_NAME -f $COMPOSE_FILE logs --tail=250 backend"
    echo
    echo "For a test installation without important measurements, you can restart with a fresh database:"
    echo "  cd $APP_DIR"
    echo "  docker compose -p $PROJECT_NAME -f $COMPOSE_FILE down"
    echo "  mv data/postgres data/postgres.backup.$(date +%Y%m%d-%H%M%S)"
    echo "  bash ./deploy.sh --language $BPSTRACKER_LANGUAGE"
  else
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
    echo "  bash ./deploy.sh --language $BPSTRACKER_LANGUAGE"
  fi
  exit 1
fi

if bpstracker_is_english; then
  echo "Backend is healthy. Starting frontend ..."
else
  echo "Backend ist healthy. Starte Frontend ..."
fi
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" up -d --remove-orphans frontend

if bpstracker_is_english; then echo "Container status:"; else echo "Container-Status:"; fi
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" ps

FRONTEND_PORT_DISPLAY="$(bpstracker_env_get .env FRONTEND_PORT || true)"
FRONTEND_PORT_DISPLAY="${FRONTEND_PORT_DISPLAY:-5173}"
SECRET_KEY_DISPLAY="$(bpstracker_env_get .env SECRET_KEY || true)"

echo
if bpstracker_is_english; then
  printf 'BPSTracker was deployed to %s and started.\n' "$APP_DIR"
  echo "Frontend: http://localhost:${FRONTEND_PORT_DISPLAY}"
  echo "Backend and PostgreSQL are not published externally; access is internal through the Docker network only."
  echo "API calls go through the frontend proxy: http://localhost:${FRONTEND_PORT_DISPLAY}/api/..."
  echo
  if [ -n "$SECRET_KEY_DISPLAY" ]; then
    echo "SECRET_KEY in $APP_DIR/.env:"
    echo "$SECRET_KEY_DISPLAY"
    echo "Store it safely and do not change it after production start."
    echo
  fi
else
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
fi
