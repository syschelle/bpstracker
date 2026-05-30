#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Missing .env file. Copy .env.example to .env and adjust it first."
  exit 1
fi

mkdir -p /opt/bpstracker/data/postgres /opt/bpstracker/data/backend

echo "Pulling BPSTracker images from GHCR..."
docker compose -f docker-compose.images.yml pull

echo "Starting BPSTracker..."
docker compose -f docker-compose.images.yml up -d

echo
echo "Container status:"
docker compose -f docker-compose.images.yml ps
