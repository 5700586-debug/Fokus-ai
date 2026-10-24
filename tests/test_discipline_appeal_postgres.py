"""E'tirozni atomik yuborish/hal qilish va dialog xabarlari jurnali — PRODUCTION ``PgConnection`` adapteri orqali
HAQIQIY PostgreSQL'da. Faqat vaqtincha lokal PostgreSQL (production/Supabase'ga HECH QACHON ulanmaydi):

    FOKUS_PG_TEST_DSN='postgresql://USER:PAROL@127.0.0.1:PORT/fokus_pgtest_<id>' \\
        python -m pytest -q tests/test_discipline_appeal_postgres.py

DSN o'rnatilmasa fayl SKIP qilinadi (bu PostgreSQL tekshiruvi o'tdi degani EMAS)."""

import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import psycopg2
import pytest

import db
import db_postgres
from repositories import bot_messages
from services import dialog_cleanup, discipline

_DSN = os.getenv("FOKUS_PG_TEST_DSN")

pytestmark = pytest.mark.skipif(not _DSN, reason="FOKUS_PG_TEST_DSN o'rnatilmagan (PostgreSQL tekshiruvi o'tkazilmadi)")

FOUNDER = 1
EMPLOYEE = 7_952_886_089


def _assert_safe_dsn() -> None:
    parts = urlsplit(_DSN)
    assert parts.hostname in ("127.0.0.1", "localhost"), "PG test DSN lokal bo'lishi shart"
    assert (parts.path or "").lstrip("/").startswith("fokus_pgtest_"), "baza nomi fokus_pgtest_ bilan boshlanishi shart"
    for name in ("DATABASE_URL", "TEST_DATABASE_URL"):
        assert os.getenv(name) != _DSN, f"{name} bilan bir xil DSN ishlatish taqiqlangan"


def _scalar(sql: str):
    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(sql)
        return cur.fetchone()[0]
    finally:
        conn.close()


@pytest.fixture(scope="module")
def pg_schema():
    _assert_safe_dsn()
    mp = pytest.MonkeyPatch()
    mp.setattr(db, "_DATABASE_URL", _DSN)
    db.init_db()
    mp.undo()
    yield
    db_postgres.close_all_pools()


@pytest.fixture
def pg(pg_schema, temp_db, monkeypatch):
    _assert_safe_dsn()
    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    try:
        conn.cursor().execute(
            "TRUNCATE discipline_penalties, bonus_bank_ledger, salaries, bot_workflow_messages, company_rules, supervisor_audit, nazoratchi_branch_sessions, daily_evaluations, daily_evaluation_history RESTART IDENTITY CASCADE"
        )
    finally:
        conn.close()
    monkeypatch.setattr(db, "_DATABASE_URL", _DSN)
    yield
    db_postgres.close_all_pools()


def _penalty() -> int:
    discipline.add_rule(1, "Band", "Matn", created_by=FOUNDER)
    return discipline.apply_penalty(EMPLOYEE, FOUNDER, "2026-10-19", 10, 1, "izoh", None)["penalty_id"]


def test_appeal_can_be_submitted_only_once_on_postgres(pg):
    penalty_id = _penalty()
    assert discipline.submit_appeal(penalty_id, "birinchi", None) is not None
    assert discipline.submit_appeal(penalty_id, "ikkinchi", None) is None
    assert discipline.get_penalty(penalty_id)["appeal_reason"] == "birinchi"


def test_parallel_decisions_refund_exactly_once_on_postgres(pg):
    penalty_id = _penalty()
    discipline.submit_appeal(penalty_id, "sabab", None)

    def decide():
        try:
            discipline.decide_appeal(penalty_id, discipline.DECISION_APPROVED, FOUNDER)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = [future.result() for future in [pool.submit(decide) for _ in range(4)]]

    assert outcomes.count(True) == 1
    assert _scalar(f"SELECT bonus_bank FROM salaries WHERE user_id = {EMPLOYEE}") == 0  # -10 + 10 (bir marta)
    assert _scalar("SELECT COUNT(*) FROM bonus_bank_ledger WHERE ref_type = 'appeal_refund'") == 1
    assert _scalar("SELECT COUNT(*) FROM discipline_penalties") == 1  # tarix o'chmagan


def test_dialog_message_log_survives_and_pops_on_postgres(pg):
    from aiogram.types import Chat, Message
    from datetime import datetime

    key = dialog_cleanup.minus_key(EMPLOYEE, "abcd")
    for message_id in (11, 12):
        dialog_cleanup.track(key, Message(message_id=message_id, date=datetime.now(), chat=Chat(id=EMPLOYEE, type="private"), text="x"))
    dialog_cleanup.track(dialog_cleanup.minus_key(EMPLOYEE, "other"), Message(message_id=13, date=datetime.now(), chat=Chat(id=EMPLOYEE, type="private"), text="x"))

    rows = bot_messages.pop_messages(dialog_cleanup.WORKFLOW, key)

    assert sorted(row["message_id"] for row in rows) == [11, 12]
    assert _scalar("SELECT COUNT(*) FROM bot_workflow_messages") == 1  # boshqa dialog tegilmagan


# ------------------------------- qaror + ball qaytarish + ledger BITTA tranzaksiya (PgConnection) --


def _appeal_state(penalty_id: int) -> tuple:
    return (
        _scalar(f"SELECT appeal_status FROM discipline_penalties WHERE id = {penalty_id}"),
        _scalar(f"SELECT COALESCE(SUM(bonus_bank), 0) FROM salaries WHERE user_id = {EMPLOYEE}"),
        _scalar("SELECT COUNT(*) FROM bonus_bank_ledger WHERE ref_type = 'appeal_refund'"),
        _scalar("SELECT COUNT(*) FROM bonus_bank_ledger"),
    )


def _break(table: str, event: str) -> None:
    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE OR REPLACE FUNCTION fokus_pgtest_fail() RETURNS trigger LANGUAGE plpgsql AS "
            "$$ BEGIN RAISE EXCEPTION 'sinov: yozuv xatosi'; END $$"
        )
        cur.execute(f"CREATE TRIGGER fokus_break BEFORE {event} ON {table} FOR EACH ROW EXECUTE FUNCTION fokus_pgtest_fail()")
    finally:
        conn.close()


def _repair(table: str) -> None:
    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    try:
        conn.cursor().execute(f"DROP TRIGGER IF EXISTS fokus_break ON {table}")
    finally:
        conn.close()


def _pending() -> int:
    penalty_id = _penalty()
    assert discipline.submit_appeal(penalty_id, "sabab", None)
    return penalty_id


def test_approval_is_consistent_and_rejection_changes_no_balance_on_postgres(pg):
    approved = _pending()
    discipline.decide_appeal(approved, discipline.DECISION_APPROVED, FOUNDER)
    assert _appeal_state(approved) == ("resolved", 0, 1, 2)

    discipline.add_rule(2, "Band2", "Matn2", created_by=FOUNDER)
    rejected = discipline.apply_penalty(EMPLOYEE, FOUNDER, "2026-10-19", 10, 2, None, None)["penalty_id"]
    discipline.submit_appeal(rejected, "sabab", None)
    before = _appeal_state(rejected)
    discipline.decide_appeal(rejected, discipline.DECISION_REJECTED, FOUNDER)
    after = _appeal_state(rejected)
    assert after[0] == "resolved" and after[1:3] == (before[1], 1) and after[3] == before[3]  # yangi refund yo'q


@pytest.mark.parametrize(
    ("table", "event"),
    [("discipline_penalties", "UPDATE"), ("salaries", "UPDATE"), ("bonus_bank_ledger", "INSERT")],
)
def test_decision_failure_at_each_stage_rolls_back_on_postgres(pg, table, event):
    penalty_id = _pending()
    before = _appeal_state(penalty_id)
    _break(table, event)
    try:
        with pytest.raises(Exception):
            discipline.decide_appeal(penalty_id, discipline.DECISION_APPROVED, FOUNDER)
        assert _appeal_state(penalty_id) == before and before[0] == "pending"
    finally:
        _repair(table)

    discipline.decide_appeal(penalty_id, discipline.DECISION_APPROVED, FOUNDER)  # xatodan keyin qayta urinish
    assert _appeal_state(penalty_id)[0:3] == ("resolved", 0, 1)


@pytest.mark.parametrize("second", ["approved", "rejected"])
def test_parallel_decisions_one_final_decision_at_most_one_refund_on_postgres(pg, second):
    penalty_id = _pending()

    def decide(decision):
        try:
            discipline.decide_appeal(penalty_id, decision, FOUNDER)
            return decision
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = [f.result() for f in [pool.submit(decide, d) for d in ("approved", second, "approved", second)]]

    winners = [o for o in outcomes if o]
    state = _appeal_state(penalty_id)
    assert len(winners) == 1
    assert _scalar(f"SELECT appeal_decision FROM discipline_penalties WHERE id = {penalty_id}") == winners[0]
    assert state[2] == (1 if winners[0] == "approved" else 0)
    assert state[1] == (0 if winners[0] == "approved" else -10)


def test_delivery_claim_is_exclusive_and_mark_is_once_on_postgres(pg):
    penalty_id = _pending()
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = [f.result() for f in [pool.submit(discipline.claim_appeal_delivery, penalty_id) for _ in range(4)]]
    assert claims.count(True) == 1
    assert discipline.mark_appeal_delivered(penalty_id, 4242) is True
    assert discipline.mark_appeal_delivered(penalty_id, 4343) is False
    assert discipline.claim_appeal_delivery(penalty_id) is False  # yetkazilgan: yangi karta yo'q
    row = discipline.get_penalty(penalty_id)
    assert row["appeal_founder_message_id"] == 4242 and row["appeal_delivered_at"]


# ----------------------- nazoratchi "kun yopilmadi" minusi: audit + balans + ledger BITTA tranzaksiya (PgConnection) --


def _audit_state(supervisor_id: int) -> tuple:
    return (
        _scalar(f"SELECT COUNT(*) FROM supervisor_audit WHERE supervisor_id = {supervisor_id}"),
        _scalar(f"SELECT COALESCE(SUM(bonus_bank), 0) FROM salaries WHERE user_id = {supervisor_id}"),
        _scalar(f"SELECT COUNT(*) FROM bonus_bank_ledger WHERE user_id = {supervisor_id}"),
    )


def test_supervisor_late_close_penalty_is_written_once_consistently_on_postgres(pg):
    assert discipline.penalize_supervisor_for_late_close(EMPLOYEE, "2026-03-01", 40) is True
    assert discipline.penalize_supervisor_for_late_close(EMPLOYEE, "2026-03-01", 40) is False  # takroriy
    assert discipline.penalize_supervisor_for_late_close(EMPLOYEE, "2026-03-02", 40) is True   # boshqa ish kuni
    assert _audit_state(EMPLOYEE) == (2, -80, 2)


def test_parallel_supervisor_penalties_for_one_work_date_write_exactly_one_on_postgres(pg):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = [f.result() for f in [pool.submit(discipline.penalize_supervisor_for_late_close, EMPLOYEE, "2026-03-01", 40) for _ in range(4)]]
    assert results.count(True) == 1
    assert _audit_state(EMPLOYEE) == (1, -40, 1)


@pytest.mark.parametrize(("table", "event"), [("bonus_bank_ledger", "INSERT"), ("salaries", "INSERT")])
def test_supervisor_penalty_failure_leaves_nothing_partial_on_postgres(pg, table, event):
    _break(table, event)
    try:
        with pytest.raises(Exception):
            discipline.penalize_supervisor_for_late_close(EMPLOYEE, "2026-03-01", 40)
        assert _audit_state(EMPLOYEE) == (0, 0, 0)
    finally:
        _repair(table)
    assert discipline.penalize_supervisor_for_late_close(EMPLOYEE, "2026-03-01", 40) is True  # qayta urinish
    assert _audit_state(EMPLOYEE) == (1, -40, 1)


# ------------------- baho + filial sessiyasi BITTA tranzaksiya (PgConnection) --


def _grade_state(employee_id: int) -> tuple:
    return (
        _scalar("SELECT COUNT(*) FROM daily_evaluations"),
        _scalar("SELECT COUNT(*) FROM daily_evaluation_history"),
        _scalar(f"SELECT COUNT(*) FROM bonus_bank_ledger WHERE user_id = {employee_id}"),
        _scalar("SELECT COUNT(*) FROM nazoratchi_branch_sessions"),
    )


def test_first_grade_opens_the_session_once_and_repeats_or_races_add_nothing_on_postgres(pg):
    discipline.record_daily_grade(EMPLOYEE, FOUNDER, "2026-03-10", "norma", session_branch="SATURN Charhiy")
    assert _grade_state(EMPLOYEE) == (1, 1, 1, 1)
    discipline.record_daily_grade(EMPLOYEE, FOUNDER, "2026-03-10", "norma", session_branch="SATURN Charhiy")  # takroriy
    assert _grade_state(EMPLOYEE) == (1, 1, 1, 1)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: discipline.record_daily_grade(EMPLOYEE + n, FOUNDER, "2026-03-10", "alo", session_branch="SATURN Charhiy"), range(1, 5)))
    assert _scalar("SELECT COUNT(*) FROM nazoratchi_branch_sessions") == 1


def test_closed_session_is_not_reopened_and_no_branch_means_no_session_on_postgres(pg):
    discipline.record_daily_grade(EMPLOYEE, FOUNDER, "2026-03-10", "norma", session_branch="SATURN Charhiy")
    _scalar("SELECT 1")
    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    try:
        conn.cursor().execute("UPDATE nazoratchi_branch_sessions SET status = 'closed'")
    finally:
        conn.close()

    discipline.record_daily_grade(EMPLOYEE, FOUNDER, "2026-03-10", "alo", session_branch="SATURN Charhiy")
    discipline.record_daily_grade(EMPLOYEE + 9, FOUNDER, "2026-03-10", "alo")  # filial aniqlanmagan

    assert _scalar("SELECT COUNT(*) FROM nazoratchi_branch_sessions WHERE status = 'closed'") == 1
    assert _scalar("SELECT COUNT(*) FROM nazoratchi_branch_sessions") == 1


@pytest.mark.parametrize("table", ["nazoratchi_branch_sessions", "bonus_bank_ledger", "daily_evaluation_history"])
def test_grade_or_session_failure_rolls_everything_back_on_postgres(pg, table):
    _break(table, "INSERT")
    try:
        with pytest.raises(Exception):
            discipline.record_daily_grade(EMPLOYEE, FOUNDER, "2026-03-10", "alo", session_branch="SATURN Charhiy")
        assert _grade_state(EMPLOYEE) == (0, 0, 0, 0)
    finally:
        _repair(table)
    discipline.record_daily_grade(EMPLOYEE, FOUNDER, "2026-03-10", "alo", session_branch="SATURN Charhiy")  # qayta urinish
    assert _grade_state(EMPLOYEE) == (1, 1, 1, 1)


# -------------------- startup "SELECT 1" o'lchovi va rollback hisoblagichi (PgConnection) --


def test_startup_probe_runs_against_real_postgres_and_returns_the_connection(pg):
    from services import db_startup_probe

    line = db_startup_probe._probe_sync(lambda: db_postgres.PgConnection(_DSN))

    assert line.startswith("DB_STARTUP_PROBE outcome=ok samples=7 ")
    assert len(db_postgres._get_pool(_DSN)._used) == 0  # ulanish pool'ga qaytarilgan


def test_explicit_rollback_is_counted_once_and_time_is_inside_db_ms_on_postgres(pg):
    from services import latency_probe

    token = latency_probe._metrics.set(latency_probe._Metrics())
    try:
        metrics = latency_probe._metrics.get()
        conn = db_postgres.PgConnection(_DSN)
        conn.execute("SELECT 1 AS one").fetchone()
        conn.rollback()
        conn.close()  # idle: ichki rollback ham db_finish orqali sanaladi
        assert metrics.db_queries == 1 and metrics.pool_acquires == 1
        assert metrics.rollbacks == 2 and metrics.rollback_total <= metrics.db_total
    finally:
        latency_probe._metrics.reset(token)


# ------------------- /mystars: eski/yangi execute, pool va rollback sonlari (PgConnection) --


def test_mystars_reads_use_one_connection_and_one_rollback_on_postgres(pg, monkeypatch):
    from datetime import date, timedelta

    from services import employee_dashboard, latency_probe
    from tests.test_month_hours_queries import _employee, _seed, _today
    from tests.test_mystars_roundtrips import _legacy_mystars

    _today(monkeypatch, "2026-03-31")
    user = _employee()
    _seed(user, date(2026, 3, 1), date(2026, 4, 2))

    def counted(fn):
        token = latency_probe._metrics.set(latency_probe._Metrics())
        try:
            metrics = latency_probe._metrics.get()
            result = fn()
            return result, (metrics.db_queries, metrics.pool_acquires, metrics.rollbacks)
        finally:
            latency_probe._metrics.reset(token)

    (stars_n, history_n, dash), new = counted(lambda: employee_dashboard.read_mystars(user))
    (stars_o, history_o, old), legacy = counted(lambda: _legacy_mystars(user))

    assert (stars_n, history_n) == (stars_o, history_o)
    assert dash["points"] == old["points"] and dash["hours"] == old["hours"]
    assert dash["yesterday"] == old["yesterday"] and dash["recent_days"] == old["recent_days"]
    print(f"PG /mystars (execute, pool, rollback): yangi={new} eski={legacy}")
    assert new[1] == 1 and new[2] == 1  # bitta ulanish, bitta rollback
    assert new[0] < legacy[0] and new[1] < legacy[1] and new[2] < legacy[2]
