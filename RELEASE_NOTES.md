# BPSTracker v0.9.68

## Fixed

- Fixed encrypted backup creation against BPSTracker's PostgreSQL 16 database.
- The backend image now installs `postgresql-client-16` from the official PostgreSQL APT repository instead of Debian Bookworm's PostgreSQL 15 client.
- Added explicit backend error handling and logging for missing `pg_dump`, dump timeouts and failed database exports.
- The backup UI now displays a visible progress message while a backup is being created and exposes failures through an alert region.

## Documentation

- Updated `README.md` and `deREADME.md`.
- Synchronized the English and German in-app help.
- Updated `TESTING.md`.
