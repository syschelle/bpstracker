# Testing – BPSTracker v0.9.62

## Automated tests

- `cd backend && pytest -q`: full backend regression suite in an environment with `backend/requirements.txt` installed and a configured `DATABASE_URL`.
- `cd backend && pytest -q tests/test_energy_retention_performance.py`: focused energy performance and immutability regression tests, with an SQLite file URL for imports (`DATABASE_URL=sqlite+pysqlite:////tmp/bpstracker-test.sqlite`).
- `cd frontend && npm ci && npm run build`: type-check, i18n checks and a production Vite build.

## New v0.9.62 coverage

- Ortsnetz header status tile stretches to the same cross-axis height as the air-data sensor tile while keeping its compact width and vertically centered content.
- The device-status frequency column and existing Ortsnetz upload payload remain unchanged.
- English and German README files now document the complete Ortsnetz integration, transfer-health states, privacy boundaries and measured-frequency behavior.
- In-app English and German help copies are synchronized with the updated root README files.

## New v0.9.57 coverage

- The indexed day-edge reader preserves the existing first/last non-null counter subtraction, source filters and reset handling; SQL statements do not load raw JSON payloads.
- The archive pass only calculates previously missing completed days, even after retained raw values are changed.
- Raw retention does not overwrite already archived day totals.
- The public API, dashboard summary and Kindle use the same unchanged daily counter deltas and combine them with stored history correctly.
- Maintenance runs in a worker thread and is triggered across the UTC day boundary.
- Existing dashboard/Kindle channel classification tests remain applicable without changes to energy formulas.

## Verification of the provided ZIP

- **63 non-authentication backend tests passed** (SQLite test database and temporary *import-only* shims for two security packages missing from this offline packaging environment; no authentication behavior was tested with those shims).
- `python -m compileall` passed for backend sources and tests.
- Frontend locale consistency check passed for both languages; shell script syntax checks passed.
- The full backend test suite could not run in the packaging environment because production dependencies including `psycopg`, `pyotp`, and `passlib` are unavailable offline. The full suite must be run with `backend/requirements.txt` installed before production deployment.
- `npm ci` could not finish offline (a Vite tarball was not cached). The release workflow builds a fresh frontend bundle using the GitHub Actions runner; the retained ZIP distribution bundle has only its version badge and help docs updated.
- Real Raspberry Pi PostgreSQL throughput and actual login latency still require deployment measurements; no specific speed-up is claimed.

## Operational verification on a Raspberry Pi

1. Capture `docker stats --no-stream bpstracker-backend` before/after the update.
2. Confirm that `/health` answers promptly during normal dashboard and Kindle polling.
3. Check login, daily energy cards, total energy/cost cards, history and the two Kindle displays before and after the update.
4. Check daily rollover and retained total balances the following day.

Avoid resetting or manually editing the production database during performance tests.
