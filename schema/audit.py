"""RBAC/xavfsizlik audit jurnali — rol o'zgarishi, xodim
faollashtirish/o'chirish, nazoratchi tayinlashga urinish, filiallararo
kirishga urinish va muhim ruxsatsiz boshqaruv amali shu yerga yoziladi
(qarang: ``services/audit.py``). Token/parol/``.env`` qiymati hech qachon
bu jadvalga yozilmaydi.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS security_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    actor_id INTEGER,
    actor_role TEXT,
    chat_id INTEGER,
    target_id INTEGER,
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    request_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
