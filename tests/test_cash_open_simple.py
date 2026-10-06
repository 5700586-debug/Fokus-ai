"""Soddalashtirilgan smena ochish: oldingi qoldiq tasdiqi / summani o'zgartirish / qo'lda boshlang'ich naqd."""

import pytest
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

import company_time
from config import FOUNDER_ID
from db import get_connection
from repositories import cash_shifts as cash_shifts_repo
from roles import set_role
from services import cash_shift
from tests.bot_harness import send, send_callback
from tests.test_cash_shift_bot_flows import _clear_daily_report_gate, _clear_deficiency_gate, _make_kassir

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("manual_close_review")]

NIGHT, MORNING, MOLIYACHI = 111, 112, 222
MANUAL_PROMPT = "Smenani nech pul bilan qabul qildingiz? (kassadagi boshlang'ich naqd)"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _joined(sent) -> str:
    return "\n".join(m.text for m in sent if getattr(m, "text", None))


def _buttons(sent) -> list[str]:
    return [
        b.text
        for m in sent
        if isinstance(getattr(m, "reply_markup", None), InlineKeyboardMarkup)
        for row in m.reply_markup.inline_keyboard
        for b in row
    ]


def _home(sent) -> bool:
    return any(
        isinstance(getattr(m, "reply_markup", None), ReplyKeyboardMarkup)
        and [b.text for row in m.reply_markup.keyboard for b in row] == ["🏠 Asosiy menyu"]
        for m in sent
    )


def _shift(user_id: int, date: str | None = None):
    return cash_shifts_repo.get_open_shift(user_id, date or company_time.today().isoformat())


async def _night_closes_with(main, bot, left: str = "215000") -> None:
    """Birinchi kassir smena ochadi va moliyachiga yopadi (qoldirilgan naqd = ``left``)."""
    _make_kassir(NIGHT)
    set_role(MOLIYACHI, "moliyachi", set_by=FOUNDER_ID)
    await send(main.dp, bot, NIGHT, text="/openshift")
    await send(main.dp, bot, NIGHT, text="0")
    await send(main.dp, bot, NIGHT, text="/closeshift")
    await _clear_deficiency_gate(main, bot, NIGHT)
    await _clear_daily_report_gate(main, bot, NIGHT)
    for file_id in ("n", "p", "r"):
        await send(main.dp, bot, NIGHT, photo_file_id=file_id)
    await send(main.dp, bot, NIGHT, text=left)
    await send_callback(main.dp, bot, NIGHT, data="csui_rev_send", target_chat_id=NIGHT)


async def test_no_previous_balance_asks_manual_opening_cash_with_exact_text_and_opens(bot_dp):
    main, bot = bot_dp
    _make_kassir(NIGHT)

    sent = await send(main.dp, bot, NIGHT, text="/openshift")
    assert MANUAL_PROMPT in _joined(sent) and _home(sent)

    sent = await send(main.dp, bot, NIGHT, text="150000")
    assert "✅ Smena ochildi." in _joined(sent) and "Boshlang'ich naqd:" in _joined(sent) and _home(sent)
    shift = _shift(NIGHT)
    assert (shift["opening_balance"], shift["status"]) == (150000, cash_shift.STATUS_OPEN)


async def test_last_left_cash_is_shown_for_confirmation_and_yes_opens_with_it(bot_dp):
    main, bot = bot_dp
    await _night_closes_with(main, bot, "215000")
    _make_kassir(MORNING)

    sent = await send(main.dp, bot, MORNING, text="/openshift")

    text = _joined(sent).replace(" ", " ")
    assert "Kassada 215 000 so'm bor deb qabul qilyapsizmi?" in text
    assert _buttons(sent) == ["✅ Ha, tasdiqlayman", "✏️ Summani o'zgartirish"]

    token = [b.callback_data for m in sent if getattr(m, "reply_markup", None) for row in m.reply_markup.inline_keyboard for b in row][0]
    opened = await send_callback(main.dp, bot, MORNING, data=token, target_chat_id=MORNING)

    assert "✅ Smena ochildi." in _joined(opened) and "215" in _joined(opened)
    shift = _shift(MORNING)
    assert (shift["opening_balance"], shift["status"]) == (215000, cash_shift.STATUS_OPEN)
    assert "Kassa mos" not in _joined(opened) and "Smena topshirildi" not in _joined(opened)


async def test_change_amount_opens_with_new_opening_cash_and_informs_moliyachi(bot_dp):
    main, bot = bot_dp
    await _night_closes_with(main, bot, "215000")
    _make_kassir(MORNING)

    sent = await send(main.dp, bot, MORNING, text="/openshift")
    diff_token = [
        b.callback_data for m in sent if getattr(m, "reply_markup", None) for row in m.reply_markup.inline_keyboard for b in row
    ][1]
    asked = await send_callback(main.dp, bot, MORNING, data=diff_token, target_chat_id=MORNING)
    assert MANUAL_PROMPT in _joined(asked) and _home(asked)

    opened = await send(main.dp, bot, MORNING, text="200000")

    assert "✅ Smena ochildi." in _joined(opened)
    shift = _shift(MORNING)
    assert (shift["opening_balance"], shift["received_cash_balance"]) == (200000, 200000)
    informed = [m for m in opened if isinstance(m, SendMessage) and m.chat_id == MOLIYACHI]
    assert informed and "Oldingi qoldiq" in informed[0].text and "Kassir yozgan" in informed[0].text
    compact = informed[0].text.replace(" ", "").replace(" ", "")
    assert "215000" in compact and "200000" in compact
    assert "csui_disc" not in str(informed[0].reply_markup)  # eski tafovut/sabab oqimi yo'q


async def test_previous_shift_without_known_balance_falls_back_to_manual_entry(bot_dp):
    main, bot = bot_dp
    await _night_closes_with(main, bot, "215000")
    conn = get_connection()
    try:
        conn.execute("UPDATE cash_shifts SET actual_cash_balance = NULL WHERE employee_id = ?", (NIGHT,))
        conn.commit()
    finally:
        conn.close()
    _make_kassir(MORNING)

    sent = await send(main.dp, bot, MORNING, text="/openshift")
    assert MANUAL_PROMPT in _joined(sent)

    await send(main.dp, bot, MORNING, text="90000")
    assert _shift(MORNING)["opening_balance"] == 90000


async def test_shift_sent_to_moliyachi_does_not_block_opening_a_new_one_next_day(bot_dp):
    main, bot = bot_dp
    await _night_closes_with(main, bot, "215000")
    conn = get_connection()
    try:
        conn.execute("UPDATE cash_shifts SET shift_date = '2000-01-01' WHERE employee_id = ?", (NIGHT,))
        conn.commit()
    finally:
        conn.close()

    sent = await send(main.dp, bot, NIGHT, text="/openshift")  # shu kassirning o'zi keyingi kuni

    assert "bor deb qabul qilyapsizmi?" in _joined(sent)
    assert "allaqachon" not in _joined(sent) and "Avval ochiq smenangizni" not in _joined(sent)


async def test_really_open_shift_still_blocks_a_second_open(bot_dp):
    main, bot = bot_dp
    _make_kassir(NIGHT)
    await send(main.dp, bot, NIGHT, text="/openshift")
    await send(main.dp, bot, NIGHT, text="0")

    same_day = await send(main.dp, bot, NIGHT, text="/openshift")
    assert "Bugungi smena allaqachon ochilgan" in _joined(same_day)

    conn = get_connection()
    try:
        conn.execute("UPDATE cash_shifts SET shift_date = '2000-01-01' WHERE employee_id = ?", (NIGHT,))
        conn.commit()
    finally:
        conn.close()
    older = await send(main.dp, bot, NIGHT, text="/openshift")
    assert "Avval ochiq smenangizni topshiring" in _joined(older)


async def test_closed_today_shift_is_reported_as_closed_not_open(bot_dp):
    main, bot = bot_dp
    await _night_closes_with(main, bot, "215000")

    sent = await send(main.dp, bot, NIGHT, text="/openshift")

    assert "Bugungi smena allaqachon yopilgan" in _joined(sent)


async def test_approval_after_next_shift_opened_still_finalizes_previous_shift(bot_dp):
    main, bot = bot_dp
    await _night_closes_with(main, bot, "215000")
    night_shift_id = _shift(NIGHT)["id"]
    _make_kassir(MORNING)
    sent = await send(main.dp, bot, MORNING, text="/openshift")
    token = [b.callback_data for m in sent if getattr(m, "reply_markup", None) for row in m.reply_markup.inline_keyboard for b in row][0]
    await send_callback(main.dp, bot, MORNING, data=token, target_chat_id=MORNING)

    await send_callback(main.dp, bot, MOLIYACHI, data=f"cashclose_ok:{night_shift_id}", target_chat_id=MOLIYACHI)

    assert cash_shifts_repo.get_shift(night_shift_id)["status"] == cash_shift.STATUS_CLEAN_CLOSED
    assert _shift(MORNING)["status"] == cash_shift.STATUS_OPEN
