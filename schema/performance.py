"""Rules (configurable thresholds), Nazoratchi bahosi, yulduz/bonus tarixi.

``rules`` — umumiy kalit/qiymat jadvali. Bo'sh (mavjud bo'lmagan) qatorlar
``INSERT OR IGNORE`` bilan seed qilinadi — shuning uchun Founder keyin
``/setrule`` orqali o'zgartirsa, bot qayta ishga tushganda qayta
ustidan yozib yuborilmaydi.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
    rule_key TEXT PRIMARY KEY,
    rule_value TEXT NOT NULL,
    updated_by INTEGER,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS supervisor_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    scored_by INTEGER NOT NULL,
    score_date TEXT NOT NULL,
    score INTEGER NOT NULL,
    comment TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, score_date)
);

CREATE TABLE IF NOT EXISTS monthly_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    year_month TEXT NOT NULL,
    avg_supervisor_score REAL,
    attendance_ok INTEGER,
    no_serious_violation INTEGER,
    checklist_completed INTEGER,
    full_bonus_month INTEGER NOT NULL,
    computed_at TEXT NOT NULL,
    UNIQUE(user_id, year_month)
);

CREATE TABLE IF NOT EXISTS star_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    year_month TEXT NOT NULL,
    previous_stars INTEGER NOT NULL,
    new_stars INTEGER NOT NULL,
    change INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, year_month)
);

CREATE TABLE IF NOT EXISTS bonus_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    year_month TEXT NOT NULL,
    stars INTEGER NOT NULL,
    bonus_amount INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, year_month)
);

INSERT OR IGNORE INTO rules (rule_key, rule_value, updated_by, updated_at) VALUES
    ('bonus.stars.1', '50000', NULL, NULL),
    ('bonus.stars.2', '110000', NULL, NULL),
    ('bonus.stars.3', '200000', NULL, NULL),
    ('bonus.stars.4', '300000', NULL, NULL),
    ('bonus.stars.5', '500000', NULL, NULL),
    ('star.max', '5', NULL, NULL),
    ('star.min', '0', NULL, NULL),
    ('full_bonus_month.min_supervisor_score', '80', NULL, NULL),
    ('full_bonus_month.require_attendance_ok', '1', NULL, NULL),
    ('full_bonus_month.require_no_serious_violation', '1', NULL, NULL),
    ('full_bonus_month.require_checklist_completed', '1', NULL, NULL);
"""
