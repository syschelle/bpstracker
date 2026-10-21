# BPSTracker v0.9.62

## Changed

- Reworked the compact Ortsnetz API header tile into a clear three-line layout.
- Line 1 now contains the status indicator and a bold **Ortsnetz-API** title.
- Line 2 shows only the latest HTTP status.
- Line 3 shows the date and time of the last successful upload.
- The **Ortsnetz-API** title now links to `https://www.ortsnetz-auslastung.de/` and opens in a new tab.
- Added an **OpenStreetMap** link next to the latitude label in **Setup → Interfaces → Ortsnetz-Auslastung** for easier coordinate lookup.
- Kept Ortsnetz upload behavior, frequency handling and privacy separation unchanged.

## Documentation

- Updated `README.md` and `deREADME.md` for the three-line status tile and the new external links.
- Synchronized the in-app English and German help copies with the updated documentation.
