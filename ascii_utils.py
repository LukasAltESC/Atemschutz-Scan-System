"""Hilfsfunktionen fuer ASCII-kompatible Ausgaben.

Relevant fuer CSV-Export und Bondruck, wenn Umlaute oder typografische Zeichen
in ein einfaches Ausgabeformat ueberfuehrt werden muessen.
"""

from typing import Any

ASCII_REPLACEMENTS = str.maketrans(
    {
        'ä': 'ae',
        'ö': 'oe',
        'ü': 'ue',
        'Ä': 'Ae',
        'Ö': 'Oe',
        'Ü': 'Ue',
        'ß': 'ss',
        '–': '-',
        '—': '-',
        '„': '"',
        '“': '"',
        '‚': "'",
        '’': "'",
    }
)


def to_ascii_text(value: Any) -> str:
    return str(value or '').translate(ASCII_REPLACEMENTS)


def sanitize_recursive(value: Any):
    if isinstance(value, dict):
        return {key: sanitize_recursive(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_recursive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_recursive(item) for item in value)
    if isinstance(value, str):
        return to_ascii_text(value)
    return value
