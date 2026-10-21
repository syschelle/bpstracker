# BPSTracker v0.9.61

## Changed

- Matched the compact Ortsnetz API header tile height to the air-data sensor tile.
- The Ortsnetz tile now stretches to the current header row height and keeps its contents vertically centered.
- No additional values were added to the compact tile; frequency remains in **Device status** only.
- Kept the existing Ortsnetz upload behavior and measured-frequency handling unchanged.
- Integrated the expanded Ortsnetz-Auslastung documentation into both `README.md` and `deREADME.md`.
- Synchronized the in-app English and German help copies with the updated README files.

## Documentation

- Documented the optional five-minute Ortsnetz upload, grid-meter selection, coordinates, optional PV capacity and privacy behavior.
- Documented measured grid-frequency handling for compatible Shelly devices and the deliberate `—` fallback when a device does not expose frequency.
- Documented dashboard transfer-health states and the separation between viewer-visible status and administrator-only configuration.
