"""Strict day close: cutover, explanation, award, and automatic deduction."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import db
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from repositories import discipline as repo
from roles import set_role
from services import discipline, nazoratchi_day as day

SUP, EMP = 1, 889001
BRANCH = RECRUITING_BRANCH_NAMES[0]


def _rows(table):
    conn = db.get_connection()
    try:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]
    finally:
        conn.close()


@pytest.fixture
def prepared(temp_db):
    set_role(SUP, "nazoratchi", set_by=FOUNDER_ID)
    set_role(EMP, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(EMP, {
        "familiya": "Sinov", "ism": "Xodim", "branch": BRANCH,
        "role_key": "kassir", "contacts": [],
    })
    employees.approve_profile(EMP, approved_by=FOUNDER_ID)
    return "2026-11-02"


def test_strict_close_requires_explanation_and_pays_zero_if_ungraded(prepared):
    work_date = prepared
    repo.open_branch_session(SUP, BRANCH, work_date)
    blocked = day.close_session(SUP, BRANCH, work_date)
    assert not blocked.closed and blocked.blockers
    with pytest.raises(ValueError):
        day.close_session(SUP, BRANCH, work_date, note="abc")
    closed = day.close_session(SUP, BRANCH, work_date, note="Xodimga ulgurmadim")
    assert closed.closed
    notes = _rows("day_close_notes")
    assert len(notes) == 1 and notes[0]["ungraded_count"] == 1
    assert not [a for a in _rows("supervisor_audit") if a["event_type"] == "day_full_bonus"]


def test_strict_full_close_awards_once_when_all_graded(prepared):
    work_date = prepared
    repo.open_branch_session(SUP, BRANCH, work_date)
    discipline.record_daily_grade(EMP, SUP, work_date, "alo")
    result = day.close_session(SUP, BRANCH, work_date)
    assert result.closed
    assert not day.close_session(SUP, BRANCH, work_date).closed
    awards = [a for a in _rows("supervisor_audit") if a["event_type"] == "day_full_bonus"]
    assert len(awards) == 1
    assert awards[0]["penalty_amount"] == -5
    assert awards[0]["audit_date"] == work_date
    assert discipline.get_salary(SUP)["bonus_bank"] == 5


def test_auto_close_deducts_once_and_no_session_never_penalized(prepared):
    repo.auto_close_start("2026-11-02")
    repo.open_branch_session(SUP, BRANCH, prepared)
    day.auto_close_expired(datetime(2026, 11, 3, 6, 1, tzinfo=ZoneInfo("Asia/Tashkent")))
    day.auto_close_expired(datetime(2026, 11, 3, 6, 2, tzinfo=ZoneInfo("Asia/Tashkent")))
    audits = [a for a in _rows("supervisor_audit") if a["event_type"] == "auto_close_minus"]
    assert len(audits) == 1 and audits[0]["audit_date"] == prepared
    assert audits[0]["penalty_amount"] == 5
    assert not [a for a in audits if a["supervisor_id"] != SUP]


def test_previous_month_remains_unpenalized(prepared):
    repo.auto_close_start("2026-10-30")
    repo.open_branch_session(SUP, BRANCH, "2026-10-30")
    day.auto_close_expired(datetime(2026, 11, 3, 6, 1, tzinfo=ZoneInfo("Asia/Tashkent")))
    assert not [a for a in _rows("supervisor_audit") if a["event_type"] == "auto_close_minus"]


def test_monthly_payroll_separates_full_bonus_from_auto_minus(temp_db):
    from services import payroll_view
    from repositories import discipline as discipline_repo
    from tests.test_payroll_view import _agreement, _evaluation, EMP as PAY_EMP
    _agreement()
    _evaluation("2026-09-02", 3)
    assert discipline_repo.record_supervisor_audit_with_penalty(
        PAY_EMP, "2026-09-05", "day_full_bonus", -5, "Kun to'liq yopildi (+5)"
    )
    assert discipline_repo.record_supervisor_audit_with_penalty(
        PAY_EMP, "2026-09-06", "auto_close_minus", 5, "Kun 06:00 gacha yopilmadi (-5)"
    )
    view = payroll_view.month_view(PAY_EMP, "2026-09")
    assert view["work_bonus"] == 8
    assert view["minus"] == 5
    assert view["minus_applied"] == 5
    assert not discipline_repo.record_supervisor_audit_with_penalty(
        PAY_EMP, "2026-09-06", "auto_close_minus", 5, "Kun 06:00 gacha yopilmadi (-5)"
    )


def test_no_negative_monthly_bonus_from_auto_minus(temp_db):
    from services import payroll_view
    from repositories import discipline as discipline_repo
    from tests.test_payroll_view import _agreement, EMP as PAY_EMP
    _agreement()
    discipline_repo.record_supervisor_audit_with_penalty(
        PAY_EMP, "2026-09-06", "auto_close_minus", 5, "Kun 06:00 gacha yopilmadi (-5)"
    )
    view = payroll_view.month_view(PAY_EMP, "2026-09")
    assert view["work_bonus"] == 0
    assert view["minus"] == 5
    assert view["minus_applied"] == 0


@pytest.mark.anyio
async def test_close_button_requests_note_then_saves_and_closes(bot_dp, prepared, monkeypatch):
    import company_time
    from tests.bot_harness import send, send_callback
    fixed = datetime(2026, 11, 2, 12, 0, tzinfo=ZoneInfo("Asia/Tashkent"))
    monkeypatch.setattr(company_time, "now", lambda: fixed)
    main, bot = bot_dp
    sent = await send_callback(main.dp, bot, SUP, "bos:close:0:20261102", SUP)
    assert any("kamida 5 belgili izoh" in (getattr(m, "text", None) or "") for m in sent)
    assert not repo.get_day_close_note(SUP, prepared, BRANCH)
    sent = await send(main.dp, bot, SUP, "Vaqt yetmadi, izoh")
    assert any("nazorati yopildi" in (getattr(m, "text", None) or "") for m in sent)
    assert repo.get_day_close_note(SUP, prepared, BRANCH)["note"] == "Vaqt yetmadi, izoh"
