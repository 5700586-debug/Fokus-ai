"""Two real dispatcher paths, synthetic SQLite/CI PostgreSQL data, no external API calls."""

from datetime import datetime, timedelta
import re

import pytest

import company_time
import db
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from roles import set_role
from services import attendance, discipline, employee_dashboard, latency_probe, nazoratchi_day
from repositories import discipline as discipline_repo
from tests.bot_harness import RecordingBot, send_callback
from tests.test_menu_screen_cleanup import FakeSession, env  # noqa: F401

pytestmark = pytest.mark.anyio
SUP, EMP = 1, 880001


def _connection_type():
    if db._DATABASE_URL:
        from db_postgres import PgConnection

        return PgConnection
    return db._MeasuredSqliteConnection


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def seeded(monkeypatch):
    now = datetime(2026, 10, 26, 12, 0, tzinfo=company_time.resolve_timezone())
    monkeypatch.setattr(company_time, "now", lambda: now)
    set_role(SUP, "nazoratchi", set_by=FOUNDER_ID)
    set_role(EMP, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(EMP, {"familiya": "Test", "ism": "Ali", "branch": RECRUITING_BRANCH_NAMES[0],
                                  "role_key": "kassir", "hire_date": "2026-10-01", "contacts": []})
    employees.approve_profile(EMP, approved_by=FOUNDER_ID)
    today = company_time.today()
    for offset in range(3):
        day = today - timedelta(days=offset)
        attendance.set_scheduled_work_shift(EMP, day.isoformat(), "08:00", "18:00", "test")
        attendance.record_manual_arrival(EMP, day.isoformat(), "08:00")
    return now


@pytest.fixture
def sql_trace(monkeypatch):
    class Trace(list):
        opened = set()

    captured = Trace()
    connection_type = _connection_type()
    real = connection_type.execute
    real_close = connection_type.close

    def execute(conn, sql, *args, **kwargs):
        captured.opened.add(conn)
        captured.append((sql, latency_probe._metrics.get() is not None))
        return real(conn, sql, *args, **kwargs)

    def close(conn):
        captured.opened.discard(conn)
        return real_close(conn)

    monkeypatch.setattr(connection_type, "execute", execute)
    monkeypatch.setattr(connection_type, "close", close)
    return captured


@pytest.fixture
def no_connection_during_telegram(sql_trace, monkeypatch):
    real_bot_call, real_request = RecordingBot.__call__, FakeSession.make_request

    async def bot_call(bot, method, *args, **kwargs):
        assert not sql_trace.opened, "DB connection held across a Telegram await"
        return await real_bot_call(bot, method, *args, **kwargs)

    async def request(session, bot, method, *args, **kwargs):
        assert not sql_trace.opened, "DB connection held across a Telegram await"
        return await real_request(session, bot, method, *args, **kwargs)

    monkeypatch.setattr(RecordingBot, "__call__", bot_call)
    monkeypatch.setattr(FakeSession, "make_request", request)


def _metric(capsys, handler):
    lines = capsys.readouterr().out.splitlines()
    line = next(line for line in lines if line.startswith(f"HANDLER_METRICS handler={handler} "))
    return dict(re.findall(r"(\w+)=([^ ]+)", line))


async def test_grade_queries_drop_from_39_to_20(bot_dp, seeded, sql_trace, no_connection_during_telegram, capsys):
    main, bot = bot_dp
    await send_callback(main.dp, bot, SUP, f"nzr_grade:{EMP}:alo:20261026", SUP)
    metric = _metric(capsys, "grade_pick")
    assert metric["outcome"] == "ok"
    expected, baseline = (24, 43) if db._DATABASE_URL else (20, 39)
    assert int(metric["db_queries"]) == expected < baseline  # PG also counts 4 adapter lastval() calls.
    assert int(metric["pool_acquires"]) == 14 < 29
    assert sum("AS kind, session_date" in sql for sql, active in sql_trace if active) == 2
    assert not any("employee_contacts" in sql for sql, active in sql_trace if active)
    fsm = [sql for sql, _ in sql_trace if "FROM fsm_storage" in sql]
    assert len(fsm) == 1 and "SELECT state" in fsm[0]  # No paired get_data read exists here.
    notice = next(m.text for m in bot.sent if getattr(m, "chat_id", None) == EMP)
    assert notice == ("📅 Sana: 26.10.2026\n⭐ Baho: 3 — " + discipline.GRADE_LABELS["alo"]
                      + "\nShu oy bonus: 3\nShu oy minus: 0\nShu oy jami: 3")
    card = next(m for m in bot.sent if m.__class__.__name__ == "EditMessageText")
    assert "⭐ Bugungi ish bahosi: 3" in card.text
    assert all(b.callback_data.endswith("20261026") for row in card.reply_markup.inline_keyboard
               for b in row if b.callback_data.startswith("nzr_grade:"))
    assert not sql_trace.opened


async def test_stars_queries_drop_from_11_to_7(env, seeded, sql_trace, no_connection_during_telegram, capsys):
    await env.tap(EMP, "/mystars")
    metric = _metric(capsys, "mystars_handler")
    assert metric["outcome"] == "ok"
    assert int(metric["db_queries"]) == 7 < 11  # Includes both menu-tracking queries, like production.
    assert int(metric["pool_acquires"]) == 2
    assert sum("AS kind, event_time" in sql for sql, active in sql_trace if active) == 1
    assert sum("FROM fsm_storage" in sql for sql, _ in sql_trace) == 1
    assert "⭐ Joriy yulduzlar:" in env.screens(EMP)[-1]["text"]
    assert not sql_trace.opened


@pytest.mark.parametrize("day,hire", [("2026-03-01", "2026-02-28"), ("2026-03-20", "2026-03-01"),
                                     ("2026-03-31", "2026-03-12"), ("2027-01-01", "2026-12-31"),
                                     ("2026-10-26", "2026-11-01")])
def test_batched_attendance_matches_independent_recent_and_month_reads(seeded, monkeypatch, day, hire):
    from tests.test_month_hours_queries import _seed

    now = datetime.fromisoformat(day + "T12:00:00").replace(tzinfo=company_time.resolve_timezone())
    monkeypatch.setattr(company_time, "now", lambda: now)
    conn = db.get_connection()
    try:
        conn.execute("UPDATE employees SET hire_date = ? WHERE user_id = ?", (hire, EMP))
        conn.commit()
    finally:
        conn.close()
    first = now.date().replace(day=1) - timedelta(days=1)
    _seed(EMP, first, now.date() + timedelta(days=1))  # off, missing, overnight, incomplete, invalid.
    attendance.mark_force_majeure(EMP, day, "Sintetik sabab")
    profile = employees.get_profile(EMP, include_contacts=False)
    expected_days = attendance.get_recent_days_summary(EMP)
    expected_hours = attendance.get_month_to_date_hours(EMP, profile=profile)
    conn = db.get_connection()
    try:
        days, hours = attendance.get_dashboard_attendance(EMP, profile, conn)
    finally:
        conn.close()
    assert days == expected_days
    assert hours == expected_hours
    dashboard = employee_dashboard.build_dashboard(EMP)
    assert dashboard["recent_days"] == expected_days
    assert dashboard["hours"] == expected_hours


@pytest.mark.parametrize("history_days,closed,required", [(0, False, True), (12, False, True),
                                                        (12, True, True), (5, False, False)])
def test_day_snapshot_matches_legacy_and_query_count_is_constant(
    seeded, sql_trace, history_days, closed, required,
):
    branch = RECRUITING_BRANCH_NAMES[0]
    today = company_time.today()
    for i in range(1, history_days + 1):
        day = (today - timedelta(days=i)).isoformat()
        session = discipline_repo.open_branch_session(SUP, branch, day)
        discipline_repo.close_branch_session(session["id"], 1, 1)
    if closed:
        discipline.close_day(SUP, today.isoformat(), 1)
    if not required:
        conn = db.get_connection()
        try:
            conn.execute("UPDATE employees SET status = 'offboarded' WHERE user_id = ?", (EMP,))
            conn.commit()
        finally:
            conn.close()
    expected = nazoratchi_day.active_day(SUP, seeded)
    sql_trace.clear()
    snapshot = nazoratchi_day.read_day_context(SUP, seeded)
    actual = nazoratchi_day.active_day(SUP, seeded, snapshot=snapshot)
    assert actual == expected
    assert len(sql_trace) == 2  # work-day rule + one UNION; independent of days/branches.
    assert not sql_trace.opened


@pytest.mark.parametrize("table", ["daily_evaluations", "daily_evaluation_history", "salaries",
                                   "bonus_bank_ledger", "nazoratchi_branch_sessions"])
async def test_grade_failure_rolls_back_every_write_and_sends_no_employee_notice(
    bot_dp, seeded, monkeypatch, table,
):
    main, bot = bot_dp
    connection_type = _connection_type()
    real = connection_type.execute

    def fail(conn, sql, *args, **kwargs):
        if re.match(r"INSERT(?: OR IGNORE)? INTO " + table + r"\b", sql):
            raise RuntimeError("synthetic write failure")
        return real(conn, sql, *args, **kwargs)

    monkeypatch.setattr(connection_type, "execute", fail)
    await send_callback(main.dp, bot, SUP, f"nzr_grade:{EMP}:alo:20261026", SUP)
    conn = db.get_connection()
    try:
        for name in ("daily_evaluations", "daily_evaluation_history", "salaries", "bonus_bank_ledger",
                     "nazoratchi_branch_sessions"):
            assert conn.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"] == 0
    finally:
        conn.close()
    assert not any(getattr(m, "chat_id", None) == EMP for m in bot.sent)
