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
PORTS="$(docker port bpstracker-frontend 2>/dev/null || true)"
printf '%s\n' "$PORTS"
if printf '%s\n' "$PORTS" | grep -q '^80/tcp'; then
  echo "WARNUNG: Frontend ist noch auf Container-Port 80 gemappt. Seit v0.7.3 muss es Host-Port -> 8080/tcp sein."
  echo "Fix: ports: - \"\${FRONTEND_PORT:-5173}:8080\" und Container neu erstellen."
fi
if printf '%s\n' "$PORTS" | grep -q '8080/tcp'; then
  echo "OK: Frontend-Port-Mapping zeigt auf Container-Port 8080."
fi

echo
echo "=== Frontend /health from host ==="
curl -fsS "http://127.0.0.1:${FRONTEND_PORT}/health" || true

echo
echo "=== Frontend /health from container network ==="
docker compose -p "$PROJECT_NAME" exec -T frontend sh -lc 'cat /proc/1/comm; wget -S -O- -T 5 http://127.0.0.1:8080/health 2>&1 || true; wget -S -O- -T 5 http://127.0.0.1:80/health 2>&1 || true' || true

echo
echo "=== Frontend logs ==="
docker compose -p "$PROJECT_NAME" logs --tail=160 frontend || true
