"""FOUNDER '🚨 Bugungi muammolar' (grafik) V1: faqat Founder kira
oladi, faol xodimning bugungi grafigi yo'qligi va ``pending`` grafik
o'zgartirish so'rovlari to'g'ri hisoblanishi/ko'rsatilishini
tekshiradi. Yangi DB jadval/repository YO'Q -- mavjud
``employees``/``services.attendance`` ustidan o'qiydigan
``services/founder_today_problems.py``ni tekshiradi."""

from datetime import timedelta

import pytest

import company_time
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from roles import set_role
from services import attendance as attendance_service
from services import founder_today_problems
from tests.bot_harness import send

pytestmark = pytest.mark.anyio

_BRANCH_A = RECRUITING_BRANCH_NAMES[0]
_EMPLOYEE_COUNTER = 910000


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_employee(branch: str = _BRANCH_A, role_key: str = "kassir") -> int:
    global _EMPLOYEE_COUNTER
    _EMPLOYEE_COUNTER += 1
    user_id = _EMPLOYEE_COUNTER

    set_role(user_id, role_key, set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {"familiya": "Valiyev", "ism": "Ali", "branch": branch, "role_key": role_key, "contacts": []},
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)
    return user_id


def _today_iso() -> str:
    return company_time.today().isoformat()


def _tomorrow_iso() -> str:
    return (company_time.today() + timedelta(days=1)).isoformat()


# --------------------------------------------------------------- RBAC --


async def test_only_founder_can_view_today_problems(bot_dp):
    main, bot = bot_dp
    kassir_id = _make_employee()

    sent = await send(main.dp, bot, kassir_id, text="🚨 Bugungi muammolar")

    texts = [getattr(m, "text", None) or "" for m in sent]
    assert not any("grafigi kiritilmagan" in t for t in texts)
    assert not any("Kutilayotgan grafik" in t for t in texts)


async def test_founder_sees_today_problems(bot_dp):
    main, bot = bot_dp
    _make_employee()

    sent = await send(main.dp, bot, FOUNDER_ID, text="🚨 Bugungi muammolar")

    text = sent[0].text
    assert "🚨 Bugungi muammolar" in text
    assert "Valiyev Ali" in text
    assert _BRANCH_A in text


# ------------------------------------------------- bugungi grafik yo'q --


def test_active_employee_missing_todays_schedule_is_listed():
    _make_employee()

    missing = founder_today_problems.employees_missing_todays_schedule()

    assert len(missing) == 1
    assert missing[0]["full_name"] == "Valiyev Ali"
    assert missing[0]["branch"] == _BRANCH_A
    assert missing[0]["date"] == _today_iso()


def test_employee_with_work_shift_today_is_not_listed():
    employee_id = _make_employee()
    attendance_service.set_scheduled_work_shift(
        employee_id, _today_iso(), "10:00", "19:00", attendance_service.SOURCE_MANUAL_ENTRY, created_by=FOUNDER_ID
    )

    missing = founder_today_problems.employees_missing_todays_schedule()

    assert missing == []


def test_off_status_employee_is_not_listed_as_missing():
    employee_id = _make_employee()
    attendance_service.set_scheduled_day_off(
        employee_id, _today_iso(), attendance_service.SOURCE_MANUAL_ENTRY, created_by=FOUNDER_ID
    )

    missing = founder_today_problems.employees_missing_todays_schedule()

    assert missing == []


def test_offboarded_employee_is_not_listed_as_missing():
    employee_id = _make_employee()
    employees.offboard_profile(employee_id)

    missing = founder_today_problems.employees_missing_todays_schedule()

    assert missing == []


def test_duplicate_branch_name_in_config_does_not_double_count(monkeypatch):
    _make_employee()
    monkeypatch.setattr(founder_today_problems, "RECRUITING_BRANCH_NAMES", [_BRANCH_A, _BRANCH_A])

    missing = founder_today_problems.employees_missing_todays_schedule()

    assert len(missing) == 1


# --------------------------------------------------- pending so'rovlar --


def test_only_pending_schedule_change_requests_are_listed():
    pending_employee = _make_employee()
    decided_employee = _make_employee()
    tomorrow = _tomorrow_iso()

    attendance_service.create_schedule_change_request(pending_employee, tomorrow, "work", "10:00", "19:00")
    decided_id = attendance_service.create_schedule_change_request(
        decided_employee, tomorrow, "work", "10:00", "19:00"
    )
    attendance_service.decide_schedule_change_request(decided_id, True, FOUNDER_ID)

    pending = founder_today_problems.pending_schedule_change_requests()

    assert len(pending) == 1
    assert pending[0]["full_name"] == "Valiyev Ali"
    assert pending[0]["date"] == tomorrow


def test_offboarded_employees_pending_request_is_not_listed():
    employee_id = _make_employee()
    attendance_service.create_schedule_change_request(employee_id, _tomorrow_iso(), "work", "10:00", "19:00")
    employees.offboard_profile(employee_id)

    pending = founder_today_problems.pending_schedule_change_requests()

    assert pending == []


# ---------------------------------------------------- son / 10 talik --


def test_ten_item_cap_and_total_count():
    for _ in range(12):
        _make_employee()

    summary = founder_today_problems.build_today_problems_summary()
    section = summary["missing_schedule"]

    assert section["total"] == 12
    assert len(section["items"]) == 10
