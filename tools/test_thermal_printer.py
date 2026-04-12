#!/usr/bin/env python3
import argparse
import datetime as dt
import os
import subprocess
import sys
import textwrap
import time
import unicodedata
from pathlib import Path

DEFAULT_VENDOR_ID = 0x4B43
DEFAULT_PRODUCT_ID = 0x3538
DEFAULT_DEVICE_NODE = '/dev/usb/lp0'
USB_TIMEOUT_MS = 5000
POST_WRITE_DELAY_S = 0.35

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _ascii_text(value: str) -> bytes:
    replacements = {
        'ä': 'ae',
        'ö': 'oe',
        'ü': 'ue',
        'Ä': 'Ae',
        'Ö': 'Oe',
        'Ü': 'Ue',
        'ß': 'ss',
    }
    normalized = value
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = unicodedata.normalize('NFKD', normalized).encode('ascii', 'ignore').decode('ascii')
    return normalized.encode('ascii', 'replace')


def _line_bytes(value: str) -> bytes:
    return _ascii_text(value) + b'\r\n'


def build_ticket_lines(text: str | None = None) -> list[str]:
    now = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    body = text or 'Testdruck erfolgreich.'
    return [
        '================================',
        'ATEMSCHUTZ-SCAN-SYSTEM',
        'Bondrucker-Test',
        '================================',
        '',
        f'Zeit: {now}',
        'Drucker: Caysn Thermal Printer',
        'Modell: T7-US (USB)',
        '',
        body,
        '',
        'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
        '0123456789',
        '',
        'Wenn du diesen Text lesen kannst,',
        'funktioniert der Druck ueber Linux.',
        '',
        '---- ENDE TEST ----',
        '',
    ]


def build_plain_ticket(text: str | None = None, trailing_feeds: int = 5) -> bytes:
    payload = bytearray()
    for line in build_ticket_lines(text):
        payload += _line_bytes(line)
    payload += b'\r\n' * max(trailing_feeds, 0)
    return bytes(payload)


def build_escpos_ticket(text: str | None = None, cut: bool = True) -> bytes:
    lines = build_ticket_lines(text)
    payload = bytearray()
    payload += b'\x1b@'          # initialize
    payload += b'\x1bt\x00'     # code page 0
    payload += b'\x1ba\x01'     # center
    payload += b'\x1bE\x01'     # bold on
    payload += _line_bytes(lines[1])
    payload += b'\x1bE\x00'     # bold off
    payload += _line_bytes(lines[2])
    payload += b'\x1ba\x00'     # left
    payload += _line_bytes(lines[0])
    payload += _line_bytes('')
    for line in lines[5:]:
        payload += _line_bytes(line)
    payload += b'\x1bd\x04'     # feed 4 lines
    if cut:
        payload += b'\x1dV\x00'  # full cut
    return bytes(payload)


def resolve_payload_mode(method: str, payload_mode: str, device_node: str) -> str:
    if payload_mode != 'auto':
        return payload_mode
    if method == 'usb':
        return 'escpos'
    if method == 'devnode':
        return 'plain'
    if Path(device_node).exists():
        return 'plain'
    return 'escpos'


def build_payload(method: str, payload_mode: str, text: str, cut: bool, device_node: str) -> tuple[bytes, str]:
    resolved_mode = resolve_payload_mode(method, payload_mode, device_node)
    if resolved_mode == 'plain':
        return build_plain_ticket(text=text), resolved_mode
    return build_escpos_ticket(text=text, cut=cut), resolved_mode


def format_usb_id(vendor_id: int, product_id: int) -> str:
    return f'{vendor_id:04x}:{product_id:04x}'


def list_lsusb() -> None:
    print('== lsusb ==')
    try:
        result = subprocess.run(['lsusb'], check=True, capture_output=True, text=True)
        print(result.stdout.strip())
    except FileNotFoundError:
        print('lsusb nicht gefunden. Bitte usbutils installieren.')
    except subprocess.CalledProcessError as exc:
        print(f'lsusb fehlgeschlagen: {exc}')


def find_usb_printer(vendor_id: int, product_id: int):
    try:
        import usb.core
    except ImportError as exc:
        raise SystemExit(
            'python3-usb fehlt. Bitte im install.sh python3-usb installieren. '
            f'Detail: {exc}'
        )

    device = usb.core.find(idVendor=vendor_id, idProduct=product_id)
    if device is None:
        raise SystemExit(
            f'Kein USB-Drucker mit VID:PID {format_usb_id(vendor_id, product_id)} gefunden. '
            'Mit --list kannst du die USB-Geraete pruefen.'
        )
    return device


def get_interface_descriptor(device):
    import usb.core

    try:
        cfg = device.get_active_configuration()
    except usb.core.USBError:
        cfg = device[0]

    try:
        return cfg[(0, 0)]
    except Exception:
        for interface in cfg:
            return interface
    raise SystemExit('Keine USB-Schnittstelle am Drucker gefunden.')


def print_via_pyusb(vendor_id: int, product_id: int, payload: bytes, endpoint_address: int | None) -> None:
    import usb.core
    import usb.util

    device = find_usb_printer(vendor_id, product_id)
    detached = False
    interface_number = 0
    interface_claimed = False

    try:
        interface = get_interface_descriptor(device)
        interface_number = interface.bInterfaceNumber

        try:
            if device.is_kernel_driver_active(interface_number):
                device.detach_kernel_driver(interface_number)
                detached = True
        except (NotImplementedError, usb.core.USBError):
            pass

        try:
            device.set_configuration()
        except usb.core.USBError as exc:
            if getattr(exc, 'errno', None) == 16:
                raise SystemExit(
                    'USB-Geraet ist belegt (Resource busy). '
                    'Der Drucker ist bereits ueber den Kernel-Treiber usblp eingebunden. '
                    f'Nutze stattdessen --method devnode --device-node {DEFAULT_DEVICE_NODE}. '
                    'Oder einfach ohne --method, sobald das Skript auf auto gestellt ist.'
                ) from exc
            raise

        cfg = device.get_active_configuration()
        try:
            interface = cfg[(interface_number, 0)]
        except Exception:
            interface = get_interface_descriptor(device)
            interface_number = interface.bInterfaceNumber

        try:
            usb.util.claim_interface(device, interface_number)
            interface_claimed = True
        except usb.core.USBError as exc:
            if getattr(exc, 'errno', None) == 16:
                raise SystemExit(
                    'USB-Interface ist belegt (Resource busy). '
                    f'Nutze stattdessen --method devnode --device-node {DEFAULT_DEVICE_NODE}.'
                ) from exc
            raise

        endpoint = None
        for candidate in interface:
            direction = usb.util.endpoint_direction(candidate.bEndpointAddress)
            if direction == usb.util.ENDPOINT_OUT:
                if endpoint_address is None or candidate.bEndpointAddress == endpoint_address:
                    endpoint = candidate
                    break
        if endpoint is None:
            raise SystemExit('Keinen OUT-Endpunkt gefunden. Starte das Skript notfalls mit sudo und pruefe --probe.')

        written = endpoint.write(payload, timeout=USB_TIMEOUT_MS)
        print(
            'USB-Druck erfolgreich: '
            f'{written} Byte an {format_usb_id(vendor_id, product_id)} '
            f'ueber Endpoint 0x{endpoint.bEndpointAddress:02x} gesendet.'
        )
    finally:
        if interface_claimed:
            try:
                usb.util.release_interface(device, interface_number)
            except Exception:
                pass
        try:
            if detached:
                device.attach_kernel_driver(interface_number)
        except Exception:
            pass
        usb.util.dispose_resources(device)


def print_via_device_node(device_node: str, payload: bytes) -> None:
    path = Path(device_node)
    if not path.exists():
        raise SystemExit(f'{device_node} existiert nicht. Der usblp-Treiber ist vermutlich nicht aktiv.')

    fd = os.open(str(path), os.O_WRONLY | os.O_NOCTTY)
    try:
        view = memoryview(payload)
        total_written = 0
        while total_written < len(payload):
            written = os.write(fd, view[total_written:])
            if written <= 0:
                raise OSError('os.write hat 0 Bytes geschrieben.')
            total_written += written
        time.sleep(POST_WRITE_DELAY_S)
    finally:
        os.close(fd)

    print(f'Rohdaten erfolgreich an {device_node} gesendet ({len(payload)} Byte).')


def print_probe(vendor_id: int, product_id: int, device_node: str) -> None:
    device = find_usb_printer(vendor_id, product_id)
    print('USB-Drucker gefunden:')
    print(f'  VID:PID  {format_usb_id(vendor_id, product_id)}')
    print(f'  Bus      {getattr(device, "bus", "?")}')
    print(f'  Adresse  {getattr(device, "address", "?")}')
    print(f'  Device-Node vorhanden: {Path(device_node).exists()} ({device_node})')
    if Path(device_node).exists():
        print('  Hinweis: Das spricht dafuer, dass usblp den Drucker bereits gebunden hat.')
        print('  In diesem Fall ist --method devnode der richtige Testweg.')
    try:
        interface = get_interface_descriptor(device)
        print(
            '  Interface '
            f'{interface.bInterfaceNumber} class=0x{interface.bInterfaceClass:02x} '
            f'subclass=0x{interface.bInterfaceSubClass:02x}'
        )
        for endpoint in interface:
            direction = 'OUT' if (endpoint.bEndpointAddress & 0x80) == 0 else 'IN'
            print(
                f'    Endpoint 0x{endpoint.bEndpointAddress:02x} '
                f'direction={direction} max_packet={endpoint.wMaxPacketSize}'
            )
        try:
            active = device.is_kernel_driver_active(interface.bInterfaceNumber)
            print(f'  Kernel-Treiber aktiv: {active}')
        except Exception as exc:
            print(f'  Kernel-Treiber-Status unbekannt: {exc}')
    except Exception as exc:
        print(f'  Detailabfrage eingeschraenkt: {exc}')
        if Path(device_node).exists():
            print('  Das ist in Ordnung, solange /dev/usb/lp0 vorhanden ist.')


def print_auto(vendor_id: int, product_id: int, device_node: str, payload: bytes, endpoint_address: int | None) -> None:
    if Path(device_node).exists():
        print(f'Device-Node {device_node} erkannt, verwende devnode-Methode.')
        print_via_device_node(device_node, payload)
        return

    print('Kein Device-Node vorhanden, verwende pyusb-Methode.')
    print_via_pyusb(vendor_id, product_id, payload, endpoint_address)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Testet einen per USB angeschlossenen Thermodrucker (z. B. Caysn T7-US).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            '''\
            Beispiele:
              python3 tools/test_thermal_printer.py --list
              sudo python3 tools/test_thermal_printer.py --probe
              sudo python3 tools/test_thermal_printer.py
              sudo python3 tools/test_thermal_printer.py --method auto
              sudo python3 tools/test_thermal_printer.py --method devnode --payload-mode plain
              sudo python3 tools/test_thermal_printer.py --method usb --payload-mode escpos
            '''
        ),
    )
    parser.add_argument('--vendor-id', type=lambda value: int(value, 0), default=DEFAULT_VENDOR_ID)
    parser.add_argument('--product-id', type=lambda value: int(value, 0), default=DEFAULT_PRODUCT_ID)
    parser.add_argument('--method', choices=['auto', 'usb', 'devnode'], default='auto')
    parser.add_argument('--payload-mode', choices=['auto', 'plain', 'escpos'], default='auto')
    parser.add_argument('--device-node', default=DEFAULT_DEVICE_NODE)
    parser.add_argument('--endpoint', type=lambda value: int(value, 0), default=None)
    parser.add_argument('--text', default='Testdruck erfolgreich.')
    parser.add_argument('--list', action='store_true', help='Zeigt lsusb und bekannte Standardwerte an.')
    parser.add_argument('--probe', action='store_true', help='Prueft den USB-Drucker und listet Interfaces/Endpoints auf.')
    parser.add_argument('--no-cut', action='store_true', help='Schnittbefehl am Ende bei ESC/POS nicht senden.')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print('Projektpfad:', PROJECT_ROOT)
    print('Erwarteter Drucker:', format_usb_id(args.vendor_id, args.product_id))
    print('Methode:', args.method)

    if args.list:
        list_lsusb()
        print(f'\nStandard-Geraet: {format_usb_id(DEFAULT_VENDOR_ID, DEFAULT_PRODUCT_ID)}')
        print(f'Standard-Device-Node: {DEFAULT_DEVICE_NODE}')
        if not args.probe:
            return

    if args.probe:
        print()
        print_probe(args.vendor_id, args.product_id, args.device_node)
        return

    payload, resolved_payload_mode = build_payload(
        method=args.method,
        payload_mode=args.payload_mode,
        text=args.text,
        cut=not args.no_cut,
        device_node=args.device_node,
    )
    print(f'Payload-Modus: {resolved_payload_mode}')
    print(f'Payload-Laenge: {len(payload)} Byte')

    if args.method == 'usb':
        print_via_pyusb(args.vendor_id, args.product_id, payload, args.endpoint)
    elif args.method == 'devnode':
        print_via_device_node(args.device_node, payload)
    else:
        print_auto(args.vendor_id, args.product_id, args.device_node, payload, args.endpoint)


if __name__ == '__main__':
    main()
