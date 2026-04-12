"""Verwaltet Drucklayout, Labels und Stildefinitionen fuer den Bondruck."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from config import ALL_GROUPS, PRINT_LAYOUT_PATH

def _style_preset(
    size: str,
    *,
    align: str = 'left',
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
) -> Dict[str, Any]:
    presets = {
        'small': {'font': 'b', 'width': 1, 'height': 1, 'wrap_width': 42, 'line_spacing_dots': 24},
        'medium': {'font': 'a', 'width': 1, 'height': 1, 'wrap_width': 32},
        'large': {'font': 'a', 'width': 1, 'height': 2, 'wrap_width': 32},
    }
    preset = dict(presets.get(str(size).strip().lower(), presets['medium']))
    preset.update(
        {
            'align': align,
            'bold': bool(bold),
            'italic': bool(italic),
            'underline': bool(underline),
        }
    )
    return preset


DEFAULT_PRINT_LAYOUT = {
    'device': {
        'paper_width': 32,
        'line_ending': '\r\n',
        'line_feeds_after_print': 6,
    },
    'styles': {
        'header_title': _style_preset('large', align='center', bold=True),
        'header_subtitle': _style_preset('small', align='center'),
        'document_title': _style_preset('medium', align='center', bold=True),
        'meta_primary': _style_preset('medium', bold=True),
        'meta_label_compact': {**_style_preset('medium', bold=True), 'line_spacing_dots': 20},
        'section_heading': _style_preset('medium', bold=True),
        'group_heading': _style_preset('small', bold=True),
        'material_body': _style_preset('small'),
        'details_body': _style_preset('small'),
        'remarks_body': _style_preset('small'),
        'spacer': _style_preset('medium'),
    },
    'content': {
        'header': {
            'heading': {'text': 'THW OV Donaueschingen', 'style': 'header_title', 'spacing_before': 0, 'spacing_after': 0},
            'subheading': {'text': 'Atemschutz-Scan-System', 'style': 'header_subtitle', 'spacing_before': 0, 'spacing_after': 0},
        },
        'mode': {
            'style': 'document_title',
            'spacing_before': 0,
            'spacing_after': 1,
            'labels': {
                'lieferschein': 'Lieferschein',
                'verwendungsnachweis': 'Verwendungsnachweis',
            },
        },
        'meta': {
            'operator_name': {
                'style': 'meta_primary',
                'label_style': 'meta_label_compact',
                'spacing_before': 0,
                'spacing_after': 0,
                'labels': {
                    'lieferschein': 'Erfasser',
                    'verwendungsnachweis': 'Geraetetraeger/-in',
                },
                'value_key': 'operator_name',
                'empty_placeholder_length': 31,
                'filled_template': '{label}: {value}',
                'filled_value_on_next_line': True,
                'filled_label_template': '{label}:',
                'filled_value_indent': '  ',
                'empty_template': '{label}: {placeholder}',
            },
            'datetime': {
                'style': 'meta_primary',
                'spacing_before': 0,
                'spacing_after': 0,
                'label': 'Datum',
                'date_placeholder_label': 'Datum',
                'time_placeholder_label': 'Uhrzeit',
                'template': '{label}: {date} {time}',
                'date_placeholder_template': '{label}: {placeholder}',
                'time_placeholder_template': '{label}: {placeholder} Uhr',
                'date_placeholder_length': 24,
                'time_placeholder_length': 18,
            },
            'usage_duration': {
                'style': 'meta_primary',
                'spacing_before': 0,
                'spacing_after': 0,
                'show_only_in_mode': 'verwendungsnachweis',
                'label': 'Einsatzdauer',
                'value_key': 'usage_duration_minutes',
                'filled_template': '{label}: {value}',
                'filled_value_on_next_line': True,
                'filled_label_template': '{label}:',
                'filled_value_indent': '  ',
                'empty_template': '{label}: {placeholder} min',
                'placeholder_length': 10,
                'append_suffix_if_numeric': ' min',
            },
        },
        'field_labels': {
            'item_type': 'Typ',
            'inventarnummer': 'Inv.-Nr.',
            'fabriknummer': 'Fabr.-Nr.',
            'geraetenummer': 'Serien-Nr.',
            'lf_scan': 'LF-Scan',
            'bemerkung': 'Bem.',
        },
        'sections': {
            'material': {
                'title': 'Material',
                'title_style': 'section_heading',
                'spacing_before': 1,
                'spacing_after': 0,
                'group_spacing_before': 0,
                'group_spacing_after': 0,
                'item_spacing_after': 0,
                'item_prefix_template': '{index}) ',
                'item_body_indent': '   ',
                'group_title_style': 'group_heading',
                'item_style': 'material_body',
                'empty_text': '-',
                'groups': {
                    'Atem-Druckluftflasche': {'title': 'Flasche', 'fields': ['item_type', 'inventarnummer', 'lf_scan', 'bemerkung']},
                    'Vollmaske': {'title': 'Vollmaske', 'fields': ['item_type', 'inventarnummer', 'fabriknummer', 'bemerkung']},
                    'Pressluftatmer': {'title': 'Pressluftatmer', 'fields': ['item_type', 'inventarnummer', 'bemerkung']},
                    'Lungenautomat': {'title': 'Lungenautomat', 'fields': ['item_type', 'inventarnummer', 'fabriknummer', 'bemerkung']},
                    'Mitteldruckverlängerung': {'title': 'MD-Verlaengerung', 'fields': ['item_type', 'inventarnummer', 'bemerkung']},
                },
                'group_order': list(ALL_GROUPS),
            },
            'function_cards': {
                'title': 'Einsatz- & Übungsdetails',
                'title_style': 'section_heading',
                'spacing_before': 1,
                'spacing_after': 0,
                'body_style': 'details_body',
                'empty_text': '-',
                'card_prefix': '- ',
                'card_continuation': '  ',
                'checklist_prefix': '[ ] ',
                'checklist_continuation': '    ',
                'single_line_items': ['Mit Gefahrstoffen beaufschlagt'],
            },
            'remarks': {
                'title': 'Bemerkungen',
                'title_style': 'section_heading',
                'spacing_before': 1,
                'spacing_after': 0,
                'body_style': 'remarks_body',
                'empty_write_lines': 2,
                'write_line_length': 38,
                'write_line_gap': 1,
            },
        },
    },
}


class PrintLayoutManager:
    def __init__(self, path: Path = PRINT_LAYOUT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.layout: Dict[str, Any] = {}
        self.last_error = ''
        self.load()

    def _deep_merge(self, base: Any, override: Any) -> Any:
        if isinstance(base, dict) and isinstance(override, dict):
            merged = {key: deepcopy(value) for key, value in base.items()}
            for key, value in override.items():
                if key in merged:
                    merged[key] = self._deep_merge(merged[key], value)
                else:
                    merged[str(key)] = deepcopy(value)
            return merged
        if isinstance(base, list):
            return deepcopy(override) if isinstance(override, list) else deepcopy(base)
        return deepcopy(override) if override is not None else deepcopy(base)

    def _normalize_style(self, raw_value: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
        style = dict(fallback)
        if not isinstance(raw_value, dict):
            return style
        align = str(raw_value.get('align', style.get('align', 'left'))).strip().lower()
        style['align'] = align if align in {'left', 'center', 'right'} else style.get('align', 'left')
        font = str(raw_value.get('font', style.get('font', 'a'))).strip().lower()
        style['font'] = font if font in {'a', 'b'} else style.get('font', 'a')
        for key in ('bold', 'italic', 'underline'):
            style[key] = bool(raw_value.get(key, style.get(key, False)))
        for key, minimum, maximum in (('width', 1, 8), ('height', 1, 8), ('wrap_width', 16, 128)):
            try:
                style[key] = max(minimum, min(maximum, int(raw_value.get(key, style.get(key, minimum)))))
            except Exception:
                style[key] = int(style.get(key, minimum))
        if 'line_spacing_dots' in style or (isinstance(raw_value, dict) and 'line_spacing_dots' in raw_value):
            try:
                current = raw_value.get('line_spacing_dots', style.get('line_spacing_dots'))
                style['line_spacing_dots'] = max(0, min(255, int(current))) if current is not None else None
            except Exception:
                style['line_spacing_dots'] = style.get('line_spacing_dots')
        return style

    def _normalize_layout(self, raw_value: Dict[str, Any]) -> Dict[str, Any]:
        base = deepcopy(DEFAULT_PRINT_LAYOUT)
        if not isinstance(raw_value, dict):
            raw_value = {}
        merged = self._deep_merge(base, raw_value)

        device = merged.get('device', {})
        try:
            device['paper_width'] = max(24, min(64, int(device.get('paper_width', 32))))
        except Exception:
            device['paper_width'] = base['device']['paper_width']
        device['line_ending'] = str(device.get('line_ending', '\r\n') or '\r\n')
        try:
            device['line_feeds_after_print'] = max(0, min(255, int(device.get('line_feeds_after_print', 15))))
        except Exception:
            device['line_feeds_after_print'] = base['device']['line_feeds_after_print']
        merged['device'] = device

        normalized_styles: Dict[str, Any] = {}
        raw_styles = merged.get('styles', {}) if isinstance(merged.get('styles'), dict) else {}
        for style_name, fallback in base['styles'].items():
            normalized_styles[style_name] = self._normalize_style(raw_styles.get(style_name), fallback)
        for style_name, raw_style in raw_styles.items():
            if style_name not in normalized_styles and isinstance(raw_style, dict):
                normalized_styles[style_name] = self._normalize_style(raw_style, base['styles']['spacer'])
        merged['styles'] = normalized_styles

        material = (((merged.get('content') or {}).get('sections') or {}).get('material') or {})
        group_order = []
        seen = set()
        for entry in material.get('group_order', []):
            name = str(entry).strip()
            if name in ALL_GROUPS and name not in seen:
                group_order.append(name)
                seen.add(name)
        for entry in ALL_GROUPS:
            if entry not in seen:
                group_order.append(entry)
        material['group_order'] = group_order
        if 'groups' not in material or not isinstance(material['groups'], dict):
            material['groups'] = deepcopy(base['content']['sections']['material']['groups'])
        merged['content']['sections']['material'] = material
        return merged

    def load(self) -> None:
        try:
            if not self.path.exists():
                self.layout = deepcopy(DEFAULT_PRINT_LAYOUT)
                self.path.write_text(json.dumps(self.layout, indent=2, ensure_ascii=False), encoding='utf-8')
                self.last_error = ''
                return
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            self.layout = self._normalize_layout(raw)
            self.last_error = ''
        except Exception as exc:
            self.layout = deepcopy(DEFAULT_PRINT_LAYOUT)
            self.last_error = str(exc)

    def get_layout(self) -> Dict[str, Any]:
        return deepcopy(self.layout)

    def get_status(self) -> Dict[str, Any]:
        device = self.layout.get('device', {})
        return {
            'path': str(self.path),
            'paper_width': int(device.get('paper_width', DEFAULT_PRINT_LAYOUT['device']['paper_width'])),
            'line_feeds_after_print': int(device.get('line_feeds_after_print', DEFAULT_PRINT_LAYOUT['device']['line_feeds_after_print'])),
            'last_error': self.last_error,
        }
