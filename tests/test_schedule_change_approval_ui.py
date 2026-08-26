"""Grafik o'zgartirish so'rovini TASDIQLASH UI V1 (`nazoratchi_bot.py`):
`/grafiksorov` -> kutilayotgan so'rovlar ro'yxati -> so'rov kartasi ->
"✅ Tasdiqlash" / "❌ Rad etish". Biznes mantiq YANGIDAN yozilmaydi —
qaror mavjud `services/attendance.decide_schedule_change_request`
orqali ketadi, shuning uchun bu yerda asosiy tekshiruv nuqtalari:
ro'yxat ko'rinishi, tasdiqda schedule AYNAN shu yo'l orqali yangilanishi,
rad etishda schedule'ga UMUMAN tegilmasligi va eskirgan/ikki marta
bosilgan tugma hech narsani qayta yozmasligi.
"""

from datetime import timedelta

import pytest

import company_time
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from repositories import attendance as attendance_repo
from roles import set_role
from services import attendance as attendance_service
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

_BRANCH_A = RECRUITING_BRANCH_NAMES[0]
_BRANCH_B = RECRUITING_BRANCH_NAMES[1]
_NAZORATCHI_ID = 890001
_EMPLOYEE_ID = 890010


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_nazoratchi(user_id: int = _NAZORATCHI_ID) -> None:
    set_role(user_id, "nazoratchi", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {"familiya": "Nazoratov", "ism": "Bek", "branch": _BRANCH_A, "role_key": "nazoratchi", "contacts": []},
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


def _make_employee(user_id: int = _EMPLOYEE_ID, branch: str = _BRANCH_A, role_key: str = "kassir") -> None:
    set_role(user_id, role_key, set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {"familiya": "Valiyev", "ism": "Ali", "branch": branch, "role_key": role_key, "contacts": []},
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


def _tomorrow() -> str:
    return (company_time.today() + timedelta(days=1)).isoformat()


def _work_request(employee_id: int = _EMPLOYEE_ID, shift_date: str | None = None) -> int:
    return attendance_service.create_schedule_change_request(
        employee_id, shift_date or _tomorrow(), attendance_service.SHIFT_STATUS_WORK,
        "10:00", "19:00", reason="Shifokorga borishim kerak",
    )


def _off_request(employee_id: int = _EMPLOYEE_ID, shift_date: str | None = None) -> int:
    return attendance_service.create_schedule_change_request(
        employee_id, shift_date or _tomorrow(), attendance_service.SHIFT_STATUS_OFF,
    )


def _callbacks(sent) -> list[str]:
    return [
        btn.callback_data
        for m in sent
        if getattr(m, "reply_markup", None)
        for row in m.reply_markup.inline_keyboard
        for btn in row
    ]


def _actor_screen(sent, actor_id: int = _NAZORATCHI_ID):
    return next(m for m in sent if getattr(m, "chat_id", None) == actor_id)


# ------------------------------------------------- KUTILAYOTGAN RO'YXAT --


async def test_pending_request_is_listed_with_employee_and_date(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_employee()
    request_id = _work_request()

    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="/grafiksorov")

    screen = _actor_screen(sent)
    assert "Grafik o'zgartirish so'rovlari" in screen.text
    buttons = [btn for row in screen.reply_markup.inline_keyboard for btn in row]
    assert [btn.callback_data for btn in buttons] == [f"nzr_schedreq:{request_id}"]
    assert "Valiyev" in buttons[0].text
    assert (company_time.today() + timedelta(days=1)).strftime("%d.%m.%Y") in buttons[0].text


async def test_request_card_shows_type_time_and_reason(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_employee()
    request_id = _work_request()

    sent = await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_schedreq:{request_id}", target_chat_id=_NAZORATCHI_ID
    )

    screen = _actor_screen(sent)
    assert "Ish vaqti: 10:00–19:00" in screen.text
    assert "Shifokorga borishim kerak" in screen.text
    assert f"nzr_schedreq_yes:{request_id}" in _callbacks(sent)
    assert f"nzr_schedreq_no:{request_id}" in _callbacks(sent)


async def test_off_request_card_shows_day_off_without_time(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_employee()
    request_id = _off_request()

    sent = await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_schedreq:{request_id}", target_chat_id=_NAZORATCHI_ID
    )

    assert "Dam olish" in _actor_screen(sent).text


async def test_decided_request_is_not_listed_anymore(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_employee()
    request_id = _off_request()
    attendance_service.decide_schedule_change_request(request_id, approved=False, decided_by=FOUNDER_ID)

    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="/grafiksorov")

    screen = _actor_screen(sent)
    assert "Kutilayotgan so'rov yo'q" in screen.text
    assert _callbacks(sent) == []


# ----------------------------------------------------------- TASDIQLASH --


async def test_approve_applies_the_schedule_through_the_service(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_employee()
    day = _tomorrow()
    request_id = _work_request(shift_date=day)

    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_schedreq_yes:{request_id}", target_chat_id=_NAZORATCHI_ID
    )

    shift = attendance_repo.get_shift_for_date(_EMPLOYEE_ID, day)
    assert shift["status"] == attendance_service.SHIFT_STATUS_WORK
    assert shift["planned_start"] == "10:00"
    assert shift["planned_end"] == "19:00"
    assert shift["source"] == attendance_service.SOURCE_SCHEDULE_REQUEST

    request = attendance_service.get_schedule_change_request(request_id)
    assert request["status"] == attendance_service.SCHEDULE_REQUEST_APPROVED
    assert request["decided_by"] == _NAZORATCHI_ID


async def test_approve_off_request_marks_the_day_off(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_employee()
    day = _tomorrow()
    request_id = _off_request(shift_date=day)

    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_schedreq_yes:{request_id}", target_chat_id=_NAZORATCHI_ID
    )

    assert attendance_repo.get_shift_for_date(_EMPLOYEE_ID, day)["status"] == attendance_service.SHIFT_STATUS_OFF


# ------------------------------------------------------------ RAD ETISH --


async def test_reject_marks_the_request_and_leaves_the_schedule_untouched(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_employee()
    day = _tomorrow()
    request_id = _work_request(shift_date=day)

    sent = await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_schedreq_no:{request_id}", target_chat_id=_NAZORATCHI_ID
    )

    assert attendance_service.get_schedule_change_request(request_id)["status"] == (
        attendance_service.SCHEDULE_REQUEST_REJECTED
    )
    assert attendance_repo.get_shift_for_date(_EMPLOYEE_ID, day) is None
    assert attendance_repo.list_schedule_revisions(_EMPLOYEE_ID, day) == []
    assert "Kutilayotgan so'rov yo'q" in _actor_screen(sent).text


# ------------------------------------------------- ESKIRGAN / IKKI BOSISH --


async def test_double_approve_click_does_not_rewrite_the_schedule(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_employee()
    day = _tomorrow()
    request_id = _work_request(shift_date=day)

    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_schedreq_yes:{request_id}", target_chat_id=_NAZORATCHI_ID
    )
    sent = await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_schedreq_yes:{request_id}", target_chat_id=_NAZORATCHI_ID
    )

    assert any("allaqachon hal qilingan" in (getattr(m, "text", "") or "") for m in sent)
    assert len(attendance_repo.list_schedule_revisions(_EMPLOYEE_ID, day)) == 1


async def test_stale_reject_after_approve_does_not_touch_the_schedule(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_employee()
    day = _tomorrow()
    request_id = _work_request(shift_date=day)

    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_schedreq_yes:{request_id}", target_chat_id=_NAZORATCHI_ID
    )
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_schedreq_no:{request_id}", target_chat_id=_NAZORATCHI_ID
    )

    assert attendance_service.get_schedule_change_request(request_id)["status"] == (
        attendance_service.SCHEDULE_REQUEST_APPROVED
    )
    assert attendance_repo.get_shift_for_date(_EMPLOYEE_ID, day)["planned_start"] == "10:00"
    assert len(attendance_repo.list_schedule_revisions(_EMPLOYEE_ID, day)) == 1


async def test_missing_request_id_is_reported_without_crashing(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()

    sent = await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data="nzr_schedreq_yes:999999", target_chat_id=_NAZORATCHI_ID
    )

    assert any("topilmadi" in (getattr(m, "text", "") or "") for m in sent)


# --------------------------------------------------------------- RUXSAT --


async def test_unauthorized_role_cannot_approve(bot_dp):
    main, bot = bot_dp
    kassir_id = 890020
    _make_employee(kassir_id)
    _make_employee()
    day = _tomorrow()
    request_id = _work_request(shift_date=day)

    await send_callback(
        main.dp, bot, kassir_id, data=f"nzr_schedreq_yes:{request_id}", target_chat_id=kassir_id
    )

    assert attendance_service.get_schedule_change_request(request_id)["status"] == (
        attendance_service.SCHEDULE_REQUEST_PENDING
    )
    assert attendance_repo.get_shift_for_date(_EMPLOYEE_ID, day) is None


async def test_nazoratchi_cannot_approve_own_request(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    day = _tomorrow()
    request_id = _work_request(employee_id=_NAZORATCHI_ID, shift_date=day)

    listed = await send(main.dp, bot, _NAZORATCHI_ID, text="/grafiksorov")
    assert _callbacks(listed) == []

    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data=f"nzr_schedreq_yes:{request_id}", target_chat_id=_NAZORATCHI_ID
    )

    assert attendance_service.get_schedule_change_request(request_id)["status"] == (
        attendance_service.SCHEDULE_REQUEST_PENDING
    )
    assert attendance_repo.get_shift_for_date(_NAZORATCHI_ID, day) is None


async def test_founder_sees_and_decides_requests_from_any_branch(bot_dp):
    main, bot = bot_dp
    other_branch_employee = 890030
    _make_employee(other_branch_employee, branch=_BRANCH_B)
    day = _tomorrow()
    request_id = _work_request(employee_id=other_branch_employee, shift_date=day)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/grafiksorov")
    assert f"nzr_schedreq:{request_id}" in _callbacks(sent)

    await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"nzr_schedreq_yes:{request_id}", target_chat_id=FOUNDER_ID
    )

    assert attendance_repo.get_shift_for_date(other_branch_employee, day)["planned_start"] == "10:00"
