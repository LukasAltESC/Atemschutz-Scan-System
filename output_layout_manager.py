"""Verwaltet sichtbare Materialfelder fuer Web, TXT und CSV."""

import json
from pathlib import Path
from typing import Dict, List

from config import ALL_GROUPS, OUTPUT_LAYOUT_PATH

DEFAULT_LAYOUT = {
    'Atem-Druckluftflasche': ['item_type', 'inventarnummer', 'lf_scan', 'bemerkung'],
    'Vollmaske': ['item_type', 'inventarnummer', 'fabriknummer', 'bemerkung'],
    'Pressluftatmer': ['item_type', 'inventarnummer', 'bemerkung'],
    'Lungenautomat': ['item_type', 'inventarnummer', 'fabriknummer', 'bemerkung'],
    'Mitteldruckverlängerung': ['item_type', 'inventarnummer', 'bemerkung'],
}

FIELD_LABELS = {
    'item_type': 'Typ',
    'inventarnummer': 'Inventarnummer',
    'fabriknummer': 'Fabriknummer',
    'geraetenummer': 'Seriennummer',
    'lf_scan': 'LF-Scan',
    'bemerkung': 'Bemerkungen',
}

VALID_FIELDS = set(FIELD_LABELS)


class OutputLayoutManager:
    """Verwaltet die Material-Felder für Website, Druck und Export."""

    def __init__(self, path: Path = OUTPUT_LAYOUT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.layout: Dict[str, List[str]] = {}
        self.last_error = ''
        self.load()

    def _normalize(self, raw_data) -> Dict[str, List[str]]:
        data = raw_data or {}
        if not isinstance(data, dict):
            data = {}

        group_data = data.get('group_fields', data)
        if not isinstance(group_data, dict):
            group_data = {}

        normalized = {}
        for group_name in ALL_GROUPS:
            raw_fields = group_data.get(group_name, DEFAULT_LAYOUT.get(group_name, []))
            if not isinstance(raw_fields, list):
                raw_fields = DEFAULT_LAYOUT.get(group_name, [])

            fields = []
            for field in raw_fields:
                field_name = str(field).strip()
                if field_name in VALID_FIELDS and field_name not in fields:
                    fields.append(field_name)

            if not fields:
                fields = list(DEFAULT_LAYOUT.get(group_name, []))
            normalized[group_name] = fields
        return normalized

    def load(self) -> Dict[str, List[str]]:
        if not self.path.exists():
            return self.save(DEFAULT_LAYOUT)

        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except Exception as exc:
            self.last_error = f'Ausgabelayout konnte nicht geladen werden: {exc}'
            return self.get_layout()

        self.layout = self._normalize(data)
        self.last_error = ''
        return self.get_layout()

    def save(self, rows) -> Dict[str, List[str]]:
        normalized = self._normalize(rows)
        self.path.write_text(json.dumps({'group_fields': normalized}, indent=2, ensure_ascii=False), encoding='utf-8')
        self.layout = normalized
        self.last_error = ''
        return self.get_layout()

    def get_layout(self) -> Dict[str, List[str]]:
        return {group_name: list(fields) for group_name, fields in self.layout.items()}

    def get_field_labels(self) -> Dict[str, str]:
        return dict(FIELD_LABELS)

    def get_status(self) -> Dict:
        return {
            'path': str(self.path),
            'group_count': len(self.layout),
            'last_error': self.last_error,
        }
