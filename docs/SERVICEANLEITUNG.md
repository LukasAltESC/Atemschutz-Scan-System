# Serviceanleitung

## Zweck dieser Anleitung

Diese Anleitung richtet sich an Personen, die das System installieren, konfigurieren, warten oder an neue Hardware anpassen.

## Zielsystem

Empfohlen:

- Raspberry Pi Zero 2 W
- Raspberry Pi OS Lite
- 1 bis 2 Scanner als HID-Eingabegeräte
- USB-Thermodrucker
- Taster und LEDs an GPIO

## Installationsübersicht

Installiert wird das Projekt aus dem Repository nach:

```bash
/opt/atemschutz-scan-system
```

Der Quellcode kann zum Beispiel unter folgendem Arbeitsverzeichnis liegen:

```bash
/home/agw/src/atemschutz-scan-system
```

## Schritt-für-Schritt-Installation

### 1. SD-Karte vorbereiten

Im Raspberry Pi Imager:

- OS: **Raspberry Pi OS Lite**
- Gerät: **Pi Zero 2 W**
- Hostname setzen, zum Beispiel `atemschutzsystem`
- Benutzer anlegen, zum Beispiel `agw`
- WLAN konfigurieren
- SSH aktivieren

### 2. Per SSH verbinden

```bash
ssh agw@atemschutzsystem.local
```

Falls `.local` nicht funktioniert, stattdessen die IP-Adresse des Raspberry Pi verwenden.

### 3. System aktualisieren

```bash
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

### 4. Projekt klonen

```bash
sudo apt update
sudo apt install -y git
mkdir -p /home/agw/src
cd /home/agw/src
git clone https://github.com/LukasAltESC/atemschutz-scan-system.git atemschutz-scan-system
cd atemschutz-scan-system
chmod +x install.sh update.sh
```

### 5. Installation ausführen

```bash
sudo ./install.sh
```

Das Skript:

- installiert Systempakete
- kopiert das Projekt nach `/opt/atemschutz-scan-system`
- richtet Gruppenrechte für `input`, `gpio` und `lp` ein
- installiert die systemd-Service-Datei
- startet den Dienst

### 6. Hardware-Konfiguration anpassen

Die zentrale Konfigurationsdatei ist:

```bash
sudo nano /opt/atemschutz-scan-system/config.py
```

Dort werden unter anderem gepflegt:

- `SCANNER_DEVICE_PATHS`
- `GREEN_LED_PIN`
- `RED_LED_PIN`
- `PRINT_BUTTON_PIN`
- `RESET_BUTTON_PIN`
- `MODE_BUTTON_PIN`
- `SECRET_KEY`
- Zeitwerte und Blinkverhalten

Wichtig: Es werden **BCM/GPIO-Nummern** verwendet, nicht die physischen Pin-Nummern.

### 7. Scanner-Geräte ermitteln

```bash
python3 /opt/atemschutz-scan-system/tools/list_input_devices.py
```

Anschließend die passenden Geräte in `config.py` unter `SCANNER_DEVICE_PATHS` eintragen.

Empfehlung: Nach Möglichkeit **`/dev/input/by-id/...`** verwenden statt `eventX`.

### 8. Neustart

Nach Änderungen an Benutzergruppen oder Hardwarekonfiguration:

```bash
sudo reboot
```

### 9. GPIO testen

```bash
python3 /opt/atemschutz-scan-system/tools/test_gpio_io.py
```

Damit werden getestet:

- grüne LED
- rote LED
- Drucktaster
- Reset-Taster
- Modustaster

### 10. Dienst prüfen

```bash
sudo systemctl status atemschutz-scan-system.service
journalctl -u atemschutz-scan-system.service -n 100 -f
```

### 11. Weboberfläche öffnen

Nach der Installation stehen standardmaessig zwei Netzwege zur Verfuegung:

1. **WLAN-Access-Point**
   - SSID: `Atemschutz-Scan-System`
   - Passwort: `Atemschutz2026`
   - Webinterface: `http://192.168.50.1:5000`
   - SSH: `ssh agw@192.168.50.1`

2. **LAN / Ethernet**
   - DHCP bleibt aktiv
   - Webinterface: `http://<LAN-IP>:5000`
   - SSH: `ssh agw@<LAN-IP>`

Falls der Standard angepasst werden soll, koennen beim Installieren Umgebungsvariablen gesetzt werden, zum Beispiel:

```bash
sudo AP_SSID="Atemschutz-Scan-System" AP_PASSPHRASE="MeinSicheresPasswort" AP_IP_ADDRESS="192.168.60.1" ./install.sh
```

Wenn ein Handy oder Tablet den Hotspot bereits mit einer aelteren Konfiguration gespeichert hat, das Netzwerk auf dem Geraet einmal **vergessen/loeschen** und danach neu verbinden. Andernfalls melden manche Geraete trotz korrektem Passwort faelschlich „Passwort falsch“.

## Wartung und Service

### Dienstbefehle

Status prüfen:

```bash
sudo systemctl status atemschutz-scan-system.service
```

Dienst neu starten:

```bash
sudo systemctl restart atemschutz-scan-system.service
```

Dienst stoppen:

```bash
sudo systemctl stop atemschutz-scan-system.service
```

Live-Log ansehen:

```bash
journalctl -u atemschutz-scan-system.service -n 100 -f
```

### Datenbank pflegen

Die Stammdaten-CSV liegt unter:

```bash
/opt/atemschutz-scan-system/data/Database.CSV
```

Bearbeiten:

```bash
nano /opt/atemschutz-scan-system/data/Database.CSV
```

Danach in die SQLite-Datenbank importieren:

```bash
cd /opt/atemschutz-scan-system
python3 manage_db.py import-csv
sudo systemctl restart atemschutz-scan-system.service
```

### Exporte

TXT- und CSV-Exporte werden unter folgendem Verzeichnis abgelegt:

```bash
/opt/atemschutz-scan-system/data/exports
```

### Drucker testen

Gerät prüfen:

```bash
sudo python3 /opt/atemschutz-scan-system/tools/test_thermal_printer.py --probe
```

Testdruck ausführen:

```bash
sudo python3 /opt/atemschutz-scan-system/tools/test_thermal_printer.py
```

## Wo kann ich was anpassen?

### Allgemeine Projekt- und Hardware-Konfiguration

**Datei:** `config.py`

Hier werden gepflegt:

- Projektpfade
- Modusnamen
- Pflicht- und optionale Gruppen
- Scannerpfade
- GPIO-Pins
- Laufzeit- und Blinkzeiten
- Webserver-Port
- Standardwerte für Druck und Inaktivität
- `SECRET_KEY`

### Materialstammdaten

**Datei:** `data/Database.CSV`

Spalten:

- Gruppe
- Typ
- Inventarnummer
- Fabriknummer
- Gerätenummer
- LF-Scan
- Bemerkung

### Funktionskarten

**Datei:** `data/function_cards.json`

Beispiel:

```json
[
  {"code": "6600132315", "label": "Übungsgeräte"}
]
```

### Standard-Checkliste

**Datei:** `data/detail_checklist.json`

Beispiel:

```json
[
  "Übungsgerät",
  "Einsatz (Allgemein)"
]
```

### Materialausgabe in Website/TXT/CSV

**Datei:** `data/output_layout.json`

Beispiel:

```json
{
  "group_fields": {
    "Vollmaske": ["item_type", "inventarnummer", "fabriknummer", "bemerkung"]
  }
}
```

Mögliche Feldnamen:

- `item_type`
- `inventarnummer`
- `fabriknummer`
- `geraetenummer`
- `lf_scan`
- `bemerkung`

### Bondruck-Layout

**Datei:** `data/print_layout.json`

Hier können angepasst werden:

- Papierbreite
- Zeilenabstände
- Ausrichtung
- Textblöcke
- Feldlabels
- Gruppentitel
- Druckreihenfolge
- Nachlauf nach dem Druck

### Laufzeit-Einstellungen aus der Weboberfläche

**Datei:** `data/runtime_settings.json`

Diese Datei wird von der Anwendung automatisch geschrieben. Sie enthält die zuletzt gespeicherten Web-Einstellungen.

### HTML-Templates

- `templates/base.html` – Grundlayout
- `templates/index.html` – Erfassungsseite
- `templates/print_data.html` – Ausgabe-Seite
- `templates/scanner.html` – System-/Scannerseite
- `templates/database.html` – Datenbankseite

### CSS und Optik

- `static/style.css`

### Zentrale Code-Stellen

- `app.py` – Webrouten und Systemstart
- `state_manager.py` – Scanlogik, Modi, Payload-Erzeugung
- `database.py` – CSV/SQLite und Scan-Lookup
- `scanner_input.py` – Scanner-Threads
- `gpio_controller.py` – Taster/LEDs
- `thermal_printer.py` – Bondruck
- `ticket_renderer.py` – Text-/Druckaufbereitung
- `export_manager.py` – TXT/CSV-Erzeugung

## Updates

Im Repository-Verzeichnis:

```bash
cd /home/agw/src/atemschutz-scan-system
git pull
chmod +x install.sh update.sh
sudo ./install.sh
```

Alternativ:

```bash
cd /home/agw/src/atemschutz-scan-system
./update.sh
```

## Komplette Neuinstallation

```bash
sudo systemctl stop atemschutz-scan-system.service
sudo systemctl disable atemschutz-scan-system.service
sudo rm -f /etc/systemd/system/atemschutz-scan-system.service
sudo systemctl daemon-reload
sudo rm -rf /opt/atemschutz-scan-system
rm -rf /home/agw/src/atemschutz-scan-system
```

Danach das Repository erneut klonen und wie oben beschrieben installieren.

## Hinweise zu Systemfehlern

Ein Systemfehler wird gesetzt, wenn beim Start oder Betrieb Grundfunktionen nicht verfügbar sind, zum Beispiel:

- CSV oder Datenbank kann nicht gelesen werden
- Konfigurationsdateien sind ungültig
- Druckerpfad fehlt
- GPIO-Initialisierung schlägt fehl
- Systemzeit ist unplausibel

Dann erscheint die Fehlermeldung im Webinterface im Bereich **Systemfehler**.

## Empfohlene Aufräumregeln im Repository

Nicht versionieren:

- `__pycache__/`
- `*.pyc`
- `data/atemschutz_scanner.db`
- `data/runtime_settings.json`
- `data/last_print_payload.json`
- `data/exports/*`

Diese Dateien werden zur Laufzeit erzeugt und gehören nicht in die gepflegte Projektbasis.


## Hotspot und Captive Portal

- Standard-SSID: `Atemschutz-Scan-System`
- Standard-Passwort: `Atemschutz2026`
- Hotspot-IP: `192.168.50.1`
- Portal-URL: `http://192.168.50.1/`
- Direkte Flask-URL: `http://192.168.50.1:5000/`
- LAN bleibt auf DHCP aktiv und kann weiter fuer SSH und die Weboberflaeche verwendet werden.

### Diagnose

```bash
sudo systemctl status hostapd dnsmasq nginx atemschutz-scan-system.service --no-pager
sudo journalctl -u hostapd -u dnsmasq -u nginx -u atemschutz-scan-system.service -n 150 --no-pager
```

### Wichtiger Hinweis

Moderne Geraete erkennen ein Captive Portal in der Regel ueber unverschluesselte HTTP-Tests. Eine automatische Weiterleitung funktioniert daher fuer die meisten Clients, HTTPS-Ziele koennen aus technischen Gruenden nicht transparent umgebogen werden.
