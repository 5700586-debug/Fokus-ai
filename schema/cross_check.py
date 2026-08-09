"""Ta'minotchi/haydovchi javoblarini mustaqil taqqoslash uchun sessiyalar."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS cross_check_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL,
    employee_a_id INTEGER NOT NULL,
    employee_b_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    summary TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    UNIQUE(session_date, employee_a_id, employee_b_id)
);

CREATE TABLE IF NOT EXISTS cross_check_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES cross_check_sessions(id),
    employee_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
