"""Normalisierung von Scan-Codes fuer den robusten Lookup.

Uneinheitliche Schreibweisen aus Scannern oder Etiketten werden auf einen
vergleichbaren Kernwert reduziert.
"""

import re

from config import SCAN_CHARACTER_REPLACEMENTS


def normalize_scan_code(value: str) -> str:
    if value is None:
        return ''

    text = str(value).strip()
    for old, new in SCAN_CHARACTER_REPLACEMENTS.items():
        text = text.replace(old, new)

    text = text.lower()
    return re.sub(r'[^0-9a-z]', '', text)
