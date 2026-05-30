#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="bpstracker"

echo "Veröffentlichte Ports für BPSTracker:"
docker compose -p "$PROJECT_NAME" ps

echo
if docker port bpstracker-backend 8000 >/dev/null 2>&1; then
  echo "WARNUNG: Backend-Port ist veröffentlicht:" >&2
  docker port bpstracker-backend 8000 >&2
  exit 1
fi

if docker port bpstracker-postgres 5432 >/dev/null 2>&1; then
  echo "WARNUNG: PostgreSQL-Port ist veröffentlicht:" >&2
  docker port bpstracker-postgres 5432 >&2
  exit 1
fi

echo "OK: Backend und PostgreSQL haben keine veröffentlichten Host-Ports."
echo "Das Backend ist nur innerhalb des Docker-Netzwerks erreichbar."
