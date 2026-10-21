# BPSTracker v0.9.60

## Changed

- Moved the Ortsnetz API transfer-status display out of the regular dashboard card grid into a compact tile in the dashboard header.
- Reduced the Ortsnetz status tile to the essential information: transfer state, HTTP status and last successful upload time.
- Removed grid frequency from the Ortsnetz status tile to avoid displaying the same measurement twice.
- Added a **Frequency** column to the dashboard **Device status** table when at least one current measurement provides a frequency value.
- Frequency values are displayed directly with the device/phase measurements in Hz; devices or aggregate rows without a measured value show the normal missing-value marker.
- Kept the existing v0.9.59 frequency acquisition, storage and `grid_frequency_hz` Ortsnetz upload behavior unchanged.

## UI

- The compact Ortsnetz status uses the existing green/yellow/red/grey health states.
- The status tile is shown only on the dashboard and remains responsive on smaller screens.
- Ortsnetz configuration and coordinates remain administrator-only.
