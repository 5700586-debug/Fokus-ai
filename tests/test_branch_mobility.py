"""ADVANCED WORK SCHEDULE + MOBILITY V1: ko'chma xodim siyosati
(employee-override > role-default > UNKNOWN, Nazoratchiga hardcode
qilinmagan), kunlik ANIQ filial talabi (``min_stay_minutes`` hech
qachon global hardcode qilinmaydi), provider-independent filial
kirish/chiqish eventlari, va ularning kunlik compliance hisob-kitobi.
"""

from datetime import timedelta

import company_time
import employees
from config import FOUNDER_ID
from repositories import attendance as attendance_repo
from roles import set_role
from services import attendance as attendance_service

_EMPLOYEE_COUNTER = 870000


def _make_employee(role_key: str = "nazoratchi") -> int:
    global _EMPLOYEE_COUNTER
    _EMPLOYEE_COUNTER += 1
    user_id = _EMPLOYEE_COUNTER

    set_role(user_id, role_key, set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {"familiya": "Test", "ism": "Nazoratchi", "branch": "Filial-1", "role_key": role_key, "contacts": []},
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)
    return user_id


def _visit_time(day, hour: int, minute: int) -> str:
    from datetime import datetime
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=company_time.resolve_timezone()).isoformat()


# ---------------------------------------------------------------- MOBILITY --


def test_mobility_employee_override_beats_role_default():
    user_id = _make_employee()
    attendance_service.set_role_mobility_mode("nazoratchi", attendance_service.MOBILITY_NONE)
    attendance_service.set_employee_mobility_mode(user_id, attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED)

    assert attendance_service.resolve_mobility_policy(user_id) == attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED


def test_mobility_no_policy_is_unknown():
    user_id = _make_employee()
    assert attendance_service.resolve_mobility_policy(user_id) is None


def test_mobility_role_default_applies_when_no_override():
    user_id = _make_employee(role_key="nazoratchi")
    attendance_service.set_role_mobility_mode("nazoratchi", attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED)

    assert attendance_service.resolve_mobility_policy(user_id) == attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED


def test_mobility_is_not_hardcoded_to_supervisor_role_name():
    """Boshqa (kelajakdagi) rolga ham xuddi shu mexanizm ishlashi
    kerak -- kod ichida "nazoratchi" satri maxsus tekshirilmaydi."""
    user_id = _make_employee(role_key="moliyachi")
    attendance_service.set_role_mobility_mode("moliyachi", attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED)

    assert attendance_service.resolve_mobility_policy(user_id) == attendance_service.MOBILITY_BRANCH_VISIT_REQUIRED


# ---------------------------------------------------- BRANCH REQUIREMENTS --


def test_min_stay_requirement_is_stored_exactly_as_given():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    accepted = attendance_service.set_branch_visit_requirement(user_id, today, "Saturn 1", 45)

    assert accepted is True
    requirements = attendance_service.get_branch_visit_requirements(user_id, today)
    assert len(requirements) == 1
    assert requirements[0]["min_stay_minutes"] == 45


def test_non_positive_requirement_is_rejected():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    assert attendance_service.set_branch_visit_requirement(user_id, today, "Saturn 1", 0) is False
    assert attendance_service.set_branch_visit_requirement(user_id, today, "Saturn 1", -5) is False


def test_requirement_upsert_keeps_a_single_row_per_employee_date_branch():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    attendance_service.set_branch_visit_requirement(user_id, today, "Saturn 1", 30)
    attendance_service.set_branch_visit_requirement(user_id, today, "Saturn 1", 45)

    requirements = attendance_service.get_branch_visit_requirements(user_id, today)
    assert len(requirements) == 1
    assert requirements[0]["min_stay_minutes"] == 45


def test_no_requirement_is_not_an_automatic_pass():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    compliance = attendance_service.get_daily_branch_compliance(user_id, today)
    assert compliance == []


# ----------------------------------------------------------- STAY MINUTES --


def test_thirty_minute_requirement_met_by_thirty_five_minute_stay():
    user_id = _make_employee()
    today = company_time.today()
    attendance_service.set_branch_visit_requirement(user_id, today.isoformat(), "Saturn 1", 30)
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_ENTER, _visit_time(today, 10, 0), "test"
    )
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_EXIT, _visit_time(today, 10, 35), "test"
    )

    compliance = attendance_service.get_daily_branch_compliance(user_id, today.isoformat())
    assert len(compliance) == 1
    assert compliance[0]["status"] == "complete"
    assert compliance[0]["actual_minutes"] == 35.0
    assert compliance[0]["met"] is True


def test_thirty_minute_requirement_not_met_by_twenty_minute_stay():
    user_id = _make_employee()
    today = company_time.today()
    attendance_service.set_branch_visit_requirement(user_id, today.isoformat(), "Saturn 1", 30)
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_ENTER, _visit_time(today, 10, 0), "test"
    )
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_EXIT, _visit_time(today, 10, 20), "test"
    )

    compliance = attendance_service.get_daily_branch_compliance(user_id, today.isoformat())
    assert compliance[0]["actual_minutes"] == 20.0
    assert compliance[0]["met"] is False


def test_enter_without_exit_is_incomplete_not_failed():
    user_id = _make_employee()
    today = company_time.today()
    attendance_service.set_branch_visit_requirement(user_id, today.isoformat(), "Saturn 1", 30)
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_ENTER, _visit_time(today, 10, 0), "test"
    )

    compliance = attendance_service.get_daily_branch_compliance(user_id, today.isoformat())
    assert compliance[0]["status"] == "incomplete"
    assert compliance[0]["actual_minutes"] is None
    assert compliance[0]["met"] is None


def test_two_visits_in_one_day_sum_correctly():
    user_id = _make_employee()
    today = company_time.today()
    attendance_service.set_branch_visit_requirement(user_id, today.isoformat(), "Saturn 1", 30)
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_ENTER, _visit_time(today, 10, 0), "test"
    )
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_EXIT, _visit_time(today, 10, 15), "test"
    )
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_ENTER, _visit_time(today, 15, 0), "test"
    )
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_EXIT, _visit_time(today, 15, 25), "test"
    )

    compliance = attendance_service.get_daily_branch_compliance(user_id, today.isoformat())
    assert compliance[0]["actual_minutes"] == 40.0


def test_overlapping_visits_are_not_double_counted():
    user_id = _make_employee()
    today = company_time.today()
    stay = attendance_service.get_branch_stay_minutes(
        user_id, "Saturn 1",
        _visit_time(today, 0, 0), _visit_time(today, 23, 59),
    )
    assert stay == {"status": "complete", "minutes": 0.0}

    attendance_repo.record_branch_visit_event(user_id, "Saturn 1", "enter", _visit_time(today, 10, 0), "test")
    attendance_repo.record_branch_visit_event(user_id, "Saturn 1", "enter", _visit_time(today, 10, 5), "test")
    attendance_repo.record_branch_visit_event(user_id, "Saturn 1", "exit", _visit_time(today, 10, 30), "test")

    stay = attendance_service.get_branch_stay_minutes(
        user_id, "Saturn 1", _visit_time(today, 0, 0), _visit_time(today, 23, 59)
    )
    assert stay["status"] == "complete"
    assert stay["minutes"] == 30.0


def test_other_branch_events_do_not_mix_in():
    user_id = _make_employee()
    today = company_time.today()
    attendance_service.set_branch_visit_requirement(user_id, today.isoformat(), "Saturn 1", 30)
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_ENTER, _visit_time(today, 10, 0), "test"
    )
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_EXIT, _visit_time(today, 10, 35), "test"
    )
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 2", attendance_service.VISIT_ENTER, _visit_time(today, 11, 0), "test"
    )
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 2", attendance_service.VISIT_EXIT, _visit_time(today, 11, 50), "test"
    )

    compliance = attendance_service.get_daily_branch_compliance(user_id, today.isoformat())
    assert len(compliance) == 1
    assert compliance[0]["branch"] == "Saturn 1"
    assert compliance[0]["actual_minutes"] == 35.0


def test_overnight_visit_belongs_to_the_logical_shift_date():
    user_id = _make_employee()
    today = company_time.today()
    next_day = today + timedelta(days=1)

    attendance_service.set_scheduled_work_shift(user_id, today.isoformat(), "18:00", "02:00", "test")
    attendance_service.set_branch_visit_requirement(user_id, today.isoformat(), "Saturn 1", 30)

    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_ENTER, _visit_time(next_day, 0, 30), "test"
    )
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_EXIT, _visit_time(next_day, 1, 0), "test"
    )

    compliance = attendance_service.get_daily_branch_compliance(user_id, today.isoformat())
    assert compliance[0]["status"] == "complete"
    assert compliance[0]["actual_minutes"] == 30.0
    assert compliance[0]["met"] is True


def test_min_stay_of_forty_five_is_not_hardcoded_to_thirty():
    user_id = _make_employee()
    today = company_time.today()
    attendance_service.set_branch_visit_requirement(user_id, today.isoformat(), "Saturn 3", 45)
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 3", attendance_service.VISIT_ENTER, _visit_time(today, 9, 0), "test"
    )
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 3", attendance_service.VISIT_EXIT, _visit_time(today, 9, 40), "test"
    )

    compliance = attendance_service.get_daily_branch_compliance(user_id, today.isoformat())
    assert compliance[0]["required_minutes"] == 45
    assert compliance[0]["actual_minutes"] == 40.0
    assert compliance[0]["met"] is False


def test_requirement_missing_is_unknown_not_automatic_pass():
    user_id = _make_employee()
    today = company_time.today()
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_ENTER, _visit_time(today, 10, 0), "test"
    )
    attendance_service.record_branch_visit_event(
        user_id, "Saturn 1", attendance_service.VISIT_EXIT, _visit_time(today, 10, 40), "test"
    )

    compliance = attendance_service.get_daily_branch_compliance(user_id, today.isoformat())
    assert compliance == []
