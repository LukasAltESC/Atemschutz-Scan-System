"""Bondruck ueber ein einfaches ESC/POS-faehiges USB-Geraet.

Die Ausgabe wird als Textlayout aufgebaut und anschliessend in ESC/POS-Bytes
uebersetzt, die direkt auf das Device geschrieben werden.
"""

import time
from pathlib import Path
from typing import Dict, List

from ticket_renderer import TicketRenderer


class ThermalPrinterError(RuntimeError):
    """Spezialisierte Ausnahme fuer Druck- und Device-Fehler."""


class ThermalPrinterManager:
    """Druckt Text und ESC/POS-Stile direkt auf /dev/usb/lp0."""

    def __init__(self, print_layout_manager, device_node: str = '/dev/usb/lp0', encoding: str = 'cp858'):
        self.print_layout_manager = print_layout_manager
        self.device_node = str(device_node).strip() or '/dev/usb/lp0'
        self.encoding = encoding
        self.renderer = TicketRenderer()

    def get_status(self) -> Dict:
        path = Path(self.device_node)
        layout_status = self.print_layout_manager.get_status()
        return {
            'device_node': self.device_node,
            'device_exists': path.exists(),
            'layout_path': layout_status.get('path', ''),
            'paper_width': layout_status.get('paper_width', 32),
            'line_feeds_after_print': layout_status.get('line_feeds_after_print', 0),
            'supports_styles': True,
        }

    def build_print_text(self, payload: Dict) -> str:
        return self.renderer.render_text(payload, self.print_layout_manager.get_layout(), ascii_only=True)

    def build_print_lines(self, payload: Dict) -> List[Dict]:
        return self.renderer.render_lines(payload, self.print_layout_manager.get_layout(), ascii_only=True)

    def _ensure_device(self) -> None:
        if not Path(self.device_node).exists():
            raise ThermalPrinterError(f'Drucker-Device nicht gefunden: {self.device_node}')

    def _style_cfg(self, style_name: str, layout: Dict) -> Dict:
        return dict((layout.get('styles') or {}).get(style_name, {}))

    def _effective_line_ending(self, layout: Dict) -> bytes:
        device = layout.get('device') or {}
        configured = str(device.get('line_ending', '\n') or '\n')
        if '\n' in configured:
            return b'\n'
        if '\r' in configured:
            return b'\r'
        return b'\n'

    def _print_mode_byte(self, style: Dict) -> int:
        mode = 0
        if str(style.get('font', 'a')).strip().lower() == 'b':
            mode |= 0x01
        if style.get('bold'):
            mode |= 0x08
        if style.get('italic'):
            mode |= 0x40
        if style.get('underline'):
            mode |= 0x80
        return mode

    def _style_bytes(self, style_name: str, layout: Dict) -> bytes:
        style = self._style_cfg(style_name, layout)
        align_lookup = {'left': 0, 'center': 1, 'right': 2}
        align = align_lookup.get(str(style.get('align', 'left')).strip().lower(), 0)
        font = 1 if str(style.get('font', 'a')).strip().lower() == 'b' else 0
        bold = 1 if style.get('bold') else 0
        underline = 1 if style.get('underline') else 0
        italic = 1 if style.get('italic') else 0
        try:
            width = max(1, min(8, int(style.get('width', 1))))
        except Exception:
            width = 1
        try:
            height = max(1, min(8, int(style.get('height', 1))))
        except Exception:
            height = 1
        size_byte = ((width - 1) << 4) | (height - 1)
        print_mode = self._print_mode_byte(style)
        try:
            spacing_value = style.get('line_spacing_dots')
            line_spacing_dots = max(0, min(255, int(spacing_value))) if spacing_value is not None else None
        except Exception:
            line_spacing_dots = None
        line_spacing_bytes = (b'\x1b3' + bytes([line_spacing_dots])) if line_spacing_dots is not None else b'\x1b2'
        return b''.join(
            [
                line_spacing_bytes,
                b'\x1ba' + bytes([align]),
                b'\x1b!' + bytes([print_mode]),
                b'\x1bM' + bytes([font]),
                b'\x1bE' + bytes([bold]),
                b'\x1b-' + bytes([underline]),
                b'\x1b4' + bytes([italic]),
                b'\x1d!' + bytes([size_byte]),
            ]
        )

    def _final_feed_bytes(self, layout: Dict) -> bytes:
        device = layout.get('device') or {}
        final_feeds = max(0, int(device.get('line_feeds_after_print', 0) or 0))
        if not final_feeds:
            return b''

        # Viele Bondrucker reagieren auf reine LF-Zeilen zuverlässiger als nur auf ESC d n.
        line_ending = self._effective_line_ending(layout)
        chunks = [line_ending * final_feeds]

        remaining = final_feeds
        while remaining > 0:
            step = min(remaining, 255)
            chunks.append(b'\x1bd' + bytes([step]))
            remaining -= step
        return b''.join(chunks)

    def _build_payload_bytes(self, payload: Dict) -> bytes:
        """Uebersetzt den fachlichen Payload in ESC/POS-Bytes fuer den Drucker."""
        layout = self.print_layout_manager.get_layout()
        line_ending = self._effective_line_ending(layout)
        lines = self.renderer.render_lines(payload, layout, ascii_only=True)
        chunks = [b'\x1b@', b'\x1b2']
        styles = layout.get('styles') or {}
        for line in lines:
            style_name = str(line.get('style', 'spacer') or 'spacer')
            style = styles.get(style_name, {})
            text_value = str(line.get('text', ''))
            if str(style.get('align', 'left')).strip().lower() in {'center', 'right'}:
                text_value = text_value.strip()
            chunks.append(self._style_bytes(style_name, layout))
            chunks.append(text_value.encode(self.encoding, errors='replace'))
            if not bool(line.get('suppress_trailing_newline')):
                chunks.append(line_ending)
        chunks.append(self._final_feed_bytes(layout))
        chunks.append(b'\x1b!\x00\x1d!\x00\x1ba\x00\x1bM\x00\x1bE\x00\x1b-\x00\x1b4\x00')
        return b''.join(chunks)

    def _write_bytes(self, payload_bytes: bytes) -> None:
        self._ensure_device()
        try:
            with open(self.device_node, 'wb', buffering=0) as handle:
                handle.write(payload_bytes)
                handle.flush()
        except Exception as exc:
            raise ThermalPrinterError(f'Bondruck fehlgeschlagen ({self.device_node}): {exc}') from exc

    def print_payload(self, payload: Dict, copy_count: int = 1, copy_pause_seconds: float = 2.0) -> Dict:
        """Schreibt einen Payload optional mehrfach mit definierter Pause auf den Drucker."""
        payload_bytes = self._build_payload_bytes(payload)
        rendered_text = self.build_print_text(payload)
        target_copy_count = max(1, int(copy_count or 1))
        pause_seconds = max(0.0, float(copy_pause_seconds or 0.0))

        for index in range(target_copy_count):
            self._write_bytes(payload_bytes)
            if index < (target_copy_count - 1) and pause_seconds > 0:
                time.sleep(pause_seconds)

        return {
            'ok': True,
            'device_node': self.device_node,
            'copy_count': target_copy_count,
            'rendered_text': rendered_text,
            'bytes_written': len(payload_bytes) * target_copy_count,
        }
