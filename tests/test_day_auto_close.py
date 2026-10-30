"""Approved 06:00 day-close policy; SQLite/ephemeral PG, no production/Telegram calls."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from aiogram.methods import SendMessage

import company_time
import db
import discipline_bot
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from repositories import discipline as repo
from roles import set_role
from services import discipline, nazoratchi_day as day, rules
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio
TZ = ZoneInfo("Asia/Tashkent")
SUP, EMP = 1, 880001
BRANCH = RECRUITING_BRANCH_NAMES[0]


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _now(text):
    return datetime.fromisoformat(text).replace(tzinfo=TZ)


@pytest.fixture
def seeded(monkeypatch):
    fixed = _now("2026-10-28T12:00:00")
    monkeypatch.setattr(company_time, "now", lambda: fixed)
    set_role(SUP, "nazoratchi", set_by=FOUNDER_ID)
    set_role(EMP, "kassir", set_by=FOUNDER_ID)
    set_role(FOUNDER_ID, "founder", set_by=FOUNDER_ID)
    employees.submit_profile(EMP, {"familiya": "Sintetik", "ism": "Ali", "branch": BRANCH,
                                  "role_key": "kassir", "contacts": []})
    employees.approve_profile(EMP, approved_by=FOUNDER_ID)
    return fixed


def _rows(table):
    conn = db.get_connection()
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()]
    finally:
        conn.close()


def _unchanged_tables():
    return {t: _rows(t) for t in ("daily_evaluations", "daily_evaluation_history", "salaries", "bonus_bank_ledger", "supervisor_audit")}


@pytest.mark.parametrize("stamp,expected", [
    ("2026-10-28T00:00:00", "2026-10-27"), ("2026-10-28T05:59:59", "2026-10-27"),
    ("2026-10-28T06:00:00", "2026-10-28"), ("2026-11-01T01:00:00", "2026-10-31"),
    ("2027-01-01T05:59:59", "2026-12-31"), ("2027-01-01T06:00:00", "2027-01-01"),
])
def test_work_day_boundary(stamp, expected):
    assert day.current_work_date(_now(stamp)) == expected
    assert day.current_work_date(_now(stamp).astimezone(timezone.utc)) == expected


def test_manual_close_keeps_missing_grade_distinct_from_zero(seeded):
    repo.open_branch_session(SUP, BRANCH, "2026-10-28")
    before = _unchanged_tables()
    result = day.close_session(SUP, BRANCH, "2026-10-28")  # no schedule or grade
    assert result.closed and not result.blockers and result.evaluated == 0
    assert _unchanged_tables() == before
    assert day.branch_statuses(BRANCH, "2026-10-28", SUP, closed=True)[0].status == day.STATUS_NOT_EVALUATED
    assert "baholanmadi" in day.branch_statuses(BRANCH, "2026-10-28", SUP, closed=True)[0].line()
    assert not day.close_session(SUP, BRANCH, "2026-10-28").closed
    # A genuine zero evaluation is still evaluated, never converted to missing.
    result = discipline.record_daily_grade(EMP, SUP, "2026-10-27", "bajarilmagan")
    assert result.grade_points == 0
    assert day.employee_status(employees.get_profile(EMP), "2026-10-27", closed=True).status == day.STATUS_EVALUATED


async def test_kunniyop_does_not_require_all_employees_graded(bot_dp, seeded):
    main, bot = bot_dp
    before = _unchanged_tables()
    sent = await send(main.dp, bot, SUP, "/kunniyop")
    button = sent[0].reply_markup.inline_keyboard[0][0]
    sent = await send_callback(main.dp, bot, SUP, button.callback_data, SUP)
    text = "\n".join(m.text for m in sent if getattr(m, "text", None))
    assert "nazorati yopildi" in text and "baholanmadi" in text
    assert "Yopib bo'lmaydi" not in text
    assert _unchanged_tables() == before
    assert not [m for m in sent if isinstance(m, SendMessage) and m.chat_id in (EMP, FOUNDER_ID)]


def test_cutover_is_persistent_and_not_editable_from_settings(seeded):
    assert day.ensure_auto_close_policy(seeded) == "2026-10-28"
    assert day.ensure_auto_close_policy(seeded + timedelta(days=5)) == "2026-10-28"
    with pytest.raises(ValueError):
        rules.set_rule("bos.auto_close_start_date", "2026-10-01", FOUNDER_ID)
    assert "bos.auto_close_start_date" not in rules.list_rules()


def test_tick_catchup_closes_only_post_cutover_days_and_writes_no_grades_or_penalties(seeded):
    day.ensure_auto_close_policy(seeded)
    for date in ("2026-10-17", "2026-10-28", "2026-10-29", "2026-10-30"):
        repo.open_branch_session(SUP, BRANCH, date)
    before = _unchanged_tables()
    assert day.auto_close_expired(_now("2026-10-29T05:59:59")) == {"days": 0, "sessions": 0}
    assert day.auto_close_expired(_now("2026-10-29T06:00:00")) == {"days": 1, "sessions": 1}
    assert repo.get_branch_session(SUP, BRANCH, "2026-10-17")["status"] == "open"
    assert day.auto_close_expired(_now("2026-10-30T08:00:00")) == {"days": 1, "sessions": 1}
    assert day.auto_close_expired(_now("2026-10-30T08:00:00")) == {"days": 0, "sessions": 0}
    assert repo.get_branch_session(SUP, BRANCH, "2026-10-30")["status"] == "open"
    assert _unchanged_tables() == before
    assert day.active_day(SUP, _now("2026-10-30T08:00:00")).work_date == "2026-10-30"


async def test_silent_tick_absent_supervisor_does_not_create_substitute_or_evaluation(seeded, monkeypatch):
    class Bot:
        async def send_message(self, *args, **kwargs):
            pytest.fail("Auto-close must never send a daily message")
    before = _unchanged_tables()
    await discipline_bot._day_close_tick(Bot())
    assert _unchanged_tables() == before and _rows("nazoratchi_branch_sessions") == []


def test_legacy_preview_is_read_only_and_confirmation_is_exact_and_atomic(seeded):
    day.ensure_auto_close_policy(seeded)
    discipline.record_daily_grade(EMP, SUP, "2026-10-17", "alo", session_branch=BRANCH)
    repo.open_branch_session(SUP, BRANCH, "2026-10-18")
    before = _unchanged_tables()
    sessions = _rows("nazoratchi_branch_sessions")
    rules_before = _rows("rules")
    preview = day.preview_legacy_close(seeded)
    assert len(preview["rows"]) == 2
    assert _rows("rules") == rules_before and _rows("nazoratchi_branch_sessions") == sessions
    assert _rows("daily_closures") == [] and _unchanged_tables() == before
    assert day.auto_close_expired(seeded) == {"days": 0, "sessions": 0}
    result = day.confirm_legacy_close(seeded, preview["version"])
    assert result == {"days": 2, "sessions": 2}
    assert _unchanged_tables() == before
    assert all(r["status"] == "closed" for r in _rows("nazoratchi_branch_sessions"))
    with pytest.raises(ValueError, match="eskirgan"):
        day.confirm_legacy_close(seeded, preview["version"])


def test_changed_preview_cannot_close_unreviewed_day(seeded):
    day.ensure_auto_close_policy(seeded)
    repo.open_branch_session(SUP, BRANCH, "2026-10-17")
    preview = day.preview_legacy_close(seeded)
    repo.open_branch_session(SUP, BRANCH, "2026-10-18")
    with pytest.raises(ValueError, match="eskirgan"):
        day.confirm_legacy_close(seeded, preview["version"])
    assert _rows("daily_closures") == []
    assert all(r["status"] == "open" for r in _rows("nazoratchi_branch_sessions"))


@pytest.mark.parametrize("table,event", [("daily_closures", "INSERT"), ("nazoratchi_branch_sessions", "UPDATE")])
def test_real_sql_failure_rolls_back_all_closes_and_retry_is_safe(seeded, table, event):
    day.ensure_auto_close_policy(seeded)
    for date in ("2026-10-28", "2026-10-29"):
        repo.open_branch_session(SUP, BRANCH, date)
    conn = db.get_connection()
    try:
        if db._DATABASE_URL:
            conn.execute("CREATE OR REPLACE FUNCTION fail_day_close() RETURNS trigger LANGUAGE plpgsql AS "
                         "$$ BEGIN RAISE EXCEPTION 'synthetic close failure'; END $$")
            conn.execute(f"CREATE TRIGGER fail_day_close BEFORE {event} ON {table} FOR EACH ROW EXECUTE FUNCTION fail_day_close()")
        else:
            conn.execute(f"CREATE TRIGGER fail_day_close BEFORE {event} ON {table} BEGIN SELECT RAISE(ABORT, 'synthetic close failure'); END")
        conn.commit()
    finally:
        conn.close()
    try:
        with pytest.raises(Exception):
            day.auto_close_expired(_now("2026-10-30T06:00:00"))
        assert _rows("daily_closures") == []
        assert all(r["status"] == "open" for r in _rows("nazoratchi_branch_sessions"))
    finally:
        conn = db.get_connection()
        try:
            conn.execute(f"DROP TRIGGER fail_day_close ON {table}" if db._DATABASE_URL else "DROP TRIGGER fail_day_close")
            conn.commit()
        finally:
            conn.close()
    assert day.auto_close_expired(_now("2026-10-30T06:00:00"))["days"] == 2


async def test_founder_preview_requires_same_owner_message_and_one_use_confirmation(bot_dp, seeded):
    main, bot = bot_dp
    discipline_bot._LEGACY_CLOSE_PREVIEWS.clear()
    day.ensure_auto_close_policy(seeded)
    repo.open_branch_session(SUP, BRANCH, "2026-10-17")
    before = _unchanged_tables()
    await send(main.dp, bot, SUP, "/eskikunlarniyop")
    assert not discipline_bot._LEGACY_CLOSE_PREVIEWS
    sent = await send(main.dp, bot, FOUNDER_ID, "/eskikunlarniyop")
    assert "17.10.2026" in sent[0].text
    token = sent[0].reply_markup.inline_keyboard[0][0].callback_data
    assert _rows("daily_closures") == []
    # Another user's callback cannot consume the Founder's preview.
    await send_callback(main.dp, bot, SUP, token, SUP)
    assert _rows("daily_closures") == []
    await send_callback(main.dp, bot, FOUNDER_ID, token, FOUNDER_ID, message_id=99)
    assert _rows("daily_closures") == []
    await send_callback(main.dp, bot, FOUNDER_ID, token, FOUNDER_ID, message_id=1)
    assert len(_rows("daily_closures")) == 1
    await send_callback(main.dp, bot, FOUNDER_ID, token, FOUNDER_ID, message_id=1)
    assert len(_rows("daily_closures")) == 1 and _unchanged_tables() == before


async def test_old_day_never_captures_new_grade_and_old_button_is_rejected(bot_dp, seeded):
    main, bot = bot_dp
    repo.open_branch_session(SUP, BRANCH, "2026-10-17")
    old = await send_callback(main.dp, bot, SUP, f"nzr_grade:{EMP}:alo:20261017", SUP)
    assert "eskirgan" in " ".join(m.text for m in old if getattr(m, "text", None))
    assert _rows("daily_evaluations") == []
    await send_callback(main.dp, bot, SUP, f"nzr_grade:{EMP}:alo:20261028", SUP)
    assert [r["eval_date"] for r in _rows("daily_evaluations")] == ["2026-10-28"]


@pytest.mark.parametrize("prefix", ["bos:grade", "nzr_grade"])
async def test_night_shift_and_06_rollover_preserve_separate_daily_grades(bot_dp, seeded, monkeypatch, prefix):
    main, bot = bot_dp
    day.ensure_auto_close_policy(seeded)
    for stamp, expected_day, grade in [
        ("2026-10-28T23:59:00", "20261028", "alo"),
        ("2026-10-29T00:00:00", "20261028", "norma"),
        ("2026-10-29T05:59:59", "20261028", "chala"),
        ("2026-10-29T06:00:00", "20261029", "alo"),
    ]:
        fixed = _now(stamp)
        monkeypatch.setattr(company_time, "now", lambda: fixed)
        if expected_day == "20261029":
            day.auto_close_expired(fixed)
            old = await send_callback(main.dp, bot, SUP, f"{prefix}:{EMP}:alo:20261028", SUP)
            assert "eskirgan" in " ".join(m.text for m in old if getattr(m, "text", None))
        await send_callback(main.dp, bot, SUP, f"{prefix}:{EMP}:{grade}:{expected_day}", SUP)
    grades = {r["eval_date"]: r["grade_key"] for r in _rows("daily_evaluations")}
    assert grades == {"2026-10-28": "chala", "2026-10-29": "alo"}
    assert len(_rows("daily_evaluation_history")) == 4
    assert discipline.get_salary(EMP)["bonus_bank"] == 4  # Existing delta math is unchanged.


def test_legacy_partial_day_with_closed_session_still_needs_confirmation(seeded):
    day.ensure_auto_close_policy(seeded)
    session = repo.open_branch_session(SUP, BRANCH, "2026-10-17")
    repo.close_branch_session(session["id"], 0, 1)
    assert _rows("daily_closures") == []
    assert day.auto_close_expired(seeded) == {"days": 0, "sessions": 0}
    preview = day.preview_legacy_close(seeded)
    assert len(preview["rows"]) == 1
    assert day.confirm_legacy_close(seeded, preview["version"]) == {"days": 1, "sessions": 0}


def test_parallel_close_transactions_are_idempotent(seeded):
    from concurrent.futures import ThreadPoolExecutor
    day.ensure_auto_close_policy(seeded)
    repo.open_branch_session(SUP, BRANCH, "2026-10-28")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: day.auto_close_expired(_now("2026-10-29T06:00:00")), range(2)))
    assert sum(r["days"] for r in results) == sum(r["sessions"] for r in results) == 1
    assert len(_rows("daily_closures")) == 1


async def test_preview_token_does_not_survive_restart(bot_dp, seeded):
    main, bot = bot_dp
    day.ensure_auto_close_policy(seeded)
    repo.open_branch_session(SUP, BRANCH, "2026-10-17")
    sent = await send(main.dp, bot, FOUNDER_ID, "/eskikunlarniyop")
    token = sent[0].reply_markup.inline_keyboard[0][0].callback_data
    discipline_bot._LEGACY_CLOSE_PREVIEWS.clear()
    await send_callback(main.dp, bot, FOUNDER_ID, token, FOUNDER_ID)
    assert _rows("daily_closures") == []


async def test_scheduler_is_06_tashkent_with_immediate_startup_catchup(seeded):
    class Bot:
        pass
    scheduler = discipline_bot.start_scheduler(Bot())
    try:
        job = scheduler.get_job("bos_day_close_audit")
        assert str(job.trigger.timezone) == "Asia/Tashkent"
        fire = job.trigger.get_next_fire_time(None, _now("2026-10-28T05:59:59"))
        assert fire == _now("2026-10-28T06:00:00")
        assert job.next_run_time == seeded
        # Agreement reminder + Founder haftalik/oylik hisobot; kunlik yopish uchun ikkinchi job yo'q.
        assert {j.id for j in scheduler.get_jobs()} == {
            "bos_day_close_audit", "salary_agreement_issue_reminder", "founder_weekly_report", "founder_monthly_report",
        }
    finally:
        scheduler.shutdown(wait=False)
