"""EMPLOYEE SCHEDULE-CHANGE REQUEST CORE V1: xodim so'rovi ``pending``
holatda saqlanadi, Nazoratchi/Founder qarori faqat bir marta o'tadi,
tasdiq mavjud ``employee_scheduled_shifts`` + ``employee_schedule_revisions``
mexanizmini ishlatadi (parallel ikkinchi schedule tizimi YO'Q), rad etish
esa schedule'ga umuman tegmaydi.
"""

import company_time
import employees
from config import FOUNDER_ID
from repositories import attendance as attendance_repo
from roles import set_role
from services import attendance as attendance_service

_EMPLOYEE_COUNTER = 870000


def _make_employee() -> int:
    global _EMPLOYEE_COUNTER
    _EMPLOYEE_COUNTER += 1
    user_id = _EMPLOYEE_COUNTER

    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {
            "familiya": "Test", "ism": "Xodim", "branch": "Filial-1", "role_key": "kassir",
            "hire_date": None, "work_schedule": "09:00–18:00", "contacts": [],
        },
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)
    return user_id


def _tomorrow() -> str:
    from datetime import timedelta

    return (company_time.today() + timedelta(days=1)).isoformat()


# ------------------------------------------------------------- yaratish --


def test_new_request_is_stored_as_pending():
    user_id = _make_employee()
    shift_date = _tomorrow()

    request_id = attendance_service.create_schedule_change_request(
        user_id, shift_date, "work", "10:00", "19:00", reason="Shaxsiy sabab",
    )

    assert request_id is not None
    request = attendance_service.get_schedule_change_request(request_id)
    assert request["employee_id"] == user_id
    assert request["shift_date"] == shift_date
    assert request["requested_status"] == "work"
    assert request["requested_start"] == "10:00"
    assert request["requested_end"] == "19:00"
    assert request["reason"] == "Shaxsiy sabab"
    assert request["status"] == "pending"
    assert request["created_by"] == user_id
    assert request["created_at"]
    assert request["decided_by"] is None
    assert request["decided_at"] is None

    # Hali hech qanday schedule yozuvi yaratilmagan.
    assert attendance_repo.get_shift_for_date(user_id, shift_date) is None


def test_day_off_request_is_stored_without_times():
    user_id = _make_employee()
    shift_date = _tomorrow()

    request_id = attendance_service.create_schedule_change_request(user_id, shift_date, "off")

    request = attendance_service.get_schedule_change_request(request_id)
    assert request["requested_status"] == "off"
    assert request["requested_start"] is None
    assert request["requested_end"] is None
    assert request["status"] == "pending"


def test_pending_requests_are_listable():
    user_id = _make_employee()
    attendance_service.create_schedule_change_request(user_id, _tomorrow(), "off")

    pending = attendance_service.list_schedule_change_requests(status="pending")

    assert [row["employee_id"] for row in pending] == [user_id]


# ---------------------------------------------------------- validatsiya --


def test_invalid_time_request_is_rejected_at_creation():
    user_id = _make_employee()
    shift_date = _tomorrow()

    assert attendance_service.create_schedule_change_request(user_id, shift_date, "work", "25:00", "19:00") is None
    assert attendance_service.create_schedule_change_request(user_id, shift_date, "work", "xx", "19:00") is None
    # ``start == end`` -- mavjud ``set_scheduled_work_shift`` qoidasi.
    assert attendance_service.create_schedule_change_request(user_id, shift_date, "work", "10:00", "10:00") is None
    # WORK so'rovi vaqtsiz bo'lmaydi.
    assert attendance_service.create_schedule_change_request(user_id, shift_date, "work") is None

    assert attendance_service.list_schedule_change_requests(employee_id=user_id) == []


def test_invalid_status_or_date_or_mode_is_rejected():
    user_id = _make_employee()

    assert attendance_service.create_schedule_change_request(user_id, _tomorrow(), "vacation") is None
    assert attendance_service.create_schedule_change_request(user_id, "2026-13-45", "off") is None
    assert attendance_service.create_schedule_change_request(
        user_id, _tomorrow(), "work", "10:00", "19:00", schedule_mode="turbo",
    ) is None

    assert attendance_service.list_schedule_change_requests(employee_id=user_id) == []


# --------------------------------------------------------------- qaror --


def test_approve_applies_schedule_and_keeps_revision_history():
    user_id = _make_employee()
    shift_date = _tomorrow()
    attendance_service.set_scheduled_work_shift(user_id, shift_date, "09:00", "18:00", "test")

    request_id = attendance_service.create_schedule_change_request(
        user_id, shift_date, "work", "10:00", "19:00", reason="Shifokorga",
    )
    applied = attendance_service.decide_schedule_change_request(request_id, approved=True, decided_by=FOUNDER_ID)

    assert applied is True
    shift = attendance_repo.get_shift_for_date(user_id, shift_date)
    assert shift["status"] == "work"
    assert shift["planned_start"] == "10:00"
    assert shift["planned_end"] == "19:00"
    assert shift["source"] == attendance_service.SOURCE_SCHEDULE_REQUEST

    revisions = attendance_repo.list_schedule_revisions(user_id, shift_date)
    assert len(revisions) == 2
    assert revisions[0]["new_planned_start"] == "09:00"
    assert revisions[1]["old_planned_start"] == "09:00"
    assert revisions[1]["new_planned_start"] == "10:00"
    assert revisions[1]["reason"] == "Shifokorga"
    assert revisions[1]["changed_by"] == FOUNDER_ID

    request = attendance_service.get_schedule_change_request(request_id)
    assert request["status"] == "approved"
    assert request["decided_by"] == FOUNDER_ID
    assert request["decided_at"]


def test_approved_day_off_request_sets_day_off():
    user_id = _make_employee()
    shift_date = _tomorrow()
    attendance_service.set_scheduled_work_shift(user_id, shift_date, "09:00", "18:00", "test")

    request_id = attendance_service.create_schedule_change_request(user_id, shift_date, "off")
    attendance_service.decide_schedule_change_request(request_id, approved=True, decided_by=FOUNDER_ID)

    shift = attendance_repo.get_shift_for_date(user_id, shift_date)
    assert shift["status"] == "off"
    assert shift["planned_start"] is None
    assert shift["planned_end"] is None


def test_reject_leaves_schedule_untouched():
    user_id = _make_employee()
    shift_date = _tomorrow()
    attendance_service.set_scheduled_work_shift(user_id, shift_date, "09:00", "18:00", "test")

    request_id = attendance_service.create_schedule_change_request(user_id, shift_date, "work", "10:00", "19:00")
    decided = attendance_service.decide_schedule_change_request(request_id, approved=False, decided_by=FOUNDER_ID)

    assert decided is True
    shift = attendance_repo.get_shift_for_date(user_id, shift_date)
    assert shift["planned_start"] == "09:00"
    assert shift["planned_end"] == "18:00"
    assert len(attendance_repo.list_schedule_revisions(user_id, shift_date)) == 1
    assert attendance_service.get_schedule_change_request(request_id)["status"] == "rejected"


def test_second_decision_is_noop():
    user_id = _make_employee()
    shift_date = _tomorrow()
    attendance_service.set_scheduled_work_shift(user_id, shift_date, "09:00", "18:00", "test")

    request_id = attendance_service.create_schedule_change_request(user_id, shift_date, "work", "10:00", "19:00")
    assert attendance_service.decide_schedule_change_request(request_id, approved=True, decided_by=FOUNDER_ID) is True
    revisions_after_first = attendance_repo.list_schedule_revisions(user_id, shift_date)

    # Oradagi boshqa (qonuniy) o'zgarish -- takroriy tasdiq buni bosib
    # o'tmasligi kerak.
    attendance_service.set_scheduled_work_shift(user_id, shift_date, "12:00", "20:00", "test")

    assert attendance_service.decide_schedule_change_request(request_id, approved=True, decided_by=FOUNDER_ID) is False
    assert attendance_service.decide_schedule_change_request(request_id, approved=False, decided_by=FOUNDER_ID) is False

    shift = attendance_repo.get_shift_for_date(user_id, shift_date)
    assert shift["planned_start"] == "12:00"
    assert shift["planned_end"] == "20:00"
    assert len(attendance_repo.list_schedule_revisions(user_id, shift_date)) == len(revisions_after_first) + 1
    assert attendance_service.get_schedule_change_request(request_id)["status"] == "approved"


def test_reject_after_approve_does_not_change_status():
    user_id = _make_employee()
    shift_date = _tomorrow()

    request_id = attendance_service.create_schedule_change_request(user_id, shift_date, "off")
    attendance_service.decide_schedule_change_request(request_id, approved=False, decided_by=FOUNDER_ID)

    assert attendance_service.decide_schedule_change_request(request_id, approved=True, decided_by=FOUNDER_ID) is False
    assert attendance_service.get_schedule_change_request(request_id)["status"] == "rejected"
    assert attendance_repo.get_shift_for_date(user_id, shift_date) is None


def test_decision_on_unknown_request_is_noop():
    assert attendance_service.decide_schedule_change_request(999999, approved=True, decided_by=FOUNDER_ID) is False
