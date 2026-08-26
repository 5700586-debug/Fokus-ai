"""Xodimning Telegram oqimi: `/grafik` -> bitta sanaga grafik
o'zgartirish so'rovi (`services/attendance.create_schedule_change_request`).
Tasdiqlash UI bu bosqichda YO'Q — shuning uchun asosiy tekshiruv nuqtasi:
so'rov `pending` bo'lib yoziladi, schedule'ning O'ZI o'zgarmaydi.
"""

from datetime import timedelta

import pytest

import company_time
import employees
from config import FOUNDER_ID
from repositories import attendance as attendance_repo
from roles import set_role
from services import attendance as attendance_service
from tests.bot_harness import send, texts

pytestmark = pytest.mark.anyio

EMPLOYEE_ID = 830001


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_employee(user_id: int = EMPLOYEE_ID) -> None:
    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {
            "familiya": "Test", "ism": "Xodim", "branch": "Filial-1", "role_key": "kassir",
            "hire_date": None, "contacts": [],
        },
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


def _tomorrow():
    return company_time.today() + timedelta(days=1)


def _requests(user_id: int = EMPLOYEE_ID) -> list[dict]:
    return attendance_service.list_schedule_change_requests(employee_id=user_id)


async def test_off_request_is_created_and_schedule_is_untouched(bot_dp):
    main, bot = bot_dp
    _make_employee()
    day = _tomorrow()

    await send(main.dp, bot, EMPLOYEE_ID, text="/grafik")
    await send(main.dp, bot, EMPLOYEE_ID, text=day.strftime("%d.%m.%Y"))
    await send(main.dp, bot, EMPLOYEE_ID, text="🛌 Dam olish")
    sent = await send(main.dp, bot, EMPLOYEE_ID, text="Oilaviy ish bor")

    assert "qabul qilindi" in (sent[0].text or "")

    requests = _requests()
    assert len(requests) == 1
    assert requests[0]["requested_status"] == attendance_service.SHIFT_STATUS_OFF
    assert requests[0]["shift_date"] == day.isoformat()
    assert requests[0]["status"] == attendance_service.SCHEDULE_REQUEST_PENDING
    assert requests[0]["reason"] == "Oilaviy ish bor"

    assert attendance_repo.get_shift_for_date(EMPLOYEE_ID, day.isoformat()) is None


async def test_work_request_is_created_with_requested_times(bot_dp):
    main, bot = bot_dp
    _make_employee()
    day = _tomorrow()

    await send(main.dp, bot, EMPLOYEE_ID, text="/grafik")
    await send(main.dp, bot, EMPLOYEE_ID, text=day.strftime("%d.%m.%Y"))
    await send(main.dp, bot, EMPLOYEE_ID, text="🕒 Ish vaqti")
    await send(main.dp, bot, EMPLOYEE_ID, text="10:00")
    await send(main.dp, bot, EMPLOYEE_ID, text="19:00")
    sent = await send(main.dp, bot, EMPLOYEE_ID, text="➖ O'tkazib yuborish")

    assert "qabul qilindi" in (sent[0].text or "")

    requests = _requests()
    assert len(requests) == 1
    assert requests[0]["requested_status"] == attendance_service.SHIFT_STATUS_WORK
    assert requests[0]["requested_start"] == "10:00"
    assert requests[0]["requested_end"] == "19:00"
    assert requests[0]["reason"] is None

    assert attendance_repo.get_shift_for_date(EMPLOYEE_ID, day.isoformat()) is None


async def test_invalid_time_is_re_asked_and_creates_nothing(bot_dp):
    main, bot = bot_dp
    _make_employee()
    day = _tomorrow()

    await send(main.dp, bot, EMPLOYEE_ID, text="/grafik")
    await send(main.dp, bot, EMPLOYEE_ID, text=day.strftime("%d.%m.%Y"))
    await send(main.dp, bot, EMPLOYEE_ID, text="🕒 Ish vaqti")
    sent = await send(main.dp, bot, EMPLOYEE_ID, text="25:00")

    assert "SS:DD" in (sent[0].text or "")
    assert _requests() == []

    # Bir xil boshlanish/tugash ham qabul qilinmaydi.
    await send(main.dp, bot, EMPLOYEE_ID, text="10:00")
    sent = await send(main.dp, bot, EMPLOYEE_ID, text="10:00")
    assert "bir xil" in (sent[0].text or "")
    assert _requests() == []

    # Oqim uzilmagan — to'g'ri vaqt kiritilsa davom etadi.
    await send(main.dp, bot, EMPLOYEE_ID, text="18:00")
    sent = await send(main.dp, bot, EMPLOYEE_ID, text="➖ O'tkazib yuborish")
    assert "qabul qilindi" in (sent[0].text or "")
    assert len(_requests()) == 1


async def test_invalid_date_is_re_asked_and_creates_nothing(bot_dp):
    main, bot = bot_dp
    _make_employee()

    await send(main.dp, bot, EMPLOYEE_ID, text="/grafik")
    sent = await send(main.dp, bot, EMPLOYEE_ID, text="45.13.2026")

    assert "KK.OO.YYYY" in (sent[0].text or "")
    assert _requests() == []


async def test_unknown_change_type_is_re_asked(bot_dp):
    main, bot = bot_dp
    _make_employee()

    await send(main.dp, bot, EMPLOYEE_ID, text="/grafik")
    await send(main.dp, bot, EMPLOYEE_ID, text=_tomorrow().strftime("%d.%m.%Y"))
    sent = await send(main.dp, bot, EMPLOYEE_ID, text="boshqa narsa")

    assert "tugmalardan birini tanlang" in (sent[0].text or "")
    assert _requests() == []


async def test_user_without_employee_profile_is_rejected_without_starting_the_flow(bot_dp):
    main, bot = bot_dp
    set_role(EMPLOYEE_ID, "kassir", set_by=FOUNDER_ID)  # profil ATAYLAB yaratilmagan

    sent = await send(main.dp, bot, EMPLOYEE_ID, text="/grafik")
    assert "tasdiqlangan xodim emassiz" in (sent[0].text or "")

    # Holat ochilmagani uchun keyingi matn oqimga tushmaydi.
    sent = await send(main.dp, bot, EMPLOYEE_ID, text=_tomorrow().strftime("%d.%m.%Y"))
    assert not any("Shu kunga nima so'raysiz" in (t or "") for t in texts(sent))
    assert _requests() == []


async def test_offboarded_employee_cannot_open_the_flow(bot_dp):
    main, bot = bot_dp
    _make_employee()
    employees.offboard_profile(EMPLOYEE_ID)

    sent = await send(main.dp, bot, EMPLOYEE_ID, text="/grafik")

    assert "tasdiqlangan xodim emassiz" in (sent[0].text or "")
    assert _requests() == []


async def test_cancel_button_clears_the_flow_state(bot_dp):
    main, bot = bot_dp
    _make_employee()

    await send(main.dp, bot, EMPLOYEE_ID, text="/grafik")
    sent = await send(main.dp, bot, EMPLOYEE_ID, text="❌ Bekor qilish")
    assert "bekor qilindi" in (sent[0].text or "").lower()

    # Holat tozalangani uchun sana matni endi hech qanday oqimga tegishli emas.
    sent = await send(main.dp, bot, EMPLOYEE_ID, text=_tomorrow().strftime("%d.%m.%Y"))
    assert not any("Shu kunga nima so'raysiz" in (t or "") for t in texts(sent))
    assert _requests() == []


async def test_flow_state_is_not_shared_between_two_employees(bot_dp):
    main, bot = bot_dp
    other_id = EMPLOYEE_ID + 1
    _make_employee()
    _make_employee(other_id)
    day = _tomorrow()

    await send(main.dp, bot, EMPLOYEE_ID, text="/grafik")
    await send(main.dp, bot, EMPLOYEE_ID, text=day.strftime("%d.%m.%Y"))

    # Ikkinchi xodim o'z oqimini boshlaydi — birinchisining sanasi unga o'tmaydi.
    await send(main.dp, bot, other_id, text="/grafik")
    await send(main.dp, bot, other_id, text=(day + timedelta(days=1)).strftime("%d.%m.%Y"))
    await send(main.dp, bot, other_id, text="🛌 Dam olish")
    await send(main.dp, bot, other_id, text="➖ O'tkazib yuborish")

    await send(main.dp, bot, EMPLOYEE_ID, text="🛌 Dam olish")
    await send(main.dp, bot, EMPLOYEE_ID, text="➖ O'tkazib yuborish")

    assert [r["shift_date"] for r in _requests(EMPLOYEE_ID)] == [day.isoformat()]
    assert [r["shift_date"] for r in _requests(other_id)] == [(day + timedelta(days=1)).isoformat()]


async def test_shared_menu_exposes_the_schedule_change_command(bot_dp):
    main, bot = bot_dp
    _make_employee()

    sent = await send(main.dp, bot, EMPLOYEE_ID, text="⭐ Mening natijalarim")
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]

    assert "/grafik" in buttons
    assert "Grafikni o'zgartirish" in (sent[0].text or "")
