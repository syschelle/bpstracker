#!/usr/bin/env bash
set -euo pipefail
cd /opt/bpstracker
PROJECT_NAME="bpstracker"
TS="$(date +%Y%m%d-%H%M%S)"
echo "Stoppe BPSTracker..."
docker compose -p "$PROJECT_NAME" down --remove-orphans || true
if [ -d data/postgres ]; then
  echo "Verschiebe alte PostgreSQL-Datenbank nach data/postgres.backup.$TS"
  mv data/postgres "data/postgres.backup.$TS"
fi
mkdir -p data/postgres data/backend backups
echo "Starte mit frischer Datenbank..."
bash ./deploy.sh
