#!/usr/bin/env bash
set -euo pipefail
cd /opt/bpstracker
PROJECT_NAME="bpstracker"
echo "=== Docker Compose Status ==="
docker compose -p "$PROJECT_NAME" ps || true
echo
echo "=== Backend inspect: State/Health ==="
docker inspect bpstracker-backend --format='State={{.State.Status}} Health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} ExitCode={{.State.ExitCode}} Error={{.State.Error}}' 2>/dev/null || true
echo
echo "=== PostgreSQL inspect: State/Health ==="
docker inspect bpstracker-postgres --format='State={{.State.Status}} Health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} ExitCode={{.State.ExitCode}} Error={{.State.Error}}' 2>/dev/null || true
echo
echo "=== Backend Logs ==="
docker compose -p "$PROJECT_NAME" logs --tail=300 backend || true
echo
echo "=== PostgreSQL Logs ==="
docker compose -p "$PROJECT_NAME" logs --tail=160 postgres || true
echo
echo "=== Backend /health aus dem Container-Netz testen ==="
docker run --rm --network bpstracker_default curlimages/curl:8.10.1 -sS -m 5 http://backend:8000/health || true
echo
