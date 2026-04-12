"""Verwaltung scanbarer Funktionskarten aus JSON-Dateien."""

import json
from pathlib import Path
from typing import Dict, List

from config import FUNCTION_CARDS_PATH
from normalizer import normalize_scan_code


class FunctionCardManager:
    """Liest und verwaltet scanbare Funktionskarten."""

    def __init__(self, path: Path = FUNCTION_CARDS_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: List[Dict] = []
        self.last_error = ''
        self.last_warning = ''
        self.load()

    def _extract_rows(self, raw_data):
        if isinstance(raw_data, dict):
            for key in ('cards', 'function_cards', 'items'):
                candidate = raw_data.get(key)
                if isinstance(candidate, list):
                    return candidate
            raise ValueError('Funktionskarten-Datei enthält weder Liste noch Karten-Schlüssel.')
        if not isinstance(raw_data, list):
            raise ValueError('Funktionskarten-Datei muss eine JSON-Liste sein.')
        return raw_data

    def load(self) -> List[Dict]:
        if not self.path.exists():
            return self.save([])

        try:
            raw_data = json.loads(self.path.read_text(encoding='utf-8'))
            rows = self._extract_rows(raw_data)
        except Exception as exc:
            self.last_error = f'Funktionskarten konnten nicht geladen werden: {exc}'
            self.last_warning = ''
            return list(self.data)

        cards = []
        seen_codes = set()
        duplicate_labels = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get('code', '')).strip()
            label = str(row.get('label', '')).strip()
            normalized = normalize_scan_code(code)
            if not code or not label or not normalized:
                continue
            if normalized in seen_codes:
                duplicate_labels.append(label or code)
                continue
            seen_codes.add(normalized)
            cards.append({'code': code, 'label': label, 'normalized_code': normalized})

        self.data = cards
        self.last_error = ''
        self.last_warning = ''
        if duplicate_labels:
            self.last_warning = 'Doppelte Funktionskarten-Codes wurden ignoriert: ' + ', '.join(duplicate_labels)
        return list(self.data)

    def save(self, rows: List[Dict]) -> List[Dict]:
        payload = [
            {
                'code': str(item.get('code', '')).strip(),
                'label': str(item.get('label', '')).strip(),
            }
            for item in (rows or [])
            if str(item.get('code', '')).strip() and str(item.get('label', '')).strip()
        ]
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
        self.data = []
        return self.load()

    def get_card_by_scan(self, scanned_code: str):
        normalized = normalize_scan_code(scanned_code)
        if not normalized:
            return None
        for card in self.data:
            if card['normalized_code'] == normalized:
                return dict(card)
        return None

    def list_cards(self) -> List[Dict]:
        return [{'code': card['code'], 'label': card['label']} for card in self.data]

    def get_status(self) -> Dict:
        return {
            'path': str(self.path),
            'count': len(self.data),
            'last_error': self.last_error,
            'last_warning': self.last_warning,
        }
