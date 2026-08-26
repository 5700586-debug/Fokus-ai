"""Davomat: hozircha faqat sxema. AttendanceEventProvider ulanguncha
(Face ID, webhook va h.k.) bu jadvallarni to'ldiradigan real oqim yo'q —
``providers/attendance_provider.py`` interfeysiga qarang.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS attendance_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_time TEXT NOT NULL,
    source TEXT NOT NULL,
    raw_reference TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attendance_reasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    event_date TEXT NOT NULL,
    reason_status TEXT NOT NULL,
    note TEXT,
    confirmed_by INTEGER,
    confirmed_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(employee_id, event_date)
);

-- Strukturali kunlik smena jadvali -- ``employees.work_schedule``
-- (erkin matn, majburiy format emas) o'rniga reja soatini ISHONCHLI
-- hisoblash uchun. ``status='work'`` bo'lsa ``planned_start``/
-- ``planned_end`` "HH:MM" formatida; ``status='off'`` bo'lsa ikkalasi
-- ham NULL. Bitta xodim/sana uchun bitta qator -- UNIQUE cheklovi
-- ostida, yozuv yo'q sana esa UNKNOWN (OFF DEB TAXMIN QILINMAYDI).
CREATE TABLE IF NOT EXISTS employee_scheduled_shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    shift_date TEXT NOT NULL,
    planned_start TEXT,
    planned_end TEXT,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(employee_id, shift_date)
);
"""
