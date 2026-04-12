"""Pruefungen fuer Systemzustand, Uhrzeit und druckrelevante Fehler."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

from config import SYSTEM_TIME_MAX_YEAR, SYSTEM_TIME_MIN_YEAR


def validate_system_time(now: datetime | None = None) -> Dict:
    current = now or datetime.now()
    valid = SYSTEM_TIME_MIN_YEAR <= current.year <= SYSTEM_TIME_MAX_YEAR
    message = '' if valid else f'Systemzeit unplausibel ({current.strftime("%d.%m.%Y %H:%M:%S")}). Datum/Uhrzeit-Platzhalter wird verwendet.'
    return {
        'valid': bool(valid),
        'message': message,
        'current_timestamp': current.isoformat(timespec='seconds'),
        'current_display': current.strftime('%d.%m.%Y %H:%M:%S'),
    }


def _is_readable_file(path: Path) -> bool:
    return path.exists() and path.is_file() and os.access(path, os.R_OK)


def _is_writable_target(path: Path) -> bool:
    target = Path(path)
    if target.exists():
        return os.access(target, os.R_OK | os.W_OK)
    parent = target.parent
    return parent.exists() and parent.is_dir() and os.access(parent, os.W_OK)


def collect_blocking_print_errors(
    *,
    db_manager,
    settings_manager,
    function_card_manager,
    detail_checklist_manager,
    output_layout_manager,
    print_layout_manager,
    export_manager,
    thermal_printer_manager,
    last_print_path,
    startup_faults: Iterable[str] | None = None,
) -> List[str]:
    errors: List[str] = [str(message).strip() for message in (startup_faults or []) if str(message).strip()]

    required_files = [
        ('Datenbankdatei', Path(db_manager.db_path)),
        ('CSV-Datei', Path(db_manager.csv_path)),
        ('Datenbankschema', Path(db_manager.schema_path)),
        ('Funktionskarten-Datei', Path(function_card_manager.path)),
        ('Checklisten-Datei', Path(detail_checklist_manager.path)),
        ('Ausgabelayout-Datei', Path(output_layout_manager.path)),
        ('Drucklayout-Datei', Path(print_layout_manager.path)),
    ]
    for label, path in required_files:
        if not _is_readable_file(path):
            errors.append(f'{label} fehlt oder ist nicht lesbar: {path}')

    writable_targets = [
        ('Datenbankdatei', Path(db_manager.db_path)),
        ('CSV-Datei', Path(db_manager.csv_path)),
        ('Einstellungsdatei', Path(settings_manager.path)),
        ('Letzte-Druckdaten-Datei', Path(last_print_path)),
    ]
    for label, path in writable_targets:
        if not _is_writable_target(path):
            errors.append(f'{label} ist nicht schreibbar: {path}')

    export_dir = Path(export_manager.export_dir)
    if not export_dir.exists() or not export_dir.is_dir() or not os.access(export_dir, os.W_OK):
        errors.append(f'Export-Verzeichnis ist nicht schreibbar: {export_dir}')

    printer_node = Path(thermal_printer_manager.device_node)
    if not printer_node.exists():
        errors.append(f'Bondrucker-Device fehlt: {printer_node}')
    elif not os.access(printer_node, os.W_OK):
        errors.append(f'Bondrucker-Device ist nicht schreibbar: {printer_node}')

    for label, manager in (
        ('Funktionskarten', function_card_manager),
        ('Checkliste', detail_checklist_manager),
        ('Ausgabelayout', output_layout_manager),
        ('Drucklayout', print_layout_manager),
    ):
        manager_error = str(getattr(manager, 'last_error', '') or '').strip()
        if manager_error:
            errors.append(f'{label}: {manager_error}')

    try:
        db_manager.get_summary()
    except Exception as exc:
        errors.append(f'Datenbankproblem: {exc}')

    deduped: List[str] = []
    seen = set()
    for message in errors:
        if message not in seen:
            seen.add(message)
            deduped.append(message)
    return deduped
