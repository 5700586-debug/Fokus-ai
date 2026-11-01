"""Doimiy grafik va istisno kunlar: maoshga tegadigan xavflar uchun targeted regressiyalar."""
from datetime import datetime, date
from zoneinfo import ZoneInfo
import pytest
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from db import get_connection
import company_time
from roles import set_role
from services import permanent_schedule as ps, schedule_webapp as sw, work_time


def sql(query, params=()):
    conn = get_connection()
    try:
        cur = conn.execute(query, params)
        data = [dict(row) for row in cur.fetchall()] if query.strip().upper().startswith("SELECT") else None
        conn.commit()
        return data
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(company_time, "now",
                        lambda: datetime(2026, 11, 3, 12, 0, tzinfo=ZoneInfo("Asia/Tashkent")))
    monkeypatch.setattr(company_time, "today", lambda: date(2026, 11, 3))


def seed():
    set_role(901, "nazoratchi", set_by=FOUNDER_ID)
    set_role(902, "savdo_boshligi", set_by=FOUNDER_ID)
    sql("INSERT INTO employees(user_id,familiya,ism,branch,status) VALUES(902,'Rahbar','X',?,'approved')",
        (RECRUITING_BRANCH_NAMES[0],))
    sql("INSERT INTO employees(user_id,familiya,ism,branch,status) VALUES(903,'Xodim','X',?,'approved')",
        (RECRUITING_BRANCH_NAMES[0],))


def test_permanent_is_effective_dated_and_previous_day_is_unchanged():
    seed()
    old = ps.set_default(903, "2026-11-04", "08:00", "18:00", 902, 0)
    assert old["changed"]
    conn = get_connection()
    try:
        assert ps.resolved_shift(conn, 903, "2026-11-03") is None
        assert ps.resolved_shift(conn, 903, "2026-11-04")["planned_start"] == "08:00"
    finally:
        conn.close()
    ps.set_default(903, "2026-11-10", "09:00", "19:00", 902, old["version"])
    conn = get_connection()
    try:
        assert ps.resolved_shift(conn, 903, "2026-11-09")["planned_start"] == "08:00"
        assert ps.resolved_shift(conn, 903, "2026-11-10")["planned_start"] == "09:00"
    finally:
        conn.close()


def test_day_override_does_not_change_permanent_or_other_days():
    seed()
    ps.set_default(903, "2026-11-04", "08:00", "18:00", 902, 0)
    cells = sw.week_payload(902)["branches"][0]["employees"]
    row = next(r for r in cells if r["id"] == 903)
    c = next(c for c in row["cells"] if c["date"] == "2026-11-05")
    assert c["version"] < 0 and c["start"] == "08:00"
    sw.save(902, [{"employee_id":903, "date":"2026-11-05", "status":"off", "expected_version":c["version"]}], None)
    conn = get_connection()
    try:
        assert ps.resolved_shift(conn, 903, "2026-11-05")["status"] == "off"
        assert ps.resolved_shift(conn, 903, "2026-11-06")["planned_start"] == "08:00"
    finally:
        conn.close()


def test_resolved_shift_caps_daily_work_and_early_bonus():
    seed()
    ps.set_default(903, "2026-11-04", "08:00", "18:00", 902, 0)
    conn = get_connection()
    try:
        shift = ps.resolved_shift(conn, 903, "2026-11-04")
    finally:
        conn.close()
    assert work_time.compute_day("2026-11-04", shift, "08:30", "18:30").minutes == 570
    assert work_time.compute_day("2026-11-04", shift, "07:59", "18:00").time_bonus is True
    assert work_time.compute_day("2026-11-04", shift, "08:00", "18:00").time_bonus is False


def test_stale_version_cannot_override_changed_default():
    seed()
    a = ps.set_default(903, "2026-11-04", "08:00", "18:00", 902, 0)
    ps.set_default(903, "2026-11-06", "09:00", "19:00", 902, a["version"])
    with pytest.raises(ps.ScheduleConflict):
        ps.set_default(903, "2026-11-08", "07:00", "17:00", 902, a["version"])


def test_only_founder_can_toggle_old_day_edit():
    seed()
    from services.grading_webapp import WebAppError
    with pytest.raises(WebAppError):
        sw.save_edit_settings(901, False)
    sw.save_edit_settings(FOUNDER_ID, False)
    assert sw.edit_settings(FOUNDER_ID)["allow_nazoratchi_past"] is False
    assert sql("SELECT old_enabled,new_enabled FROM employee_schedule_edit_settings_history") == [
        {"old_enabled":1, "new_enabled":0}]
    sw.save_edit_settings(FOUNDER_ID, True)


def test_today_and_past_cannot_be_used_as_permanent_effective_date():
    seed()
    with pytest.raises(ps.ScheduleConflict):
        ps.set_default(903, "2026-11-03", "14:00", "22:00", 902, 0)
    with pytest.raises(ps.ScheduleConflict):
        ps.set_default(903, "2026-11-02", "08:00", "18:00", 902, 0)
