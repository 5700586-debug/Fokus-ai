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
from urllib.parse import urlsplit

import psycopg2

from config import ENVIRONMENT
from schema import SCHEMA_STATEMENTS

_DATA_DIR = os.getenv("FOKUS_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))

# Test muhitida (ENVIRONMENT=test) DATABASE_URL emas, TEST_DATABASE_URL
# o'qiladi, va SQLite fayl nomi ham boshqa (``fokus_test.db``) — shu orqali
# test jarayoni production bazasiga tasodifan hech qachon ulanmaydi, hatto
# ikkalasi ham bir ``.env``da yoki bir diskda tursa ham.
if ENVIRONMENT == "test":
    _DB_FILE = os.path.join(_DATA_DIR, "fokus_test.db")
    _RAW_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
else:
    _DB_FILE = os.path.join(_DATA_DIR, "fokus.db")
    _RAW_DATABASE_URL = os.getenv("DATABASE_URL")

# Render Environment UI'ga qo'lda joylashtirilganda (masalan brauzerdan
# nusxa ko'chirilganda) DATABASE_URL oxiriga bilinmas bo'sh joy yoki
# qator ko'chirish ilashib qolishi mumkin — psycopg2/libpq bunday DSN'ni
# butunlay parslay olmaydi va ulanish sekundida (status 1 bilan) yiqiladi,
# shuning uchun shu yerda tozalanadi. Bo'sh qiymat ham None'ga tenglanadi,
# aks holda pastdagi ``if _DATABASE_URL`` tekshiruvlari bo'sh qatorni ham
# "Postgres yoqilgan" deb noto'g'ri talqin qilib qo'yishi mumkin edi.
_DATABASE_URL = (_RAW_DATABASE_URL or "").strip() or None

# Chaqiruvchi kod (masalan ``performance_bot.py``dagi UNIQUE constraint
# bosilganda foydalanuvchiga tushunarli xabar berish) backend qaysi
# ekanini bilmasdan shu bitta nomni ushlashi mumkin — sqlite3.IntegrityError
# va psycopg2.IntegrityError bir-biriga umuman bog'liq bo'lmagan sinflar,
# shuning uchun to'g'ridan-to'g'ri ``sqlite3.IntegrityError`` ushlash
# Postgres rejimida hech qachon ishlamaydi.
IntegrityError: type[Exception] = psycopg2.IntegrityError if _DATABASE_URL else sqlite3.IntegrityError


def _redact_dsn(url: str) -> str:
    """Log/xato xabarlarida xavfsiz ko'rsatish uchun DSN'dan parolni olib
    tashlaydi — faqat host/port/foydalanuvchi/baza nomi qoladi, shu orqali
    Render loglarida haqiqiy parol hech qachon chiqmaydi.
    """
    try:
        parts = urlsplit(url)
        host = parts.hostname or "?"
        if parts.port:
            host += f":{parts.port}"
        user = f"{parts.username}@" if parts.username else ""
        return f"{parts.scheme}://{user}{host}{parts.path}"
    except Exception:
        return "<DATABASE_URL parslab bo'lmadi>"


# (jadval, ustun, ustun_ta'rifi) — productionda allaqachon mavjud jadvalga
# keyinchalik qo'shilgan ustunlar shu yerda ro'yxatlanadi va ``init_db()``
# ularni yo'q bo'lsagina ``ALTER TABLE`` bilan qo'shadi.
_ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    ("employees", "prior_employer_reference_consent", "INTEGER"),
    ("employees", "prior_employer_contact", "TEXT"),
    ("recruiting_vacancies", "required_shift", "TEXT"),
    ("recruiting_vacancies", "requires_weekends", "INTEGER NOT NULL DEFAULT 0"),
    ("recruiting_applications", "birth_year", "INTEGER"),
    ("recruiting_applications", "residence_area", "TEXT"),
    ("recruiting_applications", "preferred_branch", "TEXT"),
    ("recruiting_applications", "shift_preference", "TEXT"),
    ("recruiting_applications", "unavailable_days_text", "TEXT"),
    ("recruiting_applications", "holiday_available", "INTEGER"),
    ("recruiting_applications", "expected_salary", "TEXT"),
    ("recruiting_applications", "commute_issue", "INTEGER"),
    ("recruiting_applications", "accommodation_needed", "INTEGER"),
    ("recruiting_applications", "accommodation_text", "TEXT"),
    ("recruiting_applications", "fit_result", "TEXT"),
    ("recruiting_applications", "fit_reason", "TEXT"),
    ("recruiting_applications", "prev_employer_text", "TEXT"),
    ("recruiting_applications", "experience_duration_text", "TEXT"),
    ("recruiting_applications", "pos_experience", "INTEGER"),
    ("recruiting_applications", "cash_handling_text", "TEXT"),
    ("recruiting_applications", "reference_check_consent", "INTEGER"),
    ("recruiting_assessments", "red_flags_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("recruiting_assessments", "clarify_questions_json", "TEXT NOT NULL DEFAULT '[]'"),
]


def get_connection():
    if _DATABASE_URL:
        from db_postgres import PgConnection

        try:
            return PgConnection(_DATABASE_URL)
        except Exception as error:
            # Render loglarida qaysi host/port/foydalanuvchiga ulanishga
            # urinilgani ko'rinsin (parolsiz) — aks holda psycopg2'ning
            # xatosi bot ishga tushmagan sababini aniqlashni qiyinlashtiradi.
            print(
                "❌ Postgres'ga ulanib bo'lmadi "
                f"({_redact_dsn(_DATABASE_URL)}): {error!r}"
            )
            raise

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
