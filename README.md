# Atemschutz-Scan-System

Raspberry-Pi-basiertes Scan- und Ausgabesystem zur Erfassung von Atemschutzmaterial.
Das Projekt unterstützt zwei Arbeitsmodi:

- **Verwendungsnachweis** für einen vollständigen Gerätesatz
- **Lieferschein** für freie Materialerfassung mit beliebig vielen Geräten

## Dokumentation

Die Dokumentation dieses ist in folgende Dateien aufgeteilt:

- [`docs/PROJEKTBESCHREIBUNG.md`](docs/PROJEKTBESCHREIBUNG.md)
- [`docs/BENUTZUNGSANLEITUNG.md`](docs/BENUTZUNGSANLEITUNG.md)
- [`docs/SERVICEANLEITUNG.md`](docs/SERVICEANLEITUNG.md)

## Schnellstart

```bash
mkdir -p /home/agw/src
cd /home/agw/src
git clone https://github.com/LukasAltESC/atemschutz-scan-system.git atemschutz-scan-system
cd atemschutz-scan-system
chmod +x install.sh update.sh
sudo ./install.sh
```

Danach ist das Webinterface typischerweise unter `http://<PI-IP>:5000` erreichbar.

Die `install.sh` richtet zusaetzlich einen WLAN-Access-Point mit folgenden Standardwerten ein:

Technisch wird dafuer auf Raspberry Pi OS Lite bewusst der klassische Stack aus `hostapd` + `dnsmasq` verwendet. Vorhandene WLAN-Client-Dienste auf `wlan0` werden deaktiviert, damit es keinen Konflikt mit dem Hotspot gibt.

- **SSID:** `Atemschutz-Scan-System`
- **Passwort:** `Atemschutz2026`
- **Statische AP-IP:** `192.168.50.1`
- **Webinterface ueber AP:** `http://192.168.50.1:5000`

Der LAN-Port bleibt parallel aktiv und bezieht weiterhin eine Adresse per DHCP. Damit sind SSH und Webinterface sowohl ueber den Access Point als auch ueber Ethernet erreichbar.

Die AP-Werte koennen beim Installieren per Umgebungsvariable angepasst werden, zum Beispiel:

```bash
sudo AP_SSID="Atemschutz-Scan-System" AP_PASSPHRASE="MeinSicheresPasswort" AP_IP_ADDRESS="192.168.60.1" ./install.sh
```

## Projektstruktur

- `app.py` – Flask-Webanwendung und Routen
- `state_manager.py` – zentrale Scan- und Ablaufsteuerung
- `database.py` – CSV-/SQLite-Verwaltung und Scan-Lookup
- `scanner_input.py` – Scanner-Erfassung über `/dev/input/event*`
- `gpio_controller.py` – Taster- und LED-Steuerung
- `thermal_printer.py` – Bondruck auf `/dev/usb/lp0`
- `ticket_renderer.py` – Aufbau des Druck-/TXT-Layouts
- `data/` – Stammdaten, Layoutdateien und Laufzeitdaten
- `templates/` – HTML-Templates
- `static/` – CSS und Bilder
- `tools/` – Hilfs- und Testskripte
- `docs/` – Projektdokumentation

## Hinweise

- Die Hardware- und Sicherheitsparameter werden direkt in `config.py` gepflegt.
- Laufzeitdateien wie SQLite-Datenbank, Exporte und Web-Einstellungen werden bewusst nicht versioniert.


## WLAN-Hotspot mit Captive Portal

- Der Hotspot **Atemschutz-Scan-System** wird waehrend `install.sh` eingerichtet.
- Verbundene Geraete erhalten per WLAN eine Adresse im Netz `192.168.50.0/24`.
- DNS-Anfragen im Hotspot werden auf den Raspberry Pi aufgeloest, damit ein Captive Portal erkannt wird.
- Die Weboberflaeche ist ueber **http://192.168.50.1/** erreichbar.
- Direktzugriff bleibt zusaetzlich ueber **http://192.168.50.1:5000/** moeglich.
- Ethernet (`eth0`) bleibt parallel auf DHCP fuer SSH und Webzugriff aktiv.
- Je nach Betriebssystem erscheint das Portal automatisch oder nach dem ersten Oeffnen einer HTTP-Seite.
