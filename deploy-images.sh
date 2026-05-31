#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Missing .env file. Copy .env.example to .env and adjust it first."
  exit 1
fi

mkdir -p /opt/bpstracker/data/postgres /opt/bpstracker/data/backend
BACKEND_UID=10001
BACKEND_GID=10001
if command -v sudo >/dev/null 2>&1; then
  sudo chown -R "${BACKEND_UID}:${BACKEND_GID}" /opt/bpstracker/data/backend
else
  chown -R "${BACKEND_UID}:${BACKEND_GID}" /opt/bpstracker/data/backend 2>/dev/null || true
fi

echo "Pulling BPSTracker images from GHCR..."
docker compose -f docker-compose.images.yml pull

echo "Starting BPSTracker..."
echo "Recreating containers so old frontend port mappings such as 5173:80 are removed..."
docker compose -f docker-compose.images.yml up -d --remove-orphans --force-recreate

echo
echo "Container status:"
docker compose -f docker-compose.images.yml ps
