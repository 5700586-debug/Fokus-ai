"""Baholash tranzaksiyasi (``record_daily_grade`` / ``save_daily_grade`` / ``_apply_bonus_delta`` /
``adjust_bonus_bank``) — PRODUCTION'da ishlatiladigan ``PgConnection`` adapteri orqali HAQIQIY PostgreSQL'da.

Faqat vaqtincha lokal PostgreSQL uchun (production/Supabase'ga HECH QACHON ulanmaydi). Ishga tushirish:

    FOKUS_PG_TEST_DSN='postgresql://USER:PAROL@127.0.0.1:PORT/fokus_pgtest_<id>' \\
        python -m pytest -q tests/test_discipline_postgres.py

``FOKUS_PG_TEST_DSN`` o'rnatilmagan bo'lsa fayl SKIP qilinadi (bu PostgreSQL tekshiruvi o'tdi degani EMAS).
Xavfsizlik: DSN hosti lokal, baza nomi ``fokus_pgtest_`` bilan boshlanishi va muhitdagi
``DATABASE_URL``/``TEST_DATABASE_URL``dan farqli bo'lishi shart — aks holda test xato bilan to'xtaydi."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import psycopg2
import pytest

import db
import db_postgres
from schema import SCHEMA_STATEMENTS
from services import discipline

_DSN = os.getenv("FOKUS_PG_TEST_DSN")

pytestmark = pytest.mark.skipif(not _DSN, reason="FOKUS_PG_TEST_DSN o'rnatilmagan (PostgreSQL tekshiruvi o'tkazilmadi)")

_DAY = "2026-10-18"
_USER = 7_952_886_089  # int4 dan katta SINTETIK Telegram-uslubidagi ID (BIGINT ustunlar tekshiruvi)
_TABLES = ("daily_evaluations", "daily_evaluation_history", "salaries", "bonus_bank_ledger")
_RULES_TABLE = "rules"  # ball tariflari (bos.grade_points.*) shu jadvaldan o'qiladi


def _assert_safe_dsn() -> None:
    parts = urlsplit(_DSN)
    assert parts.hostname in ("127.0.0.1", "localhost"), "PG test DSN lokal bo'lishi shart"
    assert (parts.path or "").lstrip("/").startswith("fokus_pgtest_"), "baza nomi fokus_pgtest_ bilan boshlanishi shart"
    for name in ("DATABASE_URL", "TEST_DATABASE_URL"):
        assert os.getenv(name) != _DSN, f"{name} bilan bir xil DSN ishlatish taqiqlangan"
    conn = psycopg2.connect(_DSN)
    try:
        cur = conn.cursor()
        cur.execute("SELECT current_database()")
        assert cur.fetchone()[0].startswith("fokus_pgtest_")
    finally:
        conn.close()


def _admin():
    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    return conn


def _canonical_create_statements() -> list[str]:
    wanted = tuple(f"CREATE TABLE IF NOT EXISTS {name} " for name in (*_TABLES, _RULES_TABLE))
    statements = []
    for script in SCHEMA_STATEMENTS:
        for part in db_postgres._split_script(script):
            if part.startswith(wanted) or part.startswith("INSERT OR IGNORE INTO rules"):
                statements.append(part)
    creates = [st for st in statements if st.startswith("CREATE TABLE")]
    assert len(creates) == len(_TABLES) + 1, "kanonik sxemadan kerakli jadvallar topilmadi"
    # CREATE'lar birinchi, keyin (rules) seed INSERT'lar: kanonik tartib saqlanadi.
    return creates + [st for st in statements if not st.startswith("CREATE TABLE")]


@pytest.fixture(scope="module")
def pg_schema():
    _assert_safe_dsn()
    admin = _admin()
    try:
        cur = admin.cursor()
        for table in (*_TABLES, _RULES_TABLE):
            cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")  # faqat shu vaqtincha bazadagi jadvallar
    finally:
        admin.close()

    mp = pytest.MonkeyPatch()
    mp.setattr(db, "_DATABASE_URL", _DSN)  # db._ensure_postgres_bigint_identity_columns va get_connection uchun
    conn = db_postgres.PgConnection(_DSN)
    try:
        for statement in _canonical_create_statements():  # kanonik sxema matni, production adapteri tarjimasi bilan
            conn.executescript(statement)
        db._ensure_postgres_bigint_identity_columns(conn)  # production'dagi BIGINT kengaytirish
        conn.commit()
    finally:
        conn.close()
    mp.undo()
    yield
    db_postgres.close_all_pools()


@pytest.fixture
def pg(pg_schema, temp_db, monkeypatch):
    """``temp_db`` (SQLite) dan KEYIN: shu testning o'zi uchun ``db`` PostgreSQL'ga yo'naltiriladi."""
    _assert_safe_dsn()
    admin = _admin()
    try:
        cur = admin.cursor()
        cur.execute("DROP TRIGGER IF EXISTS fokus_break ON daily_evaluation_history")
        cur.execute("DROP TRIGGER IF EXISTS fokus_break ON bonus_bank_ledger")
        cur.execute("DROP TRIGGER IF EXISTS fokus_break ON salaries")
        cur.execute(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY")
    finally:
        admin.close()
    monkeypatch.setattr(db, "_DATABASE_URL", _DSN)
    yield
    db_postgres.close_all_pools()


def _break_inserts(table: str) -> None:
    """Haqiqiy PostgreSQL xatosi (RAISE EXCEPTION) — shu jadvalga INSERT paytida, tranzaksiya ichida."""
    admin = _admin()
    try:
        cur = admin.cursor()
        cur.execute(
            "CREATE OR REPLACE FUNCTION fokus_pgtest_fail() RETURNS trigger LANGUAGE plpgsql AS "
            "$$ BEGIN RAISE EXCEPTION 'sinov: yozuv xatosi'; END $$"
        )
        cur.execute(f"CREATE TRIGGER fokus_break BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION fokus_pgtest_fail()")
    finally:
        admin.close()


def _repair(table: str) -> None:
    admin = _admin()
    try:
        admin.cursor().execute(f"DROP TRIGGER fokus_break ON {table}")
    finally:
        admin.close()


def _state(user_id: int = _USER) -> dict:
    """Holat adapterdan MUSTAQIL (alohida psycopg2 ulanishi) o'qiladi."""
    admin = _admin()
    try:
        cur = admin.cursor()
        cur.execute("SELECT grade_key, grade_points FROM daily_evaluations WHERE employee_id = %s AND eval_date = %s", (user_id, _DAY))
        evaluation = cur.fetchone()
        cur.execute("SELECT bonus_bank FROM salaries WHERE user_id = %s", (user_id,))
        salary = cur.fetchone()
        cur.execute("SELECT grade_points FROM daily_evaluation_history WHERE employee_id = %s ORDER BY id", (user_id,))
        history = [row[0] for row in cur.fetchall()]
        cur.execute("SELECT change_amount FROM bonus_bank_ledger WHERE user_id = %s ORDER BY id", (user_id,))
        ledger = [row[0] for row in cur.fetchall()]
    finally:
        admin.close()
    return {
        "grade": tuple(evaluation) if evaluation else None,
        "balance": salary[0] if salary else None,
        "history": history,
        "ledger": ledger,
    }


def _grade(key: str, user_id: int = _USER):
    return discipline.record_daily_grade(user_id, 1, _DAY, key)


# --------------------------------------------------------------- sxema --


def test_real_postgres_schema_matches_canonical_constraints(pg):
    admin = _admin()
    try:
        cur = admin.cursor()
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        cur.execute(
            "SELECT data_type FROM information_schema.columns WHERE table_name = 'daily_evaluations' "
            "AND column_name = 'employee_id'"
        )
        employee_type = cur.fetchone()[0]
        cur.execute(
            "SELECT tc.constraint_type, string_agg(kcu.column_name, ',' ORDER BY kcu.ordinal_position) "
            "FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu "
            "ON tc.constraint_name = kcu.constraint_name WHERE tc.table_name = 'daily_evaluations' "
            "AND tc.constraint_type IN ('UNIQUE', 'PRIMARY KEY') GROUP BY tc.constraint_name, tc.constraint_type"
        )
        constraints = {row[0]: row[1] for row in cur.fetchall()}
        cur.execute(
            "SELECT constraint_type FROM information_schema.table_constraints "
            "WHERE table_name = 'salaries' AND constraint_type = 'PRIMARY KEY'"
        )
        salaries_pk = cur.fetchone()
    finally:
        admin.close()

    print(f"PostgreSQL: {version.split(',')[0]}")
    assert version.startswith("PostgreSQL")
    assert employee_type == "bigint"  # production BIGINT kengaytirishi qo'llangan
    assert constraints.get("UNIQUE") == "employee_id,eval_date" and "PRIMARY KEY" in constraints
    assert salaries_pk is not None


# ----------------------------------------------------- 1-4: oddiy oqim --


def test_first_three_is_written_once_everywhere(pg):
    result = _grade("alo")

    assert result.changed is True and result.bonus_bank_balance == 3
    assert _state() == {"grade": ("alo", 3), "balance": 3, "history": [3], "ledger": [3]}


def test_same_three_again_changes_nothing(pg):
    _grade("alo")

    again = _grade("alo")

    assert again.changed is False and again.old_grade_points == 3
    assert _state() == {"grade": ("alo", 3), "balance": 3, "history": [3], "ledger": [3]}


def test_correction_three_to_two_and_monthly_totals_are_not_a_fake_minus(pg):
    _grade("alo")

    fixed = _grade("norma")

    assert fixed.changed and (fixed.old_grade_points, fixed.grade_points) == (3, 2)
    assert _state() == {"grade": ("norma", 2), "balance": 2, "history": [3, 2], "ledger": [3, -1]}
    totals = discipline.get_period_point_totals(_USER)
    assert (totals["bonus"], totals["minus"], totals["net"]) == (2, 0, 2)


def test_first_zero_is_saved_and_repeated_zero_adds_nothing(pg):
    first = _grade("bajarilmagan")
    again = _grade("bajarilmagan")

    assert first.changed is True and again.changed is False
    assert _state() == {"grade": ("bajarilmagan", 0), "balance": None, "history": [0], "ledger": []}


# ------------------------------------------- 5-7: haqiqiy PG xatolari --


@pytest.mark.parametrize("failing_table", ["daily_evaluation_history", "bonus_bank_ledger", "salaries"])
def test_first_grade_write_error_rolls_everything_back_and_retry_writes_once(pg, failing_table):
    _break_inserts(failing_table)

    with pytest.raises(psycopg2.Error):
        _grade("alo")

    assert _state() == {"grade": None, "balance": None, "history": [], "ledger": []}  # hech biri yarim qolmagan

    _repair(failing_table)
    result = _grade("alo")

    assert result.changed is True
    assert _state() == {"grade": ("alo", 3), "balance": 3, "history": [3], "ledger": [3]}
    assert _grade("alo").changed is False


@pytest.mark.parametrize("failing_table", ["bonus_bank_ledger", "daily_evaluation_history"])
def test_failed_correction_keeps_old_state_and_retry_gives_two(pg, failing_table):
    _grade("alo")
    before = _state()
    _break_inserts(failing_table)

    with pytest.raises(psycopg2.Error):
        _grade("norma")  # 3 -> 2

    assert _state() == before == {"grade": ("alo", 3), "balance": 3, "history": [3], "ledger": [3]}

    _repair(failing_table)
    result = _grade("norma")

    assert result.changed and result.bonus_bank_balance == 2
    assert _state() == {"grade": ("norma", 2), "balance": 2, "history": [3, 2], "ledger": [3, -1]}
    totals = discipline.get_period_point_totals(_USER)
    assert (totals["bonus"], totals["minus"]) == (2, 0)


# ---------------------------------- 8-9: alohida ulanishlardan parallel --


def _run_in_parallel(function, count: int, workers: int = 4):
    barrier = threading.Barrier(workers)

    def task(index):
        if index < workers:
            barrier.wait(timeout=10)  # birinchi to'lqin bir vaqtda boshlanadi
        return function(index)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(task, range(count)))


def test_parallel_identical_grade_from_separate_connections_applies_exactly_one_change(pg):
    results = _run_in_parallel(lambda _: _grade("alo"), count=8)

    assert sum(1 for r in results if r.changed) == 1  # aynan bitta changed=True
    assert _state() == {"grade": ("alo", 3), "balance": 3, "history": [3], "ledger": [3]}


def test_parallel_deltas_on_one_balance_do_not_lose_updates(pg):
    _run_in_parallel(lambda i: discipline.adjust_bonus_bank(_USER, 1, f"sinov {i}", "test", None), count=16)

    state = _state()
    assert state["balance"] == 16
    assert state["ledger"] == [1] * 16
    admin = _admin()
    try:
        cur = admin.cursor()
        cur.execute("SELECT balance_after FROM bonus_bank_ledger WHERE user_id = %s ORDER BY balance_after", (_USER,))
        assert [row[0] for row in cur.fetchall()] == list(range(1, 17))  # har yozuv o'z balansini ko'rgan
    finally:
        admin.close()


def test_parallel_different_corrections_keep_ledger_and_balance_consistent(pg):
    _grade("alo")

    _run_in_parallel(lambda i: _grade("norma" if i % 2 == 0 else "chala"), count=6)

    state = _state()
    assert state["balance"] == sum(state["ledger"])  # ledger yig'indisi = yakuniy balans
    assert state["grade"][1] == state["balance"]  # joriy baho ballari = yakuniy balans (boshqa manba yo'q)
    assert state["history"][0] == 3 and state["history"][-1] == state["balance"]


# ------------------------------------- 10: pool'dan qayta olingan ulanish --


def test_connection_reused_after_error_has_no_leaked_transaction(pg):
    db_postgres.close_all_pools()  # yangi pool: bitta fizik ulanish — qayta ishlatilishi aniq

    def backend_pid():
        conn = db_postgres.PgConnection(_DSN)
        try:
            return conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
        finally:
            conn.close()

    pid_before = backend_pid()
    _break_inserts("bonus_bank_ledger")
    with pytest.raises(psycopg2.Error):
        _grade("alo")  # daftar+tarix+balans yozilgan, ledger'da xato — tugallanmagan tranzaksiya

    conn = db_postgres.PgConnection(_DSN)  # pool'dan qayta olingan ulanish
    try:
        row = conn.execute("SELECT pg_backend_pid() AS pid, txid_current_if_assigned() AS txid").fetchone()
        leaked = conn.execute("SELECT count(*) AS n FROM salaries WHERE user_id = %s", (_USER,)).fetchone()["n"]
    finally:
        conn.close()
    assert row["pid"] == pid_before  # aynan o'sha fizik ulanish qayta ishlatilgan
    assert row["txid"] is None  # tugallanmagan yozuvli tranzaksiya sizib o'tmagan
    assert leaked == 0
    assert _state() == {"grade": None, "balance": None, "history": [], "ledger": []}

    admin = _admin()
    try:
        cur = admin.cursor()
        cur.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'idle in transaction'"
        )
        assert cur.fetchone()[0] == 0
    finally:
        admin.close()

    _repair("bonus_bank_ledger")
    assert _grade("alo").changed is True  # keyingi operatsiya normal
    assert _state() == {"grade": ("alo", 3), "balance": 3, "history": [3], "ledger": [3]}
