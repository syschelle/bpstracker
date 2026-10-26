# BPSTracker v0.9.67

## Fixed

- Fixed `PermissionError: [Errno 13] Permission denied: '/app/data/backups'` on hardened non-root installations using the persistent backend bind mount.
- Added a short-lived `backend-data-init` Compose service that creates `/app/data/backups` and restores ownership of `/app/data` to backend UID/GID `10001:10001` before the application backend starts.
- The runtime backend remains non-root with its existing read-only filesystem and dropped capabilities.
- Applied the initialization guard consistently to the standard, GHCR image and Raspberry Pi Zero 2 W Compose variants.

---

# BPSTracker v0.9.66

## Fixed

- Hardened the long-running measurement poller so an unexpected exception in a polling cycle no longer stops all future data collection while the API container itself remains healthy.
- The poller now logs the full exception and automatically continues with the next configured polling cycle.
- `asyncio.CancelledError` is still propagated normally so application shutdown remains clean.
- Added a regression test that injects a one-time polling failure and verifies that the following cycle still runs.

---

# BPSTracker v0.9.65

## Changed

- The compact **Ortsnetz-API** status tile is now always visible in the application header.
- The tile remains visible on Dashboard, History, Setup and Help instead of being limited to the Dashboard tab.
- Status polling, three-line layout, colors, external link and timestamp formatting remain unchanged.

---

# BPSTracker v0.9.64

## Changed

- Increased the vertical spacing between the three lines of the compact **Ortsnetz-API** header tile.
- Matched the Ortsnetz tile padding and line rhythm more closely to the neighboring air-data sensor widget.
- Kept the existing tile height, width, typography, status colors, links and content unchanged.
- The three lines remain: linked **Ortsnetz-API** title, HTTP status, and last successful upload date/time.

## Documentation

- Updated `README.md` and `deREADME.md` with the refined Ortsnetz header spacing.
- Synchronized the in-app English and German help copies with the updated documentation.
