# BPSTracker

**BPSTracker** is a self-hosted monitoring dashboard for a **Balkon-Photovoltaik-System (BPS)** / balcony photovoltaic system. It collects live power and energy data from configured Shelly devices, displays daily and total energy balances, calculates costs and savings, and provides a Kindle-friendly PNG status display for e-ink dashboards.

The project is designed to run locally in Docker, for example on a small home server or Raspberry Pi, with the backend protected inside the Docker network and only the frontend exposed to the local network.

<img width="1495" height="957" alt="image" src="https://github.com/user-attachments/assets/51082c3f-2476-4e76-a8b9-50b8d83808be" />

---

## Table of contents

- [Overview](#overview)
- [Main features](#main-features)
- [Architecture](#architecture)
- [Screens and UI](#screens-and-ui)
- [Supported data sources](#supported-data-sources)
- [Authentication and users](#authentication-and-users)
- [Kindle display API](#kindle-display-api)
- [Air quality sensor support](#air-quality-sensor-support)
- [Data retention](#data-retention)
- [Requirements](#requirements)
- [Installation](#installation)
- [Deployment](#deployment)
- [Updating](#updating)
- [Configuration](#configuration)
- [Ports and networking](#ports-and-networking)
- [Backup and restore](#backup-and-restore)
- [Troubleshooting](#troubleshooting)
- [Running on Raspberry Pi](#running-on-raspberry-pi)
- [Security notes](#security-notes)
- [Project structure](#project-structure)
- [License](#license)

---

## Overview

BPSTracker is intended for local energy monitoring of a small photovoltaic setup, especially balcony solar installations. The application focuses on a compact, understandable dashboard instead of a complex enterprise energy management system.

It can show:

- current house/grid import power
- current solar feed-in power
- daily solar production
- daily grid import
- daily grid export
- total solar production
- total grid import/export
- consumption costs
- solar savings
- amortization progress
- device status
- current measurements
- optional air sensor values
- a generated Kindle PNG display

The application uses Docker Compose and stores persistent data below:

```text
/opt/bpstracker
```

---

## Main features

### Dashboard

The dashboard provides a clear view of the current energy situation:

- **House import / Hausbezug**
  - current grid import or export
  - current solar power
  - solar/grid share visualization

- **Daily energy balance**
  - solar
  - grid import
  - grid export

- **Total energy balance**
  - total solar energy
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

### History

The history view displays measured power values over selectable periods.

The chart is aggregated into time buckets so that multi-channel Shelly devices do not create broken or misleading vertical spikes.

Supported ranges include:

- 24 hours
- 7 days
- 30 days

### Setup

The setup area allows administrators to configure:

- web interface language
- timezone
- currency
- kWh price
- investment costs
- raw data retention period
- Shelly devices
- polling intervals
- optional air quality sensor
- admin and viewer credentials

### Multilingual UI

The web interface supports:

- German
- English

The selected language is stored in the application settings.

### Theme support

The frontend supports:

- light theme
- dark theme

The selected theme is stored locally in the browser.

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

Daylight saving time and winter time are handled automatically by the timezone database.

---

## Architecture

BPSTracker consists of three main services:

```text
Frontend  ->  nginx + static React build
Backend   ->  FastAPI / Python
Database  ->  PostgreSQL
```

The backend is not exposed directly to the outside. The browser accesses the backend only through the frontend/nginx proxy.

Typical access flow:

```text
Browser / Kindle
      |
      | HTTP
      v
Frontend container :5173
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

## Screens and UI

BPSTracker is optimized for desktop and mobile browsers.

The mobile header is designed to avoid crowding:

- menu button on the left
- page title and user role in the center
- theme toggle on the right
- air sensor values in a separate responsive row

The navigation menu is available through a hamburger button and is hidden when not needed.

---

## Supported data sources

BPSTracker currently focuses on Shelly devices.

Supported or intended Shelly device types include:

- Shelly 3EM Gen1
- Shelly Pro 3EM / NG 3EM
- Shelly 2PM Gen4
- generic Shelly NG devices

Each device can be configured in the setup area with:

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

## Authentication and users

BPSTracker always requires authentication.

There are exactly two user roles:

### Admin

The admin can:

- open the dashboard
- open the history view
- open setup
- configure devices
- configure users
- configure financial settings
- configure retention
- configure language/timezone
- manage 2FA

The admin can enable TOTP-based two-factor authentication.

### Viewer

The viewer can:

- open the dashboard
- open the history view

The viewer cannot open setup and cannot manage 2FA.

### Password storage

Passwords are stored as secure hashes using Argon2id.

Usernames are stored as usernames and are freely configurable. They are not email addresses.

---

## Kindle display API

BPSTracker can generate a Kindle-friendly PNG image for e-ink displays.

The fixed endpoint is:

```text
http://<ip-address>:5173/api/kindle/display.png
```

Example:

```text
http://192.168.178.211:5173/api/kindle/display.png
```

The URL is intentionally fixed and does not require query parameters.

### Kindle image behavior

The PNG is generated by the backend using Python and Pillow.

Properties:

- format: PNG
- size: 600 × 800 px
- grayscale-friendly design
- generated inside the container
- no external rendering tools required at runtime
- generated once per minute
- not generated exactly at second `00`
- last valid PNG is kept if rendering fails

The displayed clock is shifted by one minute to better match Kindle cron refresh timing.

### Kindle debug endpoint

A metadata endpoint is available:

```text
http://<ip-address>:5173/api/kindle/meta
```

It can be used to verify the active renderer version and generation status.

### Example Kindle cron usage

A Kindle can fetch the image with a command like:

```bash
wget -O /mnt/us/bpstracker.png "http://192.168.178.211:5173/api/kindle/display.png"
```

Many older Kindle devices have problems with modern HTTPS/TLS, so using plain HTTP inside the local network is recommended.

---

## Air quality sensor support

BPSTracker can optionally read values from a Luftdaten / Sensor.Community-style sensor endpoint:

```text
http://<sensor-ip>/data.json
```

More information about the supported sensor project can be found here:

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

The air sensor values are not stored historically. They are shown only in the UI header and Kindle display.

### Air sensor polling behavior

The sensor is polled conservatively:

- normal successful polling interval: 180 seconds
- retry interval after failure: 30 seconds
- short HTTP timeouts
- last valid values are kept if the sensor is temporarily unavailable

This prevents a slow or unreachable sensor from blocking the BPSTracker application.

---

## Data retention

To prevent the database from growing indefinitely, BPSTracker supports raw data retention.

Raw measurements are deleted after the configured number of days.

Daily aggregates are kept permanently and are used for:

- total energy balance
- total cost balance
- amortization
- long-term totals

This keeps the database small while preserving important long-term values.

---

## Requirements

### Recommended system

- Linux host
- Docker
- Docker Compose plugin
- persistent storage below `/opt/bpstracker`

Recommended hardware:

- Raspberry Pi 3, 4, or 5
- small home server
- mini PC
- NAS with Docker support

### Minimum system

A Raspberry Pi Zero 2 may work, but it is close to the limit because it has only 512 MB RAM.

For low-memory systems:

- avoid building Docker images on the device
- use prebuilt images if possible
- enable swap
- keep polling intervals reasonable
- keep raw retention short

---

## Installation

Clone the repository:

```bash
git clone https://github.com/<your-user>/bpstracker.git
cd bpstracker
```

Create or review the environment file:

```bash
cp .env.example .env
nano .env
```

Deploy the application:

```bash
bash ./deploy.sh
```

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

## Updating

If you installed the project from GitHub:

```bash
cd /opt/bpstracker
git pull
bash ./deploy.sh
```

The deployment script should rebuild or restart the required services.

After updating, reload the browser page.

For major frontend changes, a hard reload may be required:

```text
Ctrl + F5
```

On mobile browsers, clearing the site cache may sometimes be necessary.

---

## Configuration

Most settings are configured in the web interface under **Setup**.

### Language

Supported languages:

- German
- English

### Timezone

Use a valid IANA timezone, for example:

```text
Europe/Berlin
```

This automatically handles daylight saving time and winter time.

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

### Devices

Each Shelly device can be configured with:

- host/IP
- type
- channel
- polling interval
- optional credentials

### Users

The setup area allows changing:

- admin username
- admin password
- viewer username
- viewer password

The viewer has no setup access.

---

## Ports and networking

Default external port:

```text
5173
```

The browser and Kindle should use:

```text
http://<server-ip>:5173
```

Backend API calls are proxied through the frontend container.

Important endpoints:

```text
/api/auth/login
/api/measurements/summary
/api/settings/air-sensor/current
/api/kindle/display.png
/api/kindle/meta
```

The backend itself should not be published to the host network.

---

## Backup and restore

The most important data is stored in the Docker volumes and persistent data directory below:

```text
/opt/bpstracker
```

Recommended backup items:

- PostgreSQL data volume
- `.env`
- application data directory
- optional generated Kindle PNG cache

Example backup approach:

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

Check the fixed URL:

```text
http://<server-ip>:5173/api/kindle/display.png
```

Check metadata:

```text
http://<server-ip>:5173/api/kindle/meta
```

The PNG is generated once per minute and may not change instantly.

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

## Security notes

BPSTracker is intended for local network use.

Recommendations:

- do not expose the application directly to the internet
- keep the backend private inside Docker
- use strong admin and viewer passwords
- enable admin 2FA
- keep the host system updated
- restrict access to the local network or VPN

The Kindle endpoint is designed for simple local access and should not be exposed publicly.

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
└── README.md
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
