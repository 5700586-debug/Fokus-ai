"""Fokus HR — aqlli rekruter: vakansiya, ariza, javob, rubrika va
tahlil jadvallari.

Nomzod bilan suhbat FSM holati (qaysi savolda turgani) mavjud
``fsm_storage`` (``storage.py``, ``SQLiteStorage``) orqali ALLAQACHON
worker restart'dan omon qoladi — shuning uchun bu yerda alohida
"session" jadvali YO'Q, faqat ``recruiting_applications.current_step``
ustuni (admin ko'rinishi/audit uchun yengil progress belgisi).

Founder qarori (``founder_decision*``) AI tavsiyasidan (``recruiting_assessments``)
ATAYLAB alohida ustunlarda — AI hech qachon yakuniy qaror chiqarmaydi.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS recruiting_vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    schedule_description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS recruiting_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_telegram_id INTEGER NOT NULL,
    vacancy_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_progress',
    current_step TEXT,
    full_name TEXT,
    phone TEXT,
    experience_text TEXT,
    leave_reason_text TEXT,
    availability_text TEXT,
    start_date_text TEXT,
    motivation_text TEXT,
    follow_up_count INTEGER NOT NULL DEFAULT 0,
    consent_given_at TEXT,
    founder_decision TEXT,
    founder_decision_by INTEGER,
    founder_decision_at TEXT,
    retention_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    cancelled_at TEXT
);

CREATE TABLE IF NOT EXISTS recruiting_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    question_key TEXT NOT NULL,
    question_text TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    answer_source TEXT NOT NULL DEFAULT 'text',
    is_follow_up INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recruiting_rubric_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    criteria_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(position_key, version)
);

CREATE TABLE IF NOT EXISTS recruiting_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL UNIQUE,
    rubric_version_id INTEGER NOT NULL,
    overall_result TEXT NOT NULL,
    criteria_scores_json TEXT NOT NULL,
    strengths_json TEXT NOT NULL,
    risks_json TEXT NOT NULL,
    ai_summary TEXT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);

INSERT OR IGNORE INTO recruiting_vacancies
    (position_key, title, schedule_description, is_active, created_at, updated_at)
VALUES
    ('kassir', 'Kassir', NULL, 1, NULL, NULL),
    ('sotuvchi', 'Sotuvchi', NULL, 1, NULL, NULL);
"""
