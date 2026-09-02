"""Business Operating System (BOS): fiks oylik/bonus banki, korxona
nizomlari, kunlik baholash, intizomiy jarima va nazoratchi mas'uliyati.

``employees``/``allowed_users`` kabi bu yerdagi ``user_id``/``employee_id``/
``supervisor_id`` ustunlari ham FK bilan bog'lanmaydi (qarang:
``schema/core.py``dagi ``allowed_users``) — Founder ``/setrole`` orqali
onboarding anketasisiz ham rol biriktirishi mumkin, shuning uchun har
doim ``employees`` jadvalida qatorga ega bo'lishi kafolatlanmaydi.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS salaries (
    user_id INTEGER PRIMARY KEY,
    fixed_salary INTEGER NOT NULL DEFAULT 0,
    bonus_bank INTEGER NOT NULL DEFAULT 0,
    updated_by INTEGER,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS company_rules (
    rule_number INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    supervisor_id INTEGER NOT NULL,
    eval_date TEXT NOT NULL,
    grade_key TEXT NOT NULL,
    grade_points INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    UNIQUE(employee_id, eval_date)
);

CREATE TABLE IF NOT EXISTS discipline_penalties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    supervisor_id INTEGER NOT NULL,
    penalty_date TEXT NOT NULL,
    amount INTEGER NOT NULL,
    rule_number INTEGER NOT NULL REFERENCES company_rules(rule_number),
    comment TEXT,
    ai_note TEXT,
    appeal_status TEXT NOT NULL DEFAULT 'none',
    appeal_reason TEXT,
    appeal_voice_file_id TEXT,
    appeal_ai_brief TEXT,
    appeal_decision TEXT,
    appeal_decided_by INTEGER,
    appeal_decided_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bonus_bank_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    change_amount INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    reason TEXT NOT NULL,
    ref_type TEXT NOT NULL,
    ref_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_closures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supervisor_id INTEGER NOT NULL,
    closure_date TEXT NOT NULL,
    evaluated_count INTEGER NOT NULL,
    total_count INTEGER NOT NULL,
    closed_at TEXT NOT NULL,
    UNIQUE(supervisor_id, closure_date)
);

CREATE TABLE IF NOT EXISTS supervisor_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supervisor_id INTEGER NOT NULL,
    audit_date TEXT NOT NULL,
    event_type TEXT NOT NULL,
    penalty_amount INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(supervisor_id, audit_date, event_type)
);

CREATE TABLE IF NOT EXISTS rule_learning_enrollments (
    employee_id INTEGER PRIMARY KEY,
    enrolled_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS rule_learning_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    rule_number INTEGER NOT NULL,
    title_snapshot TEXT NOT NULL,
    content_snapshot TEXT NOT NULL,
    sent_at TEXT,
    read_confirmed_at TEXT,
    not_understood_at TEXT,
    understood_confirmed_at TEXT,
    completed_at TEXT,
    completed_company_date TEXT,
    UNIQUE(employee_id, rule_number)
);

INSERT OR IGNORE INTO rules (rule_key, rule_value, updated_by, updated_at) VALUES
    ('bos.day_close_deadline', '20:00', NULL, NULL),
    ('bos.supervisor_late_penalty', '40', NULL, NULL),
    ('bos.grade_points.bajarilmagan', '0', NULL, NULL),
    ('bos.grade_points.chala', '1', NULL, NULL),
    ('bos.grade_points.norma', '2', NULL, NULL),
    ('bos.grade_points.alo', '3', NULL, NULL),
    ('bos.penalty_amounts', '10,20,30', NULL, NULL);
"""
