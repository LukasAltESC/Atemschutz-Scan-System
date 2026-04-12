"""Zentrale Zustands- und Ablaufsteuerung fuer Scanbetrieb und Ausgabe.

Hier laufen Scanannahme, Moduswechsel, Regeln fuer Pflichtgruppen,
Systemfehler, Payload-Erzeugung und Nachbearbeitung nach Druck oder Export
zusammen.
"""

import json
import threading
import time
from collections import deque
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ascii_utils import sanitize_recursive
from config import (
    ALL_GROUPS,
    DEFAULT_PRINT_COPY_COUNT,
    DEFAULT_PRINT_COPY_PAUSE_SECONDS,
    GROUP_CAPACITY_NORMAL_MODE,
    LAST_PRINT_PATH,
    LIEFERSCHEIN_MODE_TIMEOUT_SECONDS,
    MAX_EVENT_LOG_ENTRIES,
    MIN_REQUIRED_COUNT_BY_GROUP,
    MODE_LABELS,
    MODE_LIEFERSCHEIN,
    MODE_VERWENDUNGSNACHWEIS,
    OPTIONAL_GROUPS,
    REQUIRED_GROUPS,
)
from normalizer import normalize_scan_code

IDENTIFIER_LABELS = {
    'inventarnummer': 'Inventarnummer',
    'fabriknummer': 'Fabriknummer',
    'geraetenummer': 'Seriennummer',
    'lf_scan': 'LF-Scan',
}

NAME_LABELS = {
    MODE_VERWENDUNGSNACHWEIS: 'Geräteträger/-in',
    MODE_LIEFERSCHEIN: 'Erfasser',
}


class ScanStateManager:
    """Thread-sichere Ablaufsteuerung für Verwendungsnachweis und Lieferschein."""

    def __init__(
        self,
        db_manager,
        settings_manager,
        export_manager,
        function_card_manager,
        detail_checklist_manager,
        output_layout_manager,
        print_layout_manager,
        thermal_printer_manager,
        gpio_controller=None,
        last_print_path: Path = LAST_PRINT_PATH,
        health_check_callback: Optional[Callable[[], Dict]] = None,
    ):
        self.db_manager = db_manager
        self.settings_manager = settings_manager
        self.export_manager = export_manager
        self.function_card_manager = function_card_manager
        self.detail_checklist_manager = detail_checklist_manager
        self.output_layout_manager = output_layout_manager
        self.print_layout_manager = print_layout_manager
        self.thermal_printer_manager = thermal_printer_manager
        self.gpio_controller = gpio_controller
        self.last_print_path = Path(last_print_path)
        # Alle veraenderlichen Betriebsdaten laufen ueber diesen Lock, weil
        # Scanner, GPIO-Callbacks, Webanfragen und Monitor-Thread parallel arbeiten.
        self.lock = threading.RLock()
        self.events = deque(maxlen=MAX_EVENT_LOG_ENTRIES)
        self.on_change: Optional[Callable[[], None]] = None
        self.operator_name = ''
        self.usage_duration_minutes = ''
        self.remarks = ''
        self.last_scan = ''
        self.last_normalized_scan = ''
        self.last_error = ''
        self.last_success = ''
        self.last_print_payload = None
        self.system_error = ''
        self.system_error_level = 'none'
        self.force_datetime_placeholder = False
        self.health_check_callback = health_check_callback
        self.mode = MODE_VERWENDUNGSNACHWEIS
        self.mode_changed_at = time.time()
        self.last_activity_at = time.time()
        self.settings = self.settings_manager.load()
        self.verwendungsnachweis_slots: Dict[str, List[Dict]] = {}
        self.lieferschein_items: Dict[str, List[Dict]] = {}
        self.function_cards: List[Dict] = []
        self.stop_event = threading.Event()
        self.monitor_thread = threading.Thread(target=self._monitor_worker, daemon=True)
        self.reset_state(log_event=False)
        self.monitor_thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def set_change_callback(self, callback: Callable[[], None]) -> None:
        self.on_change = callback

    def _notify_change(self) -> None:
        if self.on_change:
            self.on_change()

    def _log_event(self, level: str, message: str, source: str = 'system') -> None:
        self.events.appendleft(
            {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': level,
                'source': source,
                'message': message,
            }
        )

    def _touch_activity(self) -> None:
        self.last_activity_at = time.time()

    def _set_green_state_locked(self) -> None:
        if not self.gpio_controller:
            return
        if self.mode == MODE_LIEFERSCHEIN:
            self.gpio_controller.set_listing_mode(True)
            self.gpio_controller.set_ready(False)
        else:
            self.gpio_controller.set_listing_mode(False)
            self.gpio_controller.set_ready(self.is_ready_locked())

    def _apply_system_error_locked(self) -> None:
        if self.gpio_controller:
            self.gpio_controller.set_system_fault_level(self.system_error_level)

    def _signal_error(self, error_type: str) -> None:
        if not self.gpio_controller:
            return
        if error_type == 'duplicate':
            self.gpio_controller.signal_duplicate_error()
        else:
            self.gpio_controller.signal_generic_error()

    def _signal_success(self, blink_count: int = 1) -> None:
        if self.gpio_controller:
            self.gpio_controller.signal_green_success(blink_count)

    def _clear_scan_payload_locked(self) -> None:
        self.verwendungsnachweis_slots = {group: [] for group in ALL_GROUPS}
        self.lieferschein_items = {group: [] for group in ALL_GROUPS}
        self.function_cards = []
        self.usage_duration_minutes = ''
        self.last_scan = ''
        self.last_normalized_scan = ''
        self.last_error = ''
        self.last_success = ''
        self._touch_activity()

    def reset_state(self, log_event: bool = True, source: str = 'system') -> None:
        with self.lock:
            self._clear_scan_payload_locked()
            if log_event:
                self._log_event('info', 'Scan-Zustand wurde zurückgesetzt.', source=source)
            self._set_green_state_locked()
        self._notify_change()

    def update_meta(
        self,
        operator_name: Optional[str] = None,
        usage_duration_minutes: Optional[str] = None,
        remarks: Optional[str] = None,
        source: str = 'web',
        log_event: bool = True,
    ) -> Dict:
        with self.lock:
            if operator_name is not None:
                self.operator_name = operator_name.strip()
            if usage_duration_minutes is not None:
                self.usage_duration_minutes = usage_duration_minutes.strip()
            if remarks is not None:
                self.remarks = remarks.strip()
            self._touch_activity()
            if log_event:
                self._log_event('info', 'Personen- und Einsatzdaten gespeichert.', source=source)
        self._notify_change()
        return {
            'operator_name': self.operator_name,
            'usage_duration_minutes': self.usage_duration_minutes,
            'remarks': self.remarks,
        }

    def clear_operator_name(self, source: str = 'web') -> Dict:
        with self.lock:
            self.operator_name = ''
            self._touch_activity()
            self._log_event('info', 'Name gelöscht.', source=source)
        self._notify_change()
        return {'ok': True, 'message': 'Name gelöscht.'}

    def clear_remarks(self, source: str = 'web') -> Dict:
        with self.lock:
            self.remarks = ''
            self._touch_activity()
            self._log_event('info', 'Bemerkungen gelöscht.', source=source)
        self._notify_change()
        return {'ok': True, 'message': 'Bemerkungen gelöscht.'}

    def clear_text_fields(self, source: str = 'system') -> Dict:
        with self.lock:
            self.operator_name = ''
            self.remarks = ''
            self._touch_activity()
            self._log_event('info', 'Name und Bemerkungen wurden gelöscht.', source=source)
        self._notify_change()
        return {'ok': True, 'message': 'Name und Bemerkungen gelöscht.'}

    def update_settings(self, source: str = 'web', log_event: bool = True, **values) -> Dict:
        with self.lock:
            current = dict(self.settings)
            current.update(values)
            self.settings = self.settings_manager.save(current)
            if log_event:
                self._log_event('info', 'Einstellungen gespeichert.', source=source)
        self.refresh_health()
        self._notify_change()
        return dict(self.settings)

    def _apply_health_snapshot_locked(self, health: Optional[Dict]) -> bool:
        snapshot = health if isinstance(health, dict) else {}
        blocking_errors = [str(message).strip() for message in snapshot.get('blocking_errors', []) if str(message).strip()]
        warnings = [str(message).strip() for message in snapshot.get('warnings', []) if str(message).strip()]
        force_placeholder = bool(snapshot.get('force_datetime_placeholder', False))

        if blocking_errors:
            new_level = 'blocking'
            new_message = ' | '.join(blocking_errors)
        elif warnings:
            new_level = 'time_warning'
            new_message = ' | '.join(warnings)
        else:
            new_level = 'none'
            new_message = ''

        changed = (
            new_message != self.system_error
            or new_level != self.system_error_level
            or force_placeholder != self.force_datetime_placeholder
        )
        if not changed:
            return False

        previous_message = self.system_error
        previous_level = self.system_error_level
        self.system_error = new_message
        self.system_error_level = new_level
        self.force_datetime_placeholder = force_placeholder
        self._apply_system_error_locked()

        if self.system_error:
            self._log_event('error', f'Systemfehler: {self.system_error}', source='healthcheck')
        elif previous_message or previous_level != 'none':
            self._log_event('info', 'Systemfehler zurückgesetzt.', source='healthcheck')
        return True

    def refresh_health(self) -> Dict:
        if not self.health_check_callback:
            return {'blocking_errors': [], 'warnings': [], 'force_datetime_placeholder': False}
        try:
            health = self.health_check_callback() or {}
        except Exception as exc:
            health = {
                'blocking_errors': [f'Systempruefung fehlgeschlagen: {exc}'],
                'warnings': [],
                'force_datetime_placeholder': False,
            }
        with self.lock:
            changed = self._apply_health_snapshot_locked(health)
        if changed:
            self._notify_change()
        return health

    def set_system_error(self, message: str) -> None:
        health = {'blocking_errors': [message] if str(message or '').strip() else [], 'warnings': [], 'force_datetime_placeholder': False}
        with self.lock:
            changed = self._apply_health_snapshot_locked(health)
        if changed:
            self._notify_change()

    def clear_system_error(self) -> None:
        with self.lock:
            changed = self._apply_health_snapshot_locked({'blocking_errors': [], 'warnings': [], 'force_datetime_placeholder': False})
        if changed:
            self._notify_change()

    def is_ready_locked(self) -> bool:
        if self.mode == MODE_LIEFERSCHEIN:
            return any(self.lieferschein_items[group] for group in ALL_GROUPS)
        for group_name, min_count in MIN_REQUIRED_COUNT_BY_GROUP.items():
            if len(self.verwendungsnachweis_slots.get(group_name, [])) < int(min_count):
                return False
        return True

    def _slot_groups_locked(self) -> Dict[str, List[Dict]]:
        if self.mode == MODE_LIEFERSCHEIN:
            return self.lieferschein_items
        return self.verwendungsnachweis_slots

    def _iter_all_current_items_locked(self) -> List[Dict]:
        items = []
        for group_items in self._slot_groups_locked().values():
            items.extend(group_items)
        return items

    def _build_item_payload(self, item: Dict, raw_code: str, normalized_code: str) -> Dict:
        matched_identifier_type = item.get('matched_identifier_type', '')
        matched_identifier_label = IDENTIFIER_LABELS.get(matched_identifier_type, matched_identifier_type or '-')
        return {
            'id': int(item['id']),
            'raw_group': item['raw_group'],
            'group_name': item['system_group'],
            'item_type': item.get('item_type', ''),
            'inventarnummer': item.get('inventarnummer', ''),
            'fabriknummer': item.get('fabriknummer', ''),
            'geraetenummer': item.get('geraetenummer', ''),
            'lf_scan': item.get('lf_scan', ''),
            'bemerkung': item.get('bemerkung', ''),
            'matched_identifier_type': matched_identifier_type,
            'matched_identifier_label': matched_identifier_label,
            'matched_identifier_value': item.get('matched_identifier_value', raw_code),
            'last_scanned_raw_code': raw_code,
            'last_scanned_normalized_code': normalized_code,
        }

    def _handle_function_card_scan_locked(self, raw_code: str, normalized_code: str, source: str) -> Optional[Dict]:
        card = self.function_card_manager.get_card_by_scan(raw_code)
        if not card:
            return None

        if any(existing['normalized_code'] == card['normalized_code'] for existing in self.function_cards):
            self.last_error = f'Funktionskarte bereits erfasst: {card["label"]}'
            self.last_success = ''
            self._log_event('error', self.last_error, source=source)
            self._signal_error('duplicate')
            return {'ok': False, 'message': self.last_error, 'error_type': 'duplicate'}

        entry = {
            'code': card['code'],
            'label': card['label'],
            'normalized_code': card['normalized_code'],
            'last_scanned_raw_code': raw_code,
            'last_scanned_normalized_code': normalized_code,
        }
        self.function_cards.append(entry)
        self.function_cards.sort(key=lambda row: row['label'].lower())
        self.last_error = ''
        self.last_success = f'Funktionskarte übernommen: {card["label"]}'
        self._log_event('success', self.last_success, source=source)
        self._signal_success(1)
        return {'ok': True, 'message': self.last_success, 'error_type': None, 'function_card': entry}

    def handle_scan(self, scanned_code: str, source: str = 'scanner') -> Dict:
        """Verarbeitet einen eingehenden Scan von Scanner, GPIO oder Web."""
        raw_code = (scanned_code or '').strip()
        normalized_code = normalize_scan_code(raw_code)
        result = {'ok': False, 'message': '', 'error_type': None}

        with self.lock:
            self.last_scan = raw_code
            self.last_normalized_scan = normalized_code
            self._touch_activity()

            if not normalized_code:
                self.last_error = 'Leerer Scan wurde ignoriert.'
                self.last_success = ''
                self._log_event('error', self.last_error, source=source)
                result.update({'message': self.last_error, 'error_type': 'empty'})
                self._signal_error('generic')
                self._notify_change()
                return result

            card_result = self._handle_function_card_scan_locked(raw_code, normalized_code, source)
            if card_result is not None:
                self._notify_change()
                return card_result

            item = self.db_manager.get_item_by_scan(raw_code)
            if not item:
                self.last_error = f'Code unbekannt: {raw_code}'
                self.last_success = ''
                self._log_event('error', self.last_error, source=source)
                result.update({'message': self.last_error, 'error_type': 'unknown'})
                self._signal_error('generic')
                self._notify_change()
                return result

            if item.get('lookup_error') == 'ambiguous':
                self.last_error = f'Code nicht eindeutig: {raw_code}'
                self.last_success = ''
                self._log_event('error', self.last_error, source=source)
                result.update({'message': self.last_error, 'error_type': 'ambiguous'})
                self._signal_error('generic')
                self._notify_change()
                return result

            group_name = item['system_group']
            if group_name not in ALL_GROUPS:
                self.last_error = f'Gruppe nicht aktiv: {group_name} ({raw_code})'
                self.last_success = ''
                self._log_event('error', self.last_error, source=source)
                result.update({'message': self.last_error, 'error_type': 'group_inactive'})
                self._signal_error('generic')
                self._notify_change()
                return result

            current_items = self._iter_all_current_items_locked()
            if any(int(existing_item['id']) == int(item['id']) for existing_item in current_items):
                self.last_error = f'Doppelscan erkannt: {raw_code}'
                self.last_success = ''
                self._log_event('error', self.last_error, source=source)
                result.update({'message': self.last_error, 'error_type': 'duplicate'})
                self._signal_error('duplicate')
                self._notify_change()
                return result

            payload_item = self._build_item_payload(item, raw_code, normalized_code)

            if self.mode == MODE_LIEFERSCHEIN:
                # Im Lieferschein werden beliebig viele Positionen gesammelt und
                # fuer eine spaetere gruppierte Darstellung vorsortiert.
                self.lieferschein_items[group_name].append(payload_item)
                self.lieferschein_items[group_name].sort(
                    key=lambda row: (
                        (row.get('item_type') or '').lower(),
                        (row.get('inventarnummer') or '').lower(),
                        (row.get('fabriknummer') or '').lower(),
                        (row.get('geraetenummer') or '').lower(),
                    )
                )
                self.last_error = ''
                self.last_success = f'{raw_code} -> {group_name} zum Lieferschein hinzugefügt.'
                self._log_event('success', self.last_success, source=source)
                self._signal_success(1)
                self._set_green_state_locked()
                result.update({'ok': True, 'message': self.last_success, 'error_type': None})
                self._notify_change()
                return result

            # Im Verwendungsnachweis darf jede Gruppe nur ihre definierte
            # Sollbelegung erreichen, damit der Ausdruck konsistent bleibt.
            capacity = int(GROUP_CAPACITY_NORMAL_MODE.get(group_name, 1))
            if len(self.verwendungsnachweis_slots[group_name]) >= capacity:
                self.last_error = f'Gruppe {group_name} bereits voll. Scan ignoriert: {raw_code}'
                self.last_success = ''
                self._log_event('error', self.last_error, source=source)
                result.update({'message': self.last_error, 'error_type': 'group_occupied'})
                self._signal_error('generic')
                self._notify_change()
                return result

            self.verwendungsnachweis_slots[group_name].append(payload_item)
            self.verwendungsnachweis_slots[group_name].sort(
                key=lambda row: (
                    (row.get('inventarnummer') or '').lower(),
                    (row.get('fabriknummer') or '').lower(),
                    (row.get('geraetenummer') or '').lower(),
                )
            )
            self.last_error = ''

            success_blinks = 1
            if group_name == 'Atem-Druckluftflasche' and len(self.verwendungsnachweis_slots[group_name]) == 2:
                self.last_success = f'{raw_code} -> zweite Atem-Druckluftflasche übernommen.'
                success_blinks = 2
            else:
                self.last_success = f'{raw_code} -> Gruppe {group_name} übernommen.'
            self._log_event('success', self.last_success, source=source)
            self._signal_success(success_blinks)
            self._set_green_state_locked()

            if self.is_ready_locked():
                self._log_event('success', 'Alle Pflichtgruppen sind belegt. Verwendungsnachweis ist druckbereit.', source='system')

            result.update({'ok': True, 'message': self.last_success, 'error_type': None})

        self._notify_change()
        return result

    def toggle_mode(self, source: str = 'system') -> Dict:
        with self.lock:
            target_mode = MODE_VERWENDUNGSNACHWEIS if self.mode == MODE_LIEFERSCHEIN else MODE_LIEFERSCHEIN
            self.mode = target_mode
            self.mode_changed_at = time.time()
            self._clear_scan_payload_locked()
            message = f'{MODE_LABELS.get(target_mode, target_mode)}-Modus aktiviert.'
            self._log_event('info', message, source=source)
            self._set_green_state_locked()
        self._notify_change()
        return {'ok': True, 'message': message, 'mode': target_mode}

    def handle_reset_action(self, source: str = 'reset') -> Dict:
        self.reset_state(log_event=True, source=source)
        return {'ok': True, 'message': 'Scan-Zustand gelöscht.', 'mode': self.mode}

    def handle_reset_long_action(self, source: str = 'reset_long') -> Dict:
        return self.clear_text_fields(source=source)

    def _build_lieferschein_groups_locked(self) -> Dict[str, List[Dict]]:
        grouped = {}
        for group_name in ALL_GROUPS:
            buckets = {}
            for item in self.lieferschein_items[group_name]:
                bucket_key = (item.get('item_type') or '').strip() or 'Ohne Typ'
                bucket = buckets.setdefault(
                    bucket_key,
                    {
                        'item_type': bucket_key,
                        'items': [],
                    },
                )
                bucket['items'].append(deepcopy(item))
            grouped[group_name] = [buckets[key] for key in sorted(buckets)]
        return grouped

    def _build_base_payload_locked(self) -> Dict:
        now = datetime.now()
        payload = {
            'timestamp': now.isoformat(timespec='seconds'),
            'date': now.strftime('%d.%m.%Y'),
            'time': now.strftime('%H:%M:%S'),
            'mode': self.mode,
            'mode_label': MODE_LABELS.get(self.mode, self.mode),
            'operator_name': self.operator_name,
            'operator_name_label': NAME_LABELS.get(self.mode, 'Name'),
            'print_operator_name': bool(self.settings.get('print_operator_name', False)),
            'clear_name_after_print': bool(self.settings.get('clear_name_after_print', False)),
            'reset_after_print': bool(self.settings.get('reset_after_print', True)),
            'show_datetime_on_print': True,
            'print_datetime_placeholder': bool(self.settings.get('print_datetime_placeholder', False)),
            'force_datetime_placeholder': bool(self.force_datetime_placeholder),
            'datetime_placeholder_text': 'Datum: ___.___.______     ___:___ Uhr',
            'print_default_details_without_card': bool(self.settings.get('print_default_details_without_card', True)),
            'print_remarks': bool(self.settings.get('print_remarks', True)),
            'required_groups_complete': self.is_ready_locked() if self.mode == MODE_VERWENDUNGSNACHWEIS else None,
            'required_groups': list(REQUIRED_GROUPS),
            'optional_groups': list(OPTIONAL_GROUPS),
            'required_group_count': len(REQUIRED_GROUPS),
            'optional_group_count': len(OPTIONAL_GROUPS),
            'usage_duration_minutes': self.usage_duration_minutes if self.mode == MODE_VERWENDUNGSNACHWEIS else '',
            'remarks': self.remarks,
            'function_cards': deepcopy(self.function_cards),
            'default_detail_checklist': self.detail_checklist_manager.get_items(),
            'output_layout': self.output_layout_manager.get_layout(),
            'output_field_labels': self.output_layout_manager.get_field_labels(),
            'print_layout': self.print_layout_manager.get_layout(),
            'printer_status': self.thermal_printer_manager.get_status(),
        }
        if self.mode == MODE_LIEFERSCHEIN:
            payload['grouped_items'] = self._build_lieferschein_groups_locked()
            payload['raw_items'] = {group: deepcopy(self.lieferschein_items[group]) for group in ALL_GROUPS if self.lieferschein_items[group]}
        else:
            payload['items'] = {group: deepcopy(self.verwendungsnachweis_slots[group]) for group in ALL_GROUPS if self.verwendungsnachweis_slots[group]}
        return payload

    def build_output_payload_locked(self, include_print_settings: bool = False, copy_count: Optional[int] = None) -> Dict:
        payload = self._build_base_payload_locked()
        if include_print_settings:
            target_copy_count = copy_count if copy_count is not None else DEFAULT_PRINT_COPY_COUNT
            payload['copy_count'] = max(1, int(target_copy_count))
            payload['copy_pause_seconds'] = float(DEFAULT_PRINT_COPY_PAUSE_SECONDS)
        return payload

    def _store_last_payload_locked(self, payload: Dict) -> None:
        stored_payload = sanitize_recursive(deepcopy(payload))
        self.last_print_payload = stored_payload
        self.last_print_path.write_text(json.dumps(stored_payload, indent=2, ensure_ascii=False), encoding='utf-8')

    def _post_print_cleanup_locked(self, source: str) -> None:
        self.usage_duration_minutes = ''
        if self.settings.get('clear_name_after_print', False):
            self.operator_name = ''
            self._log_event('info', 'Name nach Druck automatisch gelöscht.', source='system')
        if self.settings.get('reset_after_print', True):
            self.verwendungsnachweis_slots = {group: [] for group in ALL_GROUPS}
            self.lieferschein_items = {group: [] for group in ALL_GROUPS}
            self.function_cards = []
            self.last_scan = ''
            self.last_normalized_scan = ''
            self._log_event('info', 'Scan-Zustand nach Druck automatisch zurückgesetzt.', source='system')
        self._touch_activity()
        self._set_green_state_locked()

    def _ensure_can_output_locked(self, source: str) -> Optional[Dict]:
        """Prueft vor Druck oder Export, ob ein valider Ausgabezustand vorliegt."""
        if self.system_error_level == 'blocking':
            message = f"Druck gesperrt: {self.system_error or 'kritischer Systemfehler'}"
            self.last_error = message
            self.last_success = ''
            self._log_event('error', message, source=source)
            self._notify_change()
            return {'ok': False, 'message': message}
        if self.is_ready_locked():
            return None
        if self.mode == MODE_LIEFERSCHEIN:
            message = 'Aktion ignoriert: Im Lieferschein-Modus ist noch nichts erfasst.'
        else:
            message = 'Aktion ignoriert: Noch nicht alle Pflichtgruppen sind belegt.'
        self.last_error = message
        self.last_success = ''
        self._log_event('error', message, source=source)
        self._signal_error('generic')
        self._notify_change()
        return {'ok': False, 'message': message}

    def trigger_print(self, source: str = 'button', copy_count: Optional[int] = None) -> Dict:
        self.refresh_health()
        with self.lock:
            failed = self._ensure_can_output_locked(source)
            if failed:
                return failed

            payload = self.build_output_payload_locked(include_print_settings=True, copy_count=copy_count)

        try:
            print_result = self.thermal_printer_manager.print_payload(
                payload,
                copy_count=payload.get('copy_count', DEFAULT_PRINT_COPY_COUNT),
                copy_pause_seconds=payload.get('copy_pause_seconds', DEFAULT_PRINT_COPY_PAUSE_SECONDS),
            )
            export_info = self.export_manager.save(payload)
        except Exception as exc:
            with self.lock:
                self.last_error = f'Druck fehlgeschlagen: {exc}'
                self.last_success = ''
                self._log_event('error', self.last_error, source=source)
                self._signal_error('generic')
            self._notify_change()
            return {'ok': False, 'message': self.last_error}

        with self.lock:
            payload['printed_via'] = print_result.get('device_node', '')
            payload['rendered_print_text'] = print_result.get('rendered_text', '')
            payload['saved_exports'] = export_info
            payload['action'] = 'thermal_print'
            self._store_last_payload_locked(payload)
            self._log_event(
                'success',
                f'Druck ausgelöst ({payload["copy_count"]} Kopie(n) über {print_result.get("device_node", "Drucker")}).',
                source=source,
            )
            self.last_error = ''
            self.last_success = 'Bondruck erfolgreich.'
            self._post_print_cleanup_locked(source)

        self._notify_change()
        return {'ok': True, 'message': 'Bondruck erfolgreich.', 'payload': payload, 'exports': export_info}

    def create_export_files(self, source: str = 'web') -> Dict:
        self.refresh_health()
        with self.lock:
            failed = self._ensure_can_output_locked(source)
            if failed:
                return failed

            payload = self.build_output_payload_locked(include_print_settings=False)
            export_info = self.export_manager.save(payload)
            payload['saved_exports'] = export_info
            payload['action'] = 'export_files'
            self._store_last_payload_locked(payload)
            self._log_event('success', 'TXT- und CSV-Dateien erzeugt.', source=source)
            self.last_error = ''
            self.last_success = 'TXT/CSV erzeugt.'
            self._touch_activity()

        self._notify_change()
        return {'ok': True, 'message': 'TXT/CSV erzeugt.', 'payload': payload, 'exports': export_info}

    def _monitor_worker(self) -> None:
        """Ueberwacht Hintergrundzustand wie Health-Checks und Timeout-Rueckfall."""
        while not self.stop_event.is_set():
            time.sleep(1.0)
            self.refresh_health()
            notify = False
            with self.lock:
                if self.mode == MODE_LIEFERSCHEIN and (time.time() - self.last_activity_at) >= LIEFERSCHEIN_MODE_TIMEOUT_SECONDS:
                    self.mode = MODE_VERWENDUNGSNACHWEIS
                    self.mode_changed_at = time.time()
                    self._clear_scan_payload_locked()
                    timeout_minutes = int(LIEFERSCHEIN_MODE_TIMEOUT_SECONDS / 60)
                    self._log_event('info', f'Lieferschein-Modus nach {timeout_minutes} Minuten Inaktivität beendet.', source='system')
                    self._set_green_state_locked()
                    notify = True
            if notify:
                self._notify_change()

    def get_status(self) -> Dict:
        """Erzeugt einen kompletten Snapshot fuer Weboberflaeche und API."""
        with self.lock:
            active = self._slot_groups_locked()
            snapshot = {
                'operator_name': self.operator_name,
                'usage_duration_minutes': self.usage_duration_minutes,
                'remarks': self.remarks,
                'last_scan': self.last_scan,
                'last_normalized_scan': self.last_normalized_scan,
                'last_error': self.last_error,
                'last_success': self.last_success,
                'system_error': self.system_error,
                'system_error_level': self.system_error_level,
                'force_datetime_placeholder': self.force_datetime_placeholder,
                'mode': self.mode,
                'mode_label': MODE_LABELS.get(self.mode, self.mode),
                'mode_changed_at': datetime.fromtimestamp(self.mode_changed_at).strftime('%Y-%m-%d %H:%M:%S'),
                'last_activity_at': datetime.fromtimestamp(self.last_activity_at).strftime('%Y-%m-%d %H:%M:%S'),
                'ready_to_print': self.is_ready_locked(),
                'can_print': self.is_ready_locked() and self.system_error_level != 'blocking',
                'slots': deepcopy(active),
                'required_slots': {group: deepcopy(active.get(group, [])) for group in REQUIRED_GROUPS},
                'optional_slots': {group: deepcopy(active.get(group, [])) for group in OPTIONAL_GROUPS},
                'events': list(self.events),
                'last_print_payload': deepcopy(self.last_print_payload),
                'required_groups': list(REQUIRED_GROUPS),
                'optional_groups': list(OPTIONAL_GROUPS),
                'all_groups': list(ALL_GROUPS),
                'required_group_count': len(REQUIRED_GROUPS),
                'optional_group_count': len(OPTIONAL_GROUPS),
                'settings': dict(self.settings),
                'group_capacity_verwendungsnachweis': dict(GROUP_CAPACITY_NORMAL_MODE),
                'lieferschein_grouped_items': self._build_lieferschein_groups_locked() if self.mode == MODE_LIEFERSCHEIN else {},
                'function_cards': deepcopy(self.function_cards),
                'function_card_config': self.function_card_manager.list_cards(),
                'default_detail_checklist': self.detail_checklist_manager.get_items(),
                'output_layout': self.output_layout_manager.get_layout(),
                'output_field_labels': self.output_layout_manager.get_field_labels(),
                'config_status': {
                    'function_cards': self.function_card_manager.get_status(),
                    'detail_checklist': self.detail_checklist_manager.get_status(),
                    'output_layout': self.output_layout_manager.get_status(),
                    'print_layout': self.print_layout_manager.get_status(),
                },
                'printer_status': self.thermal_printer_manager.get_status(),
                'gpio_status': self.gpio_controller.get_status() if self.gpio_controller else {},
            }
        return snapshot
