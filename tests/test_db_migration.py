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


def test_postgres_bigint_migration_widens_telegram_identity_columns(monkeypatch):
    class Result:
        def fetchall(self):
            return [
                {"table_name": "invites", "column_name": "claimed_by"},
                {"table_name": "employees", "column_name": "user_id"},
                {"table_name": "employee_contacts", "column_name": "user_id"},
                {"table_name": "supplier_offers", "column_name": "supplier_id"},
            ]

    class Connection:
        def __init__(self):
            self.sql = []

        def execute(self, sql, params=()):
            self.sql.append(sql)
            if "information_schema.columns" in sql:
                return Result()
            return Result()

    monkeypatch.setattr(db, "_DATABASE_URL", "postgresql://example")
    conn = Connection()

    db._ensure_postgres_bigint_identity_columns(conn)

    joined = "\n".join(conn.sql)
    assert 'ALTER TABLE "invites" ALTER COLUMN "claimed_by" TYPE BIGINT' in joined
    assert 'ALTER TABLE "employees" ALTER COLUMN "user_id" TYPE BIGINT' in joined
    assert 'ALTER TABLE "employee_contacts" ALTER COLUMN "user_id" TYPE BIGINT' in joined
    assert 'ALTER TABLE "supplier_offers" ALTER COLUMN "supplier_id" TYPE BIGINT' not in joined
    assert "DROP CONSTRAINT IF EXISTS employee_contacts_user_id_fkey" in joined
    assert "ADD CONSTRAINT employee_contacts_user_id_fkey" in joined


def test_single_slot_role_unique_index_exists_after_init(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_FILE", str(tmp_path / "fresh.db"))
    db.init_db()

    conn = db.get_connection()
    try:
        indexes = {
            row["name"] for row in conn.execute("PRAGMA index_list(allowed_users)")
        }
    finally:
        conn.close()

    assert "idx_allowed_users_single_slot_role" in indexes


def test_single_slot_role_unique_index_rejects_duplicate_role_key(tmp_path, monkeypatch):
    """``nazoratchi=1`` DB invarianti — hatto ilova (``roles.set_role()``)
    qatlamidan chetlab o'tib, to'g'ridan-to'g'ri SQL bilan ikkinchi
    nazoratchi yozilsa ham, qisman UNIQUE indeks buni rad etadi.
    """
    monkeypatch.setattr(db, "_DB_FILE", str(tmp_path / "fresh.db"))
    db.init_db()

    conn = db.get_connection()
    try:
        conn.execute(
            "INSERT INTO allowed_users (user_id, role_key, added_by, added_at) "
            "VALUES (1, 'nazoratchi', 999, 'now')"
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO allowed_users (user_id, role_key, added_by, added_at) "
                "VALUES (2, 'nazoratchi', 999, 'now')"
            )
    finally:
        conn.close()


def test_single_slot_role_unique_index_allows_different_single_slot_roles(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_FILE", str(tmp_path / "fresh.db"))
    db.init_db()

    conn = db.get_connection()
    try:
        conn.execute(
            "INSERT INTO allowed_users (user_id, role_key, added_by, added_at) "
            "VALUES (1, 'nazoratchi', 999, 'now')"
        )
        conn.execute(
            "INSERT INTO allowed_users (user_id, role_key, added_by, added_at) "
            "VALUES (2, 'haydovchi', 999, 'now')"
        )
        conn.commit()

        rows = conn.execute("SELECT COUNT(*) AS c FROM allowed_users").fetchone()
        assert rows["c"] == 2
    finally:
        conn.close()
