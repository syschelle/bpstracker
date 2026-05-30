#!/usr/bin/env bash
set -euo pipefail
PROJECT_NAME="bpstracker"
APP_DIR="/opt/bpstracker"
cd "$APP_DIR"

docker compose -p "$PROJECT_NAME" exec -T postgres psql -U "${POSTGRES_USER:-bpstracker}" -d "${POSTGRES_DB:-bpstracker}" <<'SQL'
SELECT 'raw_measurements' AS table_name, count(*) AS rows FROM measurements
UNION ALL
SELECT 'daily_energy_summary' AS table_name, count(*) AS rows FROM daily_energy_summary;

SELECT min(timestamp) AS oldest_raw, max(timestamp) AS newest_raw FROM measurements;
SELECT min(date) AS first_summary_day, max(date) AS last_summary_day FROM daily_energy_summary;
SQL
