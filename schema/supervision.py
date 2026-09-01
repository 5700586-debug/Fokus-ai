"""Nazoratchi kunlik nazorat oqimi: xodimga biriktirilgan doimiy
vazifalar/hududlar va vaqt bonusining qo'lda (fallback) tasdiqlash
tarixi.

Ish sifati bahosi (0/1/2/3) ``schema/discipline.py``dagi mavjud
``daily_evaluations`` orqali saqlanadi (yangi baho darajasi
qo'shiladi, jadval o'zi qayta ishlatiladi). Minus ball ham mavjud
``discipline_penalties``/``company_rules`` orqali saqlanadi (qarang
``db.py``dagi ``_ADDITIVE_COLUMNS`` — ``company_rules`` ga
``default_penalty_amount`` ustuni shu orqali qo'shiladi). Bu yerda
FAQAT haqiqatan yangi bo'lgan ikkita narsa uchun jadval bor: vazifa
biriktirish va vaqt bonusi tarixi.

``employee_id``/``assigned_by``/``confirmed_by``/``reported_by``
ustunlari ``schema/discipline.py``dagi bilan bir xil sababga ko'ra FK
bilan bog'lanmaydi (Founder onboarding anketasisiz ham rol
biriktirishi mumkin)."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    employee_id INTEGER NOT NULL,
    assigned_by INTEGER NOT NULL,
    assigned_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(task_id, employee_id)
);

CREATE TABLE IF NOT EXISTS time_bonus_grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    grant_date TEXT NOT NULL,
    source TEXT NOT NULL,
    confirmed_by INTEGER,
    confirmed_at TEXT NOT NULL,
    UNIQUE(employee_id, grant_date)
);

CREATE TABLE IF NOT EXISTS discipline_unmatched_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    reported_by INTEGER NOT NULL,
    report_text TEXT NOT NULL,
    ai_note TEXT,
    status TEXT NOT NULL DEFAULT 'sent_to_founder',
    created_at TEXT NOT NULL
);
"""
