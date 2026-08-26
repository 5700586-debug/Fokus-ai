"""WORK HOURS CORE V1: oy boshidan REJA va HAQIQIY ishlangan soat
(``services/attendance.py::get_worked_hours_for_day``/
``get_month_to_date_hours``). Hech qanday Telegram UI yoki Face ID
integratsiyasi qamrab olinmaydi -- faqat repository/service qatlami.
"""

from datetime import date, timedelta

import company_time
import employees
from config import FOUNDER_ID
from roles import set_role
from services import attendance as attendance_service

_EMPLOYEE_COUNTER = 840000


def _make_employee(hire_date: str | None = None, work_schedule: str | None = None) -> int:
    global _EMPLOYEE_COUNTER
    _EMPLOYEE_COUNTER += 1
    user_id = _EMPLOYEE_COUNTER

    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {
            "familiya": "Test", "ism": "Xodim", "branch": "Filial-1", "role_key": "kassir",
            "hire_date": hire_date, "work_schedule": work_schedule, "contacts": [],
        },
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)
    return user_id


# --------------------------------------------------- get_worked_hours_for_day --


def test_worked_hours_valid_check_in_and_check_out():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    attendance_service.record_manual_arrival(user_id, today, "08:00")
    attendance_service.record_manual_departure(user_id, today, "17:00")

    assert attendance_service.get_worked_hours_for_day(user_id, today) == 9.0


def test_worked_hours_none_when_check_out_missing():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    attendance_service.record_manual_arrival(user_id, today, "08:00")

    assert attendance_service.get_worked_hours_for_day(user_id, today) is None


def test_worked_hours_none_when_check_in_missing():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    attendance_service.record_manual_departure(user_id, today, "17:00")

    assert attendance_service.get_worked_hours_for_day(user_id, today) is None


def test_worked_hours_none_for_invalid_negative_interval():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    attendance_service.record_manual_arrival(user_id, today, "18:00")
    attendance_service.record_manual_departure(user_id, today, "08:00")

    assert attendance_service.get_worked_hours_for_day(user_id, today) is None


def test_worked_hours_uses_first_check_in_and_last_check_out_when_multiple():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    attendance_service.record_manual_arrival(user_id, today, "09:00")
    attendance_service.record_manual_arrival(user_id, today, "08:00")
    attendance_service.record_manual_departure(user_id, today, "17:00")
    attendance_service.record_manual_departure(user_id, today, "18:30")

    assert attendance_service.get_worked_hours_for_day(user_id, today) == 10.5


def test_worked_hours_none_when_no_events_at_all():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    assert attendance_service.get_worked_hours_for_day(user_id, today) is None


# --------------------------------------------------- get_month_to_date_hours --


def test_month_to_date_hours_unknown_employee_returns_none():
    assert attendance_service.get_month_to_date_hours(999999999) is None


def test_month_to_date_hours_returns_no_data_fallback_for_unparseable_schedule():
    user_id = _make_employee(hire_date="2020-01-01", work_schedule="Erkin grafik")
    result = attendance_service.get_month_to_date_hours(user_id)

    assert result["planned_hours"] is None


def test_month_to_date_hours_returns_no_data_fallback_when_schedule_missing():
    user_id = _make_employee(hire_date="2020-01-01", work_schedule=None)
    result = attendance_service.get_month_to_date_hours(user_id)

    assert result["planned_hours"] is None


def test_month_to_date_planned_hours_ignores_legacy_free_text_and_uses_structured_schedule():
    """``work_schedule`` erkin matni "09:00-18:00" (9 soat/kun) desa
    ham, strukturali smena jadvali "10:00-16:00" (6 soat/kun) bilan
    to'ldirilgan -- natija strukturali manbaga mos kelishi kerak, eski
    matn ustuniga emas (qarang STRUCTURED WORK SCHEDULE CORE V1)."""
    user_id = _make_employee(hire_date="2020-01-01", work_schedule="09:00–18:00")
    today = company_time.today()
    month_start = date(today.year, today.month, 1)
    expected_day_count = (today - month_start).days + 1

    current = month_start
    while current <= today:
        attendance_service.set_scheduled_work_shift(user_id, current.isoformat(), "10:00", "16:00", "test")
        current += timedelta(days=1)

    result = attendance_service.get_month_to_date_hours(user_id)

    assert result["planned_hours"] == 6.0 * expected_day_count
    assert result["range_start"] == month_start.isoformat()
    assert result["range_end"] == today.isoformat()


def test_month_to_date_actual_hours_excludes_previous_month():
    user_id = _make_employee(hire_date="2020-01-01", work_schedule="09:00–18:00")
    today = company_time.today()
    last_day_prev_month = date(today.year, today.month, 1) - timedelta(days=1)

    attendance_service.record_manual_arrival(user_id, last_day_prev_month.isoformat(), "08:00")
    attendance_service.record_manual_departure(user_id, last_day_prev_month.isoformat(), "17:00")
    attendance_service.record_manual_arrival(user_id, today.isoformat(), "08:00")
    attendance_service.record_manual_departure(user_id, today.isoformat(), "12:00")

    result = attendance_service.get_month_to_date_hours(user_id)

    assert result["actual_hours"] == 4.0


def test_month_to_date_hours_respects_hire_date_floor():
    today = company_time.today()
    user_id = _make_employee(hire_date=today.isoformat(), work_schedule="09:00–18:00")
    yesterday = today - timedelta(days=1)

    attendance_service.record_manual_arrival(user_id, yesterday.isoformat(), "08:00")
    attendance_service.record_manual_departure(user_id, yesterday.isoformat(), "17:00")
    attendance_service.record_manual_arrival(user_id, today.isoformat(), "08:00")
    attendance_service.record_manual_departure(user_id, today.isoformat(), "11:00")
    attendance_service.set_scheduled_work_shift(user_id, today.isoformat(), "09:00", "18:00", "test")

    result = attendance_service.get_month_to_date_hours(user_id)

    assert result["range_start"] == today.isoformat()
    assert result["actual_hours"] == 3.0
    assert result["planned_hours"] == 9.0


def test_month_to_date_hours_hire_date_in_the_future_gives_no_data():
    today = company_time.today()
    future_hire_date = (today + timedelta(days=5)).isoformat()
    user_id = _make_employee(hire_date=future_hire_date, work_schedule="09:00–18:00")

    result = attendance_service.get_month_to_date_hours(user_id)

    assert result["planned_hours"] is None
    assert result["actual_hours"] == 0.0
