"""Verwaltung der Standard-Checkliste fuer Einsatz- und Uebungsdetails."""

import json
from pathlib import Path
from typing import Dict, List

from config import DETAIL_CHECKLIST_PATH


class DetailChecklistManager:
    """Liest und verwaltet die Standard-Checkliste für Einsatz- & Übungsdetails."""

    def __init__(self, path: Path = DETAIL_CHECKLIST_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.items: List[str] = []
        self.last_error = ''
        self.load()

    def load(self) -> List[str]:
        if not self.path.exists():
            return self.save([])
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                data = data.get('items', [])
            if not isinstance(data, list):
                raise ValueError('Checklisten-Datei muss eine JSON-Liste sein.')
        except Exception as exc:
            self.last_error = f'Checkliste konnte nicht geladen werden: {exc}'
            return list(self.items)

        self.items = [str(item).strip() for item in data if str(item).strip()]
        self.last_error = ''
        return list(self.items)

    def save(self, items: List[str]) -> List[str]:
        payload = [str(item).strip() for item in (items or []) if str(item).strip()]
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
        self.items = []
        return self.load()

    def get_items(self) -> List[str]:
        return list(self.items)

    def get_status(self) -> Dict:
        return {
            'path': str(self.path),
            'count': len(self.items),
            'last_error': self.last_error,
        }
