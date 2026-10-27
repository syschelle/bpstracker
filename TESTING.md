# Testing – BPSTracker v0.9.75

## v0.9.75 trusted-proxy login protection

- Verify the login protection settings are disabled by default after upgrade.
- Open the client-IP diagnostic through the public Traefik URL and verify direct backend peer, X-Real-IP, X-Forwarded-For and resolved client IP are shown.
- With no trusted Traefik IP configured, verify the resolved address stops at the untrusted proxy.
- Add the actual Traefik host IP/CIDR and verify the resolved address becomes the real browser/source IP.
- Verify a spoofed leftmost X-Forwarded-For value is not selected when the next hop is not trusted.
- Enable blocking, trigger the configured number of failed password logins and verify HTTP 429 plus Retry-After are returned until the block expires.
- Verify a successful login clears the failure state for the resolved source IP.
- Verify `auth.login.failed` and `auth.login.blocked` audit entries contain the resolved source IP but never a password.
- If enabled, verify Pushover/Gotify sends one security notification when a new block is created.
- Verify the existing short-window login and 2FA rate limits use the resolved source IP.


## v0.9.74 dashboard screenshot and Ortsnetz naming

- Verify the English dashboard header tile is labeled `Ortsnetz-API`, not `Grid API`.
- Verify `docs/images/dashboard-overview.png` matches the current dashboard screenshot.
- Verify the bundled help image `frontend/public/help/docs/images/dashboard-overview.png` is synchronized.

## v0.9.73 Pushover device targeting

- Save notification settings with a valid Pushover device name and verify test notifications include the configured `device` parameter.
- Leave the device field empty and verify notifications are sent without a `device` parameter.
- Verify device names longer than 25 characters or containing characters outside `[A-Za-z0-9_-]` are rejected.


## New v0.9.71 coverage

- Verify `POST /api/backups/create-download` returns an encrypted `.bpsenc` attachment and removes the temporary file after the response completes.
- Verify creating a new backup does not require `/app/data/backups` to exist or be writable.
- Verify restore accepts only `.bpsenc` uploads with a valid password and BPSTracker encryption header/manifest.
- Verify restore rejects path traversal, symlinks, hard links, device/FIFO entries, oversized uploads and oversized extracted archives.
- Verify PostgreSQL restore uses `ON_ERROR_STOP` and `--single-transaction` so failed imports roll back atomically.
- Verify uploaded/encrypted/decrypted restore files live only in temporary storage and are removed after the request.
- Verify backend data restore ignores legacy backup archives.
- Verify the Setup UI downloads a newly created backup directly and provides file upload + password controls for restore.
- Verify `update.sh` downloads the Compose file matching the requested tag (or `main` for `--latest`), validates it before replacement, and keeps a timestamped backup of the previous file.

## Automated tests

- `cd backend && pytest -q`: full backend regression suite in an environment with `backend/requirements.txt` installed and a configured `DATABASE_URL`.
- `cd backend && pytest -q tests/test_energy_retention_performance.py`: focused energy performance and immutability regression tests, with an SQLite file URL for imports (`DATABASE_URL=sqlite+pysqlite:////tmp/bpstracker-test.sqlite`).
- `cd frontend && npm ci && npm run build`: type-check, i18n checks and a production Vite build.

## New v0.9.68 coverage

- Validate all three Compose variants define `backend-data-init` and mount `/opt/bpstracker/data/backend` at `/app/data`.
- Verify the init service runs as root only for initialization, creates `/app/data/backups`, and restores UID/GID `10001:10001`.
- Verify the backend waits for `backend-data-init` with `service_completed_successfully` before starting.
- Verify the normal backend service remains read-only and non-root.


## New v0.9.66 coverage

- Inject a one-time unexpected exception into the poller loop and verify a later polling cycle still executes.
- Verify the recovered exception is emitted as an error log with traceback context.
- Verify task cancellation is not swallowed by the resilience guard.


## New v0.9.64 coverage

- The compact Ortsnetz header tile keeps the same three-line content and height while using increased vertical spacing.
- Desktop padding and line rhythm more closely match the neighboring air-data sensor widget.
- The <=1180 px layout keeps a slightly tighter but still increased spacing for responsive headers.
- Typography, HTTP success/error colors, external links and last-success timestamp behavior remain unchanged.
- English and German README/help copies document the spacing refinement.

## New v0.9.63 coverage

- The linked **Ortsnetz-API** title uses the same desktop and <=1180 px font sizes and the same weight as the primary air-sensor values.
- The Ortsnetz `HTTP` line uses the same font size, weight and line height as the Weather Underground status line.
- `HTTP 202` is rendered with the Weather Underground success green; failed HTTP/error states use the matching error red, including dark-theme variants.
- The last-success date/time line and the existing three-line tile layout remain unchanged.
- English and German README/help copies document the refined header presentation.

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


## New v0.9.65 coverage

- Verify the Ortsnetz API header tile remains rendered while switching between Dashboard, History, Setup and Help.
- Verify status refresh, colors, HTTP code, timestamp and external link behavior are unchanged.

## New v0.9.68 coverage

- Build the backend image and verify `pg_dump --version` reports PostgreSQL 16.x.
- Create an encrypted backup with matching passwords of at least 12 characters and verify the `.bpsenc` file is listed and automatically downloaded.
- Verify the UI displays a progress notice while backup creation is running.
- Force a `pg_dump` failure and verify the API returns a descriptive error and the frontend displays it.


## v0.9.72 notifications and monitoring
- Save Pushover settings, send a test notification and verify secrets are not returned by the API.
- Save Gotify URL/application token, send a test notification and verify delivery.
- Enable stale-measurement monitoring, stop fresh measurements beyond the threshold and verify one alert is sent; resume measurements and verify one recovery message.
- Enable the daily report and verify generation, grid import, grid export and PV self-consumption are sent once per local calendar day at/after the configured time.
- Verify the monitoring task survives transient notification delivery errors without terminating the backend.
