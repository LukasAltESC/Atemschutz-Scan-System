"""Zentrale Projektkonfiguration.

Alle Pfade, Gruppen, Webserver-Parameter sowie GPIO- und Laufzeitwerte werden
zentral in dieser Datei gepflegt, damit Servicearbeiten an einer Stelle
starten koennen.
"""

from pathlib import Path

# Projekt- und Dateipfade
PROJECT_NAME = 'Atemschutz-Scan-System'
PROJECT_SLUG = 'atemschutz-scan-system'

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
DB_PATH = DATA_DIR / 'atemschutz_scanner.db'
CSV_PATH = DATA_DIR / 'Database.CSV'
LAST_PRINT_PATH = DATA_DIR / 'last_print_payload.json'
SETTINGS_PATH = DATA_DIR / 'runtime_settings.json'
FUNCTION_CARDS_PATH = DATA_DIR / 'function_cards.json'
DETAIL_CHECKLIST_PATH = DATA_DIR / 'detail_checklist.json'
OUTPUT_LAYOUT_PATH = DATA_DIR / 'output_layout.json'
PRINT_LAYOUT_PATH = DATA_DIR / 'print_layout.json'
EXPORT_DIR = DATA_DIR / 'exports'
SCHEMA_PATH = BASE_DIR / 'schema.sql'

# Fachliche Betriebsmodi
MODE_VERWENDUNGSNACHWEIS = 'verwendungsnachweis'
MODE_LIEFERSCHEIN = 'lieferschein'

MODE_LABELS = {
    MODE_VERWENDUNGSNACHWEIS: 'Verwendungsnachweis',
    MODE_LIEFERSCHEIN: 'Lieferschein',
}

# Pflicht- und optionale Gruppen fuer den Verwendungsnachweis
REQUIRED_GROUPS = [
    'Atem-Druckluftflasche',
    'Vollmaske',
    'Pressluftatmer',
    'Lungenautomat',
]

OPTIONAL_GROUPS = [
    'Mitteldruckverlängerung',
]

ALL_GROUPS = REQUIRED_GROUPS + OPTIONAL_GROUPS
ACTIVE_GROUPS = list(ALL_GROUPS)

# Abbildung verschiedener CSV-/Altbezeichnungen auf die Systemgruppen.
RAW_GROUP_TO_SYSTEM_GROUP = {
    'Flasche': 'Atem-Druckluftflasche',
    'Atem-Druckluftflasche': 'Atem-Druckluftflasche',
    'Atemluftflasche': 'Atem-Druckluftflasche',
    'Atemschutz-Druckluftflasche': 'Atem-Druckluftflasche',
    'Maske': 'Vollmaske',
    'Vollmaske': 'Vollmaske',
    'Atemschutz-Vollmaske': 'Vollmaske',
    'PA': 'Pressluftatmer',
    'Pressluftatmer': 'Pressluftatmer',
    'Lungenautomat': 'Lungenautomat',
    'Verbindungsschlauch': 'Mitteldruckverlängerung',
    'Mitteldruckverlängerung': 'Mitteldruckverlängerung',
}

# Je Gruppe sind nur diese Kennungen fuer einen Lookup erlaubt.
IDENTIFIER_FIELDS_BY_GROUP = {
    'Atem-Druckluftflasche': ['inventarnummer', 'lf_scan'],
    'Vollmaske': ['inventarnummer', 'fabriknummer'],
    'Pressluftatmer': ['inventarnummer'],
    'Lungenautomat': ['inventarnummer', 'fabriknummer'],
    'Mitteldruckverlängerung': ['inventarnummer'],
}

# Maximale Anzahl je Gruppe im Verwendungsnachweismodus.
GROUP_CAPACITY_NORMAL_MODE = {
    'Atem-Druckluftflasche': 2,
    'Vollmaske': 1,
    'Pressluftatmer': 1,
    'Lungenautomat': 1,
    'Mitteldruckverlängerung': 1,
}

# Mindestanzahl, damit der Verwendungsnachweis druckbereit ist.
MIN_REQUIRED_COUNT_BY_GROUP = {
    'Atem-Druckluftflasche': 1,
    'Vollmaske': 1,
    'Pressluftatmer': 1,
    'Lungenautomat': 1,
}

# Standardpfade fuer maximal zwei Scanner. Im Servicefall moeglichst by-id-Pfade nutzen.
SCANNER_DEVICE_PATHS = [
    '/dev/input/event0',
    '/dev/input/event1',
]

# Flask-Webserver
HOST = '0.0.0.0'
PORT = 5000
SECRET_KEY = 'CHANGE_ME_BEFORE_PRODUCTION'

# Standardwerte fuer Druck und Bondruckpausen
DEFAULT_PRINT_COPY_COUNT = 1
DEFAULT_PRINT_COPY_PAUSE_SECONDS = 2.0

# GPIO-Pins im BCM-Schema
RESET_BUTTON_PIN = 17
MODE_BUTTON_PIN = 27
PRINT_BUTTON_PIN = 22
GREEN_LED_PIN = 24
RED_LED_PIN = 23
GPIO_BOUNCETIME_MS = 80
GPIO_POLL_INTERVAL_SECONDS = 0.03
RESET_LONG_PRESS_SECONDS = 1.8
MODE_BUTTON_LONG_PRESS_SECONDS = 1.0

# Blink- und Fehlerzeiten fuer Status-LEDs
ERROR_BLINK_ON_SECONDS = 0.15
ERROR_BLINK_OFF_SECONDS = 0.15
GENERIC_ERROR_BLINKS = 1
DUPLICATE_ERROR_BLINKS = 3
SUCCESS_BLINK_ON_SECONDS = 0.12
SUCCESS_BLINK_OFF_SECONDS = 0.08
LISTING_MODE_BLINK_INTERVAL_SECONDS = 0.20
SYSTEM_ERROR_BLOCKING_BLINK_ON_SECONDS = 0.06
SYSTEM_ERROR_BLOCKING_BLINK_OFF_SECONDS = 0.06
SYSTEM_ERROR_TIME_WARNING_BLINK_ON_SECONDS = 0.35
SYSTEM_ERROR_TIME_WARNING_BLINK_OFF_SECONDS = 0.35
SYSTEM_TIME_MIN_YEAR = 2024
SYSTEM_TIME_MAX_YEAR = 2099

# Laufzeitverhalten
LIEFERSCHEIN_MODE_TIMEOUT_SECONDS = 300
SCAN_DEBOUNCE_SECONDS = 0.2
MAX_EVENT_LOG_ENTRIES = 80
EXPORT_HISTORY_LIMIT = 40

# Vor der Suche werden problematische Zeichen auf ein stabiles Format reduziert.
SCAN_CHARACTER_REPLACEMENTS = {
    'ß': '-',
    '–': '-',
    '—': '-',
    '_': '-',
    ' ': '',
}

# Diese Werte werden als Basis fuer die Web-Einstellungen verwendet.
DEFAULT_RUNTIME_SETTINGS = {
    'reset_after_print': True,
    'print_operator_name': True,
    'clear_name_after_print': False,
    'show_datetime_on_print': True,
    'print_datetime_placeholder': False,
    'print_default_details_without_card': True,
    'print_remarks': True,
    'scanner_device_paths': list(SCANNER_DEVICE_PATHS),
}

ACTIVE_GPIO_CONFIG = {
    'reset_button_pin': int(RESET_BUTTON_PIN),
    'mode_button_pin': int(MODE_BUTTON_PIN),
    'print_button_pin': int(PRINT_BUTTON_PIN),
    'green_led_pin': int(GREEN_LED_PIN),
    'red_led_pin': int(RED_LED_PIN),
}

CONFIG_FILE_PATHS = {
    'base_dir': str(BASE_DIR),
    'function_cards': str(FUNCTION_CARDS_PATH),
    'detail_checklist': str(DETAIL_CHECKLIST_PATH),
    'output_layout': str(OUTPUT_LAYOUT_PATH),
    'print_layout': str(PRINT_LAYOUT_PATH),
    'database_csv': str(CSV_PATH),
    'runtime_settings': str(SETTINGS_PATH),
}
