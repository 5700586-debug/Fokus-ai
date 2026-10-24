"""Oylik ishlangan/reja soat: natija ESKI (har kun uchun DB'ga qaytadigan) algoritm bilan bir xil, SQL so'rovlari esa
kunlar soniga bog'liq emas. Eski algoritm shu faylda aynan nusxa sifatida saqlangan (mos yozuv)."""

from datetime import date, datetime, timedelta, timezone

import pytest

import company_time
import employees
from config import FOUNDER_ID
from repositories import attendance as attendance_repo
from roles import set_role
from services import attendance as svc
from services import employee_dashboard, latency_probe

TZ = company_time.resolve_timezone()
_COUNTER = 860000


def _employee(hire_date: str | None = None) -> int:
    global _COUNTER
    _COUNTER += 1
    set_role(_COUNTER, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        _COUNTER,
        {"familiya": "T", "ism": "X", "branch": "Filial-1", "role_key": "kassir", "hire_date": hire_date, "contacts": []},
    )
    employees.approve_profile(_COUNTER, approved_by=FOUNDER_ID)
    return _COUNTER


def _at(day: date, hhmm: str, plus_days: int = 0) -> str:
    hour, minute = (int(part) for part in hhmm.split(":"))
    target = day + timedelta(days=plus_days)
    return datetime(target.year, target.month, target.day, hour, minute, tzinfo=TZ).isoformat()


def _seed(user: int, first: date, last: date) -> None:
    """Har xil kun turlari: dam, kunduzgi, tun smenasi, smenasiz, grafik yo'q, yaroqsiz, to'liq emas, ertangi smena bilan aralash."""
    day = first
    while day <= last:
        kind = day.day % 8
        iso = day.isoformat()
        if kind == 0:
            svc.set_scheduled_day_off(user, iso, "test")
        elif kind == 1:  # kunduzgi, to'liq
            svc.set_scheduled_work_shift(user, iso, "09:00", "18:00", "test")
            attendance_repo.record_event(user, svc.EVENT_CHECK_IN, _at(day, "09:05"), "test")
            attendance_repo.record_event(user, svc.EVENT_CHECK_OUT, _at(day, "18:00"), "test")
        elif kind == 2:  # tun smenasi, chiqish ertasi kuni
            svc.set_scheduled_work_shift(user, iso, "20:00", "08:00", "test")
            attendance_repo.record_event(user, svc.EVENT_CHECK_IN, _at(day, "20:00"), "test")
            attendance_repo.record_event(user, svc.EVENT_CHECK_OUT, _at(day, "07:30", 1), "test")
        elif kind == 3:  # smena bor, voqea yo'q
            svc.set_scheduled_work_shift(user, iso, "09:00", "18:00", "test")
        elif kind == 4:  # grafik yo'q (noma'lum), lekin voqealar bor
            attendance_repo.record_event(user, svc.EVENT_CHECK_IN, _at(day, "10:00"), "test")
            attendance_repo.record_event(user, svc.EVENT_CHECK_OUT, _at(day, "15:00"), "test")
        elif kind == 5:  # tun smenasi, ertasi kuni 06:00 smena: oynadan keyingi chiqish hisobga olinmaydi
            svc.set_scheduled_work_shift(user, iso, "22:00", "05:00", "test")
            attendance_repo.record_event(user, svc.EVENT_CHECK_IN, _at(day, "22:00"), "test")
            attendance_repo.record_event(user, svc.EVENT_CHECK_OUT, _at(day, "05:00", 1), "test")
            attendance_repo.record_event(user, svc.EVENT_CHECK_OUT, _at(day, "08:00", 1), "test")
            svc.set_scheduled_work_shift(user, (day + timedelta(days=1)).isoformat(), "06:00", "14:00", "test")
        elif kind == 6:  # yaroqsiz: 24 soatdan oshiq
            svc.set_scheduled_work_shift(user, iso, "09:00", "18:00", "test")
            attendance_repo.record_event(user, svc.EVENT_CHECK_IN, _at(day, "09:00"), "test")
            attendance_repo.record_event(user, svc.EVENT_CHECK_OUT, _at(day, "12:00", 1), "test")
        else:  # to'liq emas: faqat kelish
            svc.set_scheduled_work_shift(user, iso, "09:00", "18:00", "test")
            attendance_repo.record_event(user, svc.EVENT_CHECK_IN, _at(day, "09:00"), "test")
        day += timedelta(days=1)


# ---- MOS YOZUV: eski algoritm (har kun uchun alohida DB so'rovi) -- aynan nusxa --


def _legacy_worked(employee_id: int, shift_date: str):
    shift = attendance_repo.get_shift_for_date(employee_id, shift_date)
    if not svc._is_overnight_shift(shift):
        events = attendance_repo.list_events_for_date(employee_id, shift_date)
        return svc._pair_check_in_check_out(events, shift_date)
    shift_day = date.fromisoformat(shift_date)
    next_day = shift_day + timedelta(days=1)
    next_shift = attendance_repo.get_shift_for_date(employee_id, next_day.isoformat())
    if next_shift is not None and next_shift.get("status") == svc.SHIFT_STATUS_WORK:
        next_start = svc._parse_hhmm(next_shift.get("planned_start") or "")
        if next_start is not None:
            window_end = datetime(next_day.year, next_day.month, next_day.day, next_start[0], next_start[1], tzinfo=TZ)
        else:
            window_end = datetime(next_day.year, next_day.month, next_day.day, 23, 59, 59, tzinfo=TZ)
    else:
        window_end = datetime(next_day.year, next_day.month, next_day.day, 23, 59, 59, tzinfo=TZ)
    events = attendance_repo.list_events_for_range(employee_id, shift_date, (next_day + timedelta(days=1)).isoformat())
    relevant = [e for e in events if e["event_time"] <= window_end.isoformat()]
    return svc._pair_check_in_check_out(relevant, shift_date)


def _legacy_month(employee_id: int):
    profile = employees.get_profile(employee_id)
    date_range = svc._month_to_date_range(profile)
    if date_range is None:
        return {"planned_hours": None, "actual_hours": 0.0, "worked_days_count": 0, "missing_days_count": 0,
                "range_start": None, "range_end": None}
    range_start, range_end = date_range
    profile2 = employees.get_profile(employee_id)  # eski kod profilni qayta o'qigan
    shifts = attendance_repo.get_schedule_for_range(employee_id, range_start.isoformat(), (range_end + timedelta(days=1)).isoformat())
    by_date = {s["shift_date"]: s for s in shifts}
    total, missing, cur = 0.0, 0, range_start
    while cur <= range_end:
        shift = by_date.get(cur.isoformat())
        if shift is None:
            missing += 1
        elif shift["status"] == svc.SHIFT_STATUS_WORK:
            total += svc._shift_duration_hours(shift["planned_start"], shift["planned_end"])
        cur += timedelta(days=1)
    actual, worked_days, cur = 0.0, 0, range_start
    while cur <= range_end:
        worked = _legacy_worked(employee_id, cur.isoformat())
        if worked is not None:
            actual += worked
            worked_days += 1
        cur += timedelta(days=1)
    assert profile2 is not None
    return {"planned_hours": None if missing else total, "actual_hours": actual, "worked_days_count": worked_days,
            "missing_days_count": missing, "range_start": range_start.isoformat(), "range_end": range_end.isoformat()}


def _counted(fn):
    token = latency_probe._metrics.set(latency_probe._Metrics())
    try:
        metrics = latency_probe._metrics.get()
        result = fn()
        return result, metrics.db_queries, metrics.pool_acquires
    finally:
        latency_probe._metrics.reset(token)


def _today(monkeypatch, iso: str) -> None:
    monkeypatch.setattr(company_time, "today", lambda: date.fromisoformat(iso))


@pytest.mark.parametrize(
    ("today", "hire_date", "seed_from"),
    [
        ("2026-03-01", None, "2026-02-25"),         # 1 kunlik davr
        ("2026-03-15", None, "2026-02-25"),         # 15 kunlik
        ("2026-03-31", None, "2026-02-25"),         # 31 kunlik
        ("2026-03-20", "2026-03-10", "2026-02-25"),  # hire_date oy ichida
        ("2026-04-02", None, "2026-03-25"),         # oy chegarasi: 31-mart tun smenasi 1-aprelda tugaydi
        ("2027-01-02", None, "2026-12-25"),         # yil chegarasi
        ("2026-03-10", "2026-03-20", "2026-03-01"),  # hire_date kelajakda: diapazon yo'q
    ],
)
def test_result_is_identical_to_legacy_and_queries_do_not_scale_with_days(monkeypatch, today, hire_date, seed_from):
    _today(monkeypatch, today)
    user = _employee(hire_date)
    last = date.fromisoformat(today) + timedelta(days=2)
    _seed(user, date.fromisoformat(seed_from), last)

    new, new_queries, new_pools = _counted(lambda: svc.get_month_to_date_hours(user))
    old, old_queries, old_pools = _counted(lambda: _legacy_month(user))

    assert new == old
    print(f"{today}: yangi sql={new_queries} pool={new_pools}; eski sql={old_queries} pool={old_pools}")
    _, profile_queries, profile_pools = _counted(lambda: employees.get_profile(user))
    if new["range_start"] is not None:
        # profil + reja diapazoni (1) + voqealar diapazoni (1) -- kunlar soniga bog'liq emas
        assert new_queries == profile_queries + 2 and new_pools == profile_pools + 2
        assert old_queries >= new_queries


def test_query_count_is_constant_while_legacy_grows_linearly(monkeypatch):
    results = {}
    for today in ("2026-03-01", "2026-03-15", "2026-03-31"):
        _today(monkeypatch, today)
        user = _employee()
        _seed(user, date(2026, 3, 1), date(2026, 4, 2))
        results[today] = (
            _counted(lambda: svc.get_month_to_date_hours(user))[1],
            _counted(lambda: _legacy_month(user))[1],
        )
    new_counts = [new for new, _ in results.values()]
    old_counts = [old for _, old in results.values()]
    assert len(set(new_counts)) == 1 and new_counts[0] <= 4
    assert old_counts[0] < old_counts[1] < old_counts[2]  # eski: kunlar soniga chiziqli


def test_missing_schedule_is_unknown_not_off_and_profile_can_be_passed_without_rereading(monkeypatch):
    _today(monkeypatch, "2026-03-05")
    user = _employee()
    svc.set_scheduled_work_shift(user, "2026-03-01", "09:00", "18:00", "test")  # qolgan kunlar noma'lum

    profile = employees.get_profile(user)
    result, queries, _ = _counted(lambda: svc.get_month_to_date_hours(user, profile=profile))

    assert result["planned_hours"] is None and result["missing_days_count"] == 4 and queries == 2


def test_dashboard_reads_far_fewer_rows_and_matches_legacy_view_model(monkeypatch):
    _today(monkeypatch, "2026-03-31")
    user = _employee()
    _seed(user, date(2026, 3, 1), date(2026, 4, 2))

    def legacy_dashboard():
        from services import discipline

        profile = employees.get_profile(user)
        return {
            "points": discipline.get_period_point_totals(user),
            "yesterday": svc.get_yesterday_summary(user),
            "hours": _legacy_month(user),
            "recent_days": svc.get_recent_days_summary(user, days=2),
            "branch": profile.get("branch"),
        }

    new, new_queries, new_pools = _counted(lambda: employee_dashboard.build_dashboard(user))
    old, old_queries, old_pools = _counted(legacy_dashboard)

    assert new["hours"] == old["hours"] and new["yesterday"] == old["yesterday"] and new["recent_days"] == old["recent_days"]
    assert new["points"] == old["points"]
    print(f"dashboard 31 kun: yangi sql={new_queries} pool={new_pools}; eski sql={old_queries} pool={old_pools}")
    assert new_queries < old_queries / 4 and new_queries <= 12
