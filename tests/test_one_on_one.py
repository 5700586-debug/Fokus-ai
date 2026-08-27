"""WEEKLY 1:1 CORE V1: bitta xodimga bitta haftada bitta yozuv, faqat
beshta ruxsat etilgan natija, hal qilinmagan masala keyingi suhbatga
o'tadi. Telegram UI, ball/bonus/minus va baholash bu qatlamda yo'q.
"""

import employees
from config import FOUNDER_ID
from roles import set_role
from services import one_on_one as one_on_one_service

_EMPLOYEE_COUNTER = 880000

_MONDAY = "2026-08-24"
_FRIDAY = "2026-08-28"
_NEXT_MONDAY = "2026-08-31"


def _make_employee(approve: bool = True) -> int:
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
    if approve:
        employees.approve_profile(user_id, approved_by=FOUNDER_ID)
    return user_id


# ------------------------------------------------------------- yaratish --


def test_valid_one_on_one_is_stored():
    user_id = _make_employee()

    record_id = one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, one_on_one_service.OUTCOME_DIFFICULTY,
        meeting_date=_FRIDAY, summary="Smena almashinuvi og'ir",
    )

    assert record_id is not None
    record = one_on_one_service.get_one_on_one(record_id)
    assert record["employee_id"] == user_id
    assert record["manager_id"] == FOUNDER_ID
    assert record["branch"] == "Filial-1"
    assert record["meeting_date"] == _FRIDAY
    # Hafta kaliti — suhbat sanasi tushgan haftaning dushanbasi.
    assert record["week_start"] == _MONDAY
    assert record["outcome"] == "difficulty"
    assert record["summary"] == "Smena almashinuvi og'ir"
    assert record["followup_text"] is None
    assert record["followup_status"] is None
    assert record["created_at"]
    assert record["updated_at"]


def test_all_five_outcomes_are_accepted():
    outcomes = [
        one_on_one_service.OUTCOME_OK,
        one_on_one_service.OUTCOME_DIFFICULTY,
        one_on_one_service.OUTCOME_SUGGESTION,
        one_on_one_service.OUTCOME_SERIOUS_ISSUE,
        one_on_one_service.OUTCOME_OTHER,
    ]
    assert outcomes == list(one_on_one_service.KNOWN_OUTCOMES)

    for outcome in outcomes:
        user_id = _make_employee()
        record_id = one_on_one_service.create_one_on_one(
            user_id, FOUNDER_ID, outcome, meeting_date=_MONDAY
        )
        assert one_on_one_service.get_one_on_one(record_id)["outcome"] == outcome


# ---------------------------------------------------------- validatsiya --


def test_unknown_outcome_is_rejected():
    user_id = _make_employee()

    assert one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, "burnout", meeting_date=_MONDAY
    ) is None
    assert one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, "", meeting_date=_MONDAY
    ) is None
    assert one_on_one_service.list_one_on_ones(user_id) == []


def test_invalid_date_is_rejected():
    user_id = _make_employee()

    assert one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, one_on_one_service.OUTCOME_OK, meeting_date="2026-13-45",
    ) is None
    assert one_on_one_service.list_one_on_ones(user_id) == []


def test_unknown_or_unapproved_or_offboarded_employee_is_rejected():
    unknown_id = 999999
    assert one_on_one_service.create_one_on_one(
        unknown_id, FOUNDER_ID, one_on_one_service.OUTCOME_OK, meeting_date=_MONDAY
    ) is None

    submitted_id = _make_employee(approve=False)
    assert one_on_one_service.create_one_on_one(
        submitted_id, FOUNDER_ID, one_on_one_service.OUTCOME_OK, meeting_date=_MONDAY
    ) is None
    assert one_on_one_service.list_one_on_ones(submitted_id) == []

    offboarded_id = _make_employee()
    employees.offboard_profile(offboarded_id)
    assert one_on_one_service.create_one_on_one(
        offboarded_id, FOUNDER_ID, one_on_one_service.OUTCOME_OK, meeting_date=_MONDAY
    ) is None
    assert one_on_one_service.list_one_on_ones(offboarded_id) == []


# ------------------------------------------------- haftalik takroriylik --


def test_second_one_on_one_in_same_week_is_blocked():
    user_id = _make_employee()

    first_id = one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, one_on_one_service.OUTCOME_OK, meeting_date=_MONDAY
    )
    # Xuddi shu haftaning boshqa kuni ham takroriy hisoblanadi.
    second_id = one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, one_on_one_service.OUTCOME_SUGGESTION, meeting_date=_FRIDAY,
    )

    assert first_id is not None
    assert second_id is None
    records = one_on_one_service.list_one_on_ones(user_id)
    assert len(records) == 1
    assert records[0]["outcome"] == "ok"


def test_next_week_one_on_one_is_allowed():
    user_id = _make_employee()

    one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, one_on_one_service.OUTCOME_OK, meeting_date=_FRIDAY
    )
    next_id = one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, one_on_one_service.OUTCOME_OK, meeting_date=_NEXT_MONDAY,
    )

    assert next_id is not None
    assert [row["week_start"] for row in one_on_one_service.list_one_on_ones(user_id)] == [
        _MONDAY, _NEXT_MONDAY,
    ]


def test_week_lookup_uses_any_day_of_that_week():
    user_id = _make_employee()
    record_id = one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, one_on_one_service.OUTCOME_OK, meeting_date=_MONDAY
    )

    assert one_on_one_service.get_one_on_one_for_week(user_id, _FRIDAY)["id"] == record_id
    assert one_on_one_service.get_one_on_one_for_week(user_id, _NEXT_MONDAY) is None


# ------------------------------------------------------------ follow-up --


def test_open_followup_is_available_for_next_conversation():
    user_id = _make_employee()
    record_id = one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, one_on_one_service.OUTCOME_DIFFICULTY, meeting_date=_MONDAY,
        followup_text="Dam olish kunini aniqlashtirish",
    )

    record = one_on_one_service.get_one_on_one(record_id)
    assert record["followup_text"] == "Dam olish kunini aniqlashtirish"
    assert record["followup_status"] == "open"

    # Keyingi hafta suhbati boshlanishida ochiq masala shu yerdan olinadi.
    open_item = one_on_one_service.get_open_followup(user_id)
    assert open_item["id"] == record_id
    assert open_item["followup_text"] == "Dam olish kunini aniqlashtirish"


def test_no_open_followup_when_text_is_absent():
    user_id = _make_employee()
    one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, one_on_one_service.OUTCOME_OK, meeting_date=_MONDAY,
        followup_text="   ",
    )

    assert one_on_one_service.get_open_followup(user_id) is None


def test_resolved_followup_is_not_returned_again():
    user_id = _make_employee()
    record_id = one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, one_on_one_service.OUTCOME_DIFFICULTY, meeting_date=_MONDAY,
        followup_text="Grafik masalasi",
    )

    assert one_on_one_service.resolve_followup(record_id, resolved_by=FOUNDER_ID) is True

    record = one_on_one_service.get_one_on_one(record_id)
    assert record["followup_status"] == "resolved"
    assert record["followup_resolved_by"] == FOUNDER_ID
    assert record["followup_resolved_at"]
    # Matn saqlanadi — tarix o'chirilmaydi.
    assert record["followup_text"] == "Grafik masalasi"
    assert one_on_one_service.get_open_followup(user_id) is None


def test_second_resolve_is_noop():
    user_id = _make_employee()
    record_id = one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, one_on_one_service.OUTCOME_DIFFICULTY, meeting_date=_MONDAY,
        followup_text="Grafik masalasi",
    )
    one_on_one_service.resolve_followup(record_id, resolved_by=FOUNDER_ID)
    first_resolved_at = one_on_one_service.get_one_on_one(record_id)["followup_resolved_at"]

    assert one_on_one_service.resolve_followup(record_id, resolved_by=123456) is False

    record = one_on_one_service.get_one_on_one(record_id)
    assert record["followup_resolved_by"] == FOUNDER_ID
    assert record["followup_resolved_at"] == first_resolved_at


def test_resolve_without_followup_or_unknown_record_is_noop():
    user_id = _make_employee()
    record_id = one_on_one_service.create_one_on_one(
        user_id, FOUNDER_ID, one_on_one_service.OUTCOME_OK, meeting_date=_MONDAY
    )

    assert one_on_one_service.resolve_followup(record_id, resolved_by=FOUNDER_ID) is False
    assert one_on_one_service.resolve_followup(999999, resolved_by=FOUNDER_ID) is False
