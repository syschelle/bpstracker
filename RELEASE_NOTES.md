# BPSTracker v0.9.77

## Added

- Added a dedicated `rotate-secret-key.sh` maintenance script for controlled `SECRET_KEY` rotation.
- The script always creates and verifies a complete local recovery backup before any key change. The backup contains a PostgreSQL custom-format dump, PostgreSQL globals, backend application data, the original `.env`, deployment files, Docker inspect snapshots, a manifest, and SHA-256 checksums.
- Added `--backup-only` so administrators can create and verify the recovery package without changing configuration or encrypted data.
- The new `SECRET_KEY` is entered interactively twice with terminal echo disabled. The script never generates or prints the key and requires at least 32 characters.
- Stored TOTP secrets, Shelly passwords, Weather Underground credentials, Pushover credentials, Gotify tokens, and any future AppSetting values ending in `_ciphertext` are re-encrypted transactionally.
- Added automatic rollback of `.env` and encrypted database values when a rotation step fails before successful verification.

## Security

- `update.sh` no longer creates a missing `.env`. It aborts instead of falling back to defaults.
- Every image update now saves a protected pre-update `.env` copy under `security-backups/` before changing the persisted image tag.
- `update.sh` validates downloaded deployment files before replacing the working copies, refreshes `rotate-secret-key.sh`, and refreshes itself after a successful container update.
- `.env`, recovery backups, and maintenance files are kept root-owned with restrictive permissions.

## Notes

- A `SECRET_KEY` rotation invalidates existing login sessions; users must sign in again.
- Recovery backups contain the previous `SECRET_KEY` and other sensitive deployment information. Keep the `security-backups` directory root-only and do not upload it to Git.
- The script intentionally does not rotate the PostgreSQL password. Database credential rotation is a separate maintenance operation.

# BPSTracker v0.9.76

## Security

- Moved trusted reverse-proxy configuration out of the web-managed database settings and into the protected `.env` deployment configuration.
- Added `BPSTRACKER_TRUSTED_PROXIES` as a comma-separated IP/CIDR list.
- Trusted proxy values are now read-only in the web diagnostic and cannot be changed through the API/UI.
- Install scripts keep `.env` at mode `0600`; the image update script now re-applies `0600` before modifying the image tag.
- Existing `.env` values are preserved across installs/updates.
- Install/update scripts use a restrictive `umask 077`, and deployment scripts no longer print `SECRET_KEY` in plaintext to the console.

# BPSTracker v0.9.75

## Added

- Added configurable source-IP blocking after repeated failed password logins.
- Added explicit trusted reverse-proxy IP/CIDR configuration for safe `X-Forwarded-For` evaluation.
- Added an admin client-IP diagnostic showing the direct backend peer, `X-Real-IP`, `X-Forwarded-For`, configured trusted proxies and the resolved client IP.
- Added optional Pushover/Gotify notification when a source IP is newly blocked.
- Added audit entries for failed and blocked login attempts without storing passwords.

## Security

- Forwarded client addresses are resolved from right to left and only explicitly configured upstream proxies are removed from the chain.
- The bundled frontend nginx is accepted as the immediate transport proxy because the backend port is only exposed inside the Compose network.
- Existing short-term login and 2FA rate limits remain active and now use the resolved client IP.
- Login blocking is disabled by default so administrators can verify the proxy diagnostic before enabling it.

# BPSTracker v0.9.74

## Changed

- Replaced `dashboard-overview.png` with the current dashboard screenshot.
- Kept the German project name **Ortsnetz-API** in the English dashboard instead of translating it to `Grid API`.
- Updated the bundled help copy of the dashboard screenshot.

# BPSTracker v0.9.73

## Added

- Added an optional Pushover `device` setting to target notifications to a specific registered device.
- Leaving the device field empty keeps the existing behavior and sends notifications to all active devices for the configured Pushover user.
- Device names are validated to the Pushover-compatible character set and maximum length.

# BPSTracker v0.9.72

## Added

- Added integrated system monitoring with selectable Pushover or Gotify delivery.
- Added a stale-measurement watchdog that alerts once when active-device measurements stop updating for the configured number of minutes.
- Added optional recovery notifications when fresh measurements resume.
- Added optional daily energy reports at a configurable local time with PV generation, grid import, grid export and calculated PV self-consumption.
- Added a notification test button in Setup.
- Pushover user/application keys and Gotify application tokens are encrypted at rest with BPSTracker's existing secret encryption.

## Notes

- The internal watchdog detects a stalled poller or stale measurement flow while the BPSTracker backend remains alive.
- A complete Docker host/container outage cannot send its own notification and therefore still requires an external uptime monitor.

# BPSTracker v0.9.71

## Fixed

- Fixed direct backup creation failing with `No space left on device` when the PostgreSQL dump exceeded the backend container's 64 MiB `/tmp` tmpfs.
- Backup creation and restore now use `/app/data/.backup-work` as a temporary disk-backed workspace instead of RAM-backed `/tmp`.
- Temporary backup work files are still deleted after download/restore and are excluded from backup contents and restore copying.
- The Compose init service now creates and owns the temporary backup workspace for backend UID/GID `10001:10001`.

# BPSTracker v0.9.70

## Changed

- Reworked encrypted backups to use a direct-download workflow instead of permanently storing newly created backup archives on the BPSTracker host.
- New backups are assembled in temporary storage, streamed to the browser, and automatically deleted from the backend after the download response completes.
- Added encrypted backup restore directly from the Setup UI by uploading a `.bpsenc` file and entering its backup password.
- Uploaded and decrypted restore files are processed only in temporary storage and removed automatically.
- Backup restore validates the encryption header, password, manifest, archive structure, path safety, file types, and extraction size before modifying the database.
- PostgreSQL restore runs in a single transaction so a failed import rolls back instead of leaving the database partially restored.
- Persisted backend data contained in the backup is restored while legacy server-side backup archives are excluded.
- Host `.env` and `SECRET_KEY` values are intentionally not overwritten; cross-host restores require carrying the original `SECRET_KEY` separately.
- Legacy list/download/delete endpoints remain available for backup files created by BPSTracker 0.9.68 and earlier, but new backups are no longer stored there.

## Update workflow

- `update.sh` now downloads the matching `docker-compose.images.yml` before pulling images.
- Tagged updates load the Compose file from the same Git tag; `--latest` loads it from `main`.
- The downloaded Compose file is validated with Docker Compose before replacing the local file.
- The previous Compose file is retained as a timestamped `.bak` file.
- This ensures future service or volume changes are delivered to image-based installations instead of updating containers with an outdated Compose definition.

## Documentation

- Updated `README.md` and `deREADME.md`.
- Synchronized the English and German in-app help.
- Updated `TESTING.md`.
