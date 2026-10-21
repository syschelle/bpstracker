# BPSTracker v0.9.59

## Changes

- Added grid-frequency acquisition for Shelly Pro 3EM measurements, including common flattened `a_freq`/`b_freq`/`c_freq`, nested and array-shaped RPC responses.
- Added nullable `frequency_hz` storage to measurements with automatic startup migration for existing PostgreSQL installations.
- Ortsnetz uploads now include `grid_frequency_hz` when a valid 45–55 Hz measurement is available; no fallback or estimated frequency is generated.
- Added an Ortsnetz API health card to the authenticated dashboard. It shows whether uploads are working, the latest HTTP status, the last transmitted grid frequency and the last successful upload time.
- Dashboard API health is green only after a recent successful HTTP 202 response; stale/pending, failed and disabled states are visually distinct.
- Allowed authenticated viewer accounts to read the non-sensitive Ortsnetz transfer status while keeping coordinates and integration configuration admin-only.
- Added parser and payload tests for Pro 3EM grid-frequency handling.
