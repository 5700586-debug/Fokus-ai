import os
import sqlite3

import pytest

import db

# Bu fayl bevosita ``sqlite3.connect``/``PRAGMA table_info`` ishlatadi —
# SQLite'ning additive-column migratsiya mexanizmini tekshiradi, Postgres
# backend'ga tegishli emas (qarang: ``db_postgres.py``'da xuddi shu
# mantiq ``information_schema.columns`` orqali qilinadi).
pytestmark = pytest.mark.skipif(
    bool(os.getenv("DATABASE_URL")), reason="SQLite-specific migration mexanizmi"
)


def _old_employees_table_sql() -> str:
    return """
    CREATE TABLE employees (
        user_id INTEGER PRIMARY KEY,
        invite_token TEXT,
        familiya TEXT,
        ism TEXT,
        status TEXT NOT NULL DEFAULT 'draft'
    );
    """


def test_additive_columns_are_added_to_old_schema(tmp_path, monkeypatch):
    old_db_file = str(tmp_path / "old_fokus.db")
    monkeypatch.setattr(db, "_DB_FILE", old_db_file)

    conn = sqlite3.connect(old_db_file)
    try:
        conn.executescript(_old_employees_table_sql())
        conn.execute(
            "INSERT INTO employees (user_id, familiya, status) VALUES (1, 'Familiyev', 'submitted')"
        )
        conn.commit()
    finally:
        conn.close()

    check_conn = sqlite3.connect(old_db_file)
    try:
        columns_before = {row[1] for row in check_conn.execute("PRAGMA table_info(employees)")}
    finally:
        check_conn.close()
    assert "prior_employer_reference_consent" not in columns_before

    db.init_db()

    conn = db.get_connection()
    try:
        columns_after = {row["name"] for row in conn.execute("PRAGMA table_info(employees)")}
        row = conn.execute(
            "SELECT * FROM employees WHERE user_id = 1"
        ).fetchone()
    finally:
        conn.close()

    assert "prior_employer_reference_consent" in columns_after
    assert "prior_employer_contact" in columns_after
    # Eski qator (va uning ma'lumotlari) saqlanib qolgan bo'lishi kerak.
    assert row["familiya"] == "Familiyev"
    assert row["prior_employer_reference_consent"] is None


def test_additive_column_migration_runs_twice_without_error(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_FILE", str(tmp_path / "fresh.db"))

    db.init_db()
    db.init_db()  # ustun allaqachon mavjud bo'lsa ham xato bermasligi kerak

    conn = db.get_connection()
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(employees)")}
    finally:
        conn.close()

    assert "prior_employer_reference_consent" in columns
