"""Xodim dashboardi (``/mystars`` kengaytmasi, ``services/employee_dashboard.py``
+ ``services/attendance.py``): profil, davr Bonus/Minus/Jami, kechagi
davomat, oxirgi 2 kunlik tafsilot. Foto/attendance ma'lumoti yo'q
holatlarda ham cho'kmasligi (crash qilmasligi) va eski tarixni
o'chirmasligi asosiy tekshiruv nuqtalari."""

from datetime import timedelta

import company_time
import employees
from config import FOUNDER_ID
from repositories import attendance as attendance_repo
from roles import set_role
from services import attendance as attendance_service
from services import employee_dashboard


def _make_employee(user_id: int, branch: str = "Filial-1") -> None:
    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {"familiya": "Test", "ism": "Xodim", "branch": branch, "role_key": "kassir", "contacts": []},
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
