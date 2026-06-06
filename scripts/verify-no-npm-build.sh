#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# shellcheck source=scripts/env-setup.sh
if [ -f scripts/env-setup.sh ]; then
  source scripts/env-setup.sh
fi

if declare -F bpstracker_is_english >/dev/null 2>&1 && bpstracker_is_english; then
  echo "Checking frontend Dockerfiles ..."
else
  echo "Prüfe Frontend-Dockerfiles ..."
fi

for f in frontend/Dockerfile frontend/Dockerfile.static; do
  if [ ! -f "$f" ]; then
    echo "ERROR: $f missing." >&2
    exit 1
  fi
  echo "--- $f ---"
  sed -n '1,120p' "$f"
  if grep -Ei 'npm|node:|yarn|pnpm' "$f" >/dev/null; then
    if declare -F bpstracker_is_english >/dev/null 2>&1 && bpstracker_is_english; then
      echo "ERROR: $f still contains npm/node/yarn/pnpm. This package is not the no-NPM version." >&2
    else
      echo "ERROR: $f enthält noch npm/node/yarn/pnpm. Dieses Paket ist nicht die No-NPM-Version." >&2
    fi
    exit 1
  fi
done

if grep -E 'dockerfile:[[:space:]]*Dockerfile.static' docker-compose.yml >/dev/null; then
  if declare -F bpstracker_is_english >/dev/null 2>&1 && bpstracker_is_english; then
    echo "OK: docker-compose.yml uses frontend/Dockerfile.static."
  else
    echo "OK: docker-compose.yml nutzt frontend/Dockerfile.static."
  fi
else
  if declare -F bpstracker_is_english >/dev/null 2>&1 && bpstracker_is_english; then
    echo "ERROR: docker-compose.yml does not use frontend/Dockerfile.static." >&2
  else
    echo "ERROR: docker-compose.yml nutzt nicht frontend/Dockerfile.static." >&2
  fi
  exit 1
fi

if [ ! -f frontend/dist/index.html ]; then
  if declare -F bpstracker_is_english >/dev/null 2>&1 && bpstracker_is_english; then
    echo "ERROR: frontend/dist/index.html is missing. Without dist, Docker would need to run npm, which is not allowed here." >&2
  else
    echo "ERROR: frontend/dist/index.html fehlt. Ohne dist müsste Docker npm ausführen, was hier nicht erlaubt ist." >&2
  fi
  exit 1
fi

if declare -F bpstracker_is_english >/dev/null 2>&1 && bpstracker_is_english; then
  echo "OK: frontend build is static. Docker will not run npm install/npm ci."
else
  echo "OK: Frontend-Build ist statisch. Docker wird kein npm install/npm ci ausführen."
fi
