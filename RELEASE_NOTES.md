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
