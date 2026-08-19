"""Fokus HR — aqlli rekruter: vakansiya, ariza, javob, rubrika va
tahlil jadvallari.

Nomzod bilan suhbat FSM holati (qaysi savolda turgani) mavjud
``fsm_storage`` (``storage.py``, ``SQLiteStorage``) orqali ALLAQACHON
worker restart'dan omon qoladi — shuning uchun bu yerda alohida
"session" jadvali YO'Q, faqat ``recruiting_applications.current_step``
ustuni (admin ko'rinishi/audit uchun yengil progress belgisi).

Founder qarori (``founder_decision*``) AI tavsiyasidan (``recruiting_assessments``)
ATAYLAB alohida ustunlarda — AI hech qachon yakuniy qaror chiqarmaydi.

``fit_result``/``fit_reason`` — jadval/asosiy talab moslik natijasi
(qarang ``services/recruiting_fit.py``), baholash rubrikasidan ATAYLAB
alohida ustun: talab mosligi axloqiy/kompetensiya bahosi EMAS.

Bu jadvallarga keyinchalik qo'shilgan ustunlar productionda allaqachon
mavjud jadvalga ``ALTER TABLE`` bilan qo'shiladi — qarang
``db._ADDITIVE_COLUMNS``.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS recruiting_vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    schedule_description TEXT,
    required_shift TEXT,
    requires_weekends INTEGER NOT NULL DEFAULT 0,
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
    birth_year INTEGER,
    birth_date_text TEXT,
    birth_day INTEGER,
    birth_month INTEGER,
    phone TEXT,
    residence_area TEXT,
    preferred_branch TEXT,
    shift_preference TEXT,
    unavailable_days_text TEXT,
    holiday_available INTEGER,
    expected_salary TEXT,
    commute_issue INTEGER,
    accommodation_needed INTEGER,
    accommodation_text TEXT,
    fit_result TEXT,
    fit_reason TEXT,
    prev_employer_text TEXT,
    experience_duration_text TEXT,
    pos_experience INTEGER,
    cash_handling_text TEXT,
    reference_check_consent INTEGER,
    prev_salary_text TEXT,
    retention_intent TEXT,
    retention_intent_reason TEXT,
    attendance_barrier_text TEXT,
    substance_policy_agree INTEGER,
    criminal_record INTEGER,
    candidate_photo_file_id TEXT,
    leave_reason_followup_text TEXT,
    property_honesty_flag INTEGER,
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
    red_flags_json TEXT NOT NULL DEFAULT '[]',
    clarify_questions_json TEXT NOT NULL DEFAULT '[]',
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
