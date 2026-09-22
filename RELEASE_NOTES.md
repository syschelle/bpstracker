# BPSTracker v0.9.57 – Performance-Optimierung

## Änderungen

- Bereits gespeicherte Tageszusammenfassungen werden nicht mehr automatisch neu berechnet. Nach einem Ausfall werden ausschließlich fehlende abgeschlossene Tage nachgetragen.
- Auch beim Aufräumen alter Rohmessungen bleiben bestehende Tageszusammenfassungen unangetastet.
- Dashboard, öffentliche JSON-API und Kindle verwenden für die aktuelle Tagesbilanz nur den ersten und letzten gültigen Zählerstand je Gerät, Kanal und Phase; Roh-JSON-Daten müssen dazu nicht mehr massenhaft geladen werden.
- Die stündliche Datenbankwartung läuft außerhalb des Hauptthreads und wird zusätzlich beim UTC-Tageswechsel ausgeführt.
- `/api/current-values` blockiert den Hauptthread nicht mehr mit synchronen Datenbankabfragen.
- Die bisherigen Berechnungsformeln, die getrennte Netzeinspeisung, Shelly-Zuordnungen, History, Gesamtbilanz und Gesamtkostenbilanz bleiben unverändert.
- Keine Datenbankmigration und kein Zurücksetzen vorhandener Messwerte erforderlich.

## Tests

- Neue Regressionstests für Ergebnisgleichheit mit den bisherigen Energiezählerberechnungen, unterschiedliche Kanäle/Phasen, Nullwerte, Zähler-Reset sowie unveränderliche abgeschlossene Tage.
- Nach der Bereitstellung auf dem Raspberry Pi sollten CPU-Auslastung und Antwortzeit von `/health` und der Anmeldung überprüft werden.

## Aktualisierung (Docker-Images)

Sobald GitHub Actions die Images für dieses Tag veröffentlicht hat:

```bash
cd /opt/bpstracker
bash ./update.sh --tag v0.9.57
```

Vor produktiven Updates wird ein reguläres Datenbank-Backup empfohlen.
