#!/usr/bin/env bash
set -euo pipefail

cd /opt/bpstracker
PROJECT_NAME="${PROJECT_NAME:-bpstracker}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

echo "=== docker compose ps ==="
docker compose -p "$PROJECT_NAME" ps frontend || true

echo
echo "=== Frontend health state ==="
docker inspect --format='{{json .State.Health}}' bpstracker-frontend 2>/dev/null || true

echo
echo "=== Frontend port mapping ==="
docker port bpstracker-frontend 2>/dev/null || true

echo
echo "=== Frontend /health from host ==="
curl -fsS "http://127.0.0.1:${FRONTEND_PORT}/health" || true

echo
echo "=== Frontend /health from container network ==="
docker compose -p "$PROJECT_NAME" exec -T frontend sh -lc 'cat /proc/1/comm; test -s /usr/share/nginx/html/index.html; test -s /tmp/bpstracker-config/config.js; echo ok' || true

echo
echo "=== Frontend logs ==="
docker compose -p "$PROJECT_NAME" logs --tail=160 frontend || true
