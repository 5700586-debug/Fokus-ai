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


# ------------------------------------------- "🏠 Asosiy menyu" grafik so'rovi bosqichlarida --

HOME = "🏠 Asosiy menyu"


def _keyboards(sent) -> list[list[str]]:
    return [
        [b.text for row in m.reply_markup.keyboard for b in row]
        for m in sent
        if getattr(m, "reply_markup", None) is not None and hasattr(m.reply_markup, "keyboard")
    ]


async def _fsm_state(main, bot, user_id: int):
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey

    context = FSMContext(storage=main.dp.storage, key=StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id))
    return await context.get_state()


async def test_home_button_stays_on_every_schedule_request_step_and_error(bot_dp):
    main, bot = bot_dp
    _make_employee()
    day = _tomorrow().strftime("%d.%m.%Y")

    steps = [
        await send(main.dp, bot, EMPLOYEE_ID, text="/grafik"),                   # sana so'rovi
        await send(main.dp, bot, EMPLOYEE_ID, text="noto'g'ri sana"),            # sana xatosi
        await send(main.dp, bot, EMPLOYEE_ID, text=day),                         # ish/dam tanlash
        await send(main.dp, bot, EMPLOYEE_ID, text="nimadir"),                   # tanlash xatosi
        await send(main.dp, bot, EMPLOYEE_ID, text="🕒 Ish vaqti"),               # boshlanish vaqti
        await send(main.dp, bot, EMPLOYEE_ID, text="99:99"),                     # vaqt xatosi
        await send(main.dp, bot, EMPLOYEE_ID, text="09:00"),                     # tugash vaqti
        await send(main.dp, bot, EMPLOYEE_ID, text="09:00"),                     # tugash xatosi (bir xil)
        await send(main.dp, bot, EMPLOYEE_ID, text="18:00"),                     # sabab
    ]

    for index, sent in enumerate(steps):
        assert any(HOME in keyboard for keyboard in _keyboards(sent)), f"{index}-bosqichda Asosiy menyu tugmasi yo'q"
    assert _requests() == []


@pytest.mark.parametrize("stage", ["date", "type", "start", "end", "reason"])
async def test_home_clears_schedule_request_without_sending_it(bot_dp, stage):
    main, bot = bot_dp
    _make_employee()
    day = _tomorrow().strftime("%d.%m.%Y")

    await send(main.dp, bot, EMPLOYEE_ID, text="/grafik")
    if stage != "date":
        await send(main.dp, bot, EMPLOYEE_ID, text=day)
    if stage in ("start", "end", "reason"):
        await send(main.dp, bot, EMPLOYEE_ID, text="🕒 Ish vaqti")
    if stage in ("end", "reason"):
        await send(main.dp, bot, EMPLOYEE_ID, text="09:00")
    if stage == "reason":
        await send(main.dp, bot, EMPLOYEE_ID, text="18:00")

    sent = await send(main.dp, bot, EMPLOYEE_ID, text=HOME)

    assert await _fsm_state(main, bot, EMPLOYEE_ID) is None
    assert _requests() == []  # so'rov yuborilmagan
    menus = _keyboards(sent)
    assert any("💰 Kassa" in keyboard for keyboard in menus) and [HOME] not in menus  # asosiy menyu

    # Keyingi matn eski bosqichning javobi sifatida yutilmaydi.
    after = await send(main.dp, bot, EMPLOYEE_ID, text="Oilaviy ish bor")
    assert _requests() == [] and "qabul qilindi" not in "".join(texts(after))


async def test_off_request_flow_and_schedule_are_unchanged_with_home_keyboard(bot_dp):
    main, bot = bot_dp
    _make_employee()
    day = _tomorrow()

    await send(main.dp, bot, EMPLOYEE_ID, text="/grafik")
    await send(main.dp, bot, EMPLOYEE_ID, text=day.strftime("%d.%m.%Y"))
    type_step = await send(main.dp, bot, EMPLOYEE_ID, text="🛌 Dam olish")
    assert any(HOME in keyboard for keyboard in _keyboards(type_step))  # sabab bosqichi
    sent = await send(main.dp, bot, EMPLOYEE_ID, text="Oilaviy ish bor")

    assert "qabul qilindi" in (sent[0].text or "")
    assert len(_requests()) == 1
    assert attendance_repo.get_shift_for_date(EMPLOYEE_ID, day.isoformat()) is None
