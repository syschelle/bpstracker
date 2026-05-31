#!/usr/bin/env bash
set -euo pipefail
cd /opt/bpstracker
PROJECT_NAME="bpstracker"

echo "=== docker compose ps ==="
docker compose -p "$PROJECT_NAME" ps || true

echo
echo "=== Backend health ==="
docker inspect --format='{{json .State.Health}}' bpstracker-backend 2>/dev/null || true

echo
echo "=== Backend logs ==="
docker compose -p "$PROJECT_NAME" logs --tail=250 backend || true

echo
echo "=== PostgreSQL logs ==="
docker compose -p "$PROJECT_NAME" logs --tail=120 postgres || true

echo
echo "=== Frontend health state ==="
docker inspect --format='{{json .State.Health}}' bpstracker-frontend 2>/dev/null || true

echo
echo "=== Frontend port mapping ==="
docker port bpstracker-frontend 2>/dev/null || true

echo
echo "=== Frontend logs ==="
docker compose -p "$PROJECT_NAME" logs --tail=120 frontend || true
