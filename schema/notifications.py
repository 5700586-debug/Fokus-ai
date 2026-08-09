"""Yuborilgan (yoki yuborishga urinilgan) xabarlar jurnali — bitta
scheduled xabar ikki marta yuborilib ketmasligi uchun (idempotency).
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_key TEXT NOT NULL,
    target TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent',
    sent_at TEXT NOT NULL,
    UNIQUE(job_key, target)
);
"""
