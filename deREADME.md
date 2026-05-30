# BPSTracker

**BPSTracker** ist eine selbst gehostete Webanwendung zur Überwachung eines Balkon-Photovoltaik-Systems. Die Anwendung erfasst Leistungs- und Energiewerte von Shelly-Geräten, bereitet diese in einem responsiven Dashboard auf und stellt optionale Zusatzfunktionen wie Kindle-Anzeige, Luftdaten, JSON-API, Simulation, verschlüsselte Backups und Akku-Amortisationsberechnung bereit.

Das Projekt ist für den lokalen Betrieb im Heimnetz gedacht. Backend und Datenbank laufen innerhalb des Docker-Netzwerks; nach außen wird nur die Weboberfläche bereitgestellt.

---

## Inhaltsverzeichnis

- [Screenshots](#screenshots)
- [Hauptfunktionen](#hauptfunktionen)
- [Architektur](#architektur)
- [Unterstützte Geräte](#unterstützte-geräte)
- [Installation mit Docker](#installation-mit-docker)
- [Betrieb mit vorgebauten Docker-Images](#betrieb-mit-vorgebauten-docker-images)
- [Setup in der Weboberfläche](#setup-in-der-weboberfläche)
- [Dashboard](#dashboard)
- [Historie](#historie)
- [Simulation](#simulation)
- [Kindle-Display](#kindle-display)
- [JSON-API](#json-api)
- [Luftdatensensor](#luftdatensensor)
- [Akku-Amortisationsberechnung](#akku-amortisationsberechnung)
- [Verschlüsselte Backups](#verschlüsselte-backups)
- [Werte zurücksetzen](#werte-zurücksetzen)
- [Datenaufbewahrung](#datenaufbewahrung)
- [Raspberry Pi Hinweise](#raspberry-pi-hinweise)
- [Updates](#updates)
- [Sicherheit](#sicherheit)
- [Lizenz](#lizenz)

---

## Screenshots

### Dashboard-Übersicht

![BPSTracker dashboard overview](docs/images/dashboard-overview.png)

### Historie mit Simulationsmodus

![BPSTracker history with simulation mode](docs/images/history-simulation.png)

### Setup-Übersicht

![BPSTracker setup overview](docs/images/setup-overview.jpeg)


---

## Hauptfunktionen

- Überwachung von Balkon-PV-Erzeugung und Haus-/Netzbezug
- Unterstützung für Shelly-Geräte
- responsives Web-Dashboard
- helle und dunkle Darstellung mit gespeicherter Theme-Auswahl
- Tagesbilanz und Gesamtbilanz
- Kosten- und Einsparungsübersicht
- Amortisationsanzeige für das Balkonkraftwerk
- optionale Akku-Amortisationsberechnung
- optionale Simulation für Demo- und Testbetrieb
- optionale Luftdatenanzeige im Header
- optionale Kindle-kompatible PNG-Anzeige
- optionale JSON-API für aktuelle Werte
- verschlüsselte Admin-Backups
- Reset-Funktion für Messwerte
- Docker-Deployment
- Multi-Arch-Docker-Images für `linux/amd64` und `linux/arm64`

---

## Architektur

BPSTracker besteht aus mehreren Komponenten:

```text
frontend/   React/Vite-Weboberfläche
backend/    FastAPI-Backend
postgres    PostgreSQL-Datenbank
nginx       statische Auslieferung und API-Proxy im Frontend-Container
```

Typischer Betrieb:

```text
Browser / Kindle / API-Client
        |
        v
Frontend / nginx :5173
        |
        v
Backend / FastAPI :8000
        |
        v
PostgreSQL
```

---

## Unterstützte Geräte

BPSTracker ist auf Shelly-basierte Messungen ausgelegt.

Typische Geräte:

- Shelly 3EM Gen1
- Shelly Pro 3EM Gen2
- Shelly 2PM Gen4
- generische Shelly-NG-Geräte

Die Anwendung unterscheidet zwischen Netz-/Hausbezug und Solarerzeugung. Für die Solarproduktion wird typischerweise ein Shelly-Schalt-/Messkanal am Wechselrichter oder der PV-Einspeisung verwendet.

---

## Installation mit Docker

Repository klonen:

```bash
git clone https://github.com/syschelle/bpstracker.git
cd bpstracker
```

Konfiguration anlegen:

```bash
cp .env.example .env
```

Danach `.env` anpassen.

Start mit lokalem Build:

```bash
bash ./deploy.sh
```

Die Weboberfläche ist anschließend erreichbar unter:

```text
http://<ip-adresse>:5173
```

---

## Betrieb mit vorgebauten Docker-Images

BPSTracker kann über GitHub Actions als Multi-Arch-Docker-Image gebaut werden.

Verwendete Images:

```text
ghcr.io/syschelle/bpstracker-backend:latest
ghcr.io/syschelle/bpstracker-frontend:latest
```

Unterstützte Plattformen:

```text
linux/amd64
linux/arm64
```

Betrieb mit vorgebauten Images:

```bash
docker compose -f docker-compose.images.yml pull
docker compose -f docker-compose.images.yml up -d
```

Oder mit Script:

```bash
bash ./deploy-images.sh
```

Für einen festen Release-Stand kann in `.env` gesetzt werden:

```env
BPSTRACKER_IMAGE_TAG=v0.3.1
```

Dann wird genau dieser Release verwendet.

---

## Setup in der Weboberfläche

Im Setup können unter anderem konfiguriert werden:

- Sprache
- Zeitzone
- GitHub-Repository-Link
- Kindle-Display
- Simulation
- JSON-API
- Admin-/Viewer-Zugang
- Finanzwerte
- Akku-Amortisationsberechnung
- verschlüsselte Backups
- Werte-Reset
- Datenaufbewahrung
- Luftdatensensor
- Geräte

Die Zeitzone wird als IANA-Zeitzone gespeichert, zum Beispiel:

```text
Europe/Berlin
```

Sommerzeit und Winterzeit werden dadurch automatisch berücksichtigt.

---

## Dashboard

Das Dashboard zeigt unter anderem:

- aktuellen Netz-/Hausbezug
- aktuelle Solarproduktion
- Tagesbilanz
- Gesamtbilanz
- Tageskostenbilanz
- Gesamtkostenbilanz
- Amortisation
- Akku-Bewertung, falls aktiviert
- Gerätestatus
- aktuelle Messwerte
- Luftdaten im Header, falls aktiviert
- Simulationshinweis, falls der Demo-Modus aktiv ist

Bei aktivierter Simulation wird im Header angezeigt:

```text
Du bist in der Matrix 😎 Simulation läuft!
```

---

## Historie

Die Historie zeigt Messwerte als Zeitreihe.

Die Darstellung enthält getrennte Kurven für:

- Solarproduktion
- Netzbezug
- Einspeisung

Die Werte sind farblich getrennt, damit sie leichter unterschieden werden können. Einspeisung wird positiv dargestellt, um sie im Diagramm besser mit Solar und Netzbezug vergleichen zu können.

---

## Simulation

Der Simulationsmodus kann im Setup aktiviert werden.

Er simuliert:

- eine 800-Watt-Balkon-PV-Anlage
- einen typischen 2-Personen-Haushalt
- realistische Tagesverläufe
- Morgen- und Abendspitzen
- Haushaltsgeräte-Spikes
- Grundlast
- Wolken- und Erzeugungsschwankungen
- saisonale Solarvariation

Die Simulation betrifft:

- Dashboard
- Historie
- aktuelle Messwerte
- JSON-API
- Kindle-Display
- Luftdatenanzeige

Die Simulation schreibt keine produktiven Messwerte in die Messwerttabellen. Wenn die Simulation deaktiviert wird, verschwinden die simulierten Werte wieder aus der Anzeige.

---

## Kindle-Display

BPSTracker kann ein Kindle-kompatibles PNG erzeugen:

```text
http://<ip-adresse>:5173/api/kindle/display.png
```

Die Datei wird im Hintergrund erzeugt und kann regelmäßig vom Kindle abgeholt werden.

Angezeigt werden unter anderem:

- Uhrzeit
- Datum
- Temperatur
- Luftfeuchte
- PM10
- PM2.5
- Hausbezug
- Solarwert
- Tageskosten und Einsparung

Das Kindle-Display berücksichtigt die eingestellte Sprache:

Deutsch:

```text
30.05.2026
14:05
Aktualisiert: 14:05:12
```

Englisch:

```text
05/30/2026
2:05 PM
Updated: 2:05:12 PM
```

---

## JSON-API

Die JSON-API kann im Setup aktiviert oder deaktiviert werden.

Sie stellt aktuelle Werte bereit, zum Beispiel:

- aktuelle Solarproduktion
- aktueller Netzbezug
- aktueller Gesamtverbrauch
- Tagesproduktion Solar
- Tagesbezug
- Tageseinspeisung
- Gesamtproduktion
- Gesamteinspeisung

Die API ist nützlich für externe Systeme, Smart-Home-Integrationen oder eigene Skripte.

---

## Luftdatensensor

Optional kann ein Luftdatensensor aus dem Sensor.Community-Umfeld eingebunden werden.

Projektlink:

```text
https://sensor.community/en/sensors/dnms/
```

Der Sensor liefert Daten über:

```text
http://<sensor-ip>/data.json
```

BPSTracker verwendet daraus:

- Temperatur
- Luftfeuchte
- PM10
- PM2.5

Der Sensor wird nicht historisch gespeichert. Die Werte werden nur aktuell im Webinterface und optional im Kindle-Display angezeigt.

Wenn der Sensor nicht antwortet, blockiert er die App nicht. Es werden Timeouts verwendet, und bei Fehlern bleibt der letzte bekannte Wert erhalten.

---

## Akku-Amortisationsberechnung

Die Akku-Amortisationsberechnung ist optional und kann im Setup aktiviert oder deaktiviert werden.

Im Setup können eingetragen werden:

```text
Akku-Kosten
Akku-Kapazität in kWh
```

Die Berechnung basiert auf dem Überschuss, der sonst eingespeist würde.

Wichtig: Einspeisung wird mit `0` vergütet. Der mögliche Nutzen eines Akkus entsteht daher nur dadurch, dass eingespeister Überschuss später Netzbezug ersetzen könnte.

Annahmen:

- Einspeisung wird nicht vergütet
- Akku-Wirkungsgrad: 90 %
- maximal ein Lade-/Entladezyklus pro Tag
- nutzbarer Tagesüberschuss wird durch die Akku-Kapazität begrenzt
- wenn das Balkonkraftwerk noch nicht amortisiert ist, wird die offene Rest-Amortisation mit berücksichtigt

Die Anzeige unterscheidet zwischen:

- reiner Akku-Amortisation
- offenen Restkosten des Balkonkraftwerks
- kombinierter Betrachtung aus Restkosten + Akku-Kosten

Wenn die Akku-Berechnung deaktiviert ist, bleiben die eingegebenen Werte gespeichert, werden aber nicht im Dashboard berechnet oder angezeigt.

---

## Verschlüsselte Backups

Im Setup können verschlüsselte Backups erstellt werden.

Ablauf:

1. Passwort eingeben
2. Passwort wiederholen
3. verschlüsseltes Backup erstellen
4. Backup herunterladen

Das Passwort wird nicht gespeichert.

Nicht gespeichert in:

- Datenbank
- `.env`
- App-Einstellungen
- Backup-Metadaten

Backup-Dateien haben die Endung:

```text
.tar.gz.bpsenc
```

Ein Backup enthält unter anderem:

```text
backup/
├── manifest.json
├── database.sql
├── environment.env
└── backend_data/
```

Wichtig: Ohne Passwort kann das Backup nicht wiederhergestellt werden.

---

## Werte zurücksetzen

Admins können Messwerte im Setup zurücksetzen.

Dazu muss der Text eingegeben werden:

```text
reset
```

Gelöscht werden:

- Messwerte
- Tagesaggregate
- flüchtige Luftdaten-Caches
- flüchtige Simulations-Caches
- generierte Kindle-Cache-Dateien

Erhalten bleiben:

- Benutzer
- Passwörter und 2FA
- Geräte
- Setup-Einstellungen
- Finanzwerte
- Sprache und Zeitzone

Diese Aktion kann nicht rückgängig gemacht werden.

---

## Datenaufbewahrung

Rohmesswerte können zeitlich begrenzt gespeichert werden.

Tagesaggregate bleiben dauerhaft erhalten und werden für Langzeitwerte, Gesamtbilanz und Amortisation verwendet.

Dadurch kann die Datenbank klein bleiben, ohne Langzeit-Auswertungen zu verlieren.

---

## Raspberry Pi Hinweise

Für Raspberry Pi 3/4/5 oder Raspberry Pi Zero 2 wird ein 64-Bit-Betriebssystem empfohlen.

Prüfen:

```bash
uname -m
```

Empfohlen:

```text
aarch64
```

Dann können die `linux/arm64` Docker-Images verwendet werden.

---

## Updates

Mit vorgebauten Images:

```bash
cd /opt/bpstracker
git pull
docker compose -f docker-compose.images.yml pull
docker compose -f docker-compose.images.yml up -d
```

Oder:

```bash
bash ./deploy-images.sh
```

Mit lokalem Build:

```bash
cd /opt/bpstracker
git pull
bash ./deploy.sh
```

---

## Sicherheit

Empfehlungen:

- `.env` niemals in GitHub hochladen
- starke Passwörter verwenden
- 2FA aktivieren
- regelmäßige verschlüsselte Backups erstellen
- Backup-Passwort sicher verwahren
- öffentliche Exponierung nur über Reverse Proxy mit HTTPS
- GitHub Container Registry Images bevorzugt mit festen Release-Tags verwenden

---

## Lizenz

Dieses Projekt steht unter der **Apache License Version 2.0**.

Siehe:

```text
LICENSE
```

---

## Repository

```text
https://github.com/syschelle/bpstracker
```
