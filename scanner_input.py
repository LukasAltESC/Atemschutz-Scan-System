"""Scanner-Anbindung ueber Linux-Input-Devices.

Die Scanner werden als HID-Tastaturen gelesen. Dieses Modul kapselt die
Uebersetzung von Tastencodes in Zeichenketten und den parallelen Betrieb von
mehreren Scannern.
"""

import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from evdev import InputDevice, ecodes, list_devices

from config import SCAN_DEBOUNCE_SECONDS, SCANNER_DEVICE_PATHS

KEYMAP = {
    ecodes.KEY_1: '1',
    ecodes.KEY_2: '2',
    ecodes.KEY_3: '3',
    ecodes.KEY_4: '4',
    ecodes.KEY_5: '5',
    ecodes.KEY_6: '6',
    ecodes.KEY_7: '7',
    ecodes.KEY_8: '8',
    ecodes.KEY_9: '9',
    ecodes.KEY_0: '0',
    ecodes.KEY_A: 'a',
    ecodes.KEY_B: 'b',
    ecodes.KEY_C: 'c',
    ecodes.KEY_D: 'd',
    ecodes.KEY_E: 'e',
    ecodes.KEY_F: 'f',
    ecodes.KEY_G: 'g',
    ecodes.KEY_H: 'h',
    ecodes.KEY_I: 'i',
    ecodes.KEY_J: 'j',
    ecodes.KEY_K: 'k',
    ecodes.KEY_L: 'l',
    ecodes.KEY_M: 'm',
    ecodes.KEY_N: 'n',
    ecodes.KEY_O: 'o',
    ecodes.KEY_P: 'p',
    ecodes.KEY_Q: 'q',
    ecodes.KEY_R: 'r',
    ecodes.KEY_S: 's',
    ecodes.KEY_T: 't',
    ecodes.KEY_U: 'u',
    ecodes.KEY_V: 'v',
    ecodes.KEY_W: 'w',
    ecodes.KEY_X: 'x',
    ecodes.KEY_Y: 'y',
    ecodes.KEY_Z: 'z',
    ecodes.KEY_MINUS: '-',
    ecodes.KEY_DOT: '.',
    ecodes.KEY_SLASH: '/',
    ecodes.KEY_SPACE: ' ',
}

SHIFT_KEYS = {
    ecodes.KEY_LEFTSHIFT,
    ecodes.KEY_RIGHTSHIFT,
}

SHIFTED_CHARS = {
    '1': '!',
    '2': '"',
    '3': '§',
    '4': '$',
    '5': '%',
    '6': '&',
    '7': '/',
    '8': '(',
    '9': ')',
    '0': '=',
    '-': '_',
    '.': ':',
}


def discover_input_devices() -> List[Dict]:
    """Ermittelt aktuelle /dev/input/event-Geräte inkl. by-id-Symlinks."""
    by_id_root = Path('/dev/input/by-id')
    by_id_map: Dict[str, List[str]] = {}
    if by_id_root.exists():
        for path in by_id_root.iterdir():
            try:
                target = str(path.resolve())
            except Exception:
                continue
            by_id_map.setdefault(target, []).append(str(path))

    devices = []
    for device_path in sorted(list_devices()):
        try:
            device = InputDevice(device_path)
            devices.append(
                {
                    'device_path': device.path,
                    'name': device.name,
                    'phys': device.phys,
                    'by_id_paths': sorted(by_id_map.get(device.path, [])),
                }
            )
            device.close()
        except Exception:
            continue
    return devices


class HIDScannerWorker(threading.Thread):
    """Liest einen einzelnen Scanner, der sich als Tastatur anmeldet."""

    def __init__(self, device_path: str, on_scan: Callable[[str, str], None], stop_event: threading.Event):
        super().__init__(daemon=True)
        self.device_path = device_path
        self.on_scan = on_scan
        self.stop_event = stop_event
        self.shift_pressed = False
        self.last_scan_ts = 0.0
        self.device: Optional[InputDevice] = None

    def stop(self) -> None:
        try:
            if self.device is not None:
                self.device.close()
        except Exception:
            pass

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.device = InputDevice(self.device_path)
                print(f'[Scanner] Aktiv: {self.device.name} ({self.device_path})')
                buffer = ''

                for event in self.device.read_loop():
                    if self.stop_event.is_set():
                        break

                    # Der Scanner sendet einzelne Tastaturereignisse; erst mit
                    # ENTER gilt der Buffer als vollstaendiger Scan.
                    if event.type != ecodes.EV_KEY:
                        continue

                    if event.code in SHIFT_KEYS:
                        self.shift_pressed = event.value == 1
                        continue

                    if event.value != 1:
                        continue

                    if event.code in (ecodes.KEY_ENTER, ecodes.KEY_KPENTER):
                        if buffer:
                            now = time.monotonic()
                            if now - self.last_scan_ts >= SCAN_DEBOUNCE_SECONDS:
                                self.on_scan(buffer, self.device_path)
                                self.last_scan_ts = now
                            buffer = ''
                        continue

                    if event.code in KEYMAP:
                        char = KEYMAP[event.code]
                        if self.shift_pressed:
                            if char.isalpha():
                                char = char.upper()
                            else:
                                char = SHIFTED_CHARS.get(char, char)
                        buffer += char
            except OSError as exc:
                print(f'[Scanner] Gerät {self.device_path} nicht verfügbar: {exc}. Neuer Versuch in 5s.')
                time.sleep(5)
            except Exception as exc:
                if not self.stop_event.is_set():
                    print(f'[Scanner] Fehler auf {self.device_path}: {exc}. Neuer Versuch in 2s.')
                    time.sleep(2)
            finally:
                try:
                    if self.device is not None:
                        self.device.close()
                except Exception:
                    pass
                self.device = None


class ScannerManager:
    """Startet und verwaltet bis zu zwei parallele Scanner-Worker."""

    def __init__(self, on_scan: Callable[[str, str], None], device_paths: List[str] = None):
        self.on_scan = on_scan
        self.device_paths = device_paths or list(SCANNER_DEVICE_PATHS)
        self.stop_event = threading.Event()
        self.workers: List[HIDScannerWorker] = []

    def start(self) -> None:
        self.stop_event.clear()
        self.workers = []
        for device_path in self.device_paths:
            worker = HIDScannerWorker(device_path=device_path, on_scan=self.on_scan, stop_event=self.stop_event)
            worker.start()
            self.workers.append(worker)

    def stop(self) -> None:
        self.stop_event.set()
        for worker in self.workers:
            worker.stop()

    def reload(self, device_paths: List[str]) -> None:
        self.stop()
        time.sleep(0.2)
        self.device_paths = list(device_paths or [])[:2]
        self.stop_event = threading.Event()
        self.start()

    def get_status(self) -> List[Dict]:
        return [
            {
                'device_path': worker.device_path,
                'alive': worker.is_alive(),
            }
            for worker in self.workers
        ]
