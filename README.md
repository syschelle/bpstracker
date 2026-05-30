# BPSTracker

BPSTracker ist eine lokale Docker-Webapp zur Überwachung von Solarproduktion, Hausanschluss und Einspeisesteckdose mit Shelly-Geräten.

Der vorgesehene Installationspfad ist:

```bash
/opt/bpstracker
```

Alle Projektdateien, die `.env`-Konfiguration sowie die persistenten App-Daten liegen innerhalb dieses Verzeichnisses. Die PostgreSQL-Datenbank wird nicht in einem anonymen Docker-Volume abgelegt, sondern unter:

```bash
/opt/bpstracker/data/postgres
```

## Enthalten

- App-Name: `BPSTracker`
- Docker-Compose-Projekt: `bpstracker`
- Container:
  - `bpstracker-postgres`
  - `bpstracker-backend`
  - `bpstracker-frontend`
- Images:
  - `bpstracker/backend:local`
  - `bpstracker/frontend:local`
- Backend: Python 3.12, FastAPI, SQLAlchemy, PostgreSQL
- Frontend: React, TypeScript, Vite, Recharts
- Shelly-Unterstützung:
  - Shelly 3EM Gen1 über Legacy HTTP API (`/status`, `/emeter/{id}`)
  - Shelly Gen2+/Gen4 über RPC (`/rpc/Shelly.GetStatus`, `Switch.GetStatus`, `EM.GetStatus`, `EMData.GetStatus`)
  - Shelly 2PM Gen4 über `switch:0`/`switch:1` bzw. `Switch.GetStatus?id=...`
- Setup-Reiter für IP/Hostname, Shelly-Benutzername, Shelly-Passwort, Gerätetyp und Kanal
- Setup-Reiter für kWh-Preis und Investitionskosten
- Periodisches Polling und Speicherung in PostgreSQL
- Immer aktive Authentifizierung: genau zwei Rollen `admin` und `viewer`
- Frei wählbare Benutzernamen und Passwörter im Setup-Reiter
- Viewer sieht Dashboard/Historie, aber kein Setup
- TOTP-2FA optional nur für den Admin; TOTP-Secret verschlüsselt, Recovery-Codes gehasht
- Dashboard mit Verbrauchskosten, Solar-Einsparung und Amortisations-/Breakeven-Anzeige
- Historie und CSV-Export

## Deployment immer nach `/opt/bpstracker`

BPSTracker ist so vorbereitet, dass das Deploy-Skript **immer** das Zielverzeichnis `/opt/bpstracker` verwendet. Es ist egal, aus welchem temporären Ordner du das entpackte ZIP startest: der Code wird nach `/opt/bpstracker` kopiert und Docker Compose wird anschließend aus genau diesem Verzeichnis gestartet.

```bash
unzip BPSTracker-internal-backend.zip
cd bpstracker
./deploy.sh
```

Alternativ:

```bash
./scripts/deploy-opt.sh
```

Das Skript macht automatisch:

```bash
sudo mkdir -p /opt/bpstracker
sudo chown -R $USER:$USER /opt/bpstracker
rsync ... /opt/bpstracker/
cd /opt/bpstracker
docker compose -p bpstracker build --progress=plain
docker compose -p bpstracker down --remove-orphans
docker compose -p bpstracker up -d --remove-orphans
```

Falls `/opt/bpstracker/.env` noch nicht existiert, wird sie aus `.env.example` erstellt. Danach bitte einmal prüfen und Standardpasswörter ändern:

```bash
cd /opt/bpstracker
nano .env
./deploy.sh
```

Danach öffnen:

- Direkt auf dem Docker-Host: http://localhost:5173
- Von einem anderen Gerät im Netzwerk: http://<server-ip>:5173

Das Backend wird **nicht** nach außen veröffentlicht. API-Aufrufe laufen ausschließlich über den Frontend-nginx-Proxy unter `/api/...` und werden intern im Docker-Netz an `bpstracker-backend:8000` weitergeleitet.

## Wichtige `.env`-Werte

Vor dem ersten produktiven Start mindestens ändern:

```bash
SECRET_KEY=...
INITIAL_ADMIN_USERNAME=...
INITIAL_ADMIN_PASSWORD=...
INITIAL_VIEWER_USERNAME=...
INITIAL_VIEWER_PASSWORD=...
POSTGRES_PASSWORD=...
DATABASE_URL=postgresql+psycopg://bpstracker:<POSTGRES_PASSWORD>@postgres:5432/bpstracker
```

Falls du den öffentlichen Web-Port ändern möchtest:

```bash
FRONTEND_PORT=5173
```

`BACKEND_PORT` und `POSTGRES_PORT` werden bewusst nicht mehr verwendet, weil Backend und PostgreSQL nicht auf Host-Ports veröffentlicht werden sollen. Lasse die API-Erkennung auf Same-Origin:

```bash
VITE_API_BASE_URL=same-origin
FRONTEND_ORIGIN=*
```

Der Browser ruft API-Endpunkte nur relativ über den Frontend-Port auf, z. B. `/api/auth/login`. nginx im Frontend-Container proxyt diese Requests intern an `http://backend:8000`.

## Zugriff aus dem Netzwerk

Wenn du BPSTracker von deinem PC/Tablet über die Server-IP öffnest, darf im Browser weder `localhost:8000` noch `<server-ip>:8000` als API-Ziel erscheinen. Der Backend-Port ist nicht veröffentlicht.

Richtig ist:

```text
http://192.168.1.50:5173
```

API-Aufrufe erscheinen im Browser-Netzwerk-Tab als relative Pfade, zum Beispiel:

```text
/api/auth/login
/api/measurements/summary
```

Der Frontend-Container leitet diese intern an den Backend-Container weiter. Nach einem Update bitte den Browser-Cache leeren oder hart neu laden, damit die neue Frontend-Datei aktiv wird.


## Frontend-Build ohne npm im Docker-Build

Diese Version enthält bereits ein gebautes Frontend unter `frontend/dist`. Das Docker-Image für das Frontend basiert nur noch auf nginx und führt **kein** `npm install` und **kein** `npm ci` mehr aus. Dadurch hängt das Deployment nicht mehr an `registry.npmjs.org`, DNS, IPv6 oder npm-Timeouts des Docker-Hosts.

Der Docker-Build des Frontends macht nur noch:

```Dockerfile
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY dist /usr/share/nginx/html
```

Die API-Adresse wird zur Container-Laufzeit über `/config.js` gesetzt. Standard ist `same-origin`, also relative API-Aufrufe über den Frontend-Port und interner nginx-Proxy zum Backend.

Falls du später das Frontend selbst änderst, musst du lokal im Ordner `frontend` einmal neu bauen und danach deployen:

```bash
cd /opt/bpstracker/frontend
npm ci
npm run build
cd /opt/bpstracker
./deploy.sh
```

Für den normalen Betrieb und Updates aus diesem ZIP ist kein npm-Zugriff im Docker-Build nötig.

## Betrieb

Im Zielverzeichnis `/opt/bpstracker`:

```bash
make up-detached
make logs
make ps
make down
```

Ohne Makefile direkt:

```bash
docker compose -p bpstracker up -d --build
docker compose -p bpstracker logs -f --tail=200
docker compose -p bpstracker ps
docker compose -p bpstracker down
```

## Datenhaltung

Persistente Daten liegen fest unter `/opt/bpstracker`:

```bash
/opt/bpstracker/data/postgres
/opt/bpstracker/data/backend
/opt/bpstracker/backups
```

Auch in `docker-compose.yml` sind diese Pfade als absolute Bind-Mounts eingetragen. Dadurch landen die Daten nicht versehentlich in einem anderen Verzeichnis, selbst wenn Compose einmal von außen aufgerufen wird.

## Netzwerk-Sicherheit

Nur der Frontend-Container veröffentlicht einen Host-Port:

```yaml
frontend:
  ports:
    - "${FRONTEND_PORT:-5173}:80"
```

Backend und PostgreSQL haben nur `expose`, aber keine `ports`. Das bedeutet: Sie sind für andere Container im Compose-Netz erreichbar, aber nicht direkt vom Host/LAN aus.

Prüfen kannst du das mit:

```bash
cd /opt/bpstracker
./scripts/check-exposure.sh
```

Oder manuell:

```bash
docker compose -p bpstracker ps
```

In der Spalte `PORTS` darf nur beim Frontend eine Host-Zuordnung wie `0.0.0.0:5173->80/tcp` stehen. Beim Backend darf **kein** `0.0.0.0:8000->8000/tcp` erscheinen.

Ein Datenbank-Backup erzeugst du mit:

```bash
make backup-db
```

## Lokaler Ablauf

1. Beim ersten Start werden die Rollen `admin` und `viewer` erstellt, wenn sie noch nicht existieren.
2. Login im Frontend ist immer erforderlich.
3. Als Admin im Setup-Reiter die Benutzernamen und Passwörter für Admin und Viewer frei vergeben.
4. Optional im Reiter „Admin 2FA“ einen TOTP-Secret erzeugen, aktivieren und die Recovery-Codes sicher ablegen.
5. Im Setup-Reiter unter „Finanzwerte“ den kWh-Preis und die Investitionskosten eintragen.
6. Im Setup-Reiter Shelly-Geräte anlegen.
7. Verbindung testen.
8. Polling startet automatisch für aktive Geräte.
9. Dashboard und Historie zeigen gespeicherte Messwerte. Der Viewer hat keinen Zugriff auf Setup oder 2FA.


## Benutzer und Berechtigungen

BPSTracker verwendet keine E-Mail-Adressen für den Login. Es gibt genau zwei Rollen:

- `admin`: darf Dashboard, Historie, Setup, Shelly-Konfiguration, Benutzerzugänge und Admin-2FA verwalten.
- `viewer`: darf Dashboard und Historie sehen, hat aber keinen Zugriff auf Setup und keine 2FA-Verwaltung.

Die initialen Benutzernamen und Passwörter kommen aus `.env`. Danach kannst du sie im Setup-Reiter ändern. Beim Passwortfeld gilt: leer lassen bedeutet „Passwort unverändert lassen“.

Speicherlogik der Zugangsdaten:

- Benutzernamen: Klartext, frei wählbar und eindeutig, damit Login, Anzeige und Änderung im Setup sauber funktionieren.
- Passwörter: Argon2id-Hash, niemals Klartext. Ältere bcrypt-Hashes aus Testständen bleiben loginfähig und werden beim erfolgreichen Login automatisch auf Argon2id aktualisiert.
- Admin-2FA-Secret: verschlüsselt in der Datenbank.
- Admin-Recovery-Codes: nur gehasht gespeichert und jeweils einmal verwendbar.

## Finanzwerte und Amortisation

Im Setup-Reiter kann der Admin eintragen:

- kWh-Preis in Euro
- Investitionskosten in Euro

Das Dashboard berechnet daraus:

- Verbrauchskosten heute = Netzbezug heute × kWh-Preis
- Einsparung heute = Solarproduktion an Shelly-2PM-/PM-Kanälen × kWh-Preis
- Einsparung gesamt = gespeicherte Solarproduktion seit Beginn der Messung × kWh-Preis
- Breakeven-Fortschritt = Einsparung gesamt / Investitionskosten
- voraussichtlicher Breakeven auf Basis der aktuellen Tageseinsparung

Hinweis: Die Einsparung ist eine Näherung anhand der an der Einspeisesteckdose gemessenen Solarproduktion. Eine exakte Eigenverbrauchsquote benötigt zusätzliche Bilanzlogik und ausreichend historische Messwerte.

## Shelly-Konfiguration

### Shelly 3EM Gen1

Gerätetyp: `shelly_3em_gen1` oder `auto`  
Host/IP: z. B. `192.168.178.50`

Das Backend liest `/status` und normalisiert `emeters[*]` sowie `total_power`.

### Shelly 2PM Gen4

Gerätetyp: `shelly_2pm_gen4` oder `auto`  
Host/IP: z. B. `192.168.178.51`  
Kanal: `0`, `1` oder leer für beide Kanäle

Das Backend liest per RPC `Shelly.GetStatus` und optional `Switch.GetStatus?id=0/1`.

## Entwicklung

```bash
make test
make logs
make down
```

Backend-Tests liegen in `backend/tests`.

## GitHub

Dieses Projekt ist Git-fähig. Initial lokal:

```bash
cd /opt/bpstracker
git init
git add .
git commit -m "Initial BPSTracker"
git branch -M main
git remote add origin git@github.com:<user>/<repo>.git
git push -u origin main
```

Ein GitHub-Actions-Workflow ist unter `.github/workflows/ci.yml` enthalten.

## Sicherheitshinweise

- Benutzerpasswörter werden mit Argon2id gehasht.
- Benutzernamen werden bewusst nicht gehasht, sondern eindeutig im Klartext gespeichert.
- Shelly-Passwörter und Admin-TOTP-Secrets werden verschlüsselt in der Datenbank abgelegt. Der Schlüssel wird aus `SECRET_KEY` abgeleitet.
- Admin-Recovery-Codes werden nur gehasht gespeichert und sind einmalig nutzbar.
- `SECRET_KEY` nach produktiver Inbetriebnahme nicht mehr ändern, sonst können verschlüsselte Shelly-Passwörter und TOTP-Secrets nicht mehr entschlüsselt werden.
- Secrets gehören in `.env`, nicht ins Git-Repository.
- Für produktive Nutzung HTTPS/Reverse Proxy ergänzen.
- Dieses MVP nutzt Bearer-JWT im Frontend. Für exponierte Installationen sollten SameSite/HttpOnly-Cookies, HSTS und zusätzliche Rate-Limits ergänzt werden.

### Netzwerk/API-Hinweis

Ab dieser Version ruft das Frontend das Backend standardmäßig über denselben Host und denselben Frontend-Port auf:

```text
http://<server-ip>:5173/api/...
```

Der Frontend-nginx leitet `/api/` intern an den Backend-Container `backend:8000` weiter. Der Browser muss also **nicht** mehr direkt auf `:8000` zugreifen. Das verhindert Fehler wie `localhost:8000`, `:8000/api/...` oder CORS-Probleme im LAN.


## No-NPM-Docker-Build

Diese Version ist für Systeme gedacht, bei denen `npm install` oder `npm ci` im Docker-Build hängen bleibt.

Der Frontend-Container wird ausschließlich aus einem bereits vorhandenen `frontend/dist` gebaut. Docker verwendet:

```text
frontend/Dockerfile.static
```

und dieses Image basiert nur auf nginx. Es wird **kein Node-Image** verwendet und im Docker-Build wird **kein npm install** und **kein npm ci** ausgeführt.

Prüfen:

```bash
cd /opt/bpstracker
./scripts/verify-no-npm-build.sh
```

Wenn Docker trotzdem einen npm-Schritt zeigt, läuft nicht diese Version oder Docker baut aus einem alten Verzeichnis. Dann bitte prüfen:

```bash
cd /opt/bpstracker
grep -R "npm install\|npm ci\|node:" -n frontend/Dockerfile* docker-compose.yml
```

In `frontend/Dockerfile*` und `docker-compose.yml` darf kein npm-/node-Buildschritt stehen.

## 502 Bad Gateway prüfen

Wenn der Browser bei `/api/...` einen `502 Bad Gateway` meldet, läuft nginx im Frontend, erreicht aber das Backend im Docker-Netz nicht. Prüfe dann:

```bash
cd /opt/bpstracker
./scripts/diagnose-502.sh
```

In dieser Version startet das Frontend erst, wenn das Backend den Healthcheck `/health` erfolgreich beantwortet. Außerdem enthält das Backend Best-Effort-Migrationen für ältere BPSTracker-Testdatenbanken, weil ältere Stände noch keine Alembic-Migrationen hatten.


## Mehrsprachigkeit

BPSTracker steht in Deutsch und Englisch zur Verfügung. Deutsch ist die Standardsprache.

Die Sprache wird vom Admin im Setup-Reiter unter **Sprache** eingestellt und in der PostgreSQL-Tabelle `app_settings` gespeichert. Viewer übernehmen die gespeicherte Sprache nach dem Login automatisch.

## Name

BPS steht in dieser App für **Balkon-Photovoltaik-System**.

## Viewer-Zugang reparieren

Falls nach einem Upgrade aus alten Testversionen der Viewer-Login nicht funktioniert, kann der Viewer-Zugang direkt im laufenden System neu gesetzt werden:

```bash
cd /opt/bpstracker
./scripts/reset-viewer-password.sh viewer 'NeuesPasswort123!'
```

Das Skript aktiviert genau einen Viewer, deaktiviert doppelte alte Viewer-Datensätze und entfernt 2FA/Recovery-Codes beim Viewer.

### Benutzer-Diagnose und Passwort-Reset

Aktive Benutzer anzeigen:

```bash
cd /opt/bpstracker
./scripts/list-users.sh
```

Viewer-Passwort direkt in der Datenbank neu setzen und sofort verifizieren:

```bash
cd /opt/bpstracker
./scripts/reset-viewer-password.sh viewer 'MeinNeuesPasswort123!'
```

Admin oder Viewer gezielt setzen:

```bash
cd /opt/bpstracker
./scripts/reset-role-password.sh viewer viewer 'MeinNeuesPasswort123!'
./scripts/reset-role-password.sh admin admin 'MeinAdminPasswort123!'
```

## Datenaufbewahrung / Datenbankgröße

BPSTracker speichert Rohmesswerte nur für die im Setup konfigurierte Anzahl von Tagen, standardmäßig 30 Tage. Vor dem Löschen alter Rohdaten werden abgeschlossene Tage in `daily_energy_summary` zusammengefasst. Diese Tagesaggregate bleiben dauerhaft erhalten und werden für Gesamtbilanz, Einsparung und Amortisation genutzt.

Prüfen der aktuellen Größe:

```bash
cd /opt/bpstracker
./scripts/retention-status.sh
```

Das Backend führt die Wartung automatisch etwa stündlich aus. Zusätzlich werden abgeschlossene Tage beim Laden der Dashboard-Zusammenfassung materialisiert, damit Gesamtwerte erhalten bleiben.


## Luftdatensensor

Im Setup kann optional ein Luftdatensensor aktiviert werden, der unter `http://<ip>/data.json` die Luftdaten-Firmware-JSON liefert. BPSTracker liest daraus nur die aktuellen Werte aus und zeigt sie kompakt im Header an:

- Temperatur
- Luftfeuchte
- PM10 (SDS_P1)
- PM2.5 (SDS_P2)

Diese Daten werden nicht historisch gespeichert und landen nicht in der PostgreSQL-Messwerttabelle.

### Luftdatensensor: Timeout und letzter Wert

Der optionale Luftdatensensor wird mit kurzen HTTP-Timeouts abgefragt, damit ein verzögerter oder nicht erreichbarer Sensor die BPSTracker-Oberfläche nicht blockiert. Wenn der Sensor keine neuen Werte liefert oder nicht erreichbar ist, zeigt die App weiterhin den zuletzt erfolgreich gelesenen Wert aus dem Cache an. Es wird keine Historie der Luftdaten gespeichert, nur der letzte Wert.

### Luftdatensensor Polling

Der Luftdatensensor wird nach einer erfolgreichen Abfrage höchstens alle 180 Sekunden erneut direkt abgefragt. Das passt zum Messintervall vieler Luftdaten-Sensoren. Das Frontend darf häufiger nach dem aktuellen Status fragen; das Backend liefert dann den zuletzt erfolgreich gelesenen Cache zurück. Wenn eine Abfrage fehlschlägt, wird ein schnelleres Retry-Intervall von 30 Sekunden verwendet. Die letzten gültigen Werte bleiben bei Fehlern oder leeren Antworten erhalten.

## Kindle-Display PNG

BPSTracker erzeugt serverseitig ein Kindle-geeignetes PNG mit Uhrzeit, Temperatur,
Luftfeuchte, PM10, PM2.5 und Hausbezug. Das Bild wird im Backend-Container mit
Python/Pillow erzeugt und einmal pro Minute aktualisiert, bewusst nicht bei
Sekunde 0, sondern ab Sekunde 10. Der Kindle kann es über das Frontend abrufen:

```text
http://<server-ip>:5173/api/kindle/display.png
```

Diese URL ist bewusst fest. Für Kindle-Cron-Jobs keine Query-Parameter anhängen. Die API und der nginx-Proxy senden No-Cache-Header, damit immer das zuletzt erzeugte PNG unter genau diesem Pfad ausgeliefert wird.

Debug/Status:

```text
http://<server-ip>:5173/api/kindle/meta
```

Das Backend bleibt weiterhin nur im internen Docker-Netzwerk erreichbar; der
Abruf erfolgt über den nginx-Proxy des Frontends.

## Kindle-Display

Das Kindle-PNG wird serverseitig erzeugt und bleibt dauerhaft unter dieser festen URL erreichbar:

```text
http://<ipadresse>:5173/api/kindle/display.png
```

Die angezeigte Uhrzeit wird bewusst um eine Minute nach vorne gesetzt. Der Zeitwechsel wird per Datum/Zeit-Arithmetik berechnet, sodass auch Stunden- und Tageswechsel korrekt funktionieren.

Die Icons im Kindle-PNG sind lokal im Backend unter `backend/app/assets/icons/` gebündelte Open-Source-SVGs aus dem Lucide Icon Set. Sie werden nicht zur Laufzeit aus dem Internet geladen.

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

See also:

```text
docs/ghcr-images.md
```
