"""E2E test izolyatsiyasi uchun qo'shilgan ``is_test``/``test_run_id``
ustunlari productionda ALLAQACHON mavjud ``cash_shifts``/
``shift_deficiency_items`` jadvallariga xavfsiz (additive, idempotent)
qo'shilishini tekshiradi — qarang ``db.py``dagi ``_ADDITIVE_COLUMNS``.
``tests/test_db_migration.py``dagi bir xil naqsh (SQLite'ning
additive-column mexanizmi, Postgres'da ``information_schema.columns``
orqali alohida yo'l — bu yerga tegishli emas).
"""

import os
import sqlite3

import pytest

import db

pytestmark = pytest.mark.skipif(
    bool(os.getenv("DATABASE_URL")), reason="SQLite-specific migration mexanizmi"
)


def _old_cash_shifts_and_deficiency_items_sql() -> str:
    """``is_test``/``test_run_id`` qo'shilishidan OLDINGI (production'da
    hozir mavjud) shaklga mos — ikkala jadval ham FK/asosiy ustunlar
    bilan, lekin YANGI 4 ta ustunsiz."""
    return """
    CREATE TABLE cash_shifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        branch TEXT,
        shift_date TEXT NOT NULL,
        opening_balance INTEGER NOT NULL DEFAULT 0,
        tolerance INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        opened_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(employee_id, shift_date)
    );

    CREATE TABLE shift_deficiency_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shift_id INTEGER NOT NULL REFERENCES cash_shifts(id),
        employee_id INTEGER NOT NULL,
        branch TEXT,
        category TEXT NOT NULL,
        product_name TEXT NOT NULL,
        quantity REAL NOT NULL,
        unit TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        source_date TEXT NOT NULL,
        created_at TEXT NOT NULL,
        resolved_at TEXT
    );
    """


def test_e2e_isolation_columns_added_to_old_schema_without_touching_real_rows(tmp_path, monkeypatch):
    old_db_file = str(tmp_path / "old_fokus.db")
    monkeypatch.setattr(db, "_DB_FILE", old_db_file)

    conn = sqlite3.connect(old_db_file)
    try:
        conn.executescript(_old_cash_shifts_and_deficiency_items_sql())
        conn.execute(
            "INSERT INTO cash_shifts "
            "(id, employee_id, branch, shift_date, opening_balance, tolerance, status, "
            "opened_at, created_at, updated_at) "
            "VALUES (1, 111, 'Filial-1', '2026-01-05', 0, 20000, 'open', 'now', 'now', 'now')"
        )
        conn.execute(
            "INSERT INTO shift_deficiency_items "
            "(id, shift_id, employee_id, branch, category, product_name, quantity, unit, status, "
            "source_date, created_at) "
            "VALUES (1, 1, 111, 'Filial-1', 'market', 'Pomidor', 10, 'kg', 'open', '2026-01-05', 'now')"
        )
        conn.commit()
    finally:
        conn.close()

    check_conn = sqlite3.connect(old_db_file)
    try:
        shift_columns_before = {row[1] for row in check_conn.execute("PRAGMA table_info(cash_shifts)")}
        item_columns_before = {row[1] for row in check_conn.execute("PRAGMA table_info(shift_deficiency_items)")}
    finally:
        check_conn.close()
    assert "is_test" not in shift_columns_before
    assert "test_run_id" not in shift_columns_before
    assert "is_test" not in item_columns_before
    assert "test_run_id" not in item_columns_before

    db.init_db()

    conn = db.get_connection()
    try:
        shift_columns_after = {row["name"] for row in conn.execute("PRAGMA table_info(cash_shifts)")}
        item_columns_after = {row["name"] for row in conn.execute("PRAGMA table_info(shift_deficiency_items)")}
        shift_row = conn.execute("SELECT * FROM cash_shifts WHERE id = 1").fetchone()
        item_row = conn.execute("SELECT * FROM shift_deficiency_items WHERE id = 1").fetchone()
    finally:
        conn.close()

    assert {"is_test", "test_run_id"} <= shift_columns_after
    assert {"is_test", "test_run_id"} <= item_columns_after

    # Eski real qatorlar o'zgarishsiz qolgan va yangi ustun standart
    # qiymati bilan avtomatik "real" (is_test=0) deb belgilangan.
    assert shift_row["employee_id"] == 111
    assert shift_row["branch"] == "Filial-1"
    assert shift_row["is_test"] == 0
    assert shift_row["test_run_id"] is None

    assert item_row["product_name"] == "Pomidor"
    assert item_row["quantity"] == 10
    assert item_row["is_test"] == 0
    assert item_row["test_run_id"] is None


def test_e2e_isolation_columns_migration_runs_twice_without_error(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_FILE", str(tmp_path / "fresh.db"))

    db.init_db()
    db.init_db()  # ustunlar allaqachon mavjud bo'lsa ham xato bermasligi kerak

    conn = db.get_connection()
    try:
        shift_columns = {row["name"] for row in conn.execute("PRAGMA table_info(cash_shifts)")}
        item_columns = {row["name"] for row in conn.execute("PRAGMA table_info(shift_deficiency_items)")}
    finally:
        conn.close()

    assert {"is_test", "test_run_id"} <= shift_columns
    assert {"is_test", "test_run_id"} <= item_columns
