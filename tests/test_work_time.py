"""Aniq ish vaqti (Muhammadiy qoidasi): vaqt bonusi faqat erta kelish uchun, ishlangan vaqt har kuni grafik
oynasiga kesiladi, ma'lumot yetishmasa taxmin yo'q, tuzatish tarixda qoladi, bonus faqat o'z manbasiga tegadi."""

import pytest

from db import get_connection
from services import work_time as wt

EMP = 990001
DAY = {"status": "work", "planned_start": "08:00", "planned_end": "18:00"}
NIGHT = {"status": "work", "planned_start": "22:00", "planned_end": "06:00"}


def _sql(sql, params=()):
    conn = get_connection()
    try:
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()] if sql.lstrip().upper().startswith("SELECT") else None
        conn.commit()
        return rows
    finally:
        conn.close()


def _shift(day, start="08:00", end="18:00", status="work"):
    _sql("INSERT INTO employee_scheduled_shifts (employee_id, shift_date, planned_start, planned_end, status, source, "
         "created_at) VALUES (?, ?, ?, ?, ?, 'test', 'x')", (EMP, day, start, end, status))


@pytest.mark.parametrize("arrival,bonus", [("07:59", True), ("08:00", False), ("08:01", False), ("06:30", True)])
def test_time_bonus_only_strictly_before_start(arrival, bonus):
    assert wt.compute_day("2026-11-03", DAY, arrival, "18:00").time_bonus is bonus


@pytest.mark.parametrize("arrival,departure,minutes", [
    ("07:59", "18:00", 600),   # erta kelgan daqiqa hisobga kirmaydi
    ("07:59", "18:20", 600),   # kech qolgan daqiqa ham kirmaydi (qo'shimcha ish — faqat yulduz)
    ("07:59", "17:50", 590),   # erta ketgan 10 daqiqa ayriladi
    ("08:15", "18:00", 585),   # kechikkan 15 daqiqa ayriladi
])
def test_worked_minutes_are_clamped_to_schedule_each_day(arrival, departure, minutes):
    result = wt.compute_day("2026-11-03", DAY, arrival, departure)
    assert result.status == wt.STATUS_OK and result.minutes == minutes and result.planned_minutes == 600


def test_early_arrival_keeps_bonus_even_if_left_early():
    result = wt.compute_day("2026-11-03", DAY, "07:58", "16:00")
    assert result.time_bonus and result.minutes == 480


def test_night_shift_crosses_midnight():
    result = wt.compute_day("2026-11-03", NIGHT, "21:55", "06:10")
    assert result.status == wt.STATUS_OK and result.time_bonus and result.minutes == 480
    late = wt.compute_day("2026-11-03", NIGHT, "22:30", "05:30")
    assert not late.time_bonus and late.minutes == 420


def test_missing_data_is_never_guessed():
    assert wt.compute_day("2026-11-03", None, "07:50", "18:00").status == wt.STATUS_NO_SCHEDULE
    assert wt.compute_day("2026-11-03", {"status": "off"}, "07:50", "18:00").status == wt.STATUS_DAY_OFF
    no_dep = wt.compute_day("2026-11-03", DAY, "07:50", None)
    assert no_dep.status == wt.STATUS_NO_DEPARTURE and no_dep.minutes == 0 and no_dep.time_bonus  # bonus — faqat kelish
    assert wt.compute_day("2026-11-03", DAY, None, "18:00").status == wt.STATUS_NO_ARRIVAL


def test_parse_rejects_bad_time():
    assert wt.parse_hhmm("7:59") == "07:59" and wt.parse_hhmm("") is None
    with pytest.raises(wt.WorkTimeError):
        wt.parse_hhmm("25:00")


def test_save_correct_keeps_history_and_syncs_only_own_bonus(temp_db):
    _shift("2026-11-03")
    first = wt.save_entry(EMP, "2026-11-03", "07:59", None, entered_by=1)
    assert first.time_bonus and first.status == wt.STATUS_NO_DEPARTURE
    assert _sql("SELECT source FROM time_bonus_grants WHERE employee_id = ?", (EMP,)) == [{"source": "time_entry"}]

    fixed = wt.save_entry(EMP, "2026-11-03", "08:05", "18:00", entered_by=1)  # tuzatish: aslida kechikkan
    assert not fixed.time_bonus and fixed.minutes == 595
    assert _sql("SELECT * FROM time_bonus_grants WHERE employee_id = ?", (EMP,)) == []
    entry = wt.get_entry(EMP, "2026-11-03")
    assert (entry["arrival"], entry["departure"]) == ("08:05", "18:00")
    history = _sql("SELECT old_arrival, new_arrival FROM work_time_entry_revisions WHERE employee_id = ? ORDER BY id", (EMP,))
    assert history == [{"old_arrival": None, "new_arrival": "07:59"}, {"old_arrival": "07:59", "new_arrival": "08:05"}]

    wt.save_entry(EMP, "2026-11-03", "08:05", "18:00", entered_by=1)  # o'zgarishsiz — yangi tarix qatori yo'q
    assert len(_sql("SELECT id FROM work_time_entry_revisions WHERE employee_id = ?", (EMP,))) == 2


def test_other_source_bonus_is_never_removed(temp_db):
    _shift("2026-11-04")
    _sql("INSERT INTO time_bonus_grants (employee_id, grant_date, source, confirmed_by, confirmed_at) "
         "VALUES (?, '2026-11-04', 'manual', 1, 'x')", (EMP,))
    wt.save_entry(EMP, "2026-11-04", "08:30", "18:00", entered_by=1)
    assert _sql("SELECT source FROM time_bonus_grants WHERE employee_id = ?", (EMP,)) == [{"source": "manual"}]


def test_guard_failure_writes_nothing(temp_db):
    def closed(conn):
        raise wt.WorkTimeError("Bu ish kuni yopilgan.")

    with pytest.raises(wt.WorkTimeError):
        wt.save_entry(EMP, "2026-11-03", "07:50", "18:00", entered_by=1, guard=closed)
    assert wt.get_entry(EMP, "2026-11-03") is None
    with pytest.raises(wt.WorkTimeError):
        wt.save_entry(EMP, "2026-10-30", "07:50", "18:00", entered_by=1)  # 2026-11 dan oldin — yo'q


def test_schedule_added_later_is_counted_and_bonus_resynced(temp_db):
    wt.save_entry(EMP, "2026-11-05", "07:50", "18:00", entered_by=1)
    summary = wt.month_summary(EMP, "2026-11-01", "2026-11-30")
    assert summary["days"] == 0 and summary["no_schedule"] == ["2026-11-05"]
    _shift("2026-11-05")
    assert wt.resync_day(EMP, "2026-11-05", actor=1).time_bonus
    summary = wt.month_summary(EMP, "2026-11-01", "2026-11-30")
    assert summary["days"] == 1 and summary["minutes"] == 600 and summary["bonus_days"] == ["2026-11-05"]


def test_payroll_uses_clamped_daily_minutes_from_november(temp_db, monkeypatch):
    """Bir kungi ortiqcha boshqa kungi kamni YOPMAYDI (eski xom hisobdan farqli)."""
    from datetime import date

    import company_time
    from config import FOUNDER_ID
    from services import payroll_view as pv
    from services import salary_agreement as sa

    monkeypatch.setattr(company_time, "today", lambda: date(2026, 12, 2))
    sa.save_agreement(EMP, 2_800_000, 28, 600, "2026-01-01", FOUNDER_ID, "wt1", tariff=1)
    for day, arrival, departure in (("2026-11-03", "07:00", "19:00"), ("2026-11-04", "08:00", "17:00")):
        _shift(day)
        wt.save_entry(EMP, day, arrival, departure, entered_by=1)
    view = pv.month_view(EMP, "2026-11")
    assert view["worked_minutes"] == 600 + 540  # 3-kun 600 (ortig'i yo'q), 4-kun 540 (1 soat kam)
    assert view["time_bonus_days"] == 1  # faqat 07:00 da kelgan kun
