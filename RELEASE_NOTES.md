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
