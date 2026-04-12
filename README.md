# Atemschutz-Scan-System

Raspberry-Pi-basiertes Scan- und Ausgabesystem zur Erfassung von Atemschutzmaterial.
Das Projekt unterstützt zwei Arbeitsmodi:

- **Verwendungsnachweis** für einen vollständigen Gerätesatz
- **Lieferschein** für freie Materialerfassung mit beliebig vielen Geräten

## Dokumentation

Die Dokumentation ist jetzt in einzelne, klar getrennte Dateien aufgeteilt:

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
- Eine `config_local.py` wird nicht verwendet.
- Laufzeitdateien wie SQLite-Datenbank, Exporte und Web-Einstellungen werden bewusst nicht versioniert.
