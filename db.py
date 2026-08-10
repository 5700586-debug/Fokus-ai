"""DB ulanishi va sxema boshlang'ich yaratilishi.

Ikki backend qo'llab-quvvatlanadi:

- **SQLite** (standart) — ``fokus.db`` shaxsiy xodim ma'lumotlarini
  saqlaydi, shuning uchun git repozitoriyaga kirmaydi (.gitignore).
  Render kabi platformalarda ilova papkasi konteyner qayta
  yaratilganda (deploy/restart) reset bo'ladigan ephemeral disk
  bo'lishi mumkin — shu sabab ``FOKUS_DATA_DIR`` muhit o'zgaruvchisi
  orqali fayl doimiy diskka ko'chirilishi mumkin. O'rnatilmasa,
  xatti-harakat o'zgarmaydi (ilova papkasi ishlatiladi).
- **Postgres** (``DATABASE_URL`` o'rnatilsa, masalan Supabase/Neon
  connection string) — Render Free plan disk qo'llab-quvvatlamaydi,
  shuning uchun ma'lumotlar tashqi bazada saqlanadi va deploy/restart
  uni o'chirmaydi. Qarang: ``db_postgres.py``.

Sxema endi domen bo'yicha ``schema/`` paketida bo'lingan (qarang:
``schema/__init__.py``). Bu yerda faqat ularni yig'ib bajarish va allaqachon
mavjud jadvallarga qo'shilgan yangi ustunlarni (``CREATE TABLE IF NOT
EXISTS`` productiondagi eski jadvalga ustun qo'shmaydi) xavfsiz qo'shib
qo'yish (additive column migration) mantig'i bor.
"""

import os
import sqlite3

from schema import SCHEMA_STATEMENTS

_DATA_DIR = os.getenv("FOKUS_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
_DB_FILE = os.path.join(_DATA_DIR, "fokus.db")
_DATABASE_URL = os.getenv("DATABASE_URL")

# (jadval, ustun, ustun_ta'rifi) — productionda allaqachon mavjud jadvalga
# keyinchalik qo'shilgan ustunlar shu yerda ro'yxatlanadi va ``init_db()``
# ularni yo'q bo'lsagina ``ALTER TABLE`` bilan qo'shadi.
_ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    ("employees", "prior_employer_reference_consent", "INTEGER"),
    ("employees", "prior_employer_contact", "TEXT"),
]


def get_connection():
    if _DATABASE_URL:
        from db_postgres import PgConnection

        return PgConnection(_DATABASE_URL)

    conn = sqlite3.connect(_DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # Boshqa ulanish faylni qisqa vaqt band qilib turgan bo'lsa ham darhol
    # "database is locked" xatosi bilan yiqilmasdan, biroz kutib qayta urinsin.
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_additive_columns(conn) -> None:
    if _DATABASE_URL:
        for table, column, coltype in _ADDITIVE_COLUMNS:
            existing = {
                row["column_name"]
                for row in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    (table,),
                ).fetchall()
            }
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        return

    for table, column, coltype in _ADDITIVE_COLUMNS:
        existing = {
            row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def init_db() -> None:
    conn = get_connection()
    try:
        for statement in SCHEMA_STATEMENTS:
            conn.executescript(statement)
        _ensure_additive_columns(conn)
        conn.commit()
    finally:
        conn.close()
