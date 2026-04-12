"""Flask-Webanwendung fuer das Atemschutz-Scan-System.

Das Modul verdrahtet Weboberflaeche, Scanlogik, Hardwaremanager und
Konfigurationsdateien zu einer bedienbaren Anwendung auf dem Raspberry Pi.
"""

import atexit

from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, url_for

from config import (
    BASE_DIR,
    EXPORT_DIR,
    HOST,
    MODE_LABELS,
    MODE_LIEFERSCHEIN,
    MODE_VERWENDUNGSNACHWEIS,
    OPTIONAL_GROUPS,
    PORT,
    PROJECT_NAME,
    REQUIRED_GROUPS,
    SECRET_KEY,
)
from database import DatabaseManager
from detail_checklist_manager import DetailChecklistManager
from export_manager import ExportManager
from function_card_manager import FunctionCardManager
from gpio_controller import GPIOController
from output_layout_manager import OutputLayoutManager
from print_layout_manager import PrintLayoutManager
from scanner_input import ScannerManager, discover_input_devices
from settings_manager import SettingsManager
from system_health import collect_blocking_print_errors, validate_system_time
from thermal_printer import ThermalPrinterManager
from state_manager import ScanStateManager

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

FAVICON_PATH = BASE_DIR / 'static' / 'thw-zahnkranz.png'


def log(message: str) -> None:
    print(message, flush=True)


startup_faults = []

# Die Manager werden einmal zentral aufgebaut und danach in App, Weboberflaeche
# und Scanlogik gemeinsam verwendet.
db_manager = DatabaseManager()
settings_manager = SettingsManager()
function_card_manager = FunctionCardManager()
detail_checklist_manager = DetailChecklistManager()
output_layout_manager = OutputLayoutManager()
print_layout_manager = PrintLayoutManager()
export_manager = ExportManager(print_layout_manager=print_layout_manager)
thermal_printer_manager = ThermalPrinterManager(print_layout_manager=print_layout_manager)
try:
    db_manager.initialize()
except Exception as exc:
    startup_faults.append(f'Datenbankinitialisierung fehlgeschlagen: {exc}')
    log(f'[DB] FEHLER: {exc}')

for manager_name, manager in (
    ('Funktionskarten', function_card_manager),
    ('Checkliste', detail_checklist_manager),
    ('Ausgabelayout', output_layout_manager),
    ('Drucklayout', print_layout_manager),
):
    error_message = getattr(manager, 'last_error', '')
    if error_message:
        startup_faults.append(f'{manager_name}: {error_message}')
        log(f'[{manager_name}] FEHLER: {error_message}')

try:
    # Beim Start wird die SQLite-Datenbank aus der pflegbaren CSV aufgebaut.
    # Fehlt die CSV, wird zumindest eine leere Export-Datei bereitgestellt.
    if db_manager.csv_path.exists() and db_manager.csv_path.stat().st_size > 0:
        imported_count = db_manager.import_from_csv()
        log(f'[DB] CSV importiert: {imported_count} Datensätze aus {db_manager.csv_path}')
    else:
        exported_count = db_manager.export_to_csv()
        log(f'[DB] Keine CSV gefunden. Leere CSV exportiert nach {db_manager.csv_path} ({exported_count} Datensätze).')
except Exception as exc:
    startup_faults.append(f'Datenbank/CSV-Import fehlgeschlagen: {exc}')
    log(f'[DB] FEHLER: {exc}')

gpio_controller = GPIOController()
state_manager = ScanStateManager(
    db_manager=db_manager,
    settings_manager=settings_manager,
    export_manager=export_manager,
    function_card_manager=function_card_manager,
    detail_checklist_manager=detail_checklist_manager,
    output_layout_manager=output_layout_manager,
    print_layout_manager=print_layout_manager,
    thermal_printer_manager=thermal_printer_manager,
    gpio_controller=gpio_controller,
)


def evaluate_system_health():
    active_settings = dict(state_manager.settings)
    blocking_errors = collect_blocking_print_errors(
        db_manager=db_manager,
        settings_manager=settings_manager,
        function_card_manager=function_card_manager,
        detail_checklist_manager=detail_checklist_manager,
        output_layout_manager=output_layout_manager,
        print_layout_manager=print_layout_manager,
        export_manager=export_manager,
        thermal_printer_manager=thermal_printer_manager,
        last_print_path=state_manager.last_print_path,
        startup_faults=startup_faults,
    )
    time_status = validate_system_time()
    warnings = []
    force_datetime_placeholder = False
    if not time_status['valid']:
        warnings.append(time_status['message'])
        force_datetime_placeholder = True
    return {
        'blocking_errors': blocking_errors,
        'warnings': warnings,
        'force_datetime_placeholder': force_datetime_placeholder,
    }


state_manager.health_check_callback = evaluate_system_health
state_manager.refresh_health()


def handle_scanned_code(code: str, source: str) -> None:
    result = state_manager.handle_scan(code, source=source)
    log(f'[SCAN] {source}: {code} -> {result}')


def trigger_print_action(source: str = 'web', copy_count: int = None):
    result = state_manager.trigger_print(source=source, copy_count=copy_count)
    log(f'[PRINT] {source}: {result}')
    return result


def trigger_export_action(source: str = 'web'):
    result = state_manager.create_export_files(source=source)
    log(f'[EXPORT] {source}: {result}')
    return result


def trigger_reset_action(source: str = 'web'):
    result = state_manager.handle_reset_action(source=source)
    log(f'[RESET] {source}: {result}')
    return result


def trigger_reset_long_action(source: str = 'web'):
    result = state_manager.handle_reset_long_action(source=source)
    log(f'[RESET_LONG] {source}: {result}')
    return result


def trigger_mode_toggle(source: str = 'web'):
    result = state_manager.toggle_mode(source=source)
    log(f'[MODE] {source}: {result}')
    return result


gpio_controller.on_print_pressed = trigger_print_action
gpio_controller.on_reset_pressed = trigger_reset_action
gpio_controller.on_reset_long_pressed = trigger_reset_long_action
gpio_controller.on_mode_pressed = trigger_mode_toggle
try:
    gpio_controller.initialize()
except Exception as exc:
    state_manager.set_system_error(f'GPIO-Initialisierung fehlgeschlagen: {exc}')
    log(f'[GPIO] FEHLER: {exc}')
gpio_controller.set_system_fault_level(state_manager.system_error_level)
gpio_controller.set_listing_mode(state_manager.mode == MODE_LIEFERSCHEIN)
gpio_controller.set_ready(state_manager.get_status()['ready_to_print'])

runtime_settings = settings_manager.load()
scanner_manager = ScannerManager(on_scan=handle_scanned_code, device_paths=runtime_settings.get('scanner_device_paths'))
scanner_manager.start()


@app.context_processor
def inject_globals():
    return {
        'project_name': PROJECT_NAME,
        'required_groups': REQUIRED_GROUPS,
        'optional_groups': OPTIONAL_GROUPS,
        'mode_labels': MODE_LABELS,
        'mode_verwendungsnachweis': MODE_VERWENDUNGSNACHWEIS,
        'mode_lieferschein': MODE_LIEFERSCHEIN,
        'favicon_available': FAVICON_PATH.exists(),
    }


def build_page_context():
    """Sammelt alle Daten, die mehrere Seiten gemeinsam benoetigen."""
    return {
        'status': state_manager.get_status(),
        'scanner_status': scanner_manager.get_status(),
        'db_summary': db_manager.get_summary(),
        'exports': export_manager.list_exports(),
        'printer_status': thermal_printer_manager.get_status(),
    }


def _parse_copy_count() -> int:
    try:
        return max(1, int(request.form.get('copy_count', '1') or '1'))
    except Exception:
        return 1


@app.route('/')
def index():
    return render_template('index.html', title=PROJECT_NAME, **build_page_context())


@app.route('/druckdaten')
def print_data_view():
    return render_template('print_data.html', title=f'{PROJECT_NAME} – Ausgabe', **build_page_context())


@app.route('/system')
def system_view():
    return render_template(
        'scanner.html',
        title=f'{PROJECT_NAME} – System',
        available_devices=discover_input_devices(),
        **build_page_context(),
    )


@app.route('/scanner')
def scanner_view():
    return redirect(url_for('system_view'))


@app.route('/meta/save', methods=['POST'])
def save_meta():
    state_manager.update_meta(
        operator_name=request.form.get('operator_name', ''),
        usage_duration_minutes=request.form.get('usage_duration_minutes', ''),
        remarks=request.form.get('remarks', ''),
        source='web',
        log_event=True,
    )
    flash('Personen- und Einsatzdaten gespeichert.', 'success')
    return redirect(url_for('index'))


@app.route('/api/meta', methods=['POST'])
def api_save_meta():
    state_manager.update_meta(
        operator_name=request.form.get('operator_name', ''),
        usage_duration_minutes=request.form.get('usage_duration_minutes', ''),
        remarks=request.form.get('remarks', ''),
        source='web_autosave',
        log_event=False,
    )
    return jsonify({'ok': True, 'status': state_manager.get_status()})


@app.route('/name/clear', methods=['POST'])
def clear_name():
    result = state_manager.clear_operator_name(source='web_name_clear')
    flash(result['message'], 'success')
    return redirect(url_for('index'))


@app.route('/remarks/clear', methods=['POST'])
def clear_remarks():
    result = state_manager.clear_remarks(source='web_remarks_clear')
    flash(result['message'], 'success')
    return redirect(url_for('index'))


@app.route('/text/clear', methods=['POST'])
def clear_text_fields():
    result = trigger_reset_long_action(source='web_clear_text')
    flash(result['message'], 'success')
    return redirect(url_for('index'))


@app.route('/settings/save', methods=['POST'])
def save_settings():
    state_manager.update_settings(
        reset_after_print=request.form.get('reset_after_print') == '1',
        clear_name_after_print=request.form.get('clear_name_after_print') == '1',
        print_datetime_placeholder=request.form.get('print_datetime_placeholder') == '1',
        print_default_details_without_card=request.form.get('print_default_details_without_card') == '1',
        print_remarks=request.form.get('print_remarks') == '1',
        source='web',
        log_event=True,
    )
    flash('Einstellungen gespeichert.', 'success')
    return redirect(url_for('index'))


@app.route('/api/settings', methods=['POST'])
def api_save_settings():
    settings = state_manager.update_settings(
        reset_after_print=request.form.get('reset_after_print') == '1',
        clear_name_after_print=request.form.get('clear_name_after_print') == '1',
        print_datetime_placeholder=request.form.get('print_datetime_placeholder') == '1',
        print_default_details_without_card=request.form.get('print_default_details_without_card') == '1',
        print_remarks=request.form.get('print_remarks') == '1',
        source='web_autosave',
        log_event=False,
    )
    return jsonify({'ok': True, 'settings': settings})


@app.route('/toggle-mode', methods=['POST'])
def toggle_mode():
    result = trigger_mode_toggle(source='web_mode_button')
    flash(result['message'], 'success')
    return redirect(url_for('index'))


@app.route('/trigger-print', methods=['POST'])
def trigger_print():
    copy_count = _parse_copy_count()
    result = trigger_print_action(source='web_print_button', copy_count=copy_count)
    flash(result['message'], 'success' if result['ok'] else 'error')
    return redirect(url_for('index'))


@app.route('/create-files', methods=['POST'])
def create_files():
    result = trigger_export_action(source='web_export_button')
    flash(result['message'], 'success' if result['ok'] else 'error')
    return redirect(url_for('index'))


@app.route('/reset', methods=['POST'])
def reset():
    result = trigger_reset_action(source='web_reset_button')
    flash(result['message'], 'success')
    return redirect(url_for('index'))


@app.route('/database')
def database_view():
    return render_template('database.html', title=f'{PROJECT_NAME} – Datenbank', items=db_manager.list_items())


@app.route('/database/save', methods=['POST'])
def database_save():
    raw_group = request.form.get('raw_group', '').strip()
    item_type = request.form.get('item_type', '').strip()
    inventarnummer = request.form.get('inventarnummer', '').strip()
    fabriknummer = request.form.get('fabriknummer', '').strip()
    geraetenummer = request.form.get('geraetenummer', '').strip()
    lf_scan = request.form.get('lf_scan', '').strip()
    bemerkung = request.form.get('bemerkung', '').strip()
    item_id_raw = request.form.get('item_id', '').strip()
    is_active = 1 if request.form.get('is_active') == '1' else 0

    if not raw_group or not (inventarnummer or fabriknummer or lf_scan):
        flash('Gruppe und mindestens eine scanbare Kennung sind Pflichtfelder.', 'error')
        return redirect(url_for('database_view'))

    item_id = int(item_id_raw) if item_id_raw else None

    db_manager.upsert_item(
        item_id=item_id,
        raw_group=raw_group,
        item_type=item_type,
        inventarnummer=inventarnummer,
        fabriknummer=fabriknummer,
        geraetenummer=geraetenummer,
        lf_scan=lf_scan,
        bemerkung=bemerkung,
        is_active=is_active,
    )
    db_manager.export_to_csv()
    flash('Datensatz gespeichert und CSV aktualisiert.', 'success')
    return redirect(url_for('database_view'))


@app.route('/database/delete/<int:item_id>', methods=['POST'])
def database_delete(item_id: int):
    db_manager.delete_item(item_id)
    db_manager.export_to_csv()
    flash(f'Datensatz {item_id} gelöscht.', 'success')
    return redirect(url_for('database_view'))


@app.route('/database/import-csv', methods=['POST'])
def database_import_csv():
    count = db_manager.import_from_csv()
    if count:
        flash(f'CSV importiert: {count} Datensätze.', 'success')
    else:
        flash(f'CSV leer oder nicht lesbar: {db_manager.csv_path}', 'error')
    return redirect(url_for('database_view'))


@app.route('/scanner/save', methods=['POST'])
def scanner_save():
    scanner_1 = request.form.get('scanner_1', '').strip()
    scanner_2 = request.form.get('scanner_2', '').strip()
    device_paths = [path for path in [scanner_1, scanner_2] if path]
    if not device_paths:
        flash('Mindestens ein Scanner-Pfad ist erforderlich.', 'error')
        return redirect(url_for('system_view'))
    new_settings = state_manager.update_settings(scanner_device_paths=device_paths, source='web_scanner_save', log_event=True)
    scanner_manager.reload(new_settings['scanner_device_paths'])
    flash('Scanner-Konfiguration gespeichert und neu geladen.', 'success')
    return redirect(url_for('system_view'))


@app.route('/function-cards/reload', methods=['POST'])
def reload_function_cards():
    function_card_manager.load()
    detail_checklist_manager.load()
    output_layout_manager.load()
    print_layout_manager.load()

    errors = [
        function_card_manager.last_error,
        detail_checklist_manager.last_error,
        output_layout_manager.last_error,
        print_layout_manager.last_error,
    ]
    warnings = [message for message in [function_card_manager.last_warning] if message]

    if function_card_manager.last_error or detail_checklist_manager.last_error or output_layout_manager.last_error or print_layout_manager.last_error:
        for message in errors:
            if message:
                flash(message, 'error')
    else:
        flash(
            (
                'Neu geladen: '
                f'{len(function_card_manager.list_cards())} Funktionskarten, '
                f'{len(detail_checklist_manager.get_items())} Checklisten-Einträge, '
                f'{len(output_layout_manager.get_layout())} Layout-Gruppen, '
                f'{len(print_layout_manager.get_layout().get("styles", {}))} Druckstile.'
            ),
            'success',
        )

    for message in warnings:
        flash(message, 'warning')

    return redirect(url_for('scanner_view'))


@app.route('/exports/delete-all', methods=['POST'])
def delete_all_exports():
    deleted = export_manager.clear_exports()
    flash(f'{deleted} TXT/CSV-Datei(en) gelöscht.' if deleted else 'Keine TXT/CSV-Dateien zum Löschen vorhanden.', 'success')
    return redirect(url_for('print_data_view'))


@app.route('/exports/<path:filename>')
def download_export(filename: str):
    return send_from_directory(EXPORT_DIR, filename, as_attachment=True)


@app.route('/api/status')
def api_status():
    return jsonify(
        {
            'status': state_manager.get_status(),
            'scanner_status': scanner_manager.get_status(),
            'database': db_manager.get_summary(),
            'exports': export_manager.list_exports(),
            'printer_status': thermal_printer_manager.get_status(),
        }
    )


@atexit.register
def cleanup():
    scanner_manager.stop()
    state_manager.stop()
    gpio_controller.cleanup()


if __name__ == '__main__':
    app.run(host=HOST, port=PORT, debug=False)
