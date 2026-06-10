# BPSTracker

**BPSTracker** is a self-hosted monitoring dashboard for a **Balkon-Photovoltaik-System (BPS)** / balcony photovoltaic system.

It collects live power and energy values from Shelly devices, visualizes current house import and solar production, calculates daily and total balances, estimates costs and savings, and can generate a Kindle/e-ink friendly status display.

BPSTracker is designed for local home use. The backend is kept inside the Docker network and only the frontend/nginx proxy is exposed to the LAN.

Repository:

```text
https://github.com/syschelle/bpstracker
```

![BPSTracker dashboard overview](docs/images/dashboard-overview.png)

---

## Table of contents

- [Overview](#overview)
- [Main features](#main-features)
- [Architecture](#architecture)
- [System requirements](#system-requirements)
- [Screens and UI](#screens-and-ui)
- [Supported devices and sensors](#supported-devices-and-sensors)
- [Authentication and user roles](#authentication-and-user-roles)
- [Kindle display](#kindle-display)
- [JSON API](#json-api)
- [Simulation mode](#simulation-mode)
- [Air quality sensor](#air-quality-sensor)
- [Data retention](#data-retention)
- [Encrypted backups](#encrypted-backups)
- [Requirements](#requirements)
- [Installation](#installation)
- [Deployment](#deployment)
- [Updating from GitHub](#updating-from-github)
- [Configuration](#configuration)
- [Ports and networking](#ports-and-networking)
- [Backup and restore](#backup-and-restore)
- [Troubleshooting](#troubleshooting)
- [Running on Raspberry Pi](#running-on-raspberry-pi)
- [Security notes](#security-notes)
- [Project structure](#project-structure)
- [License](#license)
- [Disclaimer](#disclaimer)

---

## Overview

BPSTracker is a compact local monitoring application for small photovoltaic systems, especially balcony solar installations.

The project focuses on:

- a clear dashboard
- low-maintenance Docker deployment
- local-only operation
- small-device friendly behavior
- persistent energy totals
- configurable retention for raw data
- optional Kindle/e-ink display support
- optional JSON export for external integrations

It is not intended to be a certified billing or metering system.

---

## Main features

### Dashboard

Solar feed-in channels may report negative power values, depending on the Shelly wiring and measurement direction. BPSTracker treats negative solar/feed-in power as positive solar production for dashboard, history, JSON API and Kindle display calculations.

The dashboard provides a compact view of the current energy situation.

It includes:

- **House import / Hausbezug**
  - current total consumption estimate
  - current signed grid power / grid import value
  - current solar power
  - solar/grid share gauge

- **Daily energy balance**
  - solar production
  - grid import
  - grid export

- **Total energy balance**
  - total solar production
  - total grid import
  - total grid export

- **Daily cost balance**
  - consumption costs
  - solar savings

- **Total cost balance**
  - accumulated consumption costs
  - accumulated savings

- **Amortization**
  - investment costs
  - breakeven progress
  - remaining amount
  - estimated remaining time

- **Device status**
  - online/offline state
  - last successful polling time

- **Latest measurements**
  - current normalized measurement data

Power values in the web dashboard automatically switch from watts to kilowatts when the value reaches 1000 W.

Examples:

```text
850 W
1.25 kW
-1.25 kW
```

### History

The history view displays measured power values over selectable periods.

The backend aggregates values into chart-friendly time buckets. This avoids visual spikes caused by multiple Shelly channels/phases being stored at nearly the same timestamp.

Typical ranges:

- 24 hours
- 7 days
- 30 days


### History chart series

The history chart shows separate series for:

- solar production
- grid import
- grid export

The series are color-coded so the values can be distinguished easily. Grid export is displayed as a positive value so it can be compared visually with grid import and solar production.

### Setup

The setup area allows administrators to configure:

- language
- timezone
- GitHub repository link
- Kindle display activation
- Kindle display preview
- JSON API activation
- JSON API preview
- user credentials
- financial values
- data retention
- air quality sensor
- Shelly devices
- polling intervals

### Multilingual UI

The web interface supports:

- German
- English

The selected language is stored as an application setting.

### Theme support

The frontend supports:

- light theme
- dark theme

The selected theme is stored in the browser.

### Currency support

The dashboard can display financial values in:

- EUR
- USD
- GBP

The application does not perform automatic currency conversion. The configured kWh price and investment costs are interpreted in the selected currency.

### Timezone support

The application supports IANA timezones such as:

```text
Europe/Berlin
Europe/London
UTC
America/New_York
```

Daylight saving time and winter time are handled automatically by Python `zoneinfo`.

---

## System requirements

BPSTracker is designed to run as a self-hosted Docker application.

Minimum requirements:

- Linux host with Docker Engine
- Docker Compose plugin
- Git, for cloning and updating the repository
- 64-bit operating system
- Network access from the BPSTracker host to the configured Shelly devices
- A modern browser for the web interface

Recommended hardware:

- Raspberry Pi 3 / 4 / 5 with a 64-bit OS
- Raspberry Pi Zero 2 W with a 64-bit OS for smaller installations
- x86_64 mini PC, NAS or server
- at least 1 GB RAM
- persistent storage for PostgreSQL data and backups

Supported container platforms:

```text
linux/amd64
linux/arm64
```

Raspberry Pi check:

```bash
uname -m
```

Recommended result:

```text
aarch64
```

For Raspberry Pi systems, a 64-bit OS is recommended so the `linux/arm64` images can be used.

Required network ports:

```text
5173  Web interface / frontend
5432  PostgreSQL, internal Docker network only
8000  Backend API, internal Docker network only
```

Only the frontend port needs to be exposed to the local network. Backend and database should stay inside the Docker network.

---

## Architecture

A possible BPSTracker setup separates grid import measurement from balcony solar generation measurement:

![Possible BPSTracker system setup](docs/images/bpstracker-system-setup.png)

BPSTracker consists of three main services:

```text
Frontend  -> nginx + static React build
Backend   -> FastAPI / Python
Database  -> PostgreSQL
```

The backend is not exposed directly to the outside. The browser accesses the backend only through the frontend/nginx proxy.

Typical access flow:

```text
Browser / Kindle / local integration
      |
      | HTTP
      v
Frontend/nginx host port :5173 → container :8080
      |
      | internal Docker network
      v
Backend container :8000
      |
      | internal Docker network
      v
PostgreSQL
```

The backend remains private inside the Docker network.

---

## Screenshots

### Dashboard overview

![BPSTracker dashboard overview](docs/images/dashboard-overview.png)

### History with simulation mode

![BPSTracker history with simulation mode](docs/images/history-simulation.png)

### Setup overview

![BPSTracker setup overview](docs/images/setup-overview.png)

### Mobile view

![BPSTracker mobile view](docs/images/mobile.png)


## Screens and UI

The screenshots show the dashboard, the color-coded history view and the setup page with simulation mode and optional integrations.


The screenshot above shows the desktop dashboard with live energy cards, air sensor values and a combined device status/current measurements table. Optional details such as channel, phase, voltage or current are hidden when they are not configured or not present in the latest data.


BPSTracker is optimized for desktop and mobile browsers.

The mobile header is designed to avoid crowding:

- hamburger menu on the left
- page title and role in the center
- theme toggle on the right
- air sensor values in a separate responsive row

The side navigation is detached and can be opened or closed with the hamburger button.

---

## Device purpose

Each Shelly device can have a purpose in Setup:

```text
Auto detect
Home/grid import
Solar/feed-in
Consumer/other
Ignore
```

This makes multi-device installations easier to configure. For example, multiple solar/feed-in Shelly devices can be configured as `Solar/feed-in`; BPSTracker sums them for the dashboard, history, JSON API and Kindle display.

Purpose behavior:

- `Home/grid import`: counted as the house/grid meter
- `Solar/feed-in`: counted as solar production / feed-in; negative Shelly power values are treated as positive solar production
- `Consumer/other`: kept as raw measurement data, but not used as the main grid or solar source
- `Ignore`: excluded from calculated dashboard values
- `Auto detect`: legacy behavior based on the detected Shelly measurement source

Existing installations are migrated automatically and keep `Auto detect` as the default purpose.


## Supported devices and sensors

BPSTracker currently focuses on Shelly devices.

Supported or intended Shelly device types include:

- Shelly 3EM Gen1
- Shelly Pro 3EM / NG 3EM
- Shelly 2PM Gen4
- generic Shelly NG devices

Each device can be configured in Setup with:

- name
- device type
- IP address or hostname
- optional username
- optional password
- polling interval
- channel
- active/inactive state

The backend normalizes measurements and stores them in PostgreSQL.

---

## Authentication and user roles

BPSTracker requires authentication.

There are two user roles:

### Admin

The admin can:

- open the dashboard
- open the history view
- open setup
- configure devices
- configure users
- configure financial settings
- configure retention
- configure language and timezone
- configure optional APIs
- manage 2FA

The admin can enable TOTP-based two-factor authentication.

### Viewer

The viewer can:

- open the dashboard
- open the history view

The viewer cannot open Setup and cannot manage 2FA.

### Password storage

Passwords are stored as secure hashes using Argon2id.

Usernames are configurable and are not required to be email addresses.

---

## Kindle display

BPSTracker can generate a Kindle/e-ink friendly PNG image.

The fixed endpoint is:

```text
http://<server-ip>:5173/api/kindle/display.png
```

Example:

```text
http://192.168.178.211:5173/api/kindle/display.png
```

The URL is intentionally fixed and does not require query parameters. `display.png` intentionally remains an optional public, cache-only image endpoint for Kindle/e-ink fetch jobs that cannot attach authentication cookies or bearer tokens. It does not expose metadata and does not provide a manual refresh API.

### Kindle display activation

The Kindle display can be enabled or disabled in Setup.

When disabled:

- no new Kindle PNG is generated
- the background task skips rendering
- the endpoint reports that the Kindle display is disabled

This is useful if the Kindle display is not used and the device should save resources.

### Kindle preview

Setup includes a Kindle preview button.

The preview shows the current generated PNG directly in the browser, so you can check how the image will look on the Kindle.

### Kindle image behavior

The Kindle display respects the configured UI language for date, time and update labels. German uses a 24-hour time format, while English uses an AM/PM time format.

The PNG is generated by the backend using Python and Pillow.

Properties:

- format: PNG
- size: 600 × 800 px
- grayscale-friendly design
- generated inside the container
- default cache path: `/tmp/bpstracker-kindle-display.png`
- no external rendering tool required at runtime
- generated once per minute
- not generated exactly at second `00`
- last valid PNG is kept if rendering fails

The displayed clock is shifted by one minute to better match Kindle cron refresh timing.

### Kindle admin metadata endpoint

A metadata endpoint is available for authenticated administrators only:

```text
GET /api/kindle/meta
```

It can be used in the setup UI or with an authenticated admin session or API bearer token to verify:

- whether the Kindle display is enabled
- when the last image was generated
- the renderer version
- the current image size
- possible rendering errors

### Example Kindle cron usage

A Kindle can fetch the image with a command like:

```bash
wget -O /mnt/us/bpstracker.png "http://192.168.178.211:5173/api/kindle/display.png"
```

Many older Kindle devices have problems with modern HTTPS/TLS. For local Kindle dashboards, plain HTTP inside the local network is usually the most reliable option.

---

## Public dashboard

BPSTracker can expose a separate dashboard-only page without requiring a login.

The feature can be enabled in Setup. The same setup page also lets you set the meter number shown on the smart-meter style public display:

```text
Setup → Public dashboard / Öffentliches Dashboard
```

When enabled, the public page is available at:

```text
/public/dashboard
```

For example:

```text
http://<ip-address>:5173/public/dashboard
```

The public dashboard shows:

- dashboard energy cards
- current air sensor values, if the air sensor is configured

It does not expose:

- device status
- latest measurements
- Setup
- History
- Account / 2FA
- user management
- backup actions
- reset actions
- admin functions

Only enable this feature when these dashboard values may be visible to visitors on your network or via your reverse proxy.


## JSON API

BPSTracker provides an optional JSON API for external tools, scripts, home automation systems or dashboards.

Endpoint:

```text
http://<server-ip>:5173/api/current-values
```

Example:

```bash
curl http://192.168.178.211:5173/api/current-values
```

### JSON API activation

The JSON API can be enabled or disabled in Setup.

When disabled:

- `/api/current-values` does not return values
- the endpoint reports that the API is disabled

This avoids exposing integration data when the API is not needed.

### JSON API preview

Setup includes a JSON preview button.

The preview calls `/api/current-values` and displays the current JSON response directly in the browser.

### Example response

```json
{
  "timestamp_utc": "2026-05-29T20:15:00+00:00",
  "local_date": "2026-05-29",
  "timezone": "Europe/Berlin",
  "last_measurement_at": "2026-05-29T20:14:55+00:00",

  "current_solar_production_w": 120.5,
  "current_grid_power_w": 284.8,
  "current_grid_import_w": 284.8,
  "current_grid_export_w": 0.0,
  "current_total_consumption_w": 405.3,

  "daily_solar_production_kwh": 1.42,
  "daily_grid_import_kwh": 8.36,
  "daily_grid_export_kwh": 0.0,

  "total_solar_production_kwh": 15.7,
  "total_grid_import_kwh": 128.4,
  "total_grid_export_kwh": 2.1
}
```

### Field meaning

| Field | Meaning |
|---|---|
| `current_solar_production_w` | current solar production in W |
| `current_grid_power_w` | signed current grid power in W |
| `current_grid_import_w` | current grid import in W |
| `current_grid_export_w` | current grid export in W |
| `current_total_consumption_w` | estimated current total consumption in W |
| `daily_solar_production_kwh` | solar production for the current local day |
| `daily_grid_import_kwh` | grid import for the current local day |
| `daily_grid_export_kwh` | grid export for the current local day |
| `total_solar_production_kwh` | total solar production |
| `total_grid_import_kwh` | total grid import |
| `total_grid_export_kwh` | total grid export |

---

## Simulation mode

BPSTracker includes an optional simulation mode for demo or test installations without real devices.

The simulation can be enabled in:

```text
Setup -> Simulation
```

When enabled, the dashboard, history chart and JSON API return simulated values instead of real device measurements.

The simulation settings include a configurable maximum solar output in watts. This value caps the generated PV curve so the simulated output matches what the real installation could actually deliver. You can also configure separate day and night baseload values in watts. These baseload values define the continuous household consumption floor, while simulated fridge cycles and appliance peaks such as coffee machine, stove/cooking and washing-machine events are still added on top.

The simulation is based on:

- a configurable balcony PV / solar installation with a maximum simulated output in watts
- a typical 2-person household
- configurable day and night baseload values
- realistic daily load curves
- morning and evening consumption peaks
- fridge cycles and appliance spikes on top of the configured baseload
- cloud and daylight fluctuations
- seasonal solar variation

No simulated measurements are written to the production measurement tables. The values are generated live and separated from production data. When simulation is disabled, the simulated view disappears and no demo values remain in the production environment.

The simulation also affects the Kindle display, JSON API and air sensor header. Simulated air data includes temperature, humidity, PM10 and PM2.5.

The header displays a visible simulation banner: **You are in the Matrix 😎**

This makes it possible to preview the UI, charts, balances, costs and JSON output before real Shelly devices are configured.

Disable simulation before using BPSTracker for real monitoring.

---


## Air quality sensor

BPSTracker can optionally read an air quality sensor based on the **Sensor.Community DNMS / Luftdaten** project.

More information about the supported sensor project:

```text
https://sensor.community/en/sensors/dnms/
```

BPSTracker reads the local sensor endpoint:

```text
http://<sensor-ip>/data.json
```

The expected JSON contains a `sensordatavalues` array, for example:

```json
{
  "software_version": "NRZ-2024-136-B1",
  "age": "95",
  "sensordatavalues": [
    { "value_type": "SDS_P1", "value": "1.83" },
    { "value_type": "SDS_P2", "value": "0.40" },
    { "value_type": "BME280_temperature", "value": "24.17" },
    { "value_type": "BME280_humidity", "value": "30.21" }
  ]
}
```

BPSTracker uses:

| Sensor value | Displayed as |
|---|---|
| `BME280_temperature` | Temperature |
| `BME280_humidity` | Humidity |
| `SDS_P1` | PM10 |
| `SDS_P2` | PM2.5 |

The air sensor values are not stored historically. They are shown only in the UI header and Kindle display. The Kindle renderer refreshes the same shared air-sensor cache before generating the PNG, so dashboard, public dashboard and Kindle display values stay aligned while still respecting the conservative sensor polling interval.

### Air sensor polling behavior

The sensor is polled conservatively:

- normal successful polling interval: 180 seconds
- retry interval after failure: 30 seconds
- short HTTP timeouts
- last valid values are kept if the sensor is temporarily unavailable

This prevents a slow or unreachable sensor from blocking the BPSTracker application.

---

## Amortization achievements

BPSTracker shows small, playful amortization achievements in the header when the total solar savings pass certain thresholds.

Examples:

```text
First solar power
Coffee fund unlocked
Pizza power
Movie night
Solar legend
```

The first achievement is unlocked when solar production is detected for the first time. The other achievements are based on `savings_total_eur`, are stored locally in the browser and remain visible for seven days after they are unlocked. Each achievement also has a small local SVG badge shown in the header. They are available in German and English and are meant as a fun motivation layer; they do not change the financial calculations.


## Battery investment analysis

BPSTracker treats grid export as unpaid by default. This means exported energy does not generate revenue in the amortization calculation.

The battery amortization calculation can be enabled or disabled in Setup. When it is disabled, battery values can remain stored but the dashboard does not calculate or show the battery amortization result.

The Setup page allows entering optional battery values:

```text
Battery cost
Battery capacity in kWh
Battery round-trip efficiency in percent
```

The dashboard then estimates whether a battery could be worthwhile based on the surplus energy that would otherwise be exported.

The current calculation uses these assumptions:

- grid export is not compensated
- exported surplus could be stored and later replace grid import
- battery round-trip efficiency defaults to a conservative 85% and can be adjusted in Setup
- maximum one usable charge/discharge cycle per day
- today's usable surplus is capped by the configured battery capacity

The battery payback estimate is therefore an approximation. It is intended as a practical first indicator, not as a detailed battery simulation.

If the balcony PV system has not paid for itself yet, the open remaining amortization amount is included in the combined battery payback view. This prevents the battery from being shown as worthwhile while the base system still has unpaid investment costs.


## Data retention

To prevent the database from growing indefinitely, BPSTracker supports raw data retention.

Raw measurements are deleted after the configured number of days.

For very small devices, BPSTracker also supports an optional low-resource mode that limits raw/live measurements to the latest 24 hours while still keeping permanent daily aggregates. This is intended for Raspberry Pi Zero 2 W installations.

Daily aggregates are kept permanently and are used for:

- total energy balance
- total cost balance
- amortization
- long-term totals

This keeps the database small while preserving important long-term values.

### Raspberry Pi Zero 2 W mode

For a Raspberry Pi Zero 2 W, select the Zero 2 W profile in the installer:

```bash
bash ./deploy.sh --zero2w
```

For prebuilt image deployments, use:

```bash
bash ./deploy-images.sh --zero2w
```

Advanced operators can still run `docker-compose.zero2w.yml` directly after `.env` has been generated by one of the install scripts.

The Zero 2 W profile enables:

- `PI_ZERO_2W_MODE=true`
- `LIVE_DATA_MAX_HOURS=24`
- `RAW_RETENTION_HOURS=24`
- lower Shelly polling concurrency
- smaller temporary filesystems

In this mode, dashboard/history live data and exported raw measurements are limited to the latest 24 hours. Permanent daily aggregates remain available and continue to feed the total balance, total cost balance and amortization cards.

---

## Requirements

### Recommended system

- Linux host
- Docker
- Docker Compose plugin
- persistent storage below `/opt/bpstracker`

Recommended hardware:

- Raspberry Pi 3, 4 or 5
- small home server
- mini PC
- NAS with Docker support

### Minimum system

A Raspberry Pi Zero 2 may work, but it is close to the limit because it only has 512 MB RAM.

For low-memory systems:

- avoid building Docker images on the device
- use prebuilt images if possible
- enable swap
- keep polling intervals reasonable
- keep raw retention short
- disable unused features such as Kindle display or JSON API

---

## Installation

Clone the repository:

```bash
git clone https://github.com/syschelle/bpstracker.git
cd bpstracker
```

Deploy the application:

```bash
bash ./deploy.sh
```

For unattended installs you can pass the language explicitly:

```bash
bash ./deploy.sh --language en
bash ./deploy.sh --language de
```

The installer first asks for the script language and then whether you want the regular installation or the Raspberry Pi Zero 2 W / low-resource installation. It creates `.env` from generated secure values and does **not** copy `.env.example` for production use. The selected language is written to `BPSTRACKER_LANGUAGE` and `BPSTRACKER_DEFAULT_LANGUAGE`, so the first-run web setup opens in the same language. The generated `SECRET_KEY` is shown once at the end of the install output; store it safely and do not change it after production start because it protects encrypted Shelly passwords and 2FA secrets.

On a fresh database, open the web interface and complete the initial setup screen. The first user sets the admin username and password there. No admin or viewer credentials are shipped in `.env`.

The deployment is designed to install and run the application below:

```text
/opt/bpstracker
```

---

## Deployment

After deployment, open the frontend in your browser:

```text
http://<server-ip>:5173
```

Example:

```text
http://192.168.178.211:5173
```

The frontend listens on port `5173`.

The backend is only reachable inside the Docker network and should not be exposed directly.

---

## Updating from GitHub

If you installed the project from GitHub:

```bash
cd /opt/bpstracker
git pull
bash ./deploy.sh
```

The deployment script should rebuild or restart the required services.

After updating, reload the browser page.

For frontend changes, a hard reload may be required:

```text
Ctrl + F5
```

On mobile browsers, closing and reopening the browser tab or clearing the site cache may be necessary.

---

## Configuration

Most settings are configured in the web interface under **Setup**.

### Language

The web UI translations are stored as locale files with metadata in:

```text
frontend/src/i18n/locales/
```

Available UI languages are derived from those files. Each locale file contains a `meta` block with the language code, native name, browser locale and help file, plus the `translations` object used by the React app. The build runs `npm run check-i18n` to verify that every locale provides the same translation keys as the English baseline.

To add another UI language, add a new file such as `frontend/src/i18n/locales/fr.json` with matching translation keys and metadata. The language switcher and setup language dropdown will pick it up automatically.

### Timezone

Use a valid IANA timezone, for example:

```text
Europe/Berlin
```

This automatically handles daylight saving time and winter time.

### GitHub repository

Setup contains a direct link to the project repository:

```text
https://github.com/syschelle/bpstracker
```

### Currency

Supported currencies:

- EUR
- USD
- GBP

No automatic currency conversion is performed.

### Financial settings

Configure:

- kWh price
- investment costs

These values are used to calculate:

- consumption costs
- solar savings
- amortization progress

### Optional interfaces

Setup allows enabling or disabling:

- Kindle display generation
- JSON API

Both features include preview/test buttons.

### Devices

Each Shelly device can be configured with:

- host/IP
- type
- channel
- polling interval
- optional credentials
- active/inactive state

### Users

The initial setup screen creates the first admin account. After that, the setup area allows changing the admin credentials and optionally creating or changing a viewer account.

The viewer has no setup access.

---

## Ports and networking

Default external port:

```text
5173
```

The browser, Kindle and local integrations should use:

```text
http://<server-ip>:5173
```

Important endpoints:

```text
/api/auth/login
/api/measurements/summary
/api/current-values
/api/settings/air-sensor/current
/api/kindle/display.png
```

The backend itself should not be published to the host network.

---

---

## Encrypted backups

BPSTracker can create encrypted backups directly from the **Setup** area.

The backup feature is intended to protect the most important application data without exposing secrets in plain text. The backup password is entered **per backup** and is **not stored** anywhere.

The password is not saved in:

- the database
- `.env`
- application settings
- the backup metadata
- the browser after the form is cleared

The backend only uses the password in memory while creating the encrypted backup.

### What is included

A backup contains:

```text
backup/
├── manifest.json
├── database.sql
├── environment.env
└── backend_data/
```

The most important part is the PostgreSQL dump:

```text
database.sql
```

It contains the BPSTracker database state, including:

- application settings
- configured devices
- users and password hashes
- 2FA configuration
- historical measurements
- daily aggregates
- financial settings
- optional interface settings

The `environment.env` file contains an environment snapshot that can help with restore or migration.

The `backend_data/` directory may contain backend-side data such as cached generated files. The backup directory itself is excluded from nested backups.

### Backup filename

Encrypted backup files use this naming scheme:

```text
bpstracker-backup-YYYYMMDD-HHMMSS.tar.gz.bpsenc
```

Example:

```text
bpstracker-backup-20260530-143012.tar.gz.bpsenc
```

### Encryption

Backups are encrypted before download.

The current format uses:

```text
AES-256-GCM
PBKDF2-HMAC-SHA256
per-backup random salt
per-backup random nonce
```

The unencrypted intermediate archive is deleted immediately after encryption.

### Creating a backup

Open the web interface as an admin user and go to:

```text
Setup -> Backup
```

Then:

1. Enter a backup password.
2. Repeat the password.
3. Click **Create encrypted backup**.
4. Download the generated `.tar.gz.bpsenc` file.
5. Store the file and password safely.

The password must be at least 12 characters long.

### Existing backups

The Setup page lists existing encrypted backups stored on the server.

For each backup you can:

- download it again
- delete it from the server

Only admin users can create, download or delete backups.

### Important warning

The backup password cannot be recovered.

If the password is lost, the backup cannot be decrypted.

This is intentional and protects the backup if the file is copied or leaked.

### Restore

Automatic restore from the web UI is intentionally not implemented yet.

Restoring a backup replaces the running application's own database and should be done manually and carefully.

A manual restore flow is expected to look like this:

1. Stop BPSTracker.
2. Decrypt the `.tar.gz.bpsenc` backup using the backup password.
3. Extract the resulting archive.
4. Restore `database.sql` into PostgreSQL.
5. Restore configuration/data files as needed.
6. Start BPSTracker again.

A dedicated restore guide should be added before using backups for production disaster recovery.

---


## Reset measured values

Admins can reset all measured values from the **Setup** area.

The reset requires typing:

```text
reset
```

This deletes:

- raw measurements
- daily energy aggregates
- volatile air sensor caches
- volatile simulation caches
- generated Kindle cache files

It keeps:

- users
- passwords and 2FA configuration
- configured devices
- financial settings
- language/timezone settings
- optional interface settings

This action cannot be undone. Create an encrypted backup before using it in production.

---


## Backup and restore

For encrypted backups created from the web interface, see [Encrypted backups](#encrypted-backups). These backups are password-protected and should be preferred over unencrypted manual archive backups.


The most important data is stored in the Docker volumes and persistent data directory below:

```text
/opt/bpstracker
```

Recommended backup items:

- PostgreSQL data volume
- `.env`
- application data directory
- optional generated Kindle PNG cache

Simple backup approach:

```bash
tar -czf bpstracker-backup.tar.gz /opt/bpstracker
```

For a database-consistent backup, use PostgreSQL tools such as `pg_dump`.

---

## Troubleshooting

### Frontend cannot login and shows `Failed to fetch`

Make sure the browser calls the same origin:

```text
http://<server-ip>:5173/api/auth/login
```

It should not call:

```text
http://localhost:8000/api/auth/login
```

The backend is intentionally not exposed directly.

### 502 Bad Gateway

A 502 usually means the frontend/nginx proxy cannot reach the backend container.

Check container status:

```bash
docker compose ps
```

Check backend logs:

```bash
docker compose logs backend --tail=100
```

### Backend healthcheck fails

Check backend logs:

```bash
docker compose logs backend --tail=200
```

Common causes:

- database not ready
- migration problem
- invalid environment variable
- Python import error
- missing dependency

### NPM install hangs

The project is intended to ship with a built frontend `dist` for low-power devices.

On small systems such as a Raspberry Pi Zero 2, avoid running npm builds locally.

### Kindle image does not update

Check whether the Kindle display is enabled in Setup.

Then check the admin-only metadata endpoint while logged in as an admin:

```text
http://<server-ip>:5173/api/kindle/meta
```

The PNG is generated once per minute and may not change instantly. Since v0.7.7 the generated PNG defaults to `/tmp/bpstracker-kindle-display.png` because it is a regeneratable cache artifact. This avoids stale images on hardened non-root containers when older installations still have a root-owned `/opt/bpstracker/data/backend` bind mount.

If you explicitly set `KINDLE_OUTPUT_PATH=/app/data/kindle-display.png`, make sure the backend data directory is writable by UID/GID `10001`:

```bash
sudo chown -R 10001:10001 /opt/bpstracker/data/backend
docker compose up -d --force-recreate backend
```

If rendering fails, the backend logs now include `Failed to generate Kindle display PNG` with the underlying error.

### JSON API does not return values

Check whether the JSON API is enabled in Setup.

Then test:

```bash
curl http://<server-ip>:5173/api/current-values
```

### Air sensor values are stale

The air sensor is intentionally polled only every 180 seconds after successful reads.

If the sensor is offline, BPSTracker keeps the last valid values.

---

## Running on Raspberry Pi

### Raspberry Pi Zero 2

The Pi Zero 2 can potentially run BPSTracker, but it is not ideal.

Limitations:

- only 512 MB RAM
- PostgreSQL can be memory-heavy
- Docker builds are slow
- npm builds should be avoided

Recommended:

- use 64-bit Raspberry Pi OS
- enable at least 1 GB swap
- avoid building images on the Pi
- keep retention short
- use reasonable polling intervals
- disable unused optional features

Check architecture:

```bash
uname -m
```

Recommended output:

```text
aarch64
```

### Raspberry Pi 3/4/5

A Raspberry Pi 3 or newer is recommended for continuous operation.

A Raspberry Pi 4 or 5 provides a much better experience.

---

---

## Prebuilt Docker images

BPSTracker can be built automatically by GitHub Actions for multiple architectures and published to GitHub Container Registry.

The repository includes the workflow:

```text
.github/workflows/docker-images.yml
```

It builds:

```text
ghcr.io/syschelle/bpstracker-backend:latest
ghcr.io/syschelle/bpstracker-frontend:latest
```

Supported platforms:

```text
linux/amd64
linux/arm64
```

This is useful for Raspberry Pi systems or small servers because they no longer need to build Python or frontend images locally.

To deploy using prebuilt images:

```bash
cd /opt/bpstracker
git pull
bash ./deploy-images.sh
```

`deploy-images.sh` asks for the script language and for the image tag (`v0.9.36` or `latest`). For unattended image deployments:

```bash
bash ./deploy-images.sh --regular --tag v0.9.36 --language en
bash ./deploy-images.sh --zero2w --latest --language de
```

See also:

```text
docs/ghcr-images.md
```

## Security notes

BPSTracker is intended for local network use.

Recommendations:

- do not expose the application directly to the internet
- keep the backend private inside Docker
- create the initial admin only through the install screen on first start
- use strong admin and optional viewer passwords
- enable admin 2FA
- keep the default HttpOnly cookie auth mode; do not reintroduce browser localStorage token storage
- set `AUTH_COOKIE_SECURE=true` when the app is served exclusively through HTTPS
- access remotely only through VPN or another trusted private network
- enable optional APIs only when they are needed
- configure Shelly and Luftdaten hosts as LAN hosts/IPs only; public, loopback and metadata IPs are rejected
- failed login and 2FA verification attempts are rate-limited in-process
- keep container hardening enabled: non-root backend/frontend images, read-only filesystems, dropped Linux capabilities and `no-new-privileges`
- leave the backend and database ports unexposed; route browser traffic through the nginx same-origin `/api/` proxy

Authentication uses an HttpOnly `bpstracker_access_token` cookie by default. The frontend no longer stores the JWT in `localStorage`; stale pre-v0.7.3 `bpstracker-token` values are cleared by the UI. Cross-origin development setups must configure explicit `FRONTEND_ORIGIN` values because credentialed wildcard CORS is intentionally disabled.

The Kindle display image and JSON API are designed for simple local access and should not be exposed publicly. Kindle `refresh` and `meta` endpoints require an authenticated admin session.

Legacy SHA-256 password verification and clear-text TOTP secret migration remain only for the v0.7 migration window. Operators should ensure all users log in once so password hashes are upgraded to Argon2id and should re-create 2FA if they still depend on an old clear-text TOTP value; both compatibility paths are scheduled for removal in a later security release.

---

## Project structure

Typical structure:

```text
bpstracker/
├── backend/
│   └── app/
│       ├── main.py
│       ├── kindle_display.py
│       ├── routers/
│       ├── models.py
│       ├── schemas.py
│       └── ...
├── frontend/
│   ├── src/
│   ├── public/
│   ├── dist/
│   └── nginx.conf
├── scripts/
├── docker-compose.yml
├── deploy.sh
├── .env.example
├── README.md
└── LICENSE
```

---

## Development notes

The frontend is a React/Vite application.

The backend is a FastAPI application.

For local development, run the services separately or through Docker Compose.

The production deployment uses the built frontend `dist` and nginx.

---

## License

This project is licensed under the **Apache License, Version 2.0**.

You may obtain a copy of the license at:

```text
https://www.apache.org/licenses/LICENSE-2.0
```

Unless required by applicable law or agreed to in writing, software distributed under the Apache License, Version 2.0 is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

---

## Disclaimer

BPSTracker is a private monitoring tool for local energy visualization. It is not a certified metering system and should not be used for billing, legal metering, or safety-critical decisions.


<!-- Fix simulation banner rendering by keeping App as the default React export. -->


<!-- Fix: battery analysis toggle is persisted correctly in finance settings. -->


In simulation mode, configured devices are also simulated according to their purpose. You can create planned Shelly devices before they physically exist and assign purposes such as `Solar/feed-in` or `Home/grid import`.


<!-- UI: grid import history color has stronger contrast in dark theme. -->


<!-- UI: The language setup panel was removed because language is now a browser cookie preference. -->


<!-- UI: History colors: solar green, grid import blue, grid export red. -->


<!-- UI: Home import value color: negative red, zero green, positive default text color. -->


<!-- UI: Fix dark mode color override for negative home import values. -->


<!-- UI: Language setup panel restored because Kindle display uses the saved UI language. -->


<!-- UI: Public dashboard hides device status and latest measurements. -->


<!-- UI: Public dashboard includes current air sensor values when configured. -->


<!-- UI: The web interface displays the current BPSTracker version from frontend/package.json. -->


<!-- Version: The displayed app version is maintained in `frontend/package.json`. -->


<!-- API: Removed public device status and latest measurement endpoints; public dashboard only uses aggregate summary and air sensor values. -->


### v0.7.4 frontend healthcheck hotfix

The frontend container uses the unprivileged nginx image and listens on container port `8080`. The host-facing URL stays unchanged, for example `http://<server-ip>:5173`, because Docker maps `${FRONTEND_PORT:-5173}` to container port `8080`.

After upgrading from a pre-v0.7.3 image, recreate the frontend container instead of only restarting it. Otherwise an old image/container may still listen on port `80` while the hardened compose file maps to `8080`:

```bash
docker compose up -d --build --force-recreate frontend
docker compose ps
curl -fsS "http://127.0.0.1:${FRONTEND_PORT:-5173}/health"
```

v0.7.5 restores an explicit HTTP healthcheck against the hardened internal nginx port `8080`, so the container status verifies the actual served `/health` endpoint.


### v0.7.5 frontend port mapping fix

This release makes the confirmed v0.7.3/v0.7.4 deployment fix explicit in both compose files and deployment scripts: the host port stays configurable via `${FRONTEND_PORT:-5173}`, but it must map to the frontend container's internal nginx port `8080`.

Correct mapping:

```yaml
ports:
  - "${FRONTEND_PORT:-5173}:8080"
```

Incorrect old mapping:

```yaml
ports:
  - "${FRONTEND_PORT:-5173}:80"
```

The frontend healthcheck now checks `http://127.0.0.1:8080/health` inside the container. `deploy-images.sh` recreates containers with `--force-recreate --remove-orphans` so old `5173:80` mappings are removed during image deployments.

Upgrade check on the server:

```bash
docker compose ps
docker port bpstracker-frontend
curl -fsS "http://127.0.0.1:${FRONTEND_PORT:-5173}/health"
```

Expected port output contains `8080/tcp -> 0.0.0.0:5173`, not `80/tcp -> 0.0.0.0:5173`.


### v0.7.8 dashboard device measurements cleanup

v0.7.8 merges the separate device status and latest measurements panels into one compact dashboard table. The table initially reduced the view to one row per device and hid optional columns such as channel, phase, voltage and current unless at least one configured device or latest measurement actually contained that value.

### v0.7.10 device-configured dashboard measurement filtering

v0.7.10 keeps the merged dashboard device/measurement table but filters displayed measurement rows according to each Shelly device setup. If a device is configured for a specific channel, only that channel is shown and counted in current dashboard values. Shelly 3EM Gen1 devices without a configured channel continue to show L1, L2, L3 and Total; configured Gen1 phase channels show only the selected phase and suppress the unconfigured device-wide total row.

### v0.7.9 multi-row dashboard measurements fix

v0.7.9 keeps the merged dashboard table but restores one latest measurement row per device/source/channel/phase. Multi-phase Shelly devices such as Shelly 3EM Gen1 therefore show L1, L2, L3 and Total again, while optional columns like Channel remain hidden when they are not meaningful for the displayed data.

### v0.7.6 dashboard balances and Shelly auto-detection fix

v0.7.6 fixes two regressions after fresh installations and recent hardening work. Dashboard day/total energy and cost balances now include Shelly grid energy counter rows while a device is still in automatic purpose mode. Successful Shelly auto-detection also persists the detected device type so newly added or successfully polled devices do not remain configured as `auto`.

### v0.7.12 header achievement badge tooltip

v0.7.12 keeps the dashboard achievement in the header compact: only the badge icon is shown. The localized achievement text is now exposed as the hover tooltip and accessibility label, so German and English users see the text according to the active language selection without the header growing wider.

### v0.7.11 achievement progression update

v0.7.11 refreshes the dashboard achievement flow. A new GoLive badge is unlocked after the system summary loads successfully, while the first solar badge is only unlocked after the configured balcony PV system has actually produced solar energy (`solar_total_kwh > 0`). Savings-based achievements continue up to 120 currency units; later progress achievements now use the configured investment amortization percentage at 25%, 50%, 75% and 100% instead of raw saved money. The English first-solar text now matches the German "electricity empire" wording more closely.


### v0.7.13 README architecture diagram

v0.7.13 adds the BPSTracker system setup schematic to the README files. The diagram documents the typical deployment with separate grid import and balcony solar measurement, Shelly-based metering, the BPSTracker server stack, browser/mobile clients, the public dashboard and Kindle display retrieval via `display.png`.

### v0.8.7 screenshot asset cleanup

v0.8.7 refreshes the documentation asset set by converting `docs/images/setup-overview.jpeg` to `docs/images/setup-overview.png` and updating the README/help references accordingly. This keeps the screenshot assets consistent in PNG format for the current project snapshot.

### v0.8.8 dashboard and history performance

v0.8.8 reduces dashboard and history loading latency. The dashboard now applies `summary`, `latest` and `devices` responses independently so the metric cards can render as soon as the summary request finishes instead of waiting for all dashboard requests. The `/api/measurements/summary` hot path no longer materializes completed daily summaries on every request; hourly poller maintenance keeps daily totals materialized. The history view now uses a combined `/api/measurements/history/series` endpoint so chart points and totals are produced from one raw history query, and the frontend sends smaller range-aware row limits for 24h, 7d and 30d views. Additional measurement indexes improve latest-value and history-window lookups on upgraded installations.

### v0.9.0 frontend healthcheck and documentation refresh

v0.9.0 updates both Compose files to use a robust frontend healthcheck that verifies the generated nginx assets and the running nginx process instead of relying on an internal `wget` request. This avoids false `unhealthy` states on minimal nginx/Alpine images and Raspberry Pi deployments where the page is served correctly but the old healthcheck cannot connect to `127.0.0.1:8080`.

The release also refreshes the History screenshot in `docs/images/history-simulation.png` and bumps the application version to `v0.9.0` across backend, frontend and built frontend assets.

### v0.9.1 history screenshot correction

v0.9.1 replaces `docs/images/history-simulation.png` with the corrected current History screenshot while keeping the v0.9.0 healthcheck and performance changes unchanged. The application version is bumped to `v0.9.1` across backend, frontend and built frontend assets.

### v0.9.2 configurable simulation solar output

v0.9.2 adds a configurable maximum solar output to the simulation settings. The configured watt value caps the generated PV curve and is used consistently by dashboard summary values, latest measurements, history charts, history totals and the current-values JSON API. This makes the simulation match the real-world output limit of the planned or actual solar installation instead of always using the former fixed 800 W demo profile.

### v0.9.3 configurable simulation baseload

v0.9.3 adds configurable day and night baseload values to the simulation settings. The configured watt values define the continuous household consumption floor for daytime and nighttime, while existing simulated consumption peaks such as fridge cycles, coffee-machine, stove/cooking and washing-machine events remain active and are added on top. The baseload values are used consistently by dashboard summary values, latest measurements, history charts, history totals, Kindle display and the current-values JSON API.

### v0.9.4 dashboard home import layout

v0.9.4 updates the dashboard **House import / Hausbezug** card. The card now shows the current total household consumption estimate first, followed by the signed grid import/export value and the current solar power. The former separator line above the solar value was removed, and the three displayed values now use the same font size for a more consistent layout.

### v0.9.5 dashboard Home Import layout refinement

v0.9.5 refines the Dashboard `Home Import` card after the v0.9.4 total-consumption addition. The value rows are now more compact so labels and values stay close together, the compact network/solar share line is restored at the bottom of the card, and positive grid import values use the same blue as the History grid import series. Negative grid values remain red for export.

### v0.9.6 aligned home import dashboard values

v0.9.6 refines the Dashboard Home Import card layout. The value column for total consumption, grid import/export and solar is now left-aligned across rows while keeping the compact spacing introduced in v0.9.5. Positive grid import remains blue, grid export remains red and solar remains green.

### v0.9.8 Raspberry Pi Zero 2 W low-resource mode

v0.9.8 adds an optional Raspberry Pi Zero 2 W mode through `docker-compose.zero2w.yml`. When enabled, BPSTracker keeps and serves only the latest 24 hours of raw/live measurements while preserving permanent daily aggregates for total energy balance, total cost balance and amortization. The backend clamps history/export requests to the configured live window, the History view hides longer ranges in 24h mode, and retention settings show the effective low-resource limit.

### v0.9.8 complete Raspberry Pi Zero 2 W compose file

v0.9.8 replaces the previous partial Zero 2 W override with a complete standalone `docker-compose.zero2w.yml`. The file now contains the full Postgres, backend and frontend stack, enables the 24h low-resource live-data mode, applies conservative Postgres memory settings, keeps reduced tmpfs sizes and limits container log growth for small SD-card installations. Start Zero 2 W deployments with `docker compose -f docker-compose.zero2w.yml up -d`.

### v0.9.9 generated install secrets and install profile selection

v0.9.9 changes the install scripts so production `.env` files are generated from secure random values instead of being copied from `.env.example`. The installer now asks for the desired profile, either regular or Raspberry Pi Zero 2 W / low-resource mode. It validates existing `.env` files, replaces missing or unsafe placeholder secrets, keeps `POSTGRES_PASSWORD` and `DATABASE_URL` consistent, and prints a newly generated `SECRET_KEY` once at the end of the install output so operators can store it safely.

### v0.9.10 install ownership proof and image tag selection

v0.9.10 hardens first-run setup by requiring the `SECRET_KEY` from `.env` in the web install form before the initial admin user can be created. The key is used only as an ownership proof, is not written from the browser to `.env`, and is not stored in the browser. The install form also lets operators choose the UI language before creating the first admin; the selected language is saved immediately as the server-side UI language and is then used by setup, help and Kindle-related formatting.

`deploy-images.sh` now asks interactively whether the fixed release tag or `latest` should be used, and it also supports `--latest`, `--tag TAG`, `--regular` and `--zero2w` for unattended installs.

### v0.9.11 CodeQL security hardening

v0.9.11 addresses the six GitHub CodeQL security findings reported against the v0.9.x line. Backup download and delete now resolve files through a strict allowlist of generated backup filenames and reject traversal, symlinks and non-regular files before any file operation. The deprecated plain SHA-256 password compatibility verifier has been removed; old accounts that still use early test-build SHA-256 hashes must be reset with the admin reset scripts. Kindle display generation metadata no longer exposes raw exception messages to API responses; detailed errors remain in server logs only.

### v0.9.12 Kindle air sensor cache alignment

v0.9.12 keeps the Kindle display air sensor values aligned with the dashboard. Kindle PNG generation now refreshes the shared air-sensor cache through the same throttled helper used by the dashboard before rendering, and the setup preview explicitly triggers an authenticated Kindle refresh before reloading the image. The public Kindle image endpoint also regenerates stale images before returning them.

### v0.9.13 dark theme home import color fix

v0.9.13 fixes the Home Import dashboard card in dark theme so zero current home/grid import values remain green and are not overridden by generic dark-theme value colors. The grid import color mapping remains red for export and blue for positive grid import.

### v0.9.15 installer language selection and compact header branding

v0.9.15 combines the unreleased v0.9.14 installer-language work with a compact header branding update. `deploy.sh` and `deploy-images.sh` can now run their prompts and status output in German or English, support `--language de|en` for unattended deployments, and write `BPSTRACKER_LANGUAGE` plus `BPSTRACKER_DEFAULT_LANGUAGE` into `.env`. The frontend runtime config receives this default language so the first-run web setup screen opens in the language selected during deployment. The backend install status and UI settings defaults also honor the configured deployment language until an admin saves a different UI language.

The authenticated header now shows only `BPSTracker` and the app version. The localized application subtitle is no longer displayed next to the version; it is exposed as a hover tooltip and accessibility label on the `BPSTracker` wordmark, matching the compact tooltip behavior used for achievements.

### v0.9.16 faster History rendering on low-resource systems

v0.9.16 optimizes the History endpoint for Raspberry Pi and other low-resource deployments. History queries now load only the columns needed for charting and energy totals instead of full measurement ORM rows with `raw_json` payloads, and rows without power or energy counter values are skipped before Python aggregation. In Raspberry Pi Zero 2 W mode, the 24h chart uses 5-minute buckets, reducing the response from up to about 1440 chart points to about 288 points while preserving the 24h trend and totals.

### v0.9.17 locale files with language metadata

v0.9.17 moves the React UI translations out of `App.tsx` into per-language locale files under `frontend/src/i18n/locales/`. Each locale now carries metadata such as language code, native name, browser locale and help document. The frontend derives the available language list from those files, so the setup language dropdown, header language switcher and help-document lookup no longer hard-code only German and English. A new `npm run check-i18n` build step validates that every locale provides the same translation keys as the English baseline. Backend language validation now accepts future locale-style language codes while the frontend falls back safely when an unavailable language is configured.

### v0.9.18 interactive deploy prompt fix

v0.9.18 fixes the interactive prompts in `deploy.sh` and `deploy-images.sh`. Language, installation profile and Docker image tag questions are now written to the terminal directly instead of being captured by command substitution, so interactive installs no longer appear to hang while waiting for hidden input. The default release image tag used by the deploy scripts was also updated to `v0.9.18`.


### v0.9.19 History watt precision

v0.9.19 makes History power values easier to read by formatting watt values with one decimal place and an explicit `W` unit on the chart axis and tooltip. The chart data is rounded consistently before rendering. New Shelly measurements stored by the poller now normalize `power_w` and `total_power_w` to two decimal places before writing to the database, reducing unnecessary floating-point noise while preserving sufficient precision for dashboard and history calculations.

### v0.9.20 session loading and 7-day login cookie

v0.9.20 prevents the brief login-screen flicker during app startup. The frontend now keeps a neutral loading state visible until the install/session check has finished, so users with a valid HttpOnly session cookie go directly to the dashboard without seeing the login form first. Successful logins now stay active for 7 days by default via `ACCESS_TOKEN_EXPIRE_MINUTES=10080`; the token is still stored only in an HttpOnly cookie and is not readable by JavaScript.

### v0.9.21 dark theme solar value color fix

v0.9.21 fixes the dark theme color override in the Home Import dashboard card. The Solar value now stays green in dark mode, matching the light theme and the existing solar color used in charts and legends.

### v0.9.22 simulation household profile tuning

v0.9.22 moderately refines the household simulation profile. The configurable day and night baseload values remain unchanged, while the generated load curve now includes a more realistic refrigerator cycle, short coffee-machine cup peaks, an evening stove/cooking session and the existing washing-machine style appliance peaks. The simulated PV output remains configurable separately through the maximum solar output setting.

### v0.9.23 dashboard balance labels and shares

v0.9.23 adds grid-import and solar percentages to the Daily Balance and Total Balance dashboard cards. The former Import label in these balance cards now reads Grid import, while the current power card is shortened from Home import to Current.

### v0.9.24 dashboard balance color refinement

v0.9.24 refines the dashboard balance rows. The percentage shares in the daily and total balance cards are shown at half the value font size, grid import uses the same blue as the current/history grid import display, solar values use the solar green, and export values use the history export red.

### v0.9.25 dashboard balance value styling

v0.9.25 corrects the dashboard balance value styling. The kWh values in Daily balance and Total balance keep their normal size, only the percentage share is rendered smaller, and the value colors are applied consistently: grid import blue, solar green and grid export red in both light and dark themes.

### v0.9.26 dashboard balance percentage order

v0.9.26 refines the dashboard Daily balance and Total balance display. Percentage shares are shown before the kWh values and use 75% of the kWh font size, while the kWh values keep their normal size and existing color coding.


### v0.9.27 dashboard balance value separator

v0.9.27 refines the dashboard balance formatting. In the daily and total balance cards, percentage shares are now separated from kWh values with the same ` · ` separator style used by the current power card, while keeping the percentage text at 75% of the kWh value size.

### v0.9.28 dashboard balance label cleanup

v0.9.28 refines the dashboard daily and total balance cards. The balance rows now use explicit labels with colons (`Total consumption:`, `Grid import:`, `Solar:` and `Export:`), while the total-consumption separator line has been removed for a cleaner compact layout.

### v0.9.29 dashboard typography and device status heading

v0.9.29 aligns the dashboard balance row typography with the compact current-values card while keeping balance percentages at 75% of the kWh value size. The dashboard device table heading is shortened from “Device status & latest measurements” to “Device status”.

### v0.9.30 dashboard heading styling

v0.9.30 aligns the Dashboard card and device-section headings with the compact current-values card. Dashboard headings now use the BPSTracker brand green, bold weight and consistent sizing. The battery dashboard heading was renamed from Battery analysis to Battery amortization.

### v0.9.31 dashboard current heading style fix

v0.9.31 includes the nested `Aktuell`/`Current` dashboard card title in the unified dashboard heading style so it matches the other dashboard section headings: bold, compact and BPSTracker green.

### v0.9.32 cost balance value colors

v0.9.32 aligns the Daily cost balance and Total cost balance value colors with the Dashboard energy balance semantics. Consumption cost values now use the same blue as grid import, while savings values use the same green as solar values, including in dark mode.

### v0.9.33 dashboard air sensor and label color alignment

v0.9.33 aligns the air sensor label/value presentation with the compact dashboard value rows and synchronizes dashboard value-label colors across the current, balance and cost cards. The air sensor header and public air sensor widget now show explicit labels for temperature, humidity, PM10 and PM2.5 values while keeping the existing compact layout.

### v0.9.34 compact air sensor values

v0.9.34 makes the dashboard air data display more compact. Temperature and humidity now show only their icon and value, while particle values show the icon plus the numeric particle size (`10` or `2.5`) and the measured value. Full labels remain available through hover/tooltips and accessibility labels.

### v0.9.35 mobile view refresh

v0.9.35 refreshes the mobile dashboard presentation and the documentation mobile screenshot. Mobile dashboard cards now use the same current typography and compact value alignment as the desktop dashboard, including balance rows, cost rows, the current power card and responsive air sensor values.

### v0.9.36 Dashboard and Kindle daily cost alignment

v0.9.36 aligns the daily cost values shown on the dashboard and the Kindle display. Dashboard day totals now use the configured UI timezone instead of UTC midnight, and the Kindle renderer applies the same configured-device channel filtering as the dashboard summary for daily energy and current power values. This prevents daily import costs from diverging between the dashboard and Kindle image on timezone-offset deployments or channel-filtered Shelly setups.

