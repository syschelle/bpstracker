#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/env-setup.sh
source "$SCRIPT_DIR/scripts/env-setup.sh"

PROFILE="${BPSTRACKER_INSTALL_PROFILE:-}"
IMAGE_TAG=""
DEFAULT_IMAGE_TAG="v0.9.22"
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
    --latest|latest)
      IMAGE_TAG="latest"
      shift
      ;;
    --tag)
      if [ $# -lt 2 ]; then
        echo "ERROR: --tag requires a value, for example --tag v0.9.22 or --tag latest." >&2
        exit 1
      fi
      IMAGE_TAG="$2"
      shift 2
      ;;
    --tag=*)
      IMAGE_TAG="${1#--tag=}"
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
      echo "Usage: bash ./deploy-images.sh [--regular|--zero2w] [--latest|--tag TAG] [--language de|en]" >&2
      exit 1
      ;;
  esac
done

if [ -n "$LANGUAGE_OPTION" ]; then
  BPSTRACKER_LANGUAGE="$LANGUAGE_OPTION"
else
  BPSTRACKER_LANGUAGE="$(bpstracker_select_language "$SCRIPT_DIR/.env")"
fi
export BPSTRACKER_LANGUAGE

if [ -z "$PROFILE" ]; then
  PROFILE="$(bpstracker_select_profile)"
fi

if [ -z "$IMAGE_TAG" ]; then
  if [ -t 0 ]; then
    bpstracker_prompt_line ""
    if bpstracker_is_english; then
      bpstracker_prompt_line "Which Docker image tag do you want to use?"
      bpstracker_prompt_line "  1) $DEFAULT_IMAGE_TAG (recommended for reproducible releases)"
      bpstracker_prompt_line "  2) latest (always the newest published image)"
      bpstracker_prompt_text 'Selection [1/2, default: 1]: '
    else
      bpstracker_prompt_line "Welchen Docker-Image-Tag möchtest du verwenden?"
      bpstracker_prompt_line "  1) $DEFAULT_IMAGE_TAG (empfohlen für reproduzierbare Releases)"
      bpstracker_prompt_line "  2) latest (immer das aktuellste veröffentlichte Image)"
      bpstracker_prompt_text 'Auswahl [1/2, Standard: 1]: '
    fi
    bpstracker_prompt_read tag_choice
    case "$tag_choice" in
      2|l|L|latest|Latest) IMAGE_TAG="latest" ;;
      *) IMAGE_TAG="$DEFAULT_IMAGE_TAG" ;;
    esac
  else
    IMAGE_TAG="${BPSTRACKER_IMAGE_TAG:-$DEFAULT_IMAGE_TAG}"
  fi
fi

bpstracker_prepare_env "$SCRIPT_DIR/.env" "$PROFILE" "$IMAGE_TAG" "$BPSTRACKER_LANGUAGE"
bpstracker_env_set "$SCRIPT_DIR/.env" BPSTRACKER_IMAGE_TAG "$IMAGE_TAG"
bpstracker_env_set "$SCRIPT_DIR/.env" BPSTRACKER_LANGUAGE "$BPSTRACKER_LANGUAGE"
bpstracker_env_set "$SCRIPT_DIR/.env" BPSTRACKER_DEFAULT_LANGUAGE "$BPSTRACKER_LANGUAGE"
COMPOSE_FILE="$(bpstracker_compose_file_for_profile "$PROFILE" images)"

mkdir -p /opt/bpstracker/data/postgres /opt/bpstracker/data/backend
BACKEND_UID=10001
BACKEND_GID=10001
if command -v sudo >/dev/null 2>&1; then
  sudo chown -R "${BACKEND_UID}:${BACKEND_GID}" /opt/bpstracker/data/backend
else
  chown -R "${BACKEND_UID}:${BACKEND_GID}" /opt/bpstracker/data/backend 2>/dev/null || true
fi

if bpstracker_is_english; then
  echo "Using script language: English"
  echo "Using installation profile: $(bpstracker_profile_label "$PROFILE")"
  echo "Using Docker image tag: $IMAGE_TAG"
  echo "Using Compose file: $COMPOSE_FILE"
  echo "Pulling BPSTracker images from GHCR..."
else
  echo "Verwende Skriptsprache: Deutsch"
  echo "Verwende Installationsprofil: $(bpstracker_profile_label "$PROFILE")"
  echo "Verwende Docker-Image-Tag: $IMAGE_TAG"
  echo "Verwende Compose-Datei: $COMPOSE_FILE"
  echo "Lade BPSTracker-Images aus GHCR..."
fi
docker compose -f "$COMPOSE_FILE" pull

if bpstracker_is_english; then
  echo "Starting BPSTracker..."
  echo "Recreating containers so old frontend port mappings are removed..."
else
  echo "Starte BPSTracker..."
  echo "Erstelle Container neu, damit alte Frontend-Port-Mappings entfernt werden..."
fi
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans --force-recreate

echo
if bpstracker_is_english; then echo "Container status:"; else echo "Container-Status:"; fi
docker compose -f "$COMPOSE_FILE" ps

FRONTEND_PORT_DISPLAY="$(bpstracker_env_get "$SCRIPT_DIR/.env" FRONTEND_PORT || true)"
FRONTEND_PORT_DISPLAY="${FRONTEND_PORT_DISPLAY:-5173}"
SECRET_KEY_DISPLAY="$(bpstracker_env_get "$SCRIPT_DIR/.env" SECRET_KEY || true)"

echo
if bpstracker_is_english; then
  echo "Frontend: http://localhost:${FRONTEND_PORT_DISPLAY}"
  if [ -n "$SECRET_KEY_DISPLAY" ]; then
    echo "SECRET_KEY in $SCRIPT_DIR/.env:"
    echo "$SECRET_KEY_DISPLAY"
    echo "Store it safely and do not change it after production start."
  fi
else
  echo "Frontend: http://localhost:${FRONTEND_PORT_DISPLAY}"
  if [ -n "$SECRET_KEY_DISPLAY" ]; then
    echo "SECRET_KEY in $SCRIPT_DIR/.env:"
    echo "$SECRET_KEY_DISPLAY"
    echo "Bitte sicher aufbewahren und nach Produktivstart nicht mehr ändern."
  fi
fi
