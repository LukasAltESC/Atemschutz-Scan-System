"""TXT- und CSV-Export fuer erzeugte Dokumente.

Die Exportdateien orientieren sich inhaltlich an demselben Payload wie der
Bondruck, damit alle Ausgabekanaele dieselbe fachliche Basis verwenden.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from ascii_utils import to_ascii_text
from config import EXPORT_DIR, EXPORT_HISTORY_LIMIT, MODE_LIEFERSCHEIN, MODE_VERWENDUNGSNACHWEIS
from ticket_renderer import TicketRenderer

ORGANIZATION_NAME = 'THW OV Donaueschingen'


class ExportManager:
    """Speichert denselben Payload wie der Bondruck zusaetzlich als Datei."""

    def __init__(self, print_layout_manager, export_dir: Path = EXPORT_DIR):
        self.print_layout_manager = print_layout_manager
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.renderer = TicketRenderer()

    def _timestamp_slug(self) -> str:
        return datetime.now().strftime('%Y%m%d_%H%M%S')

    def save(self, payload: Dict) -> Dict:
        """Erzeugt immer ein TXT- und ein CSV-Pendant zum aktuellen Payload."""
        slug = self._timestamp_slug()
        mode = payload.get('mode', MODE_VERWENDUNGSNACHWEIS)
        txt_path = self.export_dir / f'{slug}_{mode}.txt'
        csv_path = self.export_dir / f'{slug}_{mode}.csv'
        txt_path.write_text(self.renderer.render_text(payload, self.print_layout_manager.get_layout(), ascii_only=True), encoding='utf-8')
        self._write_csv(payload, csv_path)
        return {
            'txt': str(txt_path),
            'csv': str(csv_path),
            'txt_name': txt_path.name,
            'csv_name': csv_path.name,
        }

    def clear_exports(self) -> int:
        deleted = 0
        for path in self.export_dir.glob('*'):
            if path.is_file() and path.suffix.lower() in {'.txt', '.csv'}:
                try:
                    path.unlink()
                    deleted += 1
                except Exception:
                    pass
        return deleted

    def list_exports(self, limit: int = EXPORT_HISTORY_LIMIT) -> List[Dict]:
        files = []
        for path in sorted(self.export_dir.glob('*'), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.is_file():
                files.append(
                    {
                        'name': path.name,
                        'size_bytes': path.stat().st_size,
                        'modified_at': datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    }
                )
            if len(files) >= limit:
                break
        return files

    def _value(self, value) -> str:
        text = to_ascii_text(value).strip()
        return text if text else '-'

    def _material_groups(self, payload: Dict) -> List[str]:
        return list(payload.get('required_groups', [])) + list(payload.get('optional_groups', []))

    def _group_items(self, payload: Dict, group_name: str) -> List[Dict]:
        if payload.get('mode') == MODE_LIEFERSCHEIN:
            return list((payload.get('raw_items', {}) or {}).get(group_name, []))
        return list((payload.get('items', {}) or {}).get(group_name, []))

    def _write_csv(self, payload: Dict, csv_path: Path) -> None:
        with csv_path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle, delimiter=';')
            writer.writerow(['Bereich', 'Gruppe', 'Feld', 'Wert'])
            writer.writerow(['Meta', '', 'Organisation', ORGANIZATION_NAME])
            writer.writerow(['Meta', '', 'Dokumenttyp', self._value(payload.get('mode_label', ''))])
            writer.writerow(['Meta', '', self._value(payload.get('operator_name_label', 'Name')), self._value(payload.get('operator_name', ''))])

            if payload.get('print_datetime_placeholder') or payload.get('force_datetime_placeholder'):
                writer.writerow(['Meta', '', 'Datum', self._value('____________________')])
                writer.writerow(['Meta', '', 'Uhrzeit', self._value('________________ Uhr')])
            else:
                writer.writerow(['Meta', '', 'Datum', self._value(payload.get('date', ''))])
                writer.writerow(['Meta', '', 'Uhrzeit', self._value(payload.get('time', ''))])

            if payload.get('mode') == MODE_VERWENDUNGSNACHWEIS:
                duration = self._value(payload.get('usage_duration_minutes', ''))
                if duration != '-' and not any(char.isalpha() for char in duration):
                    duration = f'{duration} min'
                elif duration == '-':
                    duration = '__________ min'
                writer.writerow(['Meta', '', 'Einsatzdauer', duration])

            writer.writerow(['Meta', '', 'Bemerkungen', self._value(payload.get('remarks', ''))])
            writer.writerow([])

            field_labels = (payload.get('print_layout') or {}).get('labels', {}).get('field_labels', {})
            group_titles = (payload.get('print_layout') or {}).get('labels', {}).get('group_titles', {})
            print_fields = (payload.get('print_layout') or {}).get('print_fields', {})
            for group_name in self._material_groups(payload):
                items = self._group_items(payload, group_name)
                if not items:
                    continue
                group_label = self._value(group_titles.get(group_name, group_name))
                group_fields = list(print_fields.get(group_name, []))
                for item in items:
                    for field_name in group_fields:
                        value = self._value(item.get(field_name, ''))
                        if value == '-':
                            continue
                        label = self._value(field_labels.get(field_name, field_name))
                        writer.writerow(['Material', group_label, label, value])
                    if item.get('geraetenummer') and 'geraetenummer' not in group_fields:
                        writer.writerow(['Material', group_label, self._value(field_labels.get('geraetenummer', 'Serien-Nr.')), self._value(item.get('geraetenummer', ''))])
                    writer.writerow([])

            cards = payload.get('function_cards') or []
            if cards:
                for card in cards:
                    writer.writerow(['Details', '', 'Einsatz- & Uebungsdetails', self._value(card.get('label', ''))])
            elif payload.get('print_default_details_without_card'):
                for detail in payload.get('default_detail_checklist') or []:
                    writer.writerow(['Details', '', 'Einsatz- & Uebungsdetails', self._value(detail)])
            else:
                writer.writerow(['Details', '', 'Einsatz- & Uebungsdetails', '-'])
