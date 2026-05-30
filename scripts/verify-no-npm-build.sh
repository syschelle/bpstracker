#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Prüfe Frontend-Dockerfiles ..."
for f in frontend/Dockerfile frontend/Dockerfile.static; do
  if [ ! -f "$f" ]; then
    echo "ERROR: $f fehlt." >&2
    exit 1
  fi
  echo "--- $f ---"
  sed -n '1,120p' "$f"
  if grep -Ei 'npm|node:|yarn|pnpm' "$f" >/dev/null; then
    echo "ERROR: $f enthält noch npm/node/yarn/pnpm. Dieses Paket ist nicht die No-NPM-Version." >&2
    exit 1
  fi
done

if grep -E 'dockerfile:[[:space:]]*Dockerfile.static' docker-compose.yml >/dev/null; then
  echo "OK: docker-compose.yml nutzt frontend/Dockerfile.static."
else
  echo "ERROR: docker-compose.yml nutzt nicht frontend/Dockerfile.static." >&2
  exit 1
fi

if [ ! -f frontend/dist/index.html ]; then
  echo "ERROR: frontend/dist/index.html fehlt. Ohne dist müsste Docker npm ausführen, was hier nicht erlaubt ist." >&2
  exit 1
fi

echo "OK: Frontend-Build ist statisch. Docker wird kein npm install/npm ci ausführen."
