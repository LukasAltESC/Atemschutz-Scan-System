# Projektbeschreibung

## Ziel des Projekts

Das **Atemschutz-Scan-System** ist ein kompaktes Raspberry-Pi-System zur schnellen Erfassung von Atemschutzmaterial per Scanner. Aus den erfassten Daten erzeugt das System je nach Arbeitsmodus entweder einen **Verwendungsnachweis** oder einen **Lieferschein**.

Das Projekt ist für den praktischen Einsatz mit Scannern, GPIO-Tastern, Status-LEDs und einem USB-Thermodrucker ausgelegt. Zusätzlich steht eine Weboberfläche zur Bedienung, Kontrolle und Datenpflege zur Verfügung.

## Hauptfunktionen

### Verwendungsnachweis

Für einen druckbereiten Verwendungsnachweis müssen diese Pflichtgruppen erfasst sein:

- Atem-Druckluftflasche
- Vollmaske
- Pressluftatmer
- Lungenautomat

Optional:

- Mitteldruckverlängerung

Besonderheiten:

- Atem-Druckluftflaschen sind über **Inventarnummer** oder **LF-Scan** scanbar.
- Vollmasken und Lungenautomaten sind zusätzlich über **Fabriknummer** scanbar.
- Die **Gerätenummer/Seriennummer** wird angezeigt, aber nicht als primäre Scan-Kennung verwendet.
- Sobald alle Pflichtgruppen vorhanden sind, meldet das System den Zustand als **druckbereit**.

### Lieferschein

Im Lieferscheinmodus können beliebig viele Geräte pro Gruppe erfasst werden. Die Ausgabe wird nach Gruppen und Gerätetypen sortiert dargestellt.

## Systemaufbau

Das Projekt besteht aus fünf funktionalen Blöcken:

### 1. Webanwendung

`app.py` stellt die Flask-Weboberfläche bereit. Dort werden Metadaten, Scanstatus, Druck-/Exportfunktionen, Datenbankansicht und Systeminformationen zusammengeführt.

### 2. Ablauf- und Zustandslogik

`state_manager.py` ist das Herzstück der Anwendung. Hier werden Modi, Scan-Zustand, Prüfregeln, Ereignisprotokoll, Payload-Erzeugung und Nachbearbeitung nach Druck oder Export verwaltet.

### 3. Materialdatenbank

`database.py` verwaltet eine SQLite-Datenbank und synchronisiert sie mit der Datei `data/Database.CSV`. Dadurch ist sowohl eine einfache Bearbeitung per CSV als auch ein performanter Lookup während des Scanbetriebs möglich.

### 4. Hardware-Anbindung

- `scanner_input.py` liest Scanner über `/dev/input/event*`
- `gpio_controller.py` verarbeitet Taster und Status-LEDs
- `thermal_printer.py` sendet ESC/POS-Daten an den Bondrucker

### 5. Ausgabe- und Layoutsystem

- `ticket_renderer.py` baut Druck- und Textausgabe aus dem Payload auf
- `export_manager.py` erzeugt TXT- und CSV-Dateien
- `data/output_layout.json` steuert Materialfelder in Web/Export
- `data/print_layout.json` steuert Bondruck-Layout, Labels und Druckstil

## Datenfluss

1. Ein Scanner liefert einen Code.
2. Der Code wird normalisiert und gegen Funktionskarten sowie Materialdatenbank geprüft.
3. `state_manager.py` entscheidet abhängig vom Modus, wohin der Scan übernommen wird.
4. Die Weboberfläche zeigt den aktuellen Zustand sofort an.
5. Bei Druck oder Export wird ein strukturierter Payload erzeugt.
6. Dieser Payload wird entweder:
   - über den Thermodrucker ausgegeben oder
   - als TXT/CSV-Datei gespeichert.

## Weboberfläche

### Erfassungsseite

- Personen- und Einsatzdaten
- aktueller Scanstatus
- Materialansicht abhängig vom Modus
- Einsatz- und Übungsdetails
- Aktionen wie Druck, Export, Reset, Moduswechsel

### System-/Scannerseite

- Scannerpfade
- erkannte Eingabegeräte
- geladene Konfigurationsdateien
- Vorschau auf Funktionskarten, Checkliste und Layouts
- Reload-Funktion für JSON-Konfigurationen

### Datenbankseite

- Materialdatenbank als Webansicht
- Datensätze anlegen, ändern, löschen
- CSV neu importieren

### Ausgabeseite

- zuletzt erzeugter Payload
- vorhandene TXT-/CSV-Dateien
- Funktion zum Löschen aller Exportdateien

## Technische Besonderheiten

- getrennte Logik für Verwendungsnachweis und Lieferschein
- automatische Rückkehr aus dem Lieferscheinmodus nach Inaktivität
- LED-Rückmeldung für Erfolg, Fehler und Betriebszustand
- Blocking-/Warning-System für Systemfehler und unplausible Systemzeit
- robuste Konfigurationsdateien im JSON-Format
- CSV-basierte Stammdatenpflege ohne Datenbankkenntnisse

## Wichtige Dateien

### Kernlogik

- `app.py`
- `state_manager.py`
- `database.py`
- `scanner_input.py`
- `gpio_controller.py`
- `thermal_printer.py`
- `ticket_renderer.py`
- `export_manager.py`

### Konfiguration und Daten

- `config.py`
- `data/Database.CSV`
- `data/function_cards.json`
- `data/detail_checklist.json`
- `data/output_layout.json`
- `data/print_layout.json`

## Einsatzbereich

Das Projekt ist für einen stabilen Offline-/Netzwerkbetrieb auf einem Raspberry Pi vorgesehen, auf dem Scanner, Taster, LEDs und Drucker direkt angeschlossen sind. Die Weboberfläche dient dabei als zentrale Bedien- und Wartungsoberfläche.
