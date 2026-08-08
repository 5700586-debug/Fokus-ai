"""SQLite ulanishi va sxema boshlang'ich yaratilishi.

fokus.db shaxsiy xodim ma'lumotlarini saqlaydi, shuning uchun
git repozitoriyaga kirmaydi (.gitignore).
"""

import os
import sqlite3

_DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fokus.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS invites (
    token TEXT PRIMARY KEY,
    role_key TEXT NOT NULL,
    branch TEXT NOT NULL,
    work_schedule TEXT,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    claimed_by INTEGER,
    claimed_at TEXT
);

CREATE TABLE IF NOT EXISTS employees (
    user_id INTEGER PRIMARY KEY,
    invite_token TEXT REFERENCES invites(token),
    telegram_username TEXT,
    familiya TEXT,
    ism TEXT,
    otasining_ismi TEXT,
    birth_date TEXT,
    age INTEGER,
    jinsi TEXT,
    phone TEXT,
    marital_status TEXT,
    viloyat TEXT,
    tuman TEXT,
    mahalla TEXT,
    kocha TEXT,
    uy_raqami TEXT,
    xonadon_raqami TEXT,
    branch TEXT,
    role_key TEXT,
    hire_date TEXT,
    work_schedule TEXT,
    planned_duration TEXT,
    motivation TEXT,
    prior_experience TEXT,
    emergency_contact_id INTEGER REFERENCES employee_contacts(id),
    photo_file_id TEXT,
    extra_note TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    submitted_at TEXT,
    approved_at TEXT,
    approved_by INTEGER,
    rejected_at TEXT,
    rejected_by INTEGER
);

CREATE TABLE IF NOT EXISTS employee_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES employees(user_id),
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    relation TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fsm_storage (
    storage_key TEXT PRIMARY KEY,
    state TEXT,
    data TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
