"""Postgres orqasida ``sqlite3.Connection``ga o'xshash sirtqi interfeys.

``repositories/*.py``, ``employees.py``, ``storage.py``, ``invites.py``
barchasi ``conn.execute(sql, params).fetchone()/.fetchall()``,
``cursor.lastrowid``, ``cursor.rowcount``, ``row["col"]``,
``conn.executescript(...)`` naqshlariga tayanadi (sqlite3 API'sining bir
qismi). Bu modul aynan shu sirtqi interfeysni psycopg2 ustida qayta
yaratadi, shunday qilib ``db.get_connection()`` orqasidagi backend
(SQLite yoki Postgres) almashsa ham chaqiruvchi kod o'zgarishsiz qoladi.

SQL matni ham shu yerda kichik tarjima qilinadi (SQLite -> Postgres):
``?`` -> ``%s`` placeholder, ``INSERT OR IGNORE`` -> ``ON CONFLICT DO
NOTHING``, ``INTEGER PRIMARY KEY AUTOINCREMENT`` -> ``SERIAL PRIMARY
KEY``. Bu tarjima faqat ``schema/`` va ``repositories/`` da haqiqatda
ishlatiladigan naqshlar uchun mo'ljallangan — umumiy SQL parser emas.
"""

import re

import psycopg2
import psycopg2.extras

from schema import SCHEMA_STATEMENTS

_PLACEHOLDER_RE = re.compile(r"\?")
_AUTOINCREMENT_RE = re.compile(r"INTEGER PRIMARY KEY AUTOINCREMENT", re.IGNORECASE)
# SQLite'da ``col IS ?`` NULL-xavfsiz tenglik uchun ishlatiladi (masalan
# ixtiyoriy ``branch`` ustuni) va ``?`` ga NULL ham, oddiy qiymat ham
# bog'lanishi mumkin. Postgres'da ``IS`` faqat ``NULL``/``TRUE``/``FALSE``
# operandlarini qabul qiladi — ekvivalenti ``IS NOT DISTINCT FROM``.
_IS_NULL_SAFE_RE = re.compile(r"\bIS\s+\?", re.IGNORECASE)
_INSERT_TABLE_RE = re.compile(r"INSERT(?:\s+OR\s+IGNORE)?\s+INTO\s+(\w+)", re.IGNORECASE)
_SERIAL_TABLE_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS (\w+) \(\s*id INTEGER PRIMARY KEY AUTOINCREMENT",
    re.IGNORECASE,
)

# ``employees.emergency_contact_id`` va ``employee_contacts.user_id``
# bir-birini REFERENCES qiladi (dumaloq bog'lanish) — SQLite CREATE
# TABLE vaqtida bunga tekshirmaydi, lekin Postgres tekshiradi, shuning
# uchun ``employees`` yaratilganda bu ustun cheklovsiz qoldiriladi va
# ``employee_contacts`` yaratilgandan keyin ALTER TABLE bilan qo'shiladi
# (qarang: ``_ensure_emergency_contact_fk``).
_EMERGENCY_FK_RE = re.compile(
    r"emergency_contact_id INTEGER REFERENCES employee_contacts\(id\)", re.IGNORECASE
)
_EMERGENCY_FK_CONSTRAINT = "employees_emergency_contact_fk"


def _serial_pk_tables() -> set[str]:
    tables: set[str] = set()
    for statement in SCHEMA_STATEMENTS:
        tables.update(match.lower() for match in _SERIAL_TABLE_RE.findall(statement))
    return tables


_SERIAL_PK_TABLES = _serial_pk_tables()


def _translate_statement(sql: str) -> tuple[str, bool]:
    """Bitta SQL bayonotini SQLite dialektidan Postgres'ga o'giradi.
    Ikkinchi qaytariladigan qiymat — ``emergency_contact_id`` FK shu
    bayonotdan olib tashlangan-tashlanmaganini bildiradi (kechiktirilgan
    ALTER TABLE kerakligini chaqiruvchiga bildirish uchun).
    """
    stripped_fk = bool(_EMERGENCY_FK_RE.search(sql))
    sql = _EMERGENCY_FK_RE.sub("emergency_contact_id INTEGER", sql)
    sql = _AUTOINCREMENT_RE.sub("SERIAL PRIMARY KEY", sql)
    sql = _IS_NULL_SAFE_RE.sub("IS NOT DISTINCT FROM ?", sql)

    lead = sql.strip()[:21].upper()
    if lead.startswith("INSERT OR IGNORE INTO"):
        sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, count=1, flags=re.IGNORECASE)
        sql = sql.rstrip()
        if sql.endswith(";"):
            sql = sql[:-1]
        sql += " ON CONFLICT DO NOTHING"

    sql = _PLACEHOLDER_RE.sub("%s", sql)
    return sql, stripped_fk


def _split_script(script: str) -> list[str]:
    return [part.strip() for part in script.split(";") if part.strip()]


class _PgCursorResult:
    def __init__(self, cursor, lastrowid):
        self._cursor = cursor
        self.lastrowid = lastrowid

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class PgConnection:
    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)

    # sqlite3.Connection'da hech qanday amal bermaydi (Postgres FK'ni
    # doim majburlaydi) — chaqiruvchi tomon (``db.get_connection()``)
    # buni hech shart bo'lmasa ham chaqirishi mumkin.
    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, _value) -> None:
        pass

    def execute(self, sql: str, params=()) -> _PgCursorResult:
        translated, _stripped_fk = _translate_statement(sql)
        cursor = self._conn.cursor()
        cursor.execute(translated, params)

        lastrowid = None
        table_match = _INSERT_TABLE_RE.match(sql.strip())
        if table_match and table_match.group(1).lower() in _SERIAL_PK_TABLES:
            lastval_cursor = self._conn.cursor()
            lastval_cursor.execute("SELECT lastval() AS lastval")
            row = lastval_cursor.fetchone()
            lastrowid = row["lastval"] if row else None

        return _PgCursorResult(cursor, lastrowid)

    def executescript(self, script: str) -> None:
        cursor = self._conn.cursor()
        needs_emergency_fk = False
        for statement in _split_script(script):
            translated, stripped_fk = _translate_statement(statement)
            needs_emergency_fk = needs_emergency_fk or stripped_fk
            cursor.execute(translated)

        if needs_emergency_fk:
            self._ensure_emergency_contact_fk(cursor)

    def _ensure_emergency_contact_fk(self, cursor) -> None:
        cursor.execute(
            "SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = %s",
            (_EMERGENCY_FK_CONSTRAINT,),
        )
        if cursor.fetchone() is None:
            cursor.execute(
                f"ALTER TABLE employees ADD CONSTRAINT {_EMERGENCY_FK_CONSTRAINT} "
                "FOREIGN KEY (emergency_contact_id) REFERENCES employee_contacts(id)"
            )

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
