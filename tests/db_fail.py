"""Testlarda HAQIQIY DB yozuv xatosini simulyatsiya qilish — SQLite va Postgres ikkalasida.

SQLite: ``CREATE TRIGGER ... BEGIN SELECT RAISE(ABORT, ...); END``.
Postgres: plpgsql funksiya + ``CREATE TRIGGER ... FOR EACH ROW EXECUTE FUNCTION``.
Xato tranzaksiya ICHIDA, yozuv paytida chiqadi — monkeypatch emas, haqiqiy rollback tekshiriladi.
"""

import sqlite3

import db

if db._DATABASE_URL:
    import psycopg2

    WRITE_ERROR: type[Exception] = psycopg2.Error
else:
    WRITE_ERROR = sqlite3.IntegrityError


def _is_postgres() -> bool:
    return bool(db._DATABASE_URL)


def break_writes(table: str, event: str = "INSERT", name: str = "fokus_break", message: str = "sinov xatosi") -> None:
    """``table`` ga ``event`` (INSERT/UPDATE) paytida xato beradigan trigger o'rnatadi."""
    conn = db.get_connection()
    try:
        if _is_postgres():
            conn.execute(
                f"CREATE OR REPLACE FUNCTION {name}_fn() RETURNS trigger LANGUAGE plpgsql AS "
                f"$fokus$ BEGIN RAISE EXCEPTION '{message}'; END $fokus$"
            )
            conn.execute(f"CREATE TRIGGER {name} BEFORE {event} ON {table} FOR EACH ROW EXECUTE FUNCTION {name}_fn()")
        else:
            conn.execute(f"CREATE TRIGGER {name} BEFORE {event} ON {table} BEGIN SELECT RAISE(ABORT, '{message}'); END")
        conn.commit()
    finally:
        conn.close()


def repair(table: str, name: str = "fokus_break") -> None:
    """``break_writes`` o'rnatgan triggerni olib tashlaydi (yo'q bo'lsa jim)."""
    conn = db.get_connection()
    try:
        conn.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}" if _is_postgres() else f"DROP TRIGGER IF EXISTS {name}")
        conn.commit()
    finally:
        conn.close()


def table_columns(table: str) -> set[str]:
    """Jadval ustunlari nomlari (SQLite ``PRAGMA``, Postgres ``information_schema``)."""
    conn = db.get_connection()
    try:
        if _is_postgres():
            rows = conn.execute(
                "SELECT column_name AS name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = ?",
                (table,),
            ).fetchall()
        else:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row["name"] for row in rows}
    finally:
        conn.close()


def table_exists(table: str) -> bool:
    conn = db.get_connection()
    try:
        if _is_postgres():
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = ?",
                (table,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS n FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
        return row["n"] > 0
    finally:
        conn.close()


def list_tables() -> list[str]:
    """Foydalanuvchi jadvallari ro'yxati (SQLite ``sqlite_master``, Postgres ``information_schema``)."""
    conn = db.get_connection()
    try:
        if _is_postgres():
            rows = conn.execute(
                "SELECT table_name AS name FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
            ).fetchall()
        else:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        return [row["name"] for row in rows]
    finally:
        conn.close()
