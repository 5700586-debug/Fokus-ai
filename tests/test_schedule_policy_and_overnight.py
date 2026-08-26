"""ADVANCED WORK SCHEDULE + OVERNIGHT V1: grafik siyosati (fixed_1/
fixed_2/flexible, employee-override > role-default > UNKNOWN),
markazlashtirilgan fixed-shift shablonlari, schedule revision audit,
va tun smenasi uchun LOGICAL SHIFT actual-hours hisob-kitobi.
"""

from datetime import date, timedelta

import company_time
import employees
from config import FOUNDER_ID
from repositories import attendance as attendance_repo
from roles import set_role
from services import attendance as attendance_service

_EMPLOYEE_COUNTER = 860000


def _make_employee(hire_date: str | None = None, role_key: str = "kassir") -> int:
    global _EMPLOYEE_COUNTER
    _EMPLOYEE_COUNTER += 1
    user_id = _EMPLOYEE_COUNTER

    set_role(user_id, role_key, set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {
            "familiya": "Test", "ism": "Xodim", "branch": "Filial-1", "role_key": role_key,
            "hire_date": hire_date, "contacts": [],
        },
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)
    return user_id


# ------------------------------------------------------------- 1. SCHEDULE --


def test_fixed_1_default_template_is_ten_hours():
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_employee_schedule_mode(user_id, attendance_service.SCHEDULE_MODE_FIXED_1)

    accepted = attendance_service.apply_daily_work_schedule(user_id, today, "test")

    assert accepted is True
    shift = attendance_repo.get_shift_for_date(user_id, today)
    assert shift["planned_start"] == "08:00"
    assert shift["planned_end"] == "18:00"
    assert shift["schedule_mode"] == "fixed_1"


def test_fixed_2_default_template_is_eleven_hours_overnight():
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_employee_schedule_mode(user_id, attendance_service.SCHEDULE_MODE_FIXED_2)

    accepted = attendance_service.apply_daily_work_schedule(user_id, today, "test")

    assert accepted is True
    shift = attendance_repo.get_shift_for_date(user_id, today)
    assert shift["planned_start"] == "14:00"
    assert shift["planned_end"] == "01:00"


def test_flexible_daytime_shift_accepted():
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_employee_schedule_mode(user_id, attendance_service.SCHEDULE_MODE_FLEXIBLE)

    accepted = attendance_service.apply_daily_work_schedule(user_id, today, "test", "10:00", "20:00")

    assert accepted is True
    shift = attendance_repo.get_shift_for_date(user_id, today)
    assert shift["planned_start"] == "10:00"
    assert shift["planned_end"] == "20:00"
    assert shift["schedule_mode"] == "flexible"


def test_flexible_overnight_shift_accepted():
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_employee_schedule_mode(user_id, attendance_service.SCHEDULE_MODE_FLEXIBLE)

    accepted = attendance_service.apply_daily_work_schedule(user_id, today, "test", "18:00", "02:00")

    assert accepted is True
    shift = attendance_repo.get_shift_for_date(user_id, today)
    assert shift["planned_start"] == "18:00"
    assert shift["planned_end"] == "02:00"


def test_flexible_without_explicit_time_is_rejected():
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_employee_schedule_mode(user_id, attendance_service.SCHEDULE_MODE_FLEXIBLE)

    accepted = attendance_service.apply_daily_work_schedule(user_id, today, "test")

    assert accepted is False
    assert attendance_repo.get_shift_for_date(user_id, today) is None


def test_start_equal_end_is_rejected():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    accepted = attendance_service.set_scheduled_work_shift(user_id, today, "08:00", "08:00", "test")

    assert accepted is False
    assert attendance_repo.get_shift_for_date(user_id, today) is None


def test_off_day_contributes_zero_planned_hours():
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


def test_missing_day_is_unknown_not_off():
    user_id = _make_employee(hire_date="2020-01-01")
    today = company_time.today().isoformat()

    shift = attendance_repo.get_shift_for_date(user_id, today)
    assert shift is None

    result = attendance_service.get_month_to_date_planned_hours(user_id)
    assert result["planned_hours"] is None
    assert result["missing_days_count"] > 0


def test_employee_override_beats_role_default():
    user_id = _make_employee(role_key="kassir")
    attendance_service.set_role_schedule_mode("kassir", attendance_service.SCHEDULE_MODE_FIXED_1)
    attendance_service.set_employee_schedule_mode(user_id, attendance_service.SCHEDULE_MODE_FLEXIBLE)

    assert attendance_service.resolve_schedule_mode(user_id) == attendance_service.SCHEDULE_MODE_FLEXIBLE


def test_no_policy_at_all_is_unknown_not_fixed_1():
    user_id = _make_employee(role_key="kassir")

    assert attendance_service.resolve_schedule_mode(user_id) is None


# ------------------------------------------------------- SCHEDULE AUDIT --


def test_schedule_change_keeps_old_value_in_audit():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    attendance_service.set_scheduled_work_shift(user_id, today, "10:00", "20:00", "test")
    attendance_service.set_scheduled_work_shift(user_id, today, "12:00", "22:00", "test")

    revisions = attendance_repo.list_schedule_revisions(user_id, today)
    assert len(revisions) == 2
    assert revisions[0]["old_status"] is None
    assert revisions[1]["old_planned_start"] == "10:00"
    assert revisions[1]["old_planned_end"] == "20:00"
    assert revisions[1]["new_planned_start"] == "12:00"
    assert revisions[1]["new_planned_end"] == "22:00"


def test_upsert_keeps_a_single_row_in_the_main_table():
    user_id = _make_employee()
    today = company_time.today().isoformat()

    attendance_service.set_scheduled_work_shift(user_id, today, "10:00", "20:00", "test")
    attendance_service.set_scheduled_work_shift(user_id, today, "12:00", "22:00", "test")

    rows = attendance_repo.get_schedule_for_range(user_id, today, (company_time.today() + timedelta(days=1)).isoformat())
    assert len(rows) == 1
    assert rows[0]["planned_start"] == "12:00"


def test_late_schedule_change_is_flagged_in_audit():
    user_id = _make_employee()
    yesterday = (company_time.today() - timedelta(days=1)).isoformat()

    # Kecha uchun smena -- "hozir"ga nisbatan albatta allaqachon
    # boshlangan (kecha 00:01 ham "hozir"dan oldin).
    attendance_service.set_scheduled_work_shift(user_id, yesterday, "00:01", "23:00", "test")
    attendance_service.set_scheduled_work_shift(user_id, yesterday, "00:01", "12:00", "test")

    revisions = attendance_repo.list_schedule_revisions(user_id, yesterday)
    assert len(revisions) == 2
    assert revisions[1]["is_late_change"] == 1


# --------------------------------------------------------- OVERNIGHT ACTUAL --


def test_daytime_actual_hours_is_ten():
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_scheduled_work_shift(user_id, today, "08:00", "18:00", "test")
    attendance_service.record_manual_arrival(user_id, today, "08:00")
    attendance_service.record_manual_departure(user_id, today, "18:00")

    assert attendance_service.get_worked_hours_for_day(user_id, today) == 10.0


def test_overnight_actual_hours_is_eleven():
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_scheduled_work_shift(user_id, today, "14:00", "01:00", "test")
    attendance_service.record_manual_arrival(user_id, today, "14:00")
    attendance_service.record_manual_departure(user_id, today, "01:00")

    assert attendance_service.get_worked_hours_for_day(user_id, today) == 11.0


def test_overnight_actual_hours_with_late_departure_is_eleven_and_a_half():
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_scheduled_work_shift(user_id, today, "14:00", "01:00", "test")
    attendance_service.record_manual_arrival(user_id, today, "14:00")
    attendance_service.record_manual_departure(user_id, today, "01:30")

    assert attendance_service.get_worked_hours_for_day(user_id, today) == 11.5


def test_overnight_check_out_is_written_to_the_next_calendar_date():
    user_id = _make_employee()
    today = company_time.today()
    attendance_service.set_scheduled_work_shift(user_id, today.isoformat(), "14:00", "01:00", "test")
    attendance_service.record_manual_arrival(user_id, today.isoformat(), "14:00")
    attendance_service.record_manual_departure(user_id, today.isoformat(), "01:00")

    next_day = (today + timedelta(days=1)).isoformat()
    events = attendance_repo.list_events_for_date(user_id, next_day)
    check_outs = [e for e in events if e["event_type"] == attendance_service.EVENT_CHECK_OUT]
    assert len(check_outs) == 1

    same_day_events = attendance_repo.list_events_for_date(user_id, today.isoformat())
    assert not any(e["event_type"] == attendance_service.EVENT_CHECK_OUT for e in same_day_events)


def test_overnight_shift_counts_as_a_single_worked_day():
    user_id = _make_employee(hire_date="2020-01-01")
    today = company_time.today()
    attendance_service.set_scheduled_work_shift(user_id, today.isoformat(), "14:00", "01:00", "test")
    attendance_service.record_manual_arrival(user_id, today.isoformat(), "14:00")
    attendance_service.record_manual_departure(user_id, today.isoformat(), "01:00")

    result = attendance_service.get_month_to_date_hours(user_id)
    assert result["worked_days_count"] == 1
    assert result["actual_hours"] == 11.0


def test_overnight_shift_at_month_boundary_is_not_double_counted():
    """31-avgust 14:00 -> 1-sentabr 01:00 kabi holatni deterministik
    (kalendar chegarasidan mustaqil) tekshirish uchun: "kecha" tun
    smenasi bo'lib, uning check_out'i "bugun"ga tushadi -- bu "bugun"ning
    o'z alohida smenasi sifatida hisoblanmasligi kerak."""
    user_id = _make_employee(hire_date="2020-01-01")
    today = company_time.today()
    yesterday = today - timedelta(days=1)

    attendance_service.set_scheduled_work_shift(user_id, yesterday.isoformat(), "14:00", "01:00", "test")
    attendance_service.record_manual_arrival(user_id, yesterday.isoformat(), "14:00")
    attendance_service.record_manual_departure(user_id, yesterday.isoformat(), "01:00")

    # "bugun" uchun schedule/eventlar yo'q -- faqat kechagi tun
    # smenasining check_out qoldig'i bor edi.
    worked_today = attendance_service.get_worked_hours_for_day(user_id, today.isoformat())
    assert worked_today is None

    worked_yesterday = attendance_service.get_worked_hours_for_day(user_id, yesterday.isoformat())
    assert worked_yesterday == 11.0


def test_overnight_check_out_does_not_bleed_into_next_days_own_shift():
    user_id = _make_employee()
    today = company_time.today()
    next_day = today + timedelta(days=1)

    attendance_service.set_scheduled_work_shift(user_id, today.isoformat(), "14:00", "01:00", "test")
    attendance_service.set_scheduled_work_shift(user_id, next_day.isoformat(), "08:00", "18:00", "test")

    attendance_service.record_manual_arrival(user_id, today.isoformat(), "14:00")
    attendance_service.record_manual_departure(user_id, today.isoformat(), "01:00")
    attendance_service.record_manual_arrival(user_id, next_day.isoformat(), "08:00")
    attendance_service.record_manual_departure(user_id, next_day.isoformat(), "18:00")

    assert attendance_service.get_worked_hours_for_day(user_id, today.isoformat()) == 11.0
    assert attendance_service.get_worked_hours_for_day(user_id, next_day.isoformat()) == 10.0


def test_overnight_missing_check_out_is_none():
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_scheduled_work_shift(user_id, today, "14:00", "01:00", "test")
    attendance_service.record_manual_arrival(user_id, today, "14:00")

    assert attendance_service.get_worked_hours_for_day(user_id, today) is None


def test_overnight_missing_check_in_is_none():
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_scheduled_work_shift(user_id, today, "14:00", "01:00", "test")
    attendance_service.record_manual_departure(user_id, today, "01:00")

    assert attendance_service.get_worked_hours_for_day(user_id, today) is None


def test_over_24_hour_interval_is_rejected_as_bogus():
    """Tun smenasi 23:00->00:30 (o'zi 1.5 soat), lekin xodim "chiqish"ni
    keyingi kun 23:59da kiritsa -- bu check_in bilan 24 soatdan
    oshadigan soxta interval, rad etilishi kerak."""
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_scheduled_work_shift(user_id, today, "23:00", "00:30", "test")
    attendance_service.record_manual_arrival(user_id, today, "23:00")
    attendance_service.record_manual_departure(user_id, today, "23:59")

    assert attendance_service.get_worked_hours_for_day(user_id, today) is None


# ------------------------------------------------- FLEXIBLE RESPONSIBILITY --


def test_flexible_lateness_is_relative_to_the_confirmed_daily_start():
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_employee_schedule_mode(user_id, attendance_service.SCHEDULE_MODE_FLEXIBLE)
    attendance_service.apply_daily_work_schedule(user_id, today, "test", "10:00", "20:00")

    attendance_service.record_manual_arrival(user_id, today, "10:40")

    shift = attendance_repo.get_shift_for_date(user_id, today)
    arrival = attendance_service.get_arrival_time(user_id, today)
    assert shift["planned_start"] == "10:00"
    assert arrival == "10:40"


def test_approved_manager_permission_does_not_auto_penalize_flexible_lateness():
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_employee_schedule_mode(user_id, attendance_service.SCHEDULE_MODE_FLEXIBLE)
    attendance_service.apply_daily_work_schedule(user_id, today, "test", "10:00", "20:00")
    attendance_service.record_manual_arrival(user_id, today, "10:40")

    attendance_service.request_manager_permission(user_id, today)
    decided = attendance_service.decide_manager_permission(user_id, today, approved=True, decided_by=FOUNDER_ID)

    assert decided is True
    summary = attendance_service.get_day_summary(user_id, today)
    assert summary["reason_status"] == attendance_service.REASON_MANAGER_PERMISSION_APPROVED
    assert "kechikish" not in summary["label"].lower()


def test_force_majeure_flow_still_works_for_flexible_schedule():
    user_id = _make_employee()
    today = company_time.today().isoformat()
    attendance_service.set_employee_schedule_mode(user_id, attendance_service.SCHEDULE_MODE_FLEXIBLE)
    attendance_service.apply_daily_work_schedule(user_id, today, "test", "10:00", "20:00")
    attendance_service.record_manual_arrival(user_id, today, "11:30")

    attendance_service.mark_force_majeure(user_id, today, "Yo'lda avariya")

    summary = attendance_service.get_day_summary(user_id, today)
    assert summary["reason_status"] == attendance_service.REASON_FORCE_MAJEURE
    assert summary["note"] == "Yo'lda avariya"
