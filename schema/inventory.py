"""Kunlik ombor/qoldiq qiymati nazorati: har kunlik snapshot, kechagi
qiymatga nisbatan farq, tasdiqlangan sabablar (explained) va
tushuntirilmagan qoldiq (unexplained variance).

Hisoblash mantiqi ``services/inventory_snapshot.py`` da — bu yerda
faqat jadval ta'rifi.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory_daily_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch TEXT,
    snapshot_date TEXT NOT NULL,
    reported_by_employee_id INTEGER NOT NULL,
    total_inventory_value INTEGER NOT NULL,
    previous_inventory_value INTEGER,
    gross_difference INTEGER,
    explained_variance INTEGER NOT NULL DEFAULT 0,
    unexplained_variance INTEGER,
    threshold INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    photo_reference TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(branch, snapshot_date)
);

CREATE TABLE IF NOT EXISTS inventory_variance_explanations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES inventory_daily_snapshots(id),
    cause TEXT NOT NULL,
    amount INTEGER NOT NULL,
    comment TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_variance_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES inventory_daily_snapshots(id),
    reviewed_by INTEGER NOT NULL,
    decision TEXT NOT NULL,
    comment TEXT,
    reviewed_at TEXT NOT NULL
);

INSERT OR IGNORE INTO rules (rule_key, rule_value, updated_by, updated_at) VALUES
    ('inventory.variance_threshold', '1000000', NULL, NULL),
    ('inventory.reminder_time', '20:00', NULL, NULL);
"""
