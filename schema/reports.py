"""Xodimning kunlik erkin javoblari (ta'minotchi/haydovchi hikoyasi va h.k.).

``content`` — JSON matn sifatida saqlanadi (savol/javob juftliklari),
shuning uchun cross-check va boshqa tahlillar bir xil jadvaldan turli
rol/hisobot turlarini o'qiy oladi.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS employee_daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    report_date TEXT NOT NULL,
    role_key TEXT,
    report_type TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(employee_id, report_date, report_type)
);
"""
