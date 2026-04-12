"""Persistente Laufzeiteinstellungen fuer die Weboberflaeche."""

import json
from pathlib import Path
from typing import Dict

from config import DEFAULT_RUNTIME_SETTINGS, SETTINGS_PATH


class SettingsManager:
    """Persistente Laufzeiteinstellungen als JSON-Datei."""

    LEGACY_ALIASES = {
        'print_default_detail_checklist': 'print_default_details_without_card',
    }

    def __init__(self, path: Path = SETTINGS_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _apply_legacy_aliases(self, data: Dict) -> Dict:
        merged = dict(data or {})
        for legacy_key, new_key in self.LEGACY_ALIASES.items():
            if legacy_key in merged and new_key not in merged:
                merged[new_key] = merged[legacy_key]
        return merged

    def _merge(self, data: Dict) -> Dict:
        raw = self._apply_legacy_aliases(data)
        merged = dict(DEFAULT_RUNTIME_SETTINGS)
        merged.update({k: v for k, v in (raw or {}).items() if k in DEFAULT_RUNTIME_SETTINGS})

        scanner_paths = merged.get('scanner_device_paths')
        if not isinstance(scanner_paths, list):
            scanner_paths = list(DEFAULT_RUNTIME_SETTINGS['scanner_device_paths'])
        merged['scanner_device_paths'] = [str(path).strip() for path in scanner_paths if str(path).strip()][:2]
        if not merged['scanner_device_paths']:
            merged['scanner_device_paths'] = list(DEFAULT_RUNTIME_SETTINGS['scanner_device_paths'])

        merged['reset_after_print'] = bool(merged.get('reset_after_print', True))
        merged['print_operator_name'] = True
        merged['clear_name_after_print'] = bool(merged.get('clear_name_after_print', False))
        merged['show_datetime_on_print'] = True
        merged['print_datetime_placeholder'] = bool(merged.get('print_datetime_placeholder', False))
        merged['print_default_details_without_card'] = bool(merged.get('print_default_details_without_card', True))
        merged['print_remarks'] = bool(merged.get('print_remarks', True))
        return merged

    def load(self) -> Dict:
        if not self.path.exists():
            data = dict(DEFAULT_RUNTIME_SETTINGS)
            self.save(data)
            return self._merge(data)
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                raise ValueError('settings not dict')
        except Exception:
            data = dict(DEFAULT_RUNTIME_SETTINGS)
        return self._merge(data)

    def save(self, values: Dict) -> Dict:
        merged = self._merge(values or {})
        self.path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding='utf-8')
        return merged
