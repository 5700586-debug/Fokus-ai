"""Xodim dashboardi (``/mystars`` kengaytmasi, ``services/employee_dashboard.py``
+ ``services/attendance.py``): profil, davr Bonus/Minus/Jami, kechagi
davomat, oxirgi 2 kunlik tafsilot. Foto/attendance ma'lumoti yo'q
holatlarda ham cho'kmasligi (crash qilmasligi) va eski tarixni
o'chirmasligi asosiy tekshiruv nuqtalari."""

from datetime import date, timedelta

import company_time
import employees
from config import FOUNDER_ID
from repositories import attendance as attendance_repo
from roles import set_role
from services import attendance as attendance_service
from services import employee_dashboard


def _make_employee(user_id: int, branch: str = "Filial-1", hire_date: str | None = None) -> None:
    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {
            "familiya": "Test", "ism": "Xodim", "branch": branch, "role_key": "kassir",
            "hire_date": hire_date, "contacts": [],
        },
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


def test_build_dashboard_returns_none_for_unknown_user():
    assert employee_dashboard.build_dashboard(999999999) is None


def test_dashboard_does_not_crash_without_photo_and_without_attendance():
    user_id = 820001
    _make_employee(user_id)

    dashboard = employee_dashboard.build_dashboard(user_id)

    assert dashboard is not None
    assert dashboard["profile"]["photo_file_id"] is None
    assert dashboard["yesterday"]["arrival_time"] is None
    text = employee_dashboard.format_dashboard_text(dashboard)
    assert "Xodim" in text


def test_dashboard_shows_bonus_minus_net():
    from repositories import discipline as discipline_repo

    user_id = 820002
    _make_employee(user_id)
    discipline_repo.adjust_bonus_bank(user_id, 50, "test", "test", None)
    discipline_repo.adjust_bonus_bank(user_id, -10, "test", "test", None)

    dashboard = employee_dashboard.build_dashboard(user_id)

    assert dashboard["points"]["bonus"] == 50
    assert dashboard["points"]["minus"] == 10
    assert dashboard["points"]["net"] == 40


def test_recent_days_summary_is_limited_to_requested_days_but_older_rows_remain_in_db():
    user_id = 820003
    _make_employee(user_id)

    today = company_time.today()
    for offset in range(5):
        day = today - timedelta(days=offset)
        attendance_service.record_manual_arrival(user_id, day.isoformat(), "08:00")

    recent = attendance_service.get_recent_days_summary(user_id, days=2)
    assert len(recent) == 2

    old_day = (today - timedelta(days=4)).isoformat()
    old_events = attendance_repo.list_events_for_date(user_id, old_day)
    assert len(old_events) == 1


def test_manager_permission_approved_is_not_shown_as_bad_lateness():
    user_id = 820004
    yesterday = (company_time.today() - timedelta(days=1)).isoformat()
    _make_employee(user_id)

    attendance_service.record_manual_arrival(user_id, yesterday, "10:30")
    attendance_service.request_manager_permission(user_id, yesterday)
    decided = attendance_service.decide_manager_permission(user_id, yesterday, approved=True, decided_by=FOUNDER_ID)
    assert decided is True

    summary = attendance_service.get_yesterday_summary(user_id)
    assert summary["reason_status"] == attendance_service.REASON_MANAGER_PERMISSION_APPROVED
    assert "kechikish" not in summary["label"].lower()


def test_force_majeure_is_not_shown_as_bad_lateness():
    user_id = 820005
    yesterday = (company_time.today() - timedelta(days=1)).isoformat()
    _make_employee(user_id)

    attendance_service.record_manual_arrival(user_id, yesterday, "11:00")
    attendance_service.mark_force_majeure(user_id, yesterday, "Kasal bo'lib qoldi")

    summary = attendance_service.get_yesterday_summary(user_id)
    assert summary["reason_status"] == attendance_service.REASON_FORCE_MAJEURE
    assert "kechikish" not in summary["label"].lower()
    assert summary["note"] == "Kasal bo'lib qoldi"


def test_unjustified_reason_does_not_invent_a_penalty_amount():
    user_id = 820006
    yesterday = (company_time.today() - timedelta(days=1)).isoformat()
    _make_employee(user_id)

    attendance_service.record_manual_arrival(user_id, yesterday, "12:00")
    attendance_service.mark_unjustified(user_id, yesterday)

    from repositories import discipline as discipline_repo

    salary = discipline_repo.get_salary(user_id)
    assert salary is None or salary["bonus_bank"] == 0


def test_second_manager_permission_decision_does_not_override_the_first():
    user_id = 820007
    yesterday = (company_time.today() - timedelta(days=1)).isoformat()
    _make_employee(user_id)

    attendance_service.record_manual_arrival(user_id, yesterday, "09:15")
    attendance_service.request_manager_permission(user_id, yesterday)

    first = attendance_service.decide_manager_permission(user_id, yesterday, approved=True, decided_by=FOUNDER_ID)
    second = attendance_service.decide_manager_permission(user_id, yesterday, approved=False, decided_by=FOUNDER_ID)

    assert first is True
    assert second is False

    summary = attendance_service.get_yesterday_summary(user_id)
    assert summary["reason_status"] == attendance_service.REASON_MANAGER_PERMISSION_APPROVED


# --------------------------------------------- dashboard reja/haqiqiy soat --


def _fill_full_range_work_and_attendance(user_id: int, start_text: str, end_text: str) -> tuple[date, date, int]:
    today = company_time.today()
    month_start = date(today.year, today.month, 1)
    current = month_start
    while current <= today:
        attendance_service.set_scheduled_work_shift(user_id, current.isoformat(), start_text, end_text, "test")
        attendance_service.record_manual_arrival(user_id, current.isoformat(), start_text)
        attendance_service.record_manual_departure(user_id, current.isoformat(), end_text)
        current += timedelta(days=1)
    day_count = (today - month_start).days + 1
    return month_start, today, day_count


def test_dashboard_shows_planned_and_actual_hours_when_data_is_complete():
    user_id = 820008
    _make_employee(user_id, hire_date="2020-01-01")
    _month_start, _today, day_count = _fill_full_range_work_and_attendance(user_id, "09:00", "18:00")

    dashboard = employee_dashboard.build_dashboard(user_id)
    text = employee_dashboard.format_dashboard_text(dashboard)

    assert dashboard["hours"]["planned_hours"] == 9.0 * day_count
    assert dashboard["hours"]["actual_hours"] == 9.0 * day_count
    assert f"🗓 Reja soati: {9 * day_count:g} soat" in text
    assert f"🕒 Haqiqiy soat: {9 * day_count:g} soat" in text


def test_dashboard_formats_planned_hours_as_a_clean_integer():
    user_id = 820009
    today = company_time.today()
    _make_employee(user_id, hire_date=today.isoformat())
    attendance_service.set_scheduled_work_shift(user_id, today.isoformat(), "09:00", "18:00", "test")

    dashboard = employee_dashboard.build_dashboard(user_id)
    text = employee_dashboard.format_dashboard_text(dashboard)

    assert dashboard["hours"]["planned_hours"] == 9.0
    assert "🗓 Reja soati: 9 soat" in text


def test_dashboard_formats_actual_hours_with_a_decimal_when_needed():
    user_id = 820010
    today = company_time.today()
    _make_employee(user_id, hire_date=today.isoformat())

    attendance_service.record_manual_arrival(user_id, today.isoformat(), "09:00")
    attendance_service.record_manual_departure(user_id, today.isoformat(), "17:30")

    dashboard = employee_dashboard.build_dashboard(user_id)
    text = employee_dashboard.format_dashboard_text(dashboard)

    assert dashboard["hours"]["actual_hours"] == 8.5
    assert "🕒 Haqiqiy soat: 8.5 soat" in text


def test_dashboard_shows_no_data_message_when_planned_hours_is_none():
    user_id = 820011
    _make_employee(user_id, hire_date="2020-01-01")

    dashboard = employee_dashboard.build_dashboard(user_id)
    text = employee_dashboard.format_dashboard_text(dashboard)

    assert dashboard["hours"]["planned_hours"] is None
    assert "🗓 Reja soati: Ma'lumot yetarli emas" in text


def test_dashboard_shows_missing_days_count_when_schedule_incomplete():
    user_id = 820012
    _make_employee(user_id, hire_date="2020-01-01")
    today = company_time.today()
    month_start = date(today.year, today.month, 1)

    # Faqat oy boshini to'ldiramiz, bugungi kun ataylab UNKNOWN qoladi.
    current = month_start
    while current < today:
        attendance_service.set_scheduled_work_shift(user_id, current.isoformat(), "09:00", "18:00", "test")
        current += timedelta(days=1)

    dashboard = employee_dashboard.build_dashboard(user_id)
    text = employee_dashboard.format_dashboard_text(dashboard)

    assert dashboard["hours"]["missing_days_count"] == 1
    assert "📅 Grafik kiritilmagan: 1 kun" in text


def test_dashboard_shows_no_data_for_actual_hours_when_no_complete_day_exists():
    user_id = 820013
    _make_employee(user_id, hire_date="2020-01-01")
    today = company_time.today()

    # Faqat check_in, check_out yo'q -- hech qanday to'liq kun yo'q.
    attendance_service.record_manual_arrival(user_id, today.isoformat(), "09:00")

    dashboard = employee_dashboard.build_dashboard(user_id)
    text = employee_dashboard.format_dashboard_text(dashboard)

    assert dashboard["hours"]["worked_days_count"] == 0
    assert "🕒 Haqiqiy soat: Ma'lumot yo'q" in text


def test_dashboard_shows_real_actual_hours_when_at_least_one_complete_day_exists():
    user_id = 820014
    today = company_time.today()
    _make_employee(user_id, hire_date=today.isoformat())

    attendance_service.record_manual_arrival(user_id, today.isoformat(), "08:00")
    attendance_service.record_manual_departure(user_id, today.isoformat(), "16:00")

    dashboard = employee_dashboard.build_dashboard(user_id)
    text = employee_dashboard.format_dashboard_text(dashboard)

    assert dashboard["hours"]["worked_days_count"] == 1
    assert "🕒 Haqiqiy soat: 8 soat" in text


def test_dashboard_existing_blocks_are_unaffected_by_hours_wiring():
    user_id = 820015
    _make_employee(user_id, hire_date="2020-01-01")

    dashboard = employee_dashboard.build_dashboard(user_id)
    text = employee_dashboard.format_dashboard_text(dashboard)

    assert dashboard["profile"]["full_name"] == "Xodim Test"
    assert "🟢 Bonus:" in text
    assert "🔴 Minus:" in text
    assert "⭐ Jami:" in text
    assert "⏰ Kecha:" in text
    assert "📅 Oxirgi 2 kun:" in text
