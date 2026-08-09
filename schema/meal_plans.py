"""Savdo bo'limi boshlig'i kiritadigan oylik ovqat rejasi, kun bo'yicha."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS meal_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_date TEXT NOT NULL UNIQUE,
    meal_description TEXT NOT NULL,
    entered_by INTEGER NOT NULL,
    entered_at TEXT NOT NULL
);
"""
