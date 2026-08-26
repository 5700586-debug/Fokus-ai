"""Nazoratchi davomat/kechikish ko'rib chiqish oqimi (``nazoratchi_bot.py``):
qo'lda kelish vaqti kiritish -> 4 ta sabab tugmasi -> "Rahbar ruxsat
bergan" uchun Founderga Ha/Yo'q so'rovi. Hech qanday avtomatik minus
ball QO'LLANMAYDI — bu fayl faqat tugma/oqim ishlashini tekshiradi."""

from datetime import timedelta

import pytest

import company_time
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

_BRANCH = RECRUITING_BRANCH_NAMES[0]
_NAZORATCHI_ID = 830001


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_nazoratchi(user_id: int = _NAZORATCHI_ID) -> None:
    from roles import set_role

    set_role(user_id, "nazoratchi", set_by=FOUNDER_ID)


def _make_kassir(user_id: int, branch: str = _BRANCH) -> None:
    from roles import set_role
    import employees

    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {
            "familiya": "Valiyev", "ism": "Ali", "otasining_ismi": "Vali",
            "branch": branch, "role_key": "kassir", "contacts": [],
        },
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


async def test_attendance_button_appears_on_employee_card(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(830010)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_emp:830010", target_chat_id=_NAZORATCHI_ID)

    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert "nzr_att:830010" in buttons


async def test_opening_attendance_with_no_arrival_asks_for_time(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(830011)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_att:830011", target_chat_id=_NAZORATCHI_ID)

    assert "HH:MM" in sent[0].text


async def test_entering_arrival_time_then_shows_reason_buttons(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(830012)

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_att:830012", target_chat_id=_NAZORATCHI_ID)
    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="07:58")

    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert "nzr_attreason:830012:unjustified" in buttons
    assert "nzr_attreason:830012:manager" in buttons
    assert "nzr_attreason:830012:force" in buttons
    assert "nzr_attreason:830012:other" in buttons


async def test_invalid_arrival_time_format_is_rejected(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(830013)

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_att:830013", target_chat_id=_NAZORATCHI_ID)
    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="notatime")

    assert "HH:MM" in sent[0].text


async def test_unjustified_reason_updates_card(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(830014)

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_att:830014", target_chat_id=_NAZORATCHI_ID)
    await send(main.dp, bot, _NAZORATCHI_ID, text="09:00")
    sent = await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data="nzr_attreason:830014:unjustified", target_chat_id=_NAZORATCHI_ID
    )

    assert "Sababsiz" in sent[0].text


async def test_manager_permission_sends_founder_a_request_with_ha_yoq_buttons(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(830015)

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_att:830015", target_chat_id=_NAZORATCHI_ID)
    await send(main.dp, bot, _NAZORATCHI_ID, text="10:30")
    sent = await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data="nzr_attreason:830015:manager", target_chat_id=_NAZORATCHI_ID
    )

    founder_message = next(m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID)
    buttons = [btn.callback_data for row in founder_message.reply_markup.inline_keyboard for btn in row]
    assert "nzr_attmgr:830015:yes" in buttons
    assert "nzr_attmgr:830015:no" in buttons


async def test_founder_approving_manager_permission_updates_status(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(830016)

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_att:830016", target_chat_id=_NAZORATCHI_ID)
    await send(main.dp, bot, _NAZORATCHI_ID, text="11:15")
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data="nzr_attreason:830016:manager", target_chat_id=_NAZORATCHI_ID
    )

    sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data="nzr_attmgr:830016:yes", target_chat_id=FOUNDER_ID
    )

    assert "tasdiqlandi" in sent[0].text.lower()

    from services import attendance as attendance_service

    summary = attendance_service.get_yesterday_summary(830016)
    assert summary["reason_status"] == attendance_service.REASON_MANAGER_PERMISSION_APPROVED


async def test_non_founder_cannot_decide_manager_permission(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(830017)

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_att:830017", target_chat_id=_NAZORATCHI_ID)
    await send(main.dp, bot, _NAZORATCHI_ID, text="12:00")
    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data="nzr_attreason:830017:manager", target_chat_id=_NAZORATCHI_ID
    )

    await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data="nzr_attmgr:830017:yes", target_chat_id=_NAZORATCHI_ID
    )

    from services import attendance as attendance_service

    summary = attendance_service.get_yesterday_summary(830017)
    assert summary["reason_status"] == attendance_service.REASON_MANAGER_PERMISSION_PENDING
