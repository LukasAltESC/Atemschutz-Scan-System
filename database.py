"""Datenbank- und CSV-Zugriff fuer das Atemschutz-Scan-System.

Die SQLite-Datenbank wird fuer schnelle Lookups genutzt, waehrend die CSV als
einfach bearbeitbare Stammdatenquelle fuer Service und Pflege bestehen bleibt.
"""

import csv
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional

from ascii_utils import to_ascii_text
from config import CSV_PATH, DB_PATH, IDENTIFIER_FIELDS_BY_GROUP, RAW_GROUP_TO_SYSTEM_GROUP, SCHEMA_PATH
from normalizer import normalize_scan_code

CSV_FIELDNAMES = ['Gruppe', 'Typ', 'Inventarnummer', 'Fabriknummer', 'Gerätenummer', 'LF-Scan', 'Bemerkung']
CSV_HEADER_ALIASES = {
    'Gruppe': 'Gruppe',
    'Typ': 'Typ',
    'Inventarnummer': 'Inventarnummer',
    'Inventarnummer': 'Inventarnummer',
    'Fabriknummer': 'Fabriknummer',
    'Seriennummer': 'Gerätenummer',
    'Geraetenummer': 'Gerätenummer',
    'Gerätenummer': 'Gerätenummer',
    'LF-Scan': 'LF-Scan',
    'LF Scan': 'LF-Scan',
    'Bemerkung': 'Bemerkung',
}

IDENTIFIER_ORDER = {
    'inventarnummer': 1,
    'fabriknummer': 2,
    'lf_scan': 3,
    'geraetenummer': 4,
}


class DatabaseManager:
    """SQLite + externe CSV-Stammdaten für das Atemschutz-Scan-System."""

    def __init__(self, db_path: Path = DB_PATH, csv_path: Path = CSV_PATH, schema_path: Path = SCHEMA_PATH):
        self.db_path = Path(db_path)
        self.csv_path = Path(csv_path)
        self.schema_path = Path(schema_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA foreign_keys = ON')
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        schema_sql = self.schema_path.read_text(encoding='utf-8')
        with self.connect() as conn:
            conn.executescript(schema_sql)
            self._migrate_items_table(conn)

    def _migrate_items_table(self, conn) -> None:
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(items)').fetchall()}
        if 'fabriknummer' not in columns:
            conn.execute("ALTER TABLE items ADD COLUMN fabriknummer TEXT DEFAULT ''")

    def map_group(self, raw_group: str) -> str:
        raw_group = (raw_group or '').strip()
        return RAW_GROUP_TO_SYSTEM_GROUP.get(raw_group, raw_group or 'Unbekannt')

    def get_allowed_identifier_fields(self, system_group: str) -> List[str]:
        return list(IDENTIFIER_FIELDS_BY_GROUP.get(system_group, ['inventarnummer']))

    def _sanitize_record(self, record: Dict) -> Dict:
        sanitized = dict(record)
        if sanitized.get('system_group') != 'Atem-Druckluftflasche':
            sanitized['lf_scan'] = ''
        return sanitized

    def _build_identifier_rows(self, record: Dict) -> List[Dict]:
        record = self._sanitize_record(record)
        system_group = record['system_group']
        candidates = {
            'inventarnummer': record.get('inventarnummer', '') or '',
            'fabriknummer': record.get('fabriknummer', '') or '',
            'geraetenummer': record.get('geraetenummer', '') or '',
            'lf_scan': record.get('lf_scan', '') or '',
        }

        identifier_rows = []
        seen = set()
        for identifier_type in self.get_allowed_identifier_fields(system_group):
            raw_value = candidates.get(identifier_type, '').strip()
            normalized = normalize_scan_code(raw_value)
            if not raw_value or not normalized or normalized in seen:
                continue
            seen.add(normalized)
            identifier_rows.append(
                {
                    'identifier_type': identifier_type,
                    'identifier_value': raw_value,
                    'normalized_value': normalized,
                }
            )
        return identifier_rows

    def _detect_csv_dialect(self, text: str) -> csv.Dialect:
        sample = '\n'.join(line for line in text.splitlines()[:10] if line.strip())
        if not sample:
            return csv.excel
        try:
            return csv.Sniffer().sniff(sample, delimiters=';,\t,')
        except csv.Error:
            class SemicolonDialect(csv.excel):
                delimiter = ';'
            return SemicolonDialect()

    def _canonicalize_row(self, row: Dict) -> Dict:
        normalized = {}
        for key, value in row.items():
            canonical_key = CSV_HEADER_ALIASES.get((key or '').strip(), (key or '').strip())
            normalized[canonical_key] = (value or '').strip()
        return normalized

    def read_csv_rows(self) -> List[Dict]:
        """Liest die Material-CSV robust mit mehreren Encodings und Header-Aliassen."""
        if not self.csv_path.exists():
            return []

        for encoding in ('utf-8-sig', 'utf-8', 'latin1'):
            try:
                text = self.csv_path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue

            if not text.strip():
                return []

            dialect = self._detect_csv_dialect(text)
            reader = csv.DictReader(text.splitlines(), dialect=dialect)
            rows = []
            for raw_row in reader:
                # CSV-Dateien aus verschiedenen Quellen koennen leicht andere
                # Spaltennamen oder Kodierungen haben; daher wird jede Zeile
                # zuerst auf das erwartete Schema abgebildet.
                row = self._canonicalize_row(raw_row)
                if not any(row.values()):
                    continue
                record = {
                    'raw_group': (row.get('Gruppe') or '').strip(),
                    'system_group': self.map_group(row.get('Gruppe', '')),
                    'item_type': (row.get('Typ') or '').strip(),
                    'inventarnummer': (row.get('Inventarnummer') or '').strip(),
                    'fabriknummer': (row.get('Fabriknummer') or '').strip(),
                    'geraetenummer': (row.get('Gerätenummer') or '').strip(),
                    'lf_scan': (row.get('LF-Scan') or '').strip(),
                    'bemerkung': (row.get('Bemerkung') or '').strip(),
                    'is_active': 1,
                }
                rows.append(self._sanitize_record(record))
            return rows

        raise RuntimeError(f'Konnte CSV-Datei nicht lesen: {self.csv_path}')

    def import_from_csv(self) -> int:
        """Importiert die komplette CSV neu in die SQLite-Datenbank."""
        rows = self.read_csv_rows()
        if not rows:
            print(f'[DB] Warnung: CSV leer oder ohne verwertbare Datensätze: {self.csv_path}')
            return 0

        with self.connect() as conn:
            self._migrate_items_table(conn)
            conn.execute('DELETE FROM item_identifiers')
            conn.execute('DELETE FROM items')
            for row in rows:
                cursor = conn.execute(
                    """
                    INSERT INTO items (
                        raw_group, system_group, item_type, inventarnummer, fabriknummer, geraetenummer, lf_scan, bemerkung, is_active, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        row['raw_group'],
                        row['system_group'],
                        row.get('item_type', ''),
                        row.get('inventarnummer', ''),
                        row.get('fabriknummer', ''),
                        row.get('geraetenummer', ''),
                        row.get('lf_scan', ''),
                        row.get('bemerkung', ''),
                        int(row.get('is_active', 1)),
                    ),
                )
                item_id = cursor.lastrowid
                for identifier in self._build_identifier_rows(row):
                    conn.execute(
                        """
                        INSERT INTO item_identifiers (item_id, identifier_type, identifier_value, normalized_value)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            item_id,
                            identifier['identifier_type'],
                            identifier['identifier_value'],
                            identifier['normalized_value'],
                        ),
                    )
        return len(rows)

    def export_to_csv(self) -> int:
        """Exportiert die aktuelle SQLite-Sicht zurueck in die pflegbare CSV."""
        items = self.list_items()
        with self.csv_path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES, delimiter=';')
            writer.writeheader()
            for item in items:
                writer.writerow(
                    {
                        'Gruppe': to_ascii_text(item['raw_group']),
                        'Typ': to_ascii_text(item['item_type']),
                        'Inventarnummer': to_ascii_text(item['inventarnummer']),
                        'Fabriknummer': to_ascii_text(item['fabriknummer']),
                        'Gerätenummer': to_ascii_text(item['geraetenummer']),
                        'LF-Scan': to_ascii_text(item['lf_scan']) if item['system_group'] == 'Atem-Druckluftflasche' else '',
                        'Bemerkung': to_ascii_text(item['bemerkung']),
                    }
                )
        return len(items)

    def get_item_by_scan(self, scanned_code: str) -> Optional[Dict]:
        """Findet einen Datensatz ueber eine erlaubte Scan-Kennung."""
        normalized = normalize_scan_code(scanned_code)
        if not normalized:
            return None

        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    items.*,
                    item_identifiers.identifier_type AS matched_identifier_type,
                    item_identifiers.identifier_value AS matched_identifier_value
                FROM item_identifiers
                JOIN items ON items.id = item_identifiers.item_id
                WHERE item_identifiers.normalized_value = ?
                  AND items.is_active = 1
                ORDER BY items.system_group, items.inventarnummer
                """,
                (normalized,),
            ).fetchall()

        if not rows:
            return None
        if len(rows) > 1:
            # Mehrdeutige Kennungen werden bewusst nicht automatisch aufgeloest,
            # damit kein falsches Geraet in einen Nachweis uebernommen wird.
            return {
                'lookup_error': 'ambiguous',
                'normalized_scan': normalized,
                'matches': [dict(row) for row in rows],
            }
        return dict(rows[0])

    def list_items(self) -> List[Dict]:
        with self.connect() as conn:
            self._migrate_items_table(conn)
            rows = conn.execute(
                """
                SELECT * FROM items
                ORDER BY system_group, item_type, inventarnummer, fabriknummer, geraetenummer, id
                """
            ).fetchall()

            result = []
            for row in rows:
                item = dict(row)
                identifiers = conn.execute(
                    """
                    SELECT identifier_type, identifier_value
                    FROM item_identifiers
                    WHERE item_id = ?
                    ORDER BY
                        CASE identifier_type
                            WHEN 'inventarnummer' THEN 1
                            WHEN 'fabriknummer' THEN 2
                            WHEN 'lf_scan' THEN 3
                            WHEN 'geraetenummer' THEN 4
                            ELSE 9
                        END,
                        identifier_value
                    """,
                    (item['id'],),
                ).fetchall()
                item['identifiers'] = [dict(identifier) for identifier in identifiers]
                result.append(item)
        return result

    def upsert_item(
        self,
        item_id: Optional[int],
        raw_group: str,
        item_type: str,
        inventarnummer: str,
        fabriknummer: str,
        geraetenummer: str,
        lf_scan: str,
        bemerkung: str = '',
        is_active: int = 1,
    ) -> int:
        record = self._sanitize_record(
            {
                'raw_group': raw_group.strip(),
                'system_group': self.map_group(raw_group),
                'item_type': item_type.strip(),
                'inventarnummer': inventarnummer.strip(),
                'fabriknummer': fabriknummer.strip(),
                'geraetenummer': geraetenummer.strip(),
                'lf_scan': lf_scan.strip(),
                'bemerkung': bemerkung.strip(),
                'is_active': int(is_active),
            }
        )

        with self.connect() as conn:
            self._migrate_items_table(conn)
            if item_id:
                conn.execute(
                    """
                    UPDATE items SET
                        raw_group = ?,
                        system_group = ?,
                        item_type = ?,
                        inventarnummer = ?,
                        fabriknummer = ?,
                        geraetenummer = ?,
                        lf_scan = ?,
                        bemerkung = ?,
                        is_active = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        record['raw_group'],
                        record['system_group'],
                        record['item_type'],
                        record['inventarnummer'],
                        record['fabriknummer'],
                        record['geraetenummer'],
                        record['lf_scan'],
                        record['bemerkung'],
                        record['is_active'],
                        item_id,
                    ),
                )
                conn.execute('DELETE FROM item_identifiers WHERE item_id = ?', (item_id,))
                target_item_id = int(item_id)
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO items (
                        raw_group, system_group, item_type, inventarnummer, fabriknummer, geraetenummer, lf_scan, bemerkung, is_active, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        record['raw_group'],
                        record['system_group'],
                        record['item_type'],
                        record['inventarnummer'],
                        record['fabriknummer'],
                        record['geraetenummer'],
                        record['lf_scan'],
                        record['bemerkung'],
                        record['is_active'],
                    ),
                )
                target_item_id = cursor.lastrowid

            for identifier in self._build_identifier_rows(record):
                conn.execute(
                    """
                    INSERT INTO item_identifiers (item_id, identifier_type, identifier_value, normalized_value)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        target_item_id,
                        identifier['identifier_type'],
                        identifier['identifier_value'],
                        identifier['normalized_value'],
                    ),
                )
        return int(target_item_id)

    def delete_item(self, item_id: int) -> None:
        with self.connect() as conn:
            conn.execute('DELETE FROM items WHERE id = ?', (int(item_id),))

    def get_summary(self) -> Dict:
        items = self.list_items()
        by_group: Dict[str, int] = {}
        for item in items:
            by_group[item['system_group']] = by_group.get(item['system_group'], 0) + 1
        return {
            'count': len(items),
            'by_group': by_group,
            'csv_path': str(self.csv_path),
            'db_path': str(self.db_path),
        }
