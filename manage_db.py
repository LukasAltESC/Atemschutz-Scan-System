"""Kommandozeilenwerkzeug fuer CSV- und SQLite-Pflege."""

import argparse
import json

from database import DatabaseManager


def main():
    parser = argparse.ArgumentParser(description='SQLite/CSV-Verwaltung für das Atemschutz-Scan-System')
    subparsers = parser.add_subparsers(dest='command', required=True)

    subparsers.add_parser('list', help='Alle Datensätze anzeigen')
    subparsers.add_parser('summary', help='Kurze Übersicht anzeigen')
    subparsers.add_parser('import-csv', help='CSV nach SQLite importieren')
    subparsers.add_parser('export-csv', help='SQLite nach CSV exportieren')

    add_parser = subparsers.add_parser('add', help='Datensatz anlegen oder aktualisieren')
    add_parser.add_argument('--item-id', type=int)
    add_parser.add_argument('--raw-group', required=True)
    add_parser.add_argument('--type', dest='item_type', default='')
    add_parser.add_argument('--inventarnummer', default='')
    add_parser.add_argument('--fabriknummer', default='')
    add_parser.add_argument('--geraetenummer', default='')
    add_parser.add_argument('--lf-scan', dest='lf_scan', default='')
    add_parser.add_argument('--bemerkung', default='')
    add_parser.add_argument('--inactive', action='store_true')

    delete_parser = subparsers.add_parser('delete', help='Datensatz löschen')
    delete_parser.add_argument('--item-id', required=True, type=int)

    args = parser.parse_args()
    db = DatabaseManager()
    db.initialize()

    if args.command == 'list':
        for item in db.list_items():
            print(json.dumps(item, ensure_ascii=False))
    elif args.command == 'summary':
        print(json.dumps(db.get_summary(), indent=2, ensure_ascii=False))
    elif args.command == 'import-csv':
        print(f'{db.import_from_csv()} Datensätze aus CSV importiert.')
    elif args.command == 'export-csv':
        print(f'{db.export_to_csv()} Datensätze nach CSV exportiert.')
    elif args.command == 'add':
        item_id = db.upsert_item(
            item_id=args.item_id,
            raw_group=args.raw_group,
            item_type=args.item_type,
            inventarnummer=args.inventarnummer,
            fabriknummer=args.fabriknummer,
            geraetenummer=args.geraetenummer,
            lf_scan=args.lf_scan,
            bemerkung=args.bemerkung,
            is_active=0 if args.inactive else 1,
        )
        db.export_to_csv()
        print(f'Datensatz {item_id} gespeichert.')
    elif args.command == 'delete':
        db.delete_item(args.item_id)
        db.export_to_csv()
        print(f'Datensatz {args.item_id} gelöscht.')


if __name__ == '__main__':
    main()
