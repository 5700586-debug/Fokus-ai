"""Kassir kunlik smena nazorati: naqd/karta/boshqa savdo, xarajatlar,
kutilayotgan vs real kassa qoldig'i farqi va Nazoratchi/Founder tekshiruvi.

Formulalar va status hisoblash ``services/cash_shift.py`` da — bu yerda
faqat jadval ta'rifi.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS cash_shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    branch TEXT,
    shift_date TEXT NOT NULL,
    opening_balance INTEGER NOT NULL DEFAULT 0,
    cash_sales INTEGER,
    card_sales INTEGER,
    other_payments INTEGER,
    total_sales INTEGER,
    cash_expenses INTEGER,
    expected_cash_balance INTEGER,
    actual_cash_balance INTEGER,
    difference INTEGER,
    tolerance INTEGER NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    sales_report_photo_ref TEXT,
    cash_report_photo_ref TEXT,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(employee_id, shift_date)
);

CREATE TABLE IF NOT EXISTS cash_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id INTEGER NOT NULL REFERENCES cash_shifts(id),
    employee_id INTEGER NOT NULL,
    branch TEXT,
    category TEXT NOT NULL,
    amount INTEGER NOT NULL,
    description TEXT,
    expense_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cash_difference_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id INTEGER NOT NULL REFERENCES cash_shifts(id),
    attempt_number INTEGER NOT NULL,
    actual_cash_balance INTEGER NOT NULL,
    difference INTEGER NOT NULL,
    status_after TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cash_shift_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id INTEGER NOT NULL REFERENCES cash_shifts(id),
    reviewed_by INTEGER NOT NULL,
    decision TEXT NOT NULL,
    comment TEXT,
    reviewed_at TEXT NOT NULL
);

INSERT OR IGNORE INTO rules (rule_key, rule_value, updated_by, updated_at) VALUES
    ('cash_shift.tolerance', '20000', NULL, NULL),
    ('cash_shift.retry_limit', '3', NULL, NULL),
    ('cash_expense.baseline_min_observations', '7', NULL, NULL),
    ('cash_expense.anomaly_multiplier', '1.5', NULL, NULL);
"""
