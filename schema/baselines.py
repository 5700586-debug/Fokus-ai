"""60 kunlik kalibratsiya davrida yig'ilgan RoleBaseline va yangi xodim
adaptatsiya profillari — bilim individual xodimga bog'lanib qolmasligi
uchun.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS role_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_key TEXT NOT NULL,
    dimension TEXT NOT NULL,
    description TEXT NOT NULL,
    source_note TEXT,
    established_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS employee_adaptation_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role_key TEXT NOT NULL,
    start_date TEXT NOT NULL,
    day_number INTEGER NOT NULL,
    dimension TEXT NOT NULL,
    rating TEXT NOT NULL,
    note TEXT,
    evaluated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calibration_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    role_key TEXT NOT NULL,
    start_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calibration_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES calibration_sessions(id),
    user_id INTEGER NOT NULL,
    role_key TEXT NOT NULL,
    question_date TEXT NOT NULL,
    dimension TEXT NOT NULL,
    question_text TEXT NOT NULL,
    is_cross_check INTEGER NOT NULL DEFAULT 0,
    parent_question_id INTEGER REFERENCES calibration_questions(id),
    follow_up_count INTEGER NOT NULL DEFAULT 0,
    sent_at TEXT NOT NULL,
    answer_text TEXT,
    answered_at TEXT
);

INSERT OR IGNORE INTO rules (rule_key, rule_value, updated_by, updated_at) VALUES
    ('calibration.daily_question_time', '10:00', NULL, NULL);
"""
