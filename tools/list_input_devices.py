#!/usr/bin/env python3
from scanner_input import discover_input_devices

for device in discover_input_devices():
    print(f"{device['device_path']} | {device['name']} | phys={device['phys'] or '-'}")
    for by_id in device.get('by_id_paths', []):
        print(f"  by-id: {by_id}")
