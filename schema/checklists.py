"""Lavozim checklist/nizom matnlari va xodimning o'quv progressi."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS checklists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_key TEXT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    checklist_id INTEGER NOT NULL REFERENCES checklists(id),
    status TEXT NOT NULL DEFAULT 'assigned',
    understanding_note TEXT,
    assigned_at TEXT NOT NULL,
    completed_at TEXT
);
"""
