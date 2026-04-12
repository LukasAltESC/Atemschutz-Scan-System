"""Renderer fuer Bondruck, Textansicht und Exportdarstellung.

Das Modul formt den fachlichen Payload in Zeilen um und beachtet dabei Layout,
Textumbruch, Platzhalter und Materialgruppierung.
"""

import textwrap
from copy import deepcopy
from typing import Any, Dict, List, Optional

from ascii_utils import to_ascii_text
from config import ALL_GROUPS, MODE_LIEFERSCHEIN, MODE_VERWENDUNGSNACHWEIS


class TicketRenderer:
    """Formt den Status-Payload in formatierte Zeilen fuer Ausgabe und Export um."""

    def _clean_text(self, value: Any, ascii_only: bool = False) -> str:
        text = str(value or '').strip()
        return to_ascii_text(text) if ascii_only else text

    def _make_line(self, text: str = '', style: str = 'spacer', **extra: Any) -> Dict[str, Any]:
        line: Dict[str, Any] = {'text': str(text or '').rstrip(), 'style': style}
        line.update(extra)
        return line

    def _style_cfg(self, layout: Dict[str, Any], style_name: str) -> Dict[str, Any]:
        return dict((layout.get('styles') or {}).get(style_name, {}))

    def _wrap_width(self, layout: Dict[str, Any], style_name: str) -> int:
        style = self._style_cfg(layout, style_name)
        return max(16, int(style.get('wrap_width', self._paper_width(layout))))

    def _paper_width(self, layout: Dict[str, Any]) -> int:
        device = layout.get('device') or {}
        return max(24, int(device.get('paper_width', 32) or 32))

    def _align(self, layout: Dict[str, Any], style_name: str) -> str:
        align = str(self._style_cfg(layout, style_name).get('align', 'left')).strip().lower()
        return align if align in {'left', 'center', 'right'} else 'left'

    def _align_text(self, text: str, width: int, align: str) -> str:
        if not text:
            return ''
        if align == 'center':
            return text.center(width)
        if align == 'right':
            return text.rjust(width)
        return text

    def _wrap_text(
        self,
        text: str,
        width: int,
        initial_indent: str = '',
        subsequent_indent: Optional[str] = None,
        force_single_line: bool = False,
    ) -> List[str]:
        cleaned = str(text or '').strip()
        if not cleaned:
            return []
        if subsequent_indent is None:
            subsequent_indent = initial_indent
        if force_single_line:
            return [f'{initial_indent}{cleaned}']
        first_width = max(8, width - len(initial_indent))
        wrapped = textwrap.wrap(
            cleaned,
            width=first_width,
            break_long_words=False,
            break_on_hyphens=False,
            replace_whitespace=False,
        ) or ['']
        lines = [f'{initial_indent}{wrapped[0]}']
        continuation_width = max(8, width - len(subsequent_indent))
        for part in wrapped[1:]:
            pieces = textwrap.wrap(
                part,
                width=continuation_width,
                break_long_words=False,
                break_on_hyphens=False,
                replace_whitespace=False,
            ) or ['']
            lines.extend(f'{subsequent_indent}{piece}' for piece in pieces)
        return lines

    def _placeholder(self, length: int, suffix: str = '') -> str:
        return ('_' * max(4, int(length or 4))) + suffix

    def _content(self, layout: Dict[str, Any]) -> Dict[str, Any]:
        return dict(layout.get('content') or {})

    def _add_spacing(self, lines: List[Dict[str, str]], count: int, style: str = 'spacer') -> None:
        for _ in range(max(0, int(count or 0))):
            lines.append(self._make_line('', style))

    def _field_labels(self, layout: Dict[str, Any]) -> Dict[str, str]:
        return dict((self._content(layout).get('field_labels') or {}))

    def _material_config(self, layout: Dict[str, Any]) -> Dict[str, Any]:
        sections = (self._content(layout).get('sections') or {})
        return dict(sections.get('material') or {})

    def _details_config(self, layout: Dict[str, Any]) -> Dict[str, Any]:
        sections = (self._content(layout).get('sections') or {})
        return dict(sections.get('function_cards') or {})

    def _remarks_config(self, layout: Dict[str, Any]) -> Dict[str, Any]:
        sections = (self._content(layout).get('sections') or {})
        return dict(sections.get('remarks') or {})

    def _material_group_order(self, layout: Dict[str, Any]) -> List[str]:
        material = self._material_config(layout)
        configured = [str(name).strip() for name in material.get('group_order', []) if str(name).strip()]
        if configured:
            return configured
        return list(ALL_GROUPS)

    def _iter_group_items(self, payload: Dict[str, Any], group_name: str) -> List[Dict[str, Any]]:
        if payload.get('mode') == MODE_LIEFERSCHEIN:
            return list((payload.get('raw_items') or {}).get(group_name, []))
        return list((payload.get('items') or {}).get(group_name, []))

    def _group_cfg(self, layout: Dict[str, Any], group_name: str) -> Dict[str, Any]:
        material = self._material_config(layout)
        groups = material.get('groups') or {}
        return dict(groups.get(group_name) or {})

    def _group_title(self, layout: Dict[str, Any], group_name: str, ascii_only: bool = False) -> str:
        title = str(self._group_cfg(layout, group_name).get('title') or group_name).strip()
        return to_ascii_text(title) if ascii_only else title

    def _field_label(self, layout: Dict[str, Any], payload: Dict[str, Any], field_name: str, ascii_only: bool = False) -> str:
        label = self._field_labels(layout).get(field_name) or (payload.get('output_field_labels') or {}).get(field_name) or field_name
        label = str(label).strip()
        return to_ascii_text(label) if ascii_only else label

    def _print_fields(self, layout: Dict[str, Any], group_name: str) -> List[str]:
        group_cfg = self._group_cfg(layout, group_name)
        fields = group_cfg.get('fields') or []
        return [str(field).strip() for field in fields if str(field).strip()]

    def _render_header(self, payload: Dict[str, Any], layout: Dict[str, Any], ascii_only: bool) -> List[Dict[str, str]]:
        del payload
        content = self._content(layout)
        header = content.get('header') or {}
        paper_width = self._paper_width(layout)
        lines: List[Dict[str, str]] = []
        for key in ('heading', 'subheading'):
            block = header.get(key) or {}
            text = self._clean_text(block.get('text', ''), ascii_only=ascii_only)
            style = str(block.get('style', 'spacer'))
            if not text:
                continue
            self._add_spacing(lines, block.get('spacing_before', 0))
            aligned = self._align_text(text, paper_width, self._align(layout, style))
            lines.append(self._make_line(aligned, style))
            self._add_spacing(lines, block.get('spacing_after', 0))
        return lines

    def _render_mode(self, payload: Dict[str, Any], layout: Dict[str, Any], ascii_only: bool) -> List[Dict[str, str]]:
        content = self._content(layout)
        mode_cfg = content.get('mode') or {}
        style = str(mode_cfg.get('style', 'document_title'))
        labels = mode_cfg.get('labels') or {}
        text = str(labels.get(payload.get('mode', ''), payload.get('mode_label', '-')) or '-').strip()
        text = self._clean_text(text, ascii_only=ascii_only)
        paper_width = self._paper_width(layout)
        lines: List[Dict[str, str]] = []
        self._add_spacing(lines, mode_cfg.get('spacing_before', 0))
        lines.append(self._make_line(self._align_text(text, paper_width, self._align(layout, style)), style))
        self._add_spacing(lines, mode_cfg.get('spacing_after', 0))
        return lines

    def _render_meta(self, payload: Dict[str, Any], layout: Dict[str, Any], ascii_only: bool) -> List[Dict[str, str]]:
        content = self._content(layout)
        meta_cfg = content.get('meta') or {}
        lines: List[Dict[str, str]] = []

        operator_cfg = meta_cfg.get('operator_name') or {}
        operator_style = str(operator_cfg.get('style', 'meta_primary'))
        operator_labels = operator_cfg.get('labels') or {}
        operator_label = operator_labels.get(payload.get('mode', ''), payload.get('operator_name_label', 'Name'))
        operator_label = self._clean_text(operator_label, ascii_only=ascii_only)
        operator_value = self._clean_text(payload.get(operator_cfg.get('value_key', 'operator_name'), ''), ascii_only=ascii_only)
        operator_placeholder = self._placeholder(operator_cfg.get('empty_placeholder_length', 31))
        self._add_spacing(lines, operator_cfg.get('spacing_before', 0))
        if operator_value and bool(operator_cfg.get('filled_value_on_next_line', True)):
            label_template = str(operator_cfg.get('filled_label_template', '{label}:'))
            label_style = str(operator_cfg.get('label_style', operator_style) or operator_style)
            value_indent = str(operator_cfg.get('filled_value_indent', '  '))
            label_text = label_template.format(label=operator_label).strip()
            if label_text:
                lines.append(self._make_line(label_text, label_style))
            value_width = self._wrap_width(layout, operator_style)
            wrapped_value = self._wrap_text(
                operator_value,
                value_width,
                initial_indent=value_indent,
                subsequent_indent=value_indent,
            )
            lines.extend(self._make_line(line, operator_style) for line in wrapped_value)
        else:
            operator_template = operator_cfg.get('filled_template') if operator_value else operator_cfg.get('empty_template')
            operator_text = str(operator_template or '{label}: {value}').format(
                label=operator_label,
                value=operator_value,
                placeholder=operator_placeholder,
            )
            lines.extend(self._make_line(line, operator_style) for line in self._wrap_text(operator_text, self._wrap_width(layout, operator_style)))
        self._add_spacing(lines, operator_cfg.get('spacing_after', 0))

        datetime_cfg = meta_cfg.get('datetime') or {}
        dt_style = str(datetime_cfg.get('style', 'meta_primary'))
        self._add_spacing(lines, datetime_cfg.get('spacing_before', 0))
        if payload.get('print_datetime_placeholder') or payload.get('force_datetime_placeholder'):
            date_label = self._clean_text(datetime_cfg.get('date_placeholder_label', 'Datum'), ascii_only=ascii_only)
            time_label = self._clean_text(datetime_cfg.get('time_placeholder_label', 'Uhrzeit'), ascii_only=ascii_only)
            date_text = str(datetime_cfg.get('date_placeholder_template', '{label}: {placeholder}')).format(
                label=date_label,
                placeholder=self._placeholder(datetime_cfg.get('date_placeholder_length', 23)),
            )
            time_text = str(datetime_cfg.get('time_placeholder_template', '{label}: {placeholder} Uhr')).format(
                label=time_label,
                placeholder=self._placeholder(datetime_cfg.get('time_placeholder_length', 20)),
            )
            lines.append(self._make_line(date_text, dt_style))
            lines.append(self._make_line(time_text, dt_style))
        else:
            date_text = self._clean_text(payload.get('date', ''), ascii_only=ascii_only) or '-'
            time_text = self._clean_text(payload.get('time', ''), ascii_only=ascii_only)
            time_text = ':'.join(time_text.split(':')[:2]) if time_text else '-'
            template = str(datetime_cfg.get('template', '{label}: {date} {time}'))
            text = template.format(
                label=self._clean_text(datetime_cfg.get('label', 'Datum'), ascii_only=ascii_only),
                date=date_text,
                time=time_text,
            ).strip()
            lines.extend(self._make_line(line, dt_style) for line in self._wrap_text(text, self._wrap_width(layout, dt_style)))
        self._add_spacing(lines, datetime_cfg.get('spacing_after', 0))

        duration_cfg = meta_cfg.get('usage_duration') or {}
        if payload.get('mode') == duration_cfg.get('show_only_in_mode', MODE_VERWENDUNGSNACHWEIS):
            duration_style = str(duration_cfg.get('style', 'meta_primary'))
            value = self._clean_text(payload.get(duration_cfg.get('value_key', 'usage_duration_minutes'), ''), ascii_only=ascii_only)
            if value and not any(char.isalpha() for char in value):
                value = f"{value}{duration_cfg.get('append_suffix_if_numeric', ' min')}"
            if value:
                template = str(duration_cfg.get('filled_template', '{label}: {value}'))
                text = template.format(label=self._clean_text(duration_cfg.get('label', 'Einsatzdauer'), ascii_only=ascii_only), value=value)
            else:
                template = str(duration_cfg.get('empty_template', '{label}: {placeholder} min'))
                text = template.format(
                    label=self._clean_text(duration_cfg.get('label', 'Einsatzdauer'), ascii_only=ascii_only),
                    placeholder=self._placeholder(duration_cfg.get('placeholder_length', 10)),
                )
            self._add_spacing(lines, duration_cfg.get('spacing_before', 0))
            lines.extend(self._make_line(line, duration_style) for line in self._wrap_text(text, self._wrap_width(layout, duration_style)))
            self._add_spacing(lines, duration_cfg.get('spacing_after', 0))
        return lines

    def _item_lines(
        self,
        item: Dict[str, Any],
        group_name: str,
        payload: Dict[str, Any],
        layout: Dict[str, Any],
        ascii_only: bool,
        content_width: Optional[int] = None,
    ) -> List[str]:
        material_cfg = self._material_config(layout)
        style_name = str(material_cfg.get('item_style', 'material_body'))
        width = max(8, int(content_width or self._wrap_width(layout, style_name)))
        body_indent = str(material_cfg.get('item_body_indent', '   '))
        fields = self._print_fields(layout, group_name)
        lines: List[str] = []
        group_title = self._group_title(layout, group_name, ascii_only=ascii_only)
        item_type = self._clean_text(item.get('item_type', ''), ascii_only=ascii_only)
        if item_type and item_type.casefold() not in {group_title.casefold(), self._clean_text(group_name, ascii_only=ascii_only).casefold()}:
            label = self._field_label(layout, payload, 'item_type', ascii_only=ascii_only)
            lines.extend(self._wrap_text(f'{label}: {item_type}', width, initial_indent='', subsequent_indent=body_indent))
        for field_name in fields:
            if field_name == 'item_type':
                continue
            value = self._clean_text(item.get(field_name, ''), ascii_only=ascii_only)
            if not value:
                continue
            label = self._field_label(layout, payload, field_name, ascii_only=ascii_only)
            lines.extend(self._wrap_text(f'{label}: {value}', width, initial_indent='', subsequent_indent=body_indent))
        extra_serial = self._clean_text(item.get('geraetenummer', ''), ascii_only=ascii_only)
        if extra_serial and 'geraetenummer' not in fields:
            label = self._field_label(layout, payload, 'geraetenummer', ascii_only=ascii_only)
            lines.extend(self._wrap_text(f'{label}: {extra_serial}', width, initial_indent='', subsequent_indent=body_indent))
        return lines or ['-']

    def _render_material(self, payload: Dict[str, Any], layout: Dict[str, Any], ascii_only: bool) -> List[Dict[str, str]]:
        cfg = self._material_config(layout)
        title_style = str(cfg.get('title_style', 'section_heading'))
        group_style = str(cfg.get('group_title_style', 'group_heading'))
        body_style = str(cfg.get('item_style', 'material_body'))
        lines: List[Dict[str, str]] = []
        self._add_spacing(lines, cfg.get('spacing_before', 0))
        lines.append(self._make_line(f"{self._clean_text(cfg.get('title', 'Material'), ascii_only=ascii_only)}:", title_style))
        self._add_spacing(lines, cfg.get('spacing_after', 0))

        seen_group = False
        has_items = False
        prefix_template = str(cfg.get('item_prefix_template', '{index}) '))
        for group_name in self._material_group_order(layout):
            items = self._iter_group_items(payload, group_name)
            if not items:
                continue
            has_items = True
            if seen_group:
                self._add_spacing(lines, cfg.get('group_spacing_before', 1))

            group_title = f'{self._group_title(layout, group_name, ascii_only=ascii_only)}:'
            lines.append(self._make_line(group_title, group_style))
            item_leading_indent = str(cfg.get('item_leading_indent', '  '))
            for index, item in enumerate(items, start=1):
                prefix = prefix_template.format(index=index)
                content_width = max(8, self._wrap_width(layout, body_style) - len(item_leading_indent) - len(prefix))
                item_lines = [
                    line
                    for line in self._item_lines(item, group_name, payload, layout, ascii_only, content_width=content_width)
                    if str(line).strip()
                ]
                text_indent = f"{item_leading_indent}{' ' * len(prefix)}"
                first_line = item_lines[0].lstrip() if item_lines else '-'
                lines.append(self._make_line(f'{item_leading_indent}{prefix}{first_line}', body_style))
                for continuation in item_lines[1:]:
                    continuation_text = str(continuation).rstrip()
                    if continuation_text.strip():
                        lines.append(self._make_line(f'{text_indent}{continuation_text}', body_style))
                self._add_spacing(lines, cfg.get('item_spacing_after', 0))
            seen_group = True
        if not has_items:
            lines.append(self._make_line(str(cfg.get('empty_text', '-')), body_style))
        return lines

    def _render_details(self, payload: Dict[str, Any], layout: Dict[str, Any], ascii_only: bool) -> List[Dict[str, str]]:
        cfg = self._details_config(layout)
        title_style = str(cfg.get('title_style', 'section_heading'))
        body_style = str(cfg.get('body_style', 'details_body'))
        width = self._wrap_width(layout, body_style)
        content_lines: List[Dict[str, str]] = []

        cards = payload.get('function_cards') or []
        if cards:
            prefix = str(cfg.get('card_prefix', '- '))
            cont = str(cfg.get('card_continuation', '  '))
            for card in cards:
                label = self._clean_text(card.get('label', ''), ascii_only=ascii_only) or '-'
                wrapped = self._wrap_text(label, width, initial_indent=prefix, subsequent_indent=cont)
                content_lines.extend(self._make_line(line, body_style) for line in wrapped)
        elif payload.get('print_default_details_without_card'):
            prefix = str(cfg.get('checklist_prefix', '[ ] '))
            cont = str(cfg.get('checklist_continuation', '    '))
            single_line_items = {self._clean_text(item, ascii_only=ascii_only) for item in (cfg.get('single_line_items') or [])}
            for detail in payload.get('default_detail_checklist') or []:
                detail_text = self._clean_text(detail, ascii_only=ascii_only)
                if not detail_text:
                    continue
                wrapped = self._wrap_text(
                    detail_text,
                    width,
                    initial_indent=prefix,
                    subsequent_indent=cont,
                    force_single_line=detail_text in single_line_items,
                )
                content_lines.extend(self._make_line(line, body_style) for line in wrapped)

        if not content_lines:
            return []

        lines: List[Dict[str, str]] = []
        self._add_spacing(lines, cfg.get('spacing_before', 0))
        lines.append(self._make_line(f"{self._clean_text(cfg.get('title', 'Einsatz- & Uebungsdetails'), ascii_only=ascii_only)}:", title_style))
        self._add_spacing(lines, cfg.get('spacing_after', 0))
        lines.extend(content_lines)
        return lines

    def _render_remarks(self, payload: Dict[str, Any], layout: Dict[str, Any], ascii_only: bool) -> List[Dict[str, str]]:
        if not payload.get('print_remarks', True):
            return []

        cfg = self._remarks_config(layout)
        title_style = str(cfg.get('title_style', 'section_heading'))
        body_style = str(cfg.get('body_style', 'remarks_body'))
        width = self._wrap_width(layout, body_style)
        lines: List[Dict[str, str]] = []
        self._add_spacing(lines, cfg.get('spacing_before', 0))
        lines.append(self._make_line(f"{self._clean_text(cfg.get('title', 'Bemerkungen'), ascii_only=ascii_only)}:", title_style))
        self._add_spacing(lines, cfg.get('spacing_after', 0))

        remarks = self._clean_text(payload.get('remarks', ''), ascii_only=ascii_only)
        if remarks:
            lines.extend(self._make_line(line, body_style) for line in self._wrap_text(remarks, width))
            return lines

        write_line_length = max(4, min(width, int(cfg.get('write_line_length', width) or width)))
        write_line = self._placeholder(write_line_length)
        line_gap = max(0, int(cfg.get('write_line_gap', 0) or 0))
        for index in range(max(1, int(cfg.get('empty_write_lines', 2) or 2))):
            lines.append(self._make_line(write_line, body_style))
            if index < max(1, int(cfg.get('empty_write_lines', 2) or 2)) - 1:
                self._add_spacing(lines, line_gap, 'spacer')
        return lines

    def render_lines(self, payload: Dict[str, Any], print_layout: Dict[str, Any], ascii_only: bool = False) -> List[Dict[str, str]]:
        """Baut aus dem Payload eine lineare Liste formatierter Druckzeilen."""
        layout = deepcopy(print_layout or {})
        lines: List[Dict[str, str]] = []
        lines.extend(self._render_header(payload, layout, ascii_only))
        lines.extend(self._render_mode(payload, layout, ascii_only))
        lines.extend(self._render_meta(payload, layout, ascii_only))
        lines.extend(self._render_material(payload, layout, ascii_only))
        lines.extend(self._render_details(payload, layout, ascii_only))
        lines.extend(self._render_remarks(payload, layout, ascii_only))
        return lines

    def render_text(self, payload: Dict[str, Any], print_layout: Dict[str, Any], ascii_only: bool = False) -> str:
        """Setzt formatierte Zeilen zu einer Textansicht fuer TXT oder Vorschau zusammen."""
        lines = self.render_lines(payload, print_layout, ascii_only=ascii_only)
        text = '\n'.join((line.get('text', '') or '').rstrip() for line in lines).rstrip() + '\n'
        return to_ascii_text(text) if ascii_only else text
