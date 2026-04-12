CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_group TEXT NOT NULL,
    system_group TEXT NOT NULL,
    item_type TEXT DEFAULT '',
    inventarnummer TEXT DEFAULT '',
    fabriknummer TEXT DEFAULT '',
    geraetenummer TEXT DEFAULT '',
    lf_scan TEXT DEFAULT '',
    bemerkung TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS item_identifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    identifier_type TEXT NOT NULL,
    identifier_value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_items_system_group ON items(system_group);
CREATE INDEX IF NOT EXISTS idx_items_active ON items(is_active);
CREATE INDEX IF NOT EXISTS idx_item_identifiers_normalized_value ON item_identifiers(normalized_value);
CREATE INDEX IF NOT EXISTS idx_item_identifiers_item_id ON item_identifiers(item_id);
