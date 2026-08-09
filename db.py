"""SQLite ulanishi va sxema boshlang'ich yaratilishi.

fokus.db shaxsiy xodim ma'lumotlarini saqlaydi, shuning uchun
git repozitoriyaga kirmaydi (.gitignore).

Sxema endi domen bo'yicha ``schema/`` paketida bo'lingan (qarang:
``schema/__init__.py``). Bu yerda faqat ularni yig'ib bajarish va allaqachon
mavjud jadvallarga qo'shilgan yangi ustunlarni (``CREATE TABLE IF NOT
EXISTS`` productiondagi eski jadvalga ustun qo'shmaydi) xavfsiz qo'shib
qo'yish (additive column migration) mantig'i bor.
"""

import os
import sqlite3

from schema import SCHEMA_STATEMENTS

_DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fokus.db")

# (jadval, ustun, ustun_ta'rifi) — productionda allaqachon mavjud jadvalga
# keyinchalik qo'shilgan ustunlar shu yerda ro'yxatlanadi va ``init_db()``
# ularni yo'q bo'lsagina ``ALTER TABLE`` bilan qo'shadi.
_ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    ("employees", "prior_employer_reference_consent", "INTEGER"),
    ("employees", "prior_employer_contact", "TEXT"),
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # Boshqa ulanish faylni qisqa vaqt band qilib turgan bo'lsa ham darhol
    # "database is locked" xatosi bilan yiqilmasdan, biroz kutib qayta urinsin.
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_additive_columns(conn: sqlite3.Connection) -> None:
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
