"""Kassir oqimlarida "🏠 Asosiy menyu" tugmasi, kuzatilgan vaqtinchalik xabarlarni tozalash va rad javobi."""

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import DeleteMessage, SendMessage
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

import company_time
from config import FOUNDER_ID
from db import get_connection
from repositories import cash_shifts as cash_shifts_repo
from services import cash_shift
from tests.bot_harness import send, send_callback
from tests.test_cash_close_manual_review import (
    KASSIR, MOLIYACHI, _joined, _shift, _submit_to_moliyachi, _texts, _to_photo_prompt,
)
from tests.test_cash_shift_bot_flows import _make_kassir

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("manual_close_review")]

HOME = "🏠 Asosiy menyu"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _reply_keyboards(sent) -> list[list[str]]:
    return [
        [b.text for row in m.reply_markup.keyboard for b in row]
        for m in sent
        if isinstance(m, SendMessage) and isinstance(m.reply_markup, ReplyKeyboardMarkup)
    ]


async def _fsm_state(main, bot, user_id: int):
    context = FSMContext(storage=main.dp.storage, key=StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id))
    return await context.get_state()


def _tracked_count(workflow: str) -> int:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM bot_workflow_messages WHERE workflow = ?", (workflow,)
        ).fetchone()["n"]
    finally:
        conn.close()


# ------------------------------------------------------------ navigatsiya --


async def test_home_button_stays_while_cashier_enters_photos_and_amounts(bot_dp):
    main, bot = bot_dp
    prompt = await _to_photo_prompt(main, bot)
    assert [HOME] in _reply_keyboards(prompt)  # daftar rasmi kutilmoqda

    assert [HOME] in _reply_keyboards(await send(main.dp, bot, KASSIR, photo_file_id="n"))  # POS rasmi kutilmoqda
    assert [HOME] in _reply_keyboards(await send(main.dp, bot, KASSIR, photo_file_id="p"))  # cheklar kutilmoqda


async def test_home_button_stays_during_opening_balance_entry(bot_dp):
    main, bot = bot_dp
    _make_kassir(KASSIR)

    sent = await send(main.dp, bot, KASSIR, text="/openshift")  # birinchi smena: summa kutilmoqda

    assert [HOME] in _reply_keyboards(sent)


@pytest.mark.parametrize("stage", ["photo", "amount"])
async def test_home_clears_unfinished_input_and_shows_main_menu(bot_dp, stage):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await send(main.dp, bot, KASSIR, photo_file_id="n")
    if stage == "amount":
        await send(main.dp, bot, KASSIR, photo_file_id="p")
        await send(main.dp, bot, KASSIR, photo_file_id="r")

    sent = await send(main.dp, bot, KASSIR, text=HOME)

    assert await _fsm_state(main, bot, KASSIR) is None
    menus = _reply_keyboards(sent)
    assert any("💰 Kassa" in keyboard for keyboard in menus)  # asosiy menyu
    assert [HOME] not in menus
    assert any(isinstance(m, DeleteMessage) for m in sent)  # yuborilmagan oqimning vaqtinchalik xabarlari
    shift = _shift()
    assert shift["status"] == cash_shift.STATUS_OPEN  # smena o'zgarmagan
    # Keyin /closeshift yangidan boshlanadi, eski rasm kelmaydi.
    again = await send(main.dp, bot, KASSIR, text="/closeshift")
    assert "📒 Daftar rasmini yuboring" in _joined(again)


async def test_home_after_sending_does_not_cancel_the_review_or_delete_its_messages(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)
    shift_id = _shift()["id"]
    tracked_before = _tracked_count("cash_close_review")

    sent = await send(main.dp, bot, KASSIR, text=HOME)

    assert not any(isinstance(m, DeleteMessage) for m in sent)
    assert _tracked_count("cash_close_review") == tracked_before
    assert _shift()["status"] == cash_shift.STATUS_NEEDS_FINANCE_REVIEW
    await send_callback(main.dp, bot, MOLIYACHI, data=f"cashclose_ok:{shift_id}", target_chat_id=MOLIYACHI)
    assert _shift()["status"] == cash_shift.STATUS_CLEAN_CLOSED


# ------------------------------------------------------------ tozalash --


async def test_cashier_photos_amounts_and_interim_messages_are_tracked_then_cleaned_on_decision(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)
    shift_id = _shift()["id"]
    # kassir: 3 rasm + 1 summa; moliyachi: 3 rasm. "Smena yopildi" xabari kuzatilmaydi (qoladi).
    assert _tracked_count("cash_close_review") == 7

    sent = await send_callback(main.dp, bot, MOLIYACHI, data=f"cashclose_ok:{shift_id}", target_chat_id=MOLIYACHI)

    assert _tracked_count("cash_close_review") == 0
    assert _tracked_count("cash_shift_close") == 0
    deleted_chats = [m.chat_id for m in sent if isinstance(m, DeleteMessage)]
    assert deleted_chats.count(KASSIR) == 4 and deleted_chats.count(MOLIYACHI) == 3
    final = [m for m in sent if isinstance(m, SendMessage) and m.chat_id == KASSIR]
    assert final and "Moliyachi smenangizni tasdiqladi" in final[-1].text  # yakuniy javob qoladi (kuzatilmaydi)
    assert _tracked_count("cash_close_review") == 0


async def test_rejection_also_cleans_temporary_messages(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)
    shift_id = _shift()["id"]

    sent = await send_callback(main.dp, bot, MOLIYACHI, data=f"cashclose_no:{shift_id}", target_chat_id=MOLIYACHI)

    assert len([m for m in sent if isinstance(m, DeleteMessage)]) == 7
    assert _tracked_count("cash_close_review") == 0


async def test_failed_deletion_does_not_stop_the_main_flow(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)
    shift_id = _shift()["id"]

    async def _fail(*args, **kwargs):
        raise RuntimeError("Telegram o'chirishga ruxsat bermadi")

    bot.delete_message = _fail
    sent = await send_callback(main.dp, bot, MOLIYACHI, data=f"cashclose_ok:{shift_id}", target_chat_id=MOLIYACHI)

    assert _shift()["status"] == cash_shift.STATUS_CLEAN_CLOSED
    assert any(isinstance(m, SendMessage) and m.chat_id == KASSIR and "Moliyachi smenangizni tasdiqladi" in m.text for m in sent)


# -------------------------------------------------------------------- rad --


async def test_rejection_message_is_clear_and_has_resubmit_button_that_restarts(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)
    shift_id = _shift()["id"]

    sent = await send_callback(main.dp, bot, MOLIYACHI, data=f"cashclose_no:{shift_id}", target_chat_id=MOLIYACHI)

    notice = [m for m in sent if isinstance(m, SendMessage) and m.chat_id == KASSIR][-1]
    assert notice.text == "❌ Moliyachi qayta tekshirishga qaytardi. Rasmlar va summani qayta yuboring."
    assert isinstance(notice.reply_markup, InlineKeyboardMarkup)
    button = notice.reply_markup.inline_keyboard[0][0]
    assert button.text == "🔄 Qayta yuborish" and button.callback_data == f"csui_rev_resubmit:{shift_id}"

    restarted = await send_callback(main.dp, bot, KASSIR, data=button.callback_data, target_chat_id=KASSIR)
    assert "📒 Daftar rasmini yuboring" in _joined(restarted)
    assert [HOME] in _reply_keyboards(restarted)

    # Tugma ikkinchi marta/boshqa odam bosganda hech narsa buzilmaydi.
    await send(main.dp, bot, KASSIR, photo_file_id="n2")
    await send(main.dp, bot, KASSIR, photo_file_id="p2")
    await send(main.dp, bot, KASSIR, photo_file_id="r2")
    await send(main.dp, bot, KASSIR, text="2")
    await send_callback(main.dp, bot, KASSIR, data="csui_rev_send", target_chat_id=KASSIR)
    assert _shift()["status"] == cash_shift.STATUS_NEEDS_FINANCE_REVIEW
    await send_callback(main.dp, bot, KASSIR, data=button.callback_data, target_chat_id=KASSIR)  # eskirgan tugma
    assert await _fsm_state(main, bot, KASSIR) is None
    assert _shift()["status"] == cash_shift.STATUS_NEEDS_FINANCE_REVIEW


async def test_approval_message_has_home_keyboard_and_no_resubmit_button(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)

    sent = await send_callback(
        main.dp, bot, MOLIYACHI, data=f"cashclose_ok:{_shift()['id']}", target_chat_id=MOLIYACHI
    )

    notice = [m for m in sent if isinstance(m, SendMessage) and m.chat_id == KASSIR][-1]
    assert isinstance(notice.reply_markup, ReplyKeyboardMarkup)  # inline "Qayta yuborish" yo'q, Home qoladi
    assert [b.text for row in notice.reply_markup.keyboard for b in row] == [HOME]


async def test_resubmit_button_pressed_by_someone_else_is_refused(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)
    shift_id = _shift()["id"]
    await send_callback(main.dp, bot, MOLIYACHI, data=f"cashclose_no:{shift_id}", target_chat_id=MOLIYACHI)
    _make_kassir(112)

    await send_callback(main.dp, bot, 112, data=f"csui_rev_resubmit:{shift_id}", target_chat_id=112)

    assert await _fsm_state(main, bot, 112) is None
    assert cash_shifts_repo.get_shift(shift_id)["status"] == cash_shift.STATUS_RECHECK_REQUIRED
