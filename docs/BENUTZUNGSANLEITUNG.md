# Benutzungsanleitung

## Zweck

Das System erfasst Atemschutzmaterial per Scanner und erstellt daraus entweder einen **Verwendungsnachweis** oder einen **Lieferschein**.

## Betriebsmodi

### Verwendungsnachweis

Pflichtgruppen für einen vollständigen Nachweis:

- Atem-Druckluftflasche
- Vollmaske
- Pressluftatmer
- Lungenautomat

Optional:

- Mitteldruckverlängerung

Besonderheiten:

- Atem-Druckluftflaschen können über **Inventarnummer** oder **LF-Scan** erfasst werden.
- Vollmasken und Lungenautomaten können zusätzlich über **Fabriknummer** erfasst werden.
- Die Seriennummer/Gerätenummer wird angezeigt, aber nicht als Scan-Kennung benutzt.
- Wenn alle Pflichtgruppen vorhanden sind, ist das System druckbereit.

### Lieferschein

Im Lieferscheinmodus können beliebig viele Geräte pro Gruppe gescannt werden. Die Ansicht gruppiert die Einträge nach Gerätetyp und listet darunter die einzelnen Positionen.

## Tasterfunktionen

- **Druck**: startet den Bondruck
- **Reset**: löscht die aktuelle Materialerfassung
- **Langer Reset**: löscht zusätzlich Name und Bemerkungen
- **Modus**: wechselt zwischen Verwendungsnachweis und Lieferschein

## LED-Signale

- **1x grün blinken**: erfolgreicher Scan
- **2x grün blinken**: zweite Atem-Druckluftflasche im Verwendungsnachweis übernommen
- **grün dauerhaft an**: Verwendungsnachweis ist druckbereit
- **grün schnell blinkend**: Lieferscheinmodus aktiv
- **rot blinkend**: Fehler beim Scan oder bei der Aktion
- **rot dauerhaft/spezifisches Fehlerverhalten**: Systemfehler oder Warnzustand

## Arbeitsablauf

### Verwendungsnachweis erstellen

1. Namen und Einsatzdaten auf der Startseite eintragen.
2. Material nacheinander scannen.
3. Prüfen, ob alle Pflichtgruppen übernommen wurden.
4. Bei Bedarf Bemerkungen ergänzen.
5. Bondruck starten oder TXT/CSV erzeugen.

### Lieferschein erstellen

1. Über den Modus-Taster oder die Weboberfläche in den Lieferscheinmodus wechseln.
2. Beliebige Geräte scannen.
3. Einträge in der Materialliste prüfen.
4. Bondruck oder Export auslösen.

## Weboberfläche

### Erfassungsseite

Hier befinden sich:

- Personen- und Einsatzdaten
- der aktuelle Scanstatus
- Materialdarstellung passend zum aktuellen Modus
- Einsatz- und Übungsdetails
- Aktionen für Druck, TXT/CSV und Reset

### Rechte Seitenleiste

Hier befinden sich:

- Druck- und Exportfunktionen
- letzte Ereignisse
- Einstellungen
- Scanner- und Datenbankübersicht

### Ausgabeseite

Hier befinden sich:

- das zuletzt erzeugte Druck-/Export-Payload
- gespeicherte TXT- und CSV-Dateien
- ein Button zum Löschen aller Exportdateien

### Systemseite

Hier befinden sich:

- Scannerpfade
- verfügbare Input-Geräte
- Vorschau der Funktionskarten
- Vorschau der Standard-Checkliste
- Vorschau des Ausgabelayouts
- Vorschau des Drucklayouts
- Reload-Funktion für Konfigurationsdateien

### Datenbankseite

Hier können Materialdatensätze:

- angezeigt
- bearbeitet
- neu angelegt
- gelöscht
- per CSV importiert werden

## Ausgabeaufbau

### Kopf

Die Ausgabe enthält standardmäßig:

- Organisation
- Dokumenttyp
- Datum
- Uhrzeit
- je nach Modus Geräteträger/-in oder Erfasser
- Einsatzdauer nur im Verwendungsnachweis

### Materialblöcke

Die sichtbaren Felder pro Gruppe kommen aus `data/output_layout.json`.
Standardmäßig werden ausgegeben:

- Atem-Druckluftflasche: Typ, Inventarnummer, LF-Scan, Bemerkung
- Vollmaske: Typ, Inventarnummer, Fabriknummer, Bemerkung
- Pressluftatmer: Typ, Inventarnummer, Bemerkung
- Lungenautomat: Typ, Inventarnummer, Fabriknummer, Bemerkung
- Mitteldruckverlängerung: Typ, Inventarnummer, Bemerkung

Wenn vorhanden, wird zusätzlich auch die Seriennummer/Gerätenummer angezeigt.

### Einsatz- und Übungsdetails

- Mit Funktionskarten: Ausgabe als Liste der gescannten Karten
- Ohne Funktionskarten: Standard-Checkliste aus `data/detail_checklist.json`

## Scanbare Kennungen je Gruppe

- Atem-Druckluftflasche: Inventarnummer, LF-Scan
- Vollmaske: Inventarnummer, Fabriknummer
- Pressluftatmer: Inventarnummer
- Lungenautomat: Inventarnummer, Fabriknummer
- Mitteldruckverlängerung: Inventarnummer

## Typische Meldungen

### Erfolgreiche Meldungen

- Scan übernommen
- Funktionskarte übernommen
- Bondruck erfolgreich
- TXT/CSV erzeugt

### Fehlermeldungen

- Code unbekannt
- Doppelscan erkannt
- Gruppe bereits voll
- Code nicht eindeutig
- Druck gesperrt wegen Systemfehler

## Hinweise für den Betrieb

- Für Scanner nach Möglichkeit feste `by-id`-Pfade verwenden.
- Nach Änderungen an JSON-Dateien die Konfiguration auf der Systemseite neu laden oder den Dienst neu starten.
- Der Lieferscheinmodus fällt nach längerer Inaktivität automatisch in den Verwendungsnachweis zurück.
