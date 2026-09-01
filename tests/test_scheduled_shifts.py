"""STRUCTURED WORK SCHEDULE CORE V1: ``employee_scheduled_shifts`` --
kunduzgi/tun smena semantikasi, atomik UPSERT (dublikatsiz, oxirgi
qonuniy qiymat saqlanadi), va shu manbadan hisoblangan oy boshidan
REJA soat (``services/attendance.py::get_month_to_date_planned_hours``).
"""

from datetime import date, timedelta

import company_time
import employees
from config import FOUNDER_ID
from repositories import attendance as attendance_repo
from roles import set_role
from services import attendance as attendance_service

_EMPLOYEE_COUNTER = 850000


def _make_employee(hire_date: str | None = None) -> int:
    global _EMPLOYEE_COUNTER
    _EMPLOYEE_COUNTER += 1
    user_id = _EMPLOYEE_COUNTER

    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {
            "familiya": "Test", "ism": "Xodim", "branch": "Filial-1", "role_key": "kassir",
            "hire_date": hire_date, "work_schedule": "09:00–18:00", "contacts": [],
        },
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)
    return user_id


def _fill_range_with_work_shifts(user_id: int, start: date, end: date, start_text: str, end_text: str) -> None:
    current = start
    while current <= end:
        attendance_service.set_scheduled_work_shift(user_id, current.isoformat(), start_text, end_text, "test")
        current += timedelta(days=1)


# ------------------------------------------------------------- semantics --


def test_daytime_shift_is_accepted_and_recorded():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    accepted = attendance_service.set_scheduled_work_shift(user_id, today, "08:00", "18:00", "test")

    assert accepted is True
    rows = attendance_repo.get_schedule_for_range(user_id, today, (company_time.today() + timedelta(days=1)).isoformat())
    assert len(rows) == 1
    assert rows[0]["status"] == "work"
    assert rows[0]["planned_start"] == "08:00"
    assert rows[0]["planned_end"] == "18:00"


def test_start_equal_end_is_rejected():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    accepted = attendance_service.set_scheduled_work_shift(user_id, today, "08:00", "08:00", "test")

    assert accepted is False
    rows = attendance_repo.get_schedule_for_range(user_id, today, (company_time.today() + timedelta(days=1)).isoformat())
    assert rows == []


def test_explicit_day_off_contributes_zero_and_is_not_missing():
    user_id = _make_employee(hire_date="2020-01-01")
    today = company_time.today()
    month_start = date(today.year, today.month, 1)

    current = month_start
    while current <= today:
        attendance_service.set_scheduled_day_off(user_id, current.isoformat(), "test")
        current += timedelta(days=1)

    result = attendance_service.get_month_to_date_planned_hours(user_id)

    assert result["missing_days_count"] == 0
    assert result["planned_hours"] == 0.0


# ------------------------------------------------------------- upsert --


def test_writing_the_same_employee_and_date_twice_keeps_a_single_row():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    attendance_service.set_scheduled_work_shift(user_id, today, "08:00", "17:00", "test")
    attendance_service.set_scheduled_work_shift(user_id, today, "09:00", "18:00", "test")

    rows = attendance_repo.get_schedule_for_range(user_id, today, (company_time.today() + timedelta(days=1)).isoformat())
    assert len(rows) == 1


def test_upsert_keeps_the_latest_legal_value():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    attendance_service.set_scheduled_work_shift(user_id, today, "08:00", "17:00", "test")
    attendance_service.set_scheduled_work_shift(user_id, today, "10:00", "14:00", "test")

    rows = attendance_repo.get_schedule_for_range(user_id, today, (company_time.today() + timedelta(days=1)).isoformat())
    assert len(rows) == 1
    assert rows[0]["planned_start"] == "10:00"
    assert rows[0]["planned_end"] == "14:00"


def test_day_off_can_overwrite_a_previously_set_work_shift():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    attendance_service.set_scheduled_work_shift(user_id, today, "08:00", "17:00", "test")
    attendance_service.set_scheduled_day_off(user_id, today, "test")

    rows = attendance_repo.get_schedule_for_range(user_id, today, (company_time.today() + timedelta(days=1)).isoformat())
    assert len(rows) == 1
    assert rows[0]["status"] == "off"
    assert rows[0]["planned_start"] is None
    assert rows[0]["planned_end"] is None


# ------------------------------------------------ get_month_to_date_planned_hours --


def test_planned_hours_none_when_a_day_in_range_has_no_schedule():
    """Diapazondagi HAR kun to'ldirilishi kerak -- faqat BUGUNGI kunni
    ataylab bo'sh qoldiramiz (diapazon bir kunlik bo'lsa ham, ko'p
    kunlik bo'lsa ham har doim ANIQ 1 ta UNKNOWN qoladi -- oyning
    1-kunida ishga tushsa ham natija determinatsiyalangan)."""
    user_id = _make_employee(hire_date="2020-01-01")
    today = company_time.today()
    month_start = date(today.year, today.month, 1)

    current = month_start
    while current < today:
        attendance_service.set_scheduled_work_shift(user_id, current.isoformat(), "08:00", "18:00", "test")
        current += timedelta(days=1)
    # ``today``ning o'zi ataylab bo'sh qoldirilgan.

    result = attendance_service.get_month_to_date_planned_hours(user_id)

    assert result["planned_hours"] is None
    assert result["missing_days_count"] == 1


def test_planned_hours_computed_when_full_range_is_covered_with_night_shift():
    user_id = _make_employee(hire_date="2020-01-01")
    today = company_time.today()
    month_start = date(today.year, today.month, 1)
    day_count = (today - month_start).days + 1

    _fill_range_with_work_shifts(user_id, month_start, today, "20:00", "08:00")

    result = attendance_service.get_month_to_date_planned_hours(user_id)

    assert result["missing_days_count"] == 0
    assert result["planned_hours"] == 12.0 * day_count


def test_planned_hours_respects_hire_date_floor():
    today = company_time.today()
    user_id = _make_employee(hire_date=today.isoformat())

    attendance_service.set_scheduled_work_shift(user_id, today.isoformat(), "08:00", "16:00", "test")

    result = attendance_service.get_month_to_date_planned_hours(user_id)

    assert result["range_start"] == today.isoformat()
    assert result["missing_days_count"] == 0
    assert result["planned_hours"] == 8.0


def test_planned_hours_unknown_employee_returns_none():
    assert attendance_service.get_month_to_date_planned_hours(999999999) is None


# ---------------------------------- get_month_to_date_hours now uses structured schedule --


def test_get_month_to_date_hours_ignores_legacy_free_text_work_schedule():
    """``work_schedule`` = "09:00–18:00" erkin matn ustunida bor, lekin
    HECH QANDAY strukturali smena yozilmagan -- yangi manbaga ko'ra bu
    UNKNOWN kunlar, natija ``None`` bo'lishi kerak (eski fallback
    ishlatilmaydi)."""
    user_id = _make_employee(hire_date="2020-01-01")

    result = attendance_service.get_month_to_date_hours(user_id)

    assert result["planned_hours"] is None
    assert result["missing_days_count"] > 0


def test_get_month_to_date_hours_uses_structured_schedule_when_present():
    user_id = _make_employee(hire_date="2020-01-01")
    today = company_time.today()
    month_start = date(today.year, today.month, 1)
    day_count = (today - month_start).days + 1

    _fill_range_with_work_shifts(user_id, month_start, today, "09:00", "17:00")

    result = attendance_service.get_month_to_date_hours(user_id)

    assert result["planned_hours"] == 8.0 * day_count
    assert result["missing_days_count"] == 0
