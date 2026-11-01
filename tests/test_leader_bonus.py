"""👔 Filial rahbari kunlik jamoa bonusi: vaqt qismi (2/1/0), ish qismi (o'rtacha baho, bir kasr), asos grafik
(rahbarning kechki o'zgarishi foyda bermaydi), to'liq bo'lmagan ma'lumot — 0 va sabab, kun yopilganda muhrlanadi."""

from datetime import date

import pytest
from aiogram.methods import SendMessage

import company_time
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from db import get_connection
from services import leader_bonus as lb
from services import work_time

pytestmark = pytest.mark.anyio

NAZ, BOSS = 1, 701
B0 = RECRUITING_BRANCH_NAMES[0]
DAY = "2026-11-03"
EARLY = "2026-11-01T10:00:00+00:00"   # asos grafik vaqtidan (2026-11-01 19:00 UTC) oldin
LATE = "2026-11-02T03:00:00+00:00"    # undan keyin


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _sql(sql, params=()):
    conn = get_connection()
    try:
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()] if sql.lstrip().upper().startswith("SELECT") else None
        conn.commit()
        return rows
    finally:
        conn.close()


def _seed(n=3):
    from roles import set_role

    set_role(NAZ, "nazoratchi", set_by=FOUNDER_ID)
    set_role(BOSS, "savdo_boshligi", set_by=FOUNDER_ID)
    _sql("INSERT INTO employees (user_id, familiya, ism, branch, status) VALUES (?, 'Rahbar', 'X', ?, 'approved')",
         (BOSS, B0))
    ids = []
    for i in range(n):
        uid = 710 + i
        _sql("INSERT INTO employees (user_id, familiya, ism, branch, status) VALUES (?, ?, 'X', ?, 'approved')",
             (uid, f"Xodim{i}", B0))
        ids.append(uid)
    return ids


def _plan(emp, status="work", start="08:00", end="18:00", by=NAZ, at=EARLY, day=DAY):
    start, end = (start, end) if status == "work" else (None, None)
    _sql("INSERT INTO employee_schedule_revisions (employee_id, shift_date, new_status, new_planned_start, "
         "new_planned_end, changed_by, changed_at, is_late_change) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
         (emp, day, status, start, end, by, at))
    _sql("DELETE FROM employee_scheduled_shifts WHERE employee_id = ? AND shift_date = ?", (emp, day))
    _sql("INSERT INTO employee_scheduled_shifts (employee_id, shift_date, planned_start, planned_end, status, source, "
         "created_at) VALUES (?, ?, ?, ?, ?, 'test', 'x')", (emp, day, start, end, status))


def _arrive(emp, arrival, day=DAY):
    _sql("INSERT INTO work_time_entries (employee_id, work_date, arrival, departure, entered_by, created_at, updated_at) "
         "VALUES (?, ?, ?, '18:00', ?, 'x', 'x')", (emp, day, arrival, NAZ))


def _grade(emp, points, day=DAY):
    key = {0: "bajarilmagan", 1: "chala", 2: "norma", 3: "alo"}[points]
    _sql("INSERT INTO daily_evaluations (employee_id, supervisor_id, eval_date, grade_key, grade_points, created_at) "
         "VALUES (?, ?, ?, ?, ?, 'x')", (emp, NAZ, day, key, points))


def _close(day=DAY):
    _sql("INSERT INTO nazoratchi_branch_sessions (supervisor_id, branch, session_date, status, opened_at, closed_at) "
         "VALUES (?, ?, ?, 'closed', 'x', 'x')", (NAZ, B0, day))


def test_full_team_on_time_and_average_grade():
    ids = _seed(3)
    for emp, points in zip(ids, (3, 2, 2)):
        _plan(emp)
        _arrive(emp, "07:55")
        _grade(emp, points)
    result = lb.compute(B0, DAY)
    assert result["leaders"] == [BOSS] and result["planned"] == 3 and result["on_time"] == 3
    assert result["time_points"] == 2 and result["work_points"] == 2.3 and not result["incomplete"]
    assert "⭐ 2,3" in lb.message_text(result) and "Jami bugun: ⭐ 4,3 / 5" in lb.message_text(result)


def test_one_late_of_five_is_partial_and_two_late_is_zero():
    ids = _seed(5)
    for i, emp in enumerate(ids):
        _plan(emp)
        _arrive(emp, "08:05" if i == 0 else "07:50")
        _grade(emp, 3)
    first = lb.compute(B0, DAY)
    assert first["on_time"] == 4 and first["time_points"] == 1 and "Xodim0 X 08:05" in first["late"]
    _sql("UPDATE work_time_entries SET arrival = '08:01' WHERE employee_id = ?", (ids[1],))
    assert lb.compute(B0, DAY)["time_points"] == 0


def test_leader_cannot_improve_result_by_late_schedule_changes():
    ids = _seed(2)
    for emp in ids:
        _plan(emp)
        _grade(emp, 2)
    _arrive(ids[0], "07:50")
    _arrive(ids[1], "08:10")
    _plan(ids[1], start="08:30", by=BOSS, at=LATE)  # rahbar kech surdi: xodimga 08:10 "erta" bo'lib qoladi
    assert lb.compute(B0, DAY)["on_time"] == 1  # rahbar hisobida asos grafik 08:00 — kechikkan
    _plan(ids[1], status="off", by=BOSS, at=LATE)  # dam qilib hisobdan chiqarish ham ishlamaydi
    assert lb.compute(B0, DAY)["planned"] == 2
    _plan(ids[1], status="off", by=NAZ, at=LATE)  # nazoratchi (sabab bilan) — qabul qilinadi
    result = lb.compute(B0, DAY)
    assert result["planned"] == 1 and result["time_points"] == 2


def test_incomplete_data_gives_zero_with_reason():
    ids = _seed(2)
    for emp in ids:
        _plan(emp)
    _arrive(ids[0], "07:50")
    _grade(ids[0], 3)
    result = lb.compute(B0, DAY)
    assert result["time_points"] == 0 and result["work_points"] == 0.0
    assert any("kelish kiritilmagan" in r for r in result["incomplete"])
    assert any("baholanmagan" in r for r in result["incomplete"])
    assert "Ma'lumot to'liq emas" in lb.message_text(result)


def test_worked_without_schedule_is_not_a_success():
    ids = _seed(1)
    _arrive(ids[0], "07:50")
    _grade(ids[0], 3)
    result = lb.compute(B0, DAY)
    assert result["time_points"] == 0 and any("grafik yo'q" in r for r in result["incomplete"])


async def test_snapshot_is_frozen_and_sent_once(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(company_time, "today", lambda: date(2026, 11, 3))
    ids = _seed(1)
    _plan(ids[0])
    _arrive(ids[0], "07:50")
    _grade(ids[0], 3)
    assert lb.pending_closed_sessions("2026-11-01") == []
    _close()
    assert lb.pending_closed_sessions("2026-11-01") == [(B0, DAY)]
    bot.sent.clear()
    await lb.tick(bot)
    assert any(isinstance(m, SendMessage) and m.chat_id == BOSS and "Jamoa natijasi" in m.text for m in bot.sent)
    _sql("UPDATE daily_evaluations SET grade_points = 0 WHERE employee_id = ?", (ids[0],))  # keyingi tuzatish
    bot.sent.clear()
    await lb.tick(bot)
    assert lb.snapshot(B0, DAY) == [] and not any(m.chat_id == BOSS for m in bot.sent if isinstance(m, SendMessage))
    row = _sql("SELECT time_points, work_points FROM leader_daily_results WHERE leader_id = ?", (BOSS,))[0]
    assert row["time_points"] == 2 and float(row["work_points"]) == 3.0


def test_before_start_date_nothing_is_recorded():
    _seed(1)
    assert lb.snapshot(B0, "2026-10-30") == []


def test_payroll_uses_team_result_for_leader(monkeypatch):
    from services import payroll_view as pv
    from services import salary_agreement as sa

    ids = _seed(1)
    monkeypatch.setattr(company_time, "today", lambda: date(2026, 12, 2))
    sa.save_agreement(BOSS, 5_000_000, 26, 600, "2026-01-01", FOUNDER_ID, "lb1", tariff=1)
    for day, arrival, points in (("2026-11-03", "07:50", 3), ("2026-11-04", "08:20", 2)):
        _plan(ids[0], day=day)
        _arrive(ids[0], arrival, day=day)
        _grade(ids[0], points, day=day)
        _close(day=day)
        lb.snapshot(B0, day)
    _grade(BOSS, 3)  # rahbarning o'z bahosi — jamoa bonusi o'rniga hisoblanmaydi
    view = pv.month_view(BOSS, "2026-11")
    assert view["leader"] == {"days": 2, "time_points": 2, "work_points": 5.0}
    assert view["time_bonus"] == 2 and view["work_bonus"] == 7
