import pytest

import company_time
from config import FOUNDER_ID
from services import messages as messages_catalog
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

_DENIAL_TEXTS = {
    messages_catalog.GENERIC_DENIAL,
    messages_catalog.CASH_FINANCE_DENIAL,
    messages_catalog.MANAGEMENT_DENIAL,
    messages_catalog.REPEAT_OFFENDER_DENIAL,
}


def _assert_denied(sent) -> None:
    assert len(sent) == 1, sent
    assert sent[0].text in _DENIAL_TEXTS, sent[0].text


@pytest.fixture
def anyio_backend():
    return "asyncio"




@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("50000", 50000),
        ("50 000", 50000),
        ("50.000", 50000),
        ("50,000", 50000),
        ("2 067 000", 2067000),
        ("2067000 naqd pul", 2067000),
        ("2067000 naqt pul", 2067000),
        ("50.00", None),
        ("1.5", None),
        ("naqd 50000", None),
    ],
)
def test_parse_amount_accepts_cashier_human_formats(text, expected):
    import cash_shift_bot

    assert cash_shift_bot._parse_amount(text) == expected

def _make_kassir(user_id: int, branch: str = "Filial-1") -> None:
    from roles import set_role
    import employees

    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {
            "familiya": "Kassirov", "ism": "Ali", "otasining_ismi": "Vali",
            "branch": branch, "role_key": "kassir", "contacts": [],
        },
    )


async def _open_shift(main, bot, user_id: int, opening_balance: str = "0") -> None:
    await send(main.dp, bot, user_id, text="/openshift")
    await send(main.dp, bot, user_id, text=opening_balance)


async def _confirm_close_amount(main, bot, user_id: int, amount: str):
    """"Smenani topshirasizmi?" darvozasidan boshlab: "Ha, topshiraman"
    bosiladi, summa yoziladi, "To'g'ri" bosiladi — natijadagi matnli
    xabarlar (EditMessageReplyMarkup/AnswerCallbackQuery'siz) qaytadi."""
    await send_callback(main.dp, bot, user_id, data="csui_close_start_yes", target_chat_id=user_id)
    await send(main.dp, bot, user_id, text=amount)
    sent = await send_callback(main.dp, bot, user_id, data="csui_close_amount_ok", target_chat_id=user_id)
    return [m for m in sent if getattr(m, "text", None)]


async def _prev_data(main, bot, user_id: int) -> dict:
    ctx = main.dp.fsm.get_context(bot=bot, chat_id=user_id, user_id=user_id)
    return await ctx.get_data()


async def _click_prev(main, bot, user_id: int, action: str, token: str | None = None):
    """``action`` — "ok"/"diff"; token berilmasa joriy FSM tokeni ishlatiladi."""
    if token is None:
        token = (await _prev_data(main, bot, user_id)).get("prev_token", "none")
    return await send_callback(
        main.dp, bot, user_id, data=f"csui_open_prev_{action}:{token}", target_chat_id=user_id
    )


async def _confirm_received_amount(main, bot, user_id: int, amount: str):
    """Oldingi qoldiq tasdiqlash ekranida "Farq bor" bosiladi (boshqa
    holatda bu bosish e'tiborsiz), summa yoziladi, "To'g'ri" bosiladi —
    natijadagi matnli xabarlar qaytadi."""
    await _click_prev(main, bot, user_id, "diff")
    await send(main.dp, bot, user_id, text=amount)
    sent = await send_callback(main.dp, bot, user_id, data="csui_recv_amount_ok", target_chat_id=user_id)
    return [m for m in sent if getattr(m, "text", None)]


async def _clear_deficiency_gate(main, bot, user_id: int) -> None:
    """Yangi kamchilik hisoboti gate'i (bozor/firma/kechagi kelmaganlar
    — qarang ``cash_shift_bot.py``dagi ``DeficiencyStates``) endi
    ``/closeshift``dan OLDIN turadi. Bu test fayli gate mavjud
    bo'lishidan oldin yozilgan, shuning uchun bu yerda faqat 3
    qadamning bozor/firma qismini "bo'sh" deb tezda o'tkazib yuboradi
    (kechagi ro'yxati bo'sh bo'lgani uchun avtomatik o'tadi) — testning
    o'zi sinayotgan smena-yopish oqimiga tegilmaydi.
    """
    await send_callback(main.dp, bot, user_id, data="csdef_none", target_chat_id=user_id)  # bozor yo'q
    await send_callback(main.dp, bot, user_id, data="csdef_none", target_chat_id=user_id)  # firma yo'q


async def _clear_daily_report_gate(main, bot, user_id: int) -> None:
    """Yangi kunlik 3-savol hisoboti gate'i (prixodsiz tovar/narx
    shikoyati/xodim shikoyati — qarang ``cash_shift_bot.py``dagi
    ``DailyReportStates``/``shift_daily_report``) — mavjud kamchilik
    gate'idan keyin, real yopish jarayonidan oldin turadi. Bu yerda 3
    savolni ham "yo'q/eng kam" javob bilan tezda o'tkazib yuboradi —
    testning o'zi sinayotgan smena-yopish oqimiga tegilmaydi.
    """
    await send_callback(main.dp, bot, user_id, data="csdr_prixod:0", target_chat_id=user_id)
    await send_callback(main.dp, bot, user_id, data="csdr_price:0", target_chat_id=user_id)
    await send_callback(main.dp, bot, user_id, data="csdr_staff_no", target_chat_id=user_id)



async def test_close_shift_restart_starts_manual_amounts_from_cash_sales(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)
    await _clear_daily_report_gate(main, bot, 111)
    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")

    await send(main.dp, bot, 111, text="1000")  # xato naqd savdo
    await send(main.dp, bot, 111, text="500")   # xato karta savdo

    sent = await send_callback(main.dp, bot, 111, data="csui_close_restart", target_chat_id=111)
    assert any("Boshidan boshladik" in t for t in texts(sent) if t)

    await send(main.dp, bot, 111, text="2000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    await send_callback(main.dp, bot, 111, data="csui_close_start_yes", target_chat_id=111)
    await send(main.dp, bot, 111, text="2000")
    sent = await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)
    combined = "\n".join(t for t in texts(sent) if t)

    assert "Naqd: 2000" in combined
    assert "Karta: 0" in combined
    assert "Farq: 0" in combined
    assert "Naqd: 1000" not in combined and "Karta: 500" not in combined


async def _close_shift_happy_path(
    main, bot, user_id: int, cash_sales="100000", card_sales="0", other="0", actual="100000"
):
    await send(main.dp, bot, user_id, text="/closeshift")
    await _clear_deficiency_gate(main, bot, user_id)
    await _clear_daily_report_gate(main, bot, user_id)
    await send(main.dp, bot, user_id, photo_file_id="sales_photo")
    await send(main.dp, bot, user_id, photo_file_id="cash_photo")
    await send(main.dp, bot, user_id, text=cash_sales)
    await send(main.dp, bot, user_id, text=card_sales)
    await send(main.dp, bot, user_id, text=other)
    return await _confirm_close_amount(main, bot, user_id, actual)


async def test_openshift_requires_kassir_role(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, 111, text="/openshift")
    _assert_denied(sent)


async def test_expense_before_shift_open_shows_friendly_message_not_command(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)

    sent = await send(main.dp, bot, 111, text="/expense")

    assert "/openshift" not in sent[0].text
    assert "🟢 Smenani boshlash" in sent[0].text


async def test_closeshift_before_shift_open_shows_friendly_message_not_command(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)

    sent = await send(main.dp, bot, 111, text="/closeshift")

    assert "/openshift" not in sent[0].text
    assert "🟢 Smenani boshlash" in sent[0].text


async def test_first_shift_prompt_has_no_technical_command_wording(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)

    sent = await send(main.dp, bot, 111, text="/openshift")

    assert "birinchi smenangiz" in sent[0].text.lower()
    assert "Pul bo'lmasa 0 yozing" in sent[0].text


async def test_kassa_category_body_text_has_no_raw_slash_commands(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)

    sent = await send(main.dp, bot, 111, text="💰 Kassa")

    assert "/openshift" not in sent[0].text
    assert "/closeshift" not in sent[0].text
    assert "/expense" not in sent[0].text
    assert "🟢 Smenani boshlash" in sent[0].text


async def test_first_shift_asks_manual_opening_balance(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)

    sent = await send(main.dp, bot, 111, text="/openshift")
    assert "birinchi smenangiz" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="500000")
    assert "500000" in sent[0].text


async def test_openshift_twice_same_day_does_not_duplicate(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    sent = await send(main.dp, bot, 111, text="/openshift")
    assert "allaqachon ochilgan" in sent[0].text.lower()


async def test_expense_requires_open_shift(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)

    sent = await send(main.dp, bot, 111, text="/expense")
    assert "🟢 Smenani boshlash" in sent[0].text


async def test_expense_full_flow_no_anomaly(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    sent = await send(main.dp, bot, 111, text="/expense")
    assert "kategoriyasini" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="🚕 Taxi")
    assert "summasini" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="65000")
    assert "izoh" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="➖ O'tkazib yuborish")
    assert "qayd etildi" in sent[0].text.lower()

    from services import cash_expense
    from services import cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert cash_expense.total_expenses_for_shift(shift["id"]) == 65000


async def test_expense_finish_skipped_when_already_pending_for_same_kassir(bot_dp):
    """Atomic guard: shu kassir uchun xarajat yozish jarayoni allaqachon
    "band" bo'lsa (masalan deyarli bir vaqtda kelgan ikkinchi xabar),
    ikkinchi urinish xarajatni QAYTA yozmasligi kerak (qarang
    ``_PENDING_EXPENSE_SUBMISSIONS``).
    """
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    await send(main.dp, bot, 111, text="/expense")
    await send(main.dp, bot, 111, text="🚕 Taxi")
    await send(main.dp, bot, 111, text="65000")  # izoh holatiga o'tadi

    import cash_shift_bot
    from repositories import cash_shifts as cash_shifts_repo
    from services import cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    expenses_before = len(cash_shifts_repo.get_expenses_for_shift(shift["id"]))

    cash_shift_bot._PENDING_EXPENSE_SUBMISSIONS.add(111)
    try:
        await send(main.dp, bot, 111, text="➖ O'tkazib yuborish")
    finally:
        cash_shift_bot._PENDING_EXPENSE_SUBMISSIONS.discard(111)

    expenses_after = len(cash_shifts_repo.get_expenses_for_shift(shift["id"]))
    assert expenses_after == expenses_before


async def test_expense_anomaly_requires_reason(bot_dp):
    main, bot = bot_dp
    from repositories import cash_shifts as repo

    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    shift = repo.get_open_shift(111, company_time.today().isoformat())

    for i, amount in enumerate((60_000,) * 7):
        repo.add_expense(shift["id"], 111, "Filial-1", "taxi", amount, None, f"2020-01-{10 + i}")

    await send(main.dp, bot, 111, text="/expense")
    await send(main.dp, bot, 111, text="🚕 Taxi")
    sent = await send(main.dp, bot, 111, text="180000")
    assert "sezilarli yuqori" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="Mijoz uzoqda edi")
    assert "qayd etildi" in sent[0].text.lower()


async def test_closeshift_shows_confirm_amount_buttons(bot_dp):
    """Topshiruvchi kassir summani kiritgach, "✅ To'g'ri"/"🔄 Qayta
    yozaman" tugmalarini ko'radi (yopishdan oldin)."""
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)
    await _clear_daily_report_gate(main, bot, 111)
    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    sent = await send(main.dp, bot, 111, text="0")
    assert sent[0].text == "Smenani topshirasizmi?"

    await send_callback(main.dp, bot, 111, data="csui_close_start_yes", target_chat_id=111)
    sent = await send(main.dp, bot, 111, text="100000")

    assert sent[0].text == "100 000 so'm. To'g'rimi?"
    buttons = sent[0].reply_markup.inline_keyboard[0]
    assert [b.text for b in buttons] == ["✅ To'g'ri", "🔄 Qayta yozaman"]


async def test_closeshift_confirm_skipped_when_already_pending_for_same_kassir(bot_dp):
    """Atomic guard: shu kassir uchun smenani yopish jarayoni allaqachon
    "band" bo'lsa (masalan deyarli bir vaqtda ikkinchi marta bosilgan
    "✅ To'g'ri" tugmasi), ikkinchi bosish ``submit_close_attempt``ni
    qayta chaqirmasligi va urinish/statusni o'zgartirmasligi kerak
    (qarang ``_PENDING_CLOSE_SUBMISSIONS``).
    """
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)
    await _clear_daily_report_gate(main, bot, 111)
    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    await send_callback(main.dp, bot, 111, data="csui_close_start_yes", target_chat_id=111)
    await send(main.dp, bot, 111, text="100000")  # "confirm_actual_balance" holatiga o'tadi

    import cash_shift_bot
    from services import cash_shift

    shift_before = cash_shift.get_open_shift(111, company_time.today().isoformat())

    cash_shift_bot._PENDING_CLOSE_SUBMISSIONS.add(111)
    try:
        await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)
    finally:
        cash_shift_bot._PENDING_CLOSE_SUBMISSIONS.discard(111)

    shift_after = cash_shift.get_shift(shift_before["id"])
    assert shift_after["retry_count"] == shift_before["retry_count"]
    assert shift_after["status"] == shift_before["status"]


async def test_closeshift_clean_close(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    sent = await _close_shift_happy_path(main, bot, 111)
    assert "KASSA — KUN YAKUNI" in sent[0].text
    # closeshift smenani darhol yopmaydi — qabul qiluvchi kassir mustaqil
    # sanab tasdiqlagunicha "topshirish jarayonida" holatida qoladi.
    assert "🟡 Topshirish jarayonida" in sent[0].text


async def test_closeshift_clean_close_deletes_tracked_dialog_messages(bot_dp):
    """Smena toza yopilgandan keyin /closeshift dialogining oraliq
    xabarlari chatdan o'chirib tashlanadi (yakuniy hisobot xabari esa
    o'chirilmaydi) — DB'dagi smena yozuvi esa o'zgarishsiz qoladi.
    """
    from aiogram.methods import DeleteMessage

    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    sent = await _close_shift_happy_path(main, bot, 111)
    assert "KASSA — KUN YAKUNI" in sent[0].text

    deletes = [m for m in bot.sent if isinstance(m, DeleteMessage)]
    assert len(deletes) > 0
    assert all(m.chat_id == 111 for m in deletes)

    from services import cash_shift
    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert shift is not None
    assert shift["cash_sales"] == 100000


async def test_closeshift_within_tolerance(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    sent = await _close_shift_happy_path(main, bot, 111, actual="99990")
    assert "🟡 Topshirish jarayonida" in sent[0].text


async def test_closeshift_recheck_then_success(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)
    await _clear_daily_report_gate(main, bot, 111)
    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    sent = await _confirm_close_amount(main, bot, 111, "50000")  # 50_000 farq, tolerance 20_000dan katta
    assert "qayta tekshiring" in sent[0].text.lower()
    assert "Qolgan urinishlar: 2" in sent[0].text

    # Qayta urinishda rasm qayta so'ralmaydi — to'g'ridan-to'g'ri raqamlar
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    sent = await _confirm_close_amount(main, bot, 111, "100000")
    assert "🟡 Topshirish jarayonida" in sent[0].text


async def test_closeshift_escalates_to_supervisor_after_retry_limit(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)
    await _clear_daily_report_gate(main, bot, 111)
    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    await _confirm_close_amount(main, bot, 111, "50000")  # attempt 1: recheck

    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    await _confirm_close_amount(main, bot, 111, "50000")  # attempt 2: recheck

    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    sent = await _confirm_close_amount(main, bot, 111, "50000")  # attempt 3: escalates

    kassir_messages = [m for m in sent if getattr(m, "chat_id", None) == 111]
    assert "yuborildi" in kassir_messages[0].text.lower()

    founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert len(founder_messages) == 1
    assert "tekshiruvi kerak" in founder_messages[0].text.lower()


async def test_supervisor_approve_finalizes_and_notifies_kassir(bot_dp):
    main, bot = bot_dp
    from services import cash_shift
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    for i in range(3):
        await send(main.dp, bot, 111, text="/closeshift")
        if i == 0:
            await _clear_deficiency_gate(main, bot, 111)
            await _clear_daily_report_gate(main, bot, 111)
            await send(main.dp, bot, 111, photo_file_id="sales_photo")
            await send(main.dp, bot, 111, photo_file_id="cash_photo")
        await send(main.dp, bot, 111, text="100000")
        await send(main.dp, bot, 111, text="0")
        await send(main.dp, bot, 111, text="0")
        await _confirm_close_amount(main, bot, 111, "50000")

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert shift["status"] == cash_shift.STATUS_NEEDS_SUPERVISOR_APPROVAL

    sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"cashshift_approve:{shift['id']}", target_chat_id=FOUNDER_ID
    )
    kassir_messages = [m for m in sent if getattr(m, "chat_id", None) == 111]
    assert "tasdiqlandi" in kassir_messages[0].text.lower()

    updated = cash_shift.get_shift(shift["id"])
    assert updated["status"] == cash_shift.STATUS_APPROVED_BY_SUPERVISOR


async def test_supervisor_recheck_message_has_no_raw_slash_command(bot_dp):
    main, bot = bot_dp
    from services import cash_shift
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    for i in range(3):
        await send(main.dp, bot, 111, text="/closeshift")
        if i == 0:
            await _clear_deficiency_gate(main, bot, 111)
            await _clear_daily_report_gate(main, bot, 111)
            await send(main.dp, bot, 111, photo_file_id="sales_photo")
            await send(main.dp, bot, 111, photo_file_id="cash_photo")
        await send(main.dp, bot, 111, text="100000")
        await send(main.dp, bot, 111, text="0")
        await send(main.dp, bot, 111, text="0")
        await _confirm_close_amount(main, bot, 111, "50000")

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert shift["status"] == cash_shift.STATUS_NEEDS_SUPERVISOR_APPROVAL

    sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"cashshift_recheck:{shift['id']}", target_chat_id=FOUNDER_ID
    )
    kassir_messages = [m for m in sent if getattr(m, "chat_id", None) == 111]
    assert "/closeshift" not in kassir_messages[0].text
    assert "🔴 Smenani topshirish" in kassir_messages[0].text


async def test_non_supervisor_cannot_approve(bot_dp):
    main, bot = bot_dp
    from services import cash_shift
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    for i in range(3):
        await send(main.dp, bot, 111, text="/closeshift")
        if i == 0:
            await _clear_deficiency_gate(main, bot, 111)
            await _clear_daily_report_gate(main, bot, 111)
            await send(main.dp, bot, 111, photo_file_id="sales_photo")
            await send(main.dp, bot, 111, photo_file_id="cash_photo")
        await send(main.dp, bot, 111, text="100000")
        await send(main.dp, bot, 111, text="0")
        await send(main.dp, bot, 111, text="0")
        await _confirm_close_amount(main, bot, 111, "50000")

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())

    _make_kassir(222, branch="Filial-2")
    await send_callback(
        main.dp, bot, 222, data=f"cashshift_approve:{shift['id']}", target_chat_id=FOUNDER_ID
    )

    updated = cash_shift.get_shift(shift["id"])
    assert updated["status"] == cash_shift.STATUS_NEEDS_SUPERVISOR_APPROVAL


async def test_cashsummary_self_view(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "500000")

    sent = await send(main.dp, bot, 111, text="/cashsummary")
    assert "KASSA — KUN YAKUNI" in sent[0].text


async def test_openshift_shows_previous_balance_and_diff_flow_keeps_both_amounts(bot_dp, monkeypatch):
    main, bot = bot_dp
    from datetime import timedelta

    from services import cash_shift
    _make_kassir(111)

    await _open_shift(main, bot, 111, "500000")
    await _close_shift_happy_path(main, bot, 111, actual="777777")

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    sent = await send(main.dp, bot, 111, text="/openshift")
    assert sent[0].text == "Oldingi smenadan qoldiq: 777 777 so'm. Pulni sanang. Mosmi?"
    buttons = sent[0].reply_markup.inline_keyboard[0]
    assert [b.text for b in buttons] == ["✅ Ha, mos", "❗ Farq bor"]

    sent = await _confirm_received_amount(main, bot, 111, "333333")
    assert "Kassa farqi" in " ".join(m.text for m in sent)

    shift = cash_shift.get_open_shift(111, tomorrow.isoformat())
    assert shift["opening_balance"] == 777777
    assert shift["received_cash_balance"] == 333333


async def test_openshift_shows_confirm_received_amount_buttons(bot_dp, monkeypatch):
    """Qabul qiluvchi kassir summani kiritgach, "✅ To'g'ri"/"🔄 Yana
    sanayman" tugmalarini ko'radi (solishtirishdan oldin)."""
    main, bot = bot_dp
    from datetime import timedelta

    _make_kassir(111)
    await _open_shift(main, bot, 111, "500000")
    await _close_shift_happy_path(main, bot, 111, actual="777777")

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    await send(main.dp, bot, 111, text="/openshift")
    await _click_prev(main, bot, 111, "diff")
    sent = await send(main.dp, bot, 111, text="600000")

    assert sent[0].text == "Siz sanadingiz: 600 000 so'm"
    buttons = sent[0].reply_markup.inline_keyboard[0]
    assert [b.text for b in buttons] == ["✅ To'g'ri", "🔄 Yana sanayman"]


async def test_openshift_amounts_match(bot_dp, monkeypatch):
    main, bot = bot_dp
    from datetime import timedelta

    _make_kassir(111)

    await _open_shift(main, bot, 111, "500000")
    await _close_shift_happy_path(main, bot, 111, actual="777777")

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    await send(main.dp, bot, 111, text="/openshift")
    sent = await _confirm_received_amount(main, bot, 111, "777777")
    assert [m.text for m in sent] == ["✅ Kassa mos.", "Smena topshirildi."]


async def test_openshift_mismatch_computes_difference_and_does_not_close_shift(bot_dp, monkeypatch):
    main, bot = bot_dp
    from datetime import timedelta

    from services import cash_shift
    _make_kassir(111)

    await _open_shift(main, bot, 111, "500000")
    await _close_shift_happy_path(main, bot, 111, actual="1000000")

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    await send(main.dp, bot, 111, text="/openshift")
    sent = await _confirm_received_amount(main, bot, 111, "980000")
    assert sent[0].text == "⚠️ Kassa farqi: -20 000 so'm"
    assert sent[1].text == "Nima qilamiz?"

    shift = cash_shift.get_open_shift(111, tomorrow.isoformat())
    assert shift["status"] == cash_shift.STATUS_OPEN
    assert shift["closed_at"] is None


async def test_discrepancy_choice_retry_and_reason_buttons(bot_dp, monkeypatch):
    """Tafovutda "🔄 Yana sanayman"/"📝 Sababini yozaman" ishlaydi:
    birinchisi qayta sanashga qaytaradi, ikkinchisi tayyor sabab
    tugmalarini ko'rsatadi."""
    main, bot = bot_dp
    from datetime import timedelta

    _make_kassir(111)

    await _open_shift(main, bot, 111, "500000")
    await _close_shift_happy_path(main, bot, 111, actual="1000000")

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    await send(main.dp, bot, 111, text="/openshift")
    sent = await _confirm_received_amount(main, bot, 111, "980000")
    buttons = sent[1].reply_markup.inline_keyboard[0]
    assert [b.text for b in buttons] == ["🔄 Yana sanayman", "📝 Sababini yozaman"]

    # "🔄 Yana sanayman" — qayta sanashga qaytaradi.
    sent = await send_callback(main.dp, bot, 111, data="csui_disc_retry", target_chat_id=111)
    sent = [m for m in sent if getattr(m, "text", None)]
    assert sent[0].text == "Sanagan summangizni yozing:"

    # Qayta sanab, endi mos summa kiritadi va tasdiqlaydi — tayyor
    # sabab tugmalarini ko'rish uchun yana tafovutli summa kiritamiz.
    sent = await _confirm_received_amount(main, bot, 111, "980000")
    assert sent[1].reply_markup.inline_keyboard[0][1].text == "📝 Sababini yozaman"

    # "📝 Sababini yozaman" — tayyor sabab tugmalarini ko'rsatadi.
    sent = await send_callback(main.dp, bot, 111, data="csui_disc_reason", target_chat_id=111)
    sent = [m for m in sent if getattr(m, "text", None)]
    assert sent[0].text == "Sababni tanlang:"
    reason_buttons = [b.text for row in sent[0].reply_markup.inline_keyboard for b in row]
    assert reason_buttons == [
        "💵 Qaytimda xato", "🧾 Xarajat bo'lgan", "💳 To'lovda xato", "❓ Bilmayman", "✍️ Boshqa sabab",
    ]


async def test_discrepancy_reason_asked_and_saved_when_mismatch(bot_dp, monkeypatch):
    main, bot = bot_dp
    from datetime import timedelta

    from services import cash_shift
    _make_kassir(111)

    await _open_shift(main, bot, 111, "500000")
    await _close_shift_happy_path(main, bot, 111, actual="1000000")

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    await send(main.dp, bot, 111, text="/openshift")
    await _confirm_received_amount(main, bot, 111, "980000")
    await send_callback(main.dp, bot, 111, data="csui_disc_reason", target_chat_id=111)
    sent = await send_callback(main.dp, bot, 111, data="csui_reason:other", target_chat_id=111)
    sent = [m for m in sent if getattr(m, "text", None)]
    assert sent[0].text == "Sababini qisqa yozing:"

    await send(main.dp, bot, 111, text="Qaytimda xato bo'lishi mumkin")

    shift = cash_shift.get_open_shift(111, tomorrow.isoformat())
    assert shift["discrepancy_reason_text"] == "Qaytimda xato bo'lishi mumkin"


async def test_discrepancy_reason_not_asked_when_amounts_match(bot_dp, monkeypatch):
    main, bot = bot_dp
    from datetime import timedelta

    from services import cash_shift
    _make_kassir(111)

    await _open_shift(main, bot, 111, "500000")
    await _close_shift_happy_path(main, bot, 111, actual="777777")

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    await send(main.dp, bot, 111, text="/openshift")
    sent = await _confirm_received_amount(main, bot, 111, "777777")
    assert [m.text for m in sent] == ["✅ Kassa mos.", "Smena topshirildi."]

    shift = cash_shift.get_open_shift(111, tomorrow.isoformat())
    assert shift["discrepancy_reason_text"] is None


async def test_matching_amounts_closes_handover_and_confirms_receipt(bot_dp, monkeypatch):
    main, bot = bot_dp
    from datetime import timedelta

    from services import cash_shift
    _make_kassir(111)

    # opening=500000 + cash_sales=100000 - expenses=0 = expected 600000 —
    # aynan shu summa bilan yopilsa "toza" (clean_closed) yakunlanadi.
    original_today = company_time.today().isoformat()
    await _open_shift(main, bot, 111, "500000")
    await _close_shift_happy_path(main, bot, 111, actual="600000")

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    await send(main.dp, bot, 111, text="/openshift")
    sent = await _confirm_received_amount(main, bot, 111, "600000")
    assert [m.text for m in sent] == ["✅ Kassa mos.", "Smena topshirildi."]

    # Topshiruvchi kassirning smenasi yopilgan holatda (topshirish vaqti —
    # ``closed_at``), qabul qiluvchining yangi smenasida esa qabul
    # qilingani va vaqti qayd etilgan (``received_cash_balance``+``opened_at``).
    handed_over_shift = cash_shift.get_open_shift(111, original_today)
    assert handed_over_shift["status"] in (cash_shift.STATUS_CLEAN_CLOSED, cash_shift.STATUS_WITHIN_TOLERANCE)
    assert handed_over_shift["closed_at"] is not None

    received_shift = cash_shift.get_open_shift(111, tomorrow.isoformat())
    assert received_shift["received_cash_balance"] == 600000
    assert received_shift["opened_at"] is not None


async def test_mismatch_does_not_close_or_confirm_receipt(bot_dp, monkeypatch):
    main, bot = bot_dp
    from datetime import timedelta

    from services import cash_shift
    _make_kassir(111)

    await _open_shift(main, bot, 111, "500000")
    await _close_shift_happy_path(main, bot, 111, actual="1000000")

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    await send(main.dp, bot, 111, text="/openshift")
    sent = await _confirm_received_amount(main, bot, 111, "980000")
    joined = " ".join(m.text for m in sent)
    assert "Smena topshirildi" not in joined
    assert "Kassa mos" not in joined

    shift = cash_shift.get_open_shift(111, tomorrow.isoformat())
    assert shift["status"] == cash_shift.STATUS_OPEN
    assert shift["closed_at"] is None


async def test_closeshift_does_not_close_until_receiver_confirms_match(bot_dp, monkeypatch):
    main, bot = bot_dp
    from datetime import timedelta

    from services import cash_shift
    _make_kassir(111)

    original_today = company_time.today().isoformat()
    await _open_shift(main, bot, 111, "500000")
    # opening=500000 + cash_sales=100000 - expenses=0 = 600000 kutilgan.
    await _close_shift_happy_path(main, bot, 111, actual="600000")

    # /closeshift darhol yopmasin — qabul qiluvchi hali tasdiqlamagan.
    handed_over_shift = cash_shift.get_open_shift(111, original_today)
    assert handed_over_shift["status"] == cash_shift.STATUS_PENDING_HANDOVER
    assert handed_over_shift["closed_at"] is None

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    await send(main.dp, bot, 111, text="/openshift")
    await _confirm_received_amount(main, bot, 111, "600000")

    # Faqat shundan keyin — qabul qiluvchi mos summani tasdiqlagach —
    # topshiruvchi smenasi haqiqatan yopiladi.
    handed_over_shift = cash_shift.get_open_shift(111, original_today)
    assert handed_over_shift["status"] == cash_shift.STATUS_CLEAN_CLOSED
    assert handed_over_shift["closed_at"] is not None


async def test_closeshift_stays_pending_handover_on_mismatch(bot_dp, monkeypatch):
    main, bot = bot_dp
    from datetime import timedelta

    from services import cash_shift
    _make_kassir(111)

    original_today = company_time.today().isoformat()
    await _open_shift(main, bot, 111, "500000")
    await _close_shift_happy_path(main, bot, 111, actual="600000")

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    await send(main.dp, bot, 111, text="/openshift")
    await _confirm_received_amount(main, bot, 111, "580000")  # tafovut — mos emas

    # Tafovut bo'lganda topshiruvchi smenasi yopilmay qoladi.
    handed_over_shift = cash_shift.get_open_shift(111, original_today)
    assert handed_over_shift["status"] == cash_shift.STATUS_PENDING_HANDOVER
    assert handed_over_shift["closed_at"] is None


async def test_night_to_morning_handover_between_two_different_cashiers(bot_dp, monkeypatch):
    """End-to-end: tungi kassir (111) /closeshift qiladi va ketadi,
    ertalab BOSHQA kassir (222) /openshift qilib pulni mustaqil sanaydi.
    """
    main, bot = bot_dp
    from datetime import timedelta

    from services import cash_shift
    _make_kassir(111, branch="Filial-1")  # tungi kassir
    _make_kassir(222, branch="Filial-1")  # ertalabgi kassir, xuddi shu filial

    original_today = company_time.today().isoformat()
    await _open_shift(main, bot, 111, "500000")
    # opening=500000 + cash_sales=100000 - expenses=0 = 600000 kutilgan.
    await _close_shift_happy_path(main, bot, 111, actual="600000")

    handed_over_shift = cash_shift.get_open_shift(111, original_today)
    assert handed_over_shift["status"] == cash_shift.STATUS_PENDING_HANDOVER
    assert handed_over_shift["closed_at"] is None

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    sent = await send(main.dp, bot, 222, text="/openshift")
    joined = " ".join(m.text for m in sent)
    assert "oldingi smenadan qoldiq: 600 000 so'm" in joined.lower()

    sent = await _confirm_received_amount(main, bot, 222, "600000")
    assert [m.text for m in sent] == ["✅ Kassa mos.", "Smena topshirildi."]

    handed_over_shift = cash_shift.get_open_shift(111, original_today)
    assert handed_over_shift["status"] == cash_shift.STATUS_CLEAN_CLOSED
    assert handed_over_shift["closed_at"] is not None

    received_shift = cash_shift.get_open_shift(222, tomorrow.isoformat())
    assert received_shift["received_cash_balance"] == 600000


async def test_discrepancy_reason_notifies_founder(bot_dp, monkeypatch):
    main, bot = bot_dp
    from datetime import timedelta

    _make_kassir(111, branch="Filial-1")  # tungi (topshiruvchi) kassir
    _make_kassir(222, branch="Filial-1")  # ertalabgi (qabul qiluvchi) kassir

    await _open_shift(main, bot, 111, "500000")
    # opening=500000 + cash_sales=100000 - expenses=0 = 600000 kutilgan.
    await _close_shift_happy_path(main, bot, 111, actual="600000")

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    await send(main.dp, bot, 222, text="/openshift")
    await _confirm_received_amount(main, bot, 222, "580000")  # tafovut: -20000
    await send_callback(main.dp, bot, 222, data="csui_disc_reason", target_chat_id=222)
    await send_callback(main.dp, bot, 222, data="csui_reason:other", target_chat_id=222)

    sent = await send(main.dp, bot, 222, text="Qaytimda xato bo'lishi mumkin")

    founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert len(founder_messages) == 1
    alert_text = founder_messages[0].text
    assert "KASSA TAFOVUTI" in alert_text
    assert "Filial-1" in alert_text
    assert "Topshirilgan summa: 600000" in alert_text
    assert "Qabul qilingan summa: 580000" in alert_text
    assert "Tafovut: -20 000 so'm" in alert_text
    assert "Qaytimda xato bo'lishi mumkin" in alert_text


async def _reach_discrepancy_alert(main, bot, monkeypatch, topshiruvchi_id: int, qabul_id: int, branch="Filial-1"):
    """Topshiruvchi smenani (REAL bugungi sanada) ochib-yopadi (600000),
    keyin sana "ertaga"ga o'tkaziladi va qabul qiluvchi tafovutli summa
    (580000) kiritib sababini yozadi — Founderga "⚠️ KASSA TAFOVUTI"
    xabari ketguncha bo'lgan umumiy tayyorgarlik (bir nechta testda
    qayta ishlatiladi). Ikkala smena ALOHIDA kunlarda bo'lishi shart —
    aks holda topshiruvchi/qabul qiluvchi bir xil (filial, sana) qatorga
    to'g'ri kelib qoladi.

    Qaytaradi: ``(original_today, tomorrow)`` — ``date`` obyekti tomorrow.
    """
    from datetime import timedelta

    _make_kassir(topshiruvchi_id, branch=branch)
    _make_kassir(qabul_id, branch=branch)

    original_today = company_time.today().isoformat()
    await _open_shift(main, bot, topshiruvchi_id, "500000")
    await _close_shift_happy_path(main, bot, topshiruvchi_id, actual="600000")

    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    await send(main.dp, bot, qabul_id, text="/openshift")
    await _confirm_received_amount(main, bot, qabul_id, "580000")  # tafovut: -20000
    await send_callback(main.dp, bot, qabul_id, data="csui_disc_reason", target_chat_id=qabul_id)
    await send_callback(main.dp, bot, qabul_id, data="csui_reason:other", target_chat_id=qabul_id)
    await send(main.dp, bot, qabul_id, text="Qaytimda xato bo'lishi mumkin")

    return original_today, tomorrow


async def test_discrepancy_approve_finalizes_handed_over_shift(bot_dp, monkeypatch):
    main, bot = bot_dp
    from aiogram.methods import AnswerCallbackQuery

    from services import cash_shift

    original_today, tomorrow = await _reach_discrepancy_alert(main, bot, monkeypatch, 111, 222)

    received_shift = cash_shift.get_open_shift(222, tomorrow.isoformat())

    sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"csui_disc_approve:{received_shift['id']}", target_chat_id=FOUNDER_ID
    )

    acks = [m for m in sent if isinstance(m, AnswerCallbackQuery)]
    assert any(a.text == "✅ Kassa tafovuti qabul qilindi." for a in acks)

    # Yopilishi kerak bo'lgan — topshiruvchi kassirning smenasi.
    handed_over_shift = cash_shift.get_open_shift(111, original_today)
    assert handed_over_shift["status"] == cash_shift.STATUS_CLEAN_CLOSED
    assert handed_over_shift["closed_at"] is not None

    # Qabul qiluvchining YANGI smenasi tegilmagan — ochiq qolaveradi.
    received_shift_after = cash_shift.get_open_shift(222, tomorrow.isoformat())
    assert received_shift_after["status"] == cash_shift.STATUS_OPEN


async def test_discrepancy_recount_keeps_shift_open_and_resets_kassir_state(bot_dp, monkeypatch):
    main, bot = bot_dp
    from services import cash_shift

    original_today, tomorrow = await _reach_discrepancy_alert(main, bot, monkeypatch, 111, 222)

    received_shift = cash_shift.get_open_shift(222, tomorrow.isoformat())

    sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"csui_disc_recount:{received_shift['id']}", target_chat_id=FOUNDER_ID
    )

    kassir_messages = [m for m in sent if getattr(m, "chat_id", None) == 222 and getattr(m, "text", None)]
    assert kassir_messages[0].text == "🔄 Kassani yana bir marta sanang."

    # Topshiruvchi kassirning smenasi yopilmagan — hali PENDING_HANDOVER.
    handed_over_shift = cash_shift.get_open_shift(111, original_today)
    assert handed_over_shift["status"] == cash_shift.STATUS_PENDING_HANDOVER
    assert handed_over_shift["closed_at"] is None

    # Kassir mavjud "summani qayta kiritish" bosqichiga qaytarilgan —
    # yangi (mos) summa kiritilgach mavjud solishtirish logikasi ishlaydi.
    sent = await _confirm_received_amount(main, bot, 222, "600000")
    assert [m.text for m in sent] == ["✅ Kassa mos.", "Smena topshirildi."]


async def test_kassir_choice_buttons_are_two_per_row(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)
    await _clear_daily_report_gate(main, bot, 111)
    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    sent = await send(main.dp, bot, 111, text="0")  # "Smenani topshirasizmi?" darvozasi

    rows = sent[0].reply_markup.inline_keyboard
    assert len(rows) == 1
    assert [b.text for b in rows[0]] == ["✅ Ha, topshiraman", "❌ Orqaga"]


def _seed_closed_shift(branch: str, actual_cash_balance: int, shift_date: str, employee_id: int = 900) -> None:
    from db import get_connection
    from repositories import cash_shifts as cash_shifts_repo

    shift = cash_shifts_repo.open_shift(employee_id, branch, shift_date, 0, 0)
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE cash_shifts SET status = 'clean_closed', actual_cash_balance = ? WHERE id = ?",
            (actual_cash_balance, shift["id"]),
        )
        conn.commit()
    finally:
        conn.close()


def _yesterday() -> str:
    from datetime import timedelta

    return (company_time.today() - timedelta(days=1)).isoformat()


async def test_openshift_previous_balance_match_uses_existing_acceptance(bot_dp):
    main, bot = bot_dp
    from services import cash_shift
    _make_kassir(111, branch="Filial-1")
    _seed_closed_shift("Filial-1", 600000, _yesterday())

    await send(main.dp, bot, 111, text="/openshift")
    sent = await _click_prev(main, bot, 111, "ok")
    texts = [m.text for m in sent if getattr(m, "text", None)]
    assert texts == ["✅ Kassa mos.", "Smena topshirildi."]

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert shift["opening_balance"] == 600000
    assert shift["received_cash_balance"] == 600000

    # Takroriy bosish — holat tozalangan, hech narsa qayta bajarilmaydi.
    sent = await _click_prev(main, bot, 111, "ok")
    assert not [m for m in sent if getattr(m, "text", None)]


async def test_openshift_previous_balance_diff_asks_counted_amount_and_checks_discrepancy(bot_dp):
    main, bot = bot_dp
    from services import cash_shift
    _make_kassir(111, branch="Filial-1")
    _seed_closed_shift("Filial-1", 600000, _yesterday())

    await send(main.dp, bot, 111, text="/openshift")
    sent = await _click_prev(main, bot, 111, "diff")
    assert "Sanagan summangizni yozing:" in [getattr(m, "text", None) for m in sent]

    await send(main.dp, bot, 111, text="580000")
    sent = await send_callback(main.dp, bot, 111, data="csui_recv_amount_ok", target_chat_id=111)
    assert "⚠️ Kassa farqi: -20 000 so'm" in [getattr(m, "text", None) for m in sent]

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert shift["opening_balance"] == 600000
    assert shift["received_cash_balance"] == 580000


async def test_openshift_without_previous_balance_keeps_manual_entry(bot_dp):
    main, bot = bot_dp
    _make_kassir(111, branch="Filial-1")

    sent = await send(main.dp, bot, 111, text="/openshift")
    assert "birinchi smenangiz" in sent[0].text
    assert sent[0].reply_markup is None


async def test_openshift_previous_balance_zero_is_a_real_value(bot_dp):
    main, bot = bot_dp
    from services import cash_shift
    _make_kassir(111, branch="Filial-1")
    _seed_closed_shift("Filial-1", 0, _yesterday())

    sent = await send(main.dp, bot, 111, text="/openshift")
    assert sent[0].text == "Oldingi smenadan qoldiq: 0 so'm. Pulni sanang. Mosmi?"

    sent = await _click_prev(main, bot, 111, "ok")
    texts = [m.text for m in sent if getattr(m, "text", None)]
    assert texts == ["✅ Kassa mos.", "Smena topshirildi."]
    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert shift["opening_balance"] == 0
    assert shift["received_cash_balance"] == 0


async def test_openshift_does_not_use_other_branch_previous_balance(bot_dp):
    main, bot = bot_dp
    _make_kassir(111, branch="Filial-1")
    _seed_closed_shift("Filial-2", 999999, _yesterday())

    sent = await send(main.dp, bot, 111, text="/openshift")
    joined = " ".join(m.text for m in sent if getattr(m, "text", None))
    assert "999" not in joined
    assert "birinchi smenangiz" in joined

    _seed_closed_shift("Filial-1", 600000, _yesterday(), employee_id=901)
    await send(main.dp, bot, 111, text="/cancel")
    sent = await send(main.dp, bot, 111, text="/openshift")
    joined = " ".join(m.text for m in sent if getattr(m, "text", None))
    assert "600 000" in joined
    assert "999" not in joined


async def test_openshift_repeated_request_rejects_old_buttons_and_accepts_new(bot_dp):
    main, bot = bot_dp
    from services import cash_shift
    _make_kassir(111, branch="Filial-1")
    _seed_closed_shift("Filial-1", 600000, _yesterday())

    await send(main.dp, bot, 111, text="/openshift")
    old_token = (await _prev_data(main, bot, 111))["prev_token"]
    await send(main.dp, bot, 111, text="/openshift")
    new_token = (await _prev_data(main, bot, 111))["prev_token"]
    assert old_token != new_token

    for action in ("ok", "diff"):
        sent = await _click_prev(main, bot, 111, action, token=old_token)
        assert any("Bu tugma eskirgan" in str(getattr(m, "text", "")) for m in sent)
        assert await main.dp.fsm.get_context(bot=bot, chat_id=111, user_id=111).get_state() == (
            "OpenShiftStates:confirm_previous_balance"
        )
        assert cash_shift.get_open_shift(111, company_time.today().isoformat()) is None

    sent = await _click_prev(main, bot, 111, "ok", token=new_token)
    assert [m.text for m in sent if getattr(m, "text", None)] == ["✅ Kassa mos.", "Smena topshirildi."]


async def test_openshift_previous_shift_changed_requires_new_confirmation(bot_dp):
    main, bot = bot_dp
    from datetime import timedelta

    from services import cash_shift
    _make_kassir(111, branch="Filial-1")
    _seed_closed_shift("Filial-1", 600000, (company_time.today() - timedelta(days=2)).isoformat())

    await send(main.dp, bot, 111, text="/openshift")
    old_token = (await _prev_data(main, bot, 111))["prev_token"]

    _seed_closed_shift("Filial-1", 450000, _yesterday(), employee_id=901)

    sent = await _click_prev(main, bot, 111, "ok", token=old_token)
    texts_ = [m.text for m in sent if getattr(m, "text", None)]
    assert texts_ == ["Oldingi smenadan qoldiq: 450 000 so'm. Pulni sanang. Mosmi?"]
    assert cash_shift.get_open_shift(111, company_time.today().isoformat()) is None

    new_token = (await _prev_data(main, bot, 111))["prev_token"]
    assert new_token != old_token
    sent = await _click_prev(main, bot, 111, "ok", token=old_token)
    assert cash_shift.get_open_shift(111, company_time.today().isoformat()) is None

    sent = await _click_prev(main, bot, 111, "ok", token=new_token)
    assert [m.text for m in sent if getattr(m, "text", None)] == ["✅ Kassa mos.", "Smena topshirildi."]
    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert shift["opening_balance"] == 450000
    assert shift["received_cash_balance"] == 450000


async def _open_today_then_pass_midnight(main, bot, monkeypatch, user_id: int = 111, opening: str = "500000"):
    from datetime import timedelta

    from services import cash_shift

    original_date = company_time.today().isoformat()
    await _open_shift(main, bot, user_id, opening)
    shift = cash_shift.get_open_shift(user_id, original_date)
    next_day = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: next_day)
    return shift, original_date


async def test_closeshift_after_midnight_closes_yesterdays_open_shift_keeping_id_and_date(bot_dp, monkeypatch):
    main, bot = bot_dp
    from services import cash_shift
    _make_kassir(111)
    shift, original_date = await _open_today_then_pass_midnight(main, bot, monkeypatch)

    sent = await send(main.dp, bot, 111, text="/closeshift")
    assert "🟢 Smenani boshlash" not in " ".join(m.text for m in sent if getattr(m, "text", None))

    await _clear_deficiency_gate(main, bot, 111)
    await _clear_daily_report_gate(main, bot, 111)
    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    await _confirm_close_amount(main, bot, 111, "600000")

    closed = cash_shift.get_shift(shift["id"])
    assert closed["shift_date"] == original_date
    assert closed["status"] != "open"
    assert closed["actual_cash_balance"] == 600000
    assert cash_shift.get_open_shift(111, company_time.today().isoformat()) is None


async def test_expense_after_midnight_is_logged_on_yesterdays_open_shift(bot_dp, monkeypatch):
    main, bot = bot_dp
    from services import cash_expense
    _make_kassir(111)
    shift, original_date = await _open_today_then_pass_midnight(main, bot, monkeypatch)

    await send(main.dp, bot, 111, text="/expense")
    await send(main.dp, bot, 111, text="🚕 Taxi")
    await send(main.dp, bot, 111, text="25000")
    await send(main.dp, bot, 111, text="➖ O'tkazib yuborish")

    expenses = cash_expense.get_expenses_for_shift(shift["id"])
    assert [e["amount"] for e in expenses] == [25000]
    assert expenses[0]["expense_date"] == original_date


async def test_openshift_refuses_while_an_old_open_shift_exists(bot_dp, monkeypatch):
    main, bot = bot_dp
    from db import get_connection
    _make_kassir(111)
    shift, original_date = await _open_today_then_pass_midnight(main, bot, monkeypatch)

    sent = await send(main.dp, bot, 111, text="/openshift")
    assert [m.text for m in sent if getattr(m, "text", None)] == ["⚠️ Avval ochiq smenangizni topshiring."]

    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM cash_shifts WHERE employee_id = 111").fetchone()["c"]
    finally:
        conn.close()
    assert count == 1


async def test_unclosed_shift_lookup_ignores_other_employee_branch_test_and_non_open(bot_dp):
    main, bot = bot_dp
    from db import get_connection
    from repositories import cash_shifts as repo

    yesterday = _yesterday()
    repo.open_shift(111, "Filial-1", yesterday, 0, 0)
    other_employee = repo.open_shift(222, "Filial-1", yesterday, 0, 0)
    other_branch = repo.open_shift(333, "Filial-2", yesterday, 0, 0)
    test_shift = repo.open_shift(444, "Filial-1", yesterday, 0, 0, is_test=True, test_run_id="t1")
    closed = repo.open_shift(555, "Filial-1", yesterday, 0, 0)
    conn = get_connection()
    try:
        conn.execute("UPDATE cash_shifts SET status = 'clean_closed' WHERE id = ?", (closed["id"],))
        conn.commit()
    finally:
        conn.close()

    own = repo.get_unclosed_real_shift(111, "Filial-1")
    assert own is not None and own["employee_id"] == 111
    assert repo.get_unclosed_real_shift(111, "Filial-2") is None
    assert repo.get_unclosed_real_shift(333, "Filial-1") is None
    assert repo.get_unclosed_real_shift(444, "Filial-1") is None
    assert repo.get_unclosed_real_shift(555, "Filial-1") is None
    assert other_employee["id"] != own["id"] and other_branch["id"] != own["id"] and test_shift["id"] != own["id"]


async def _start_expense_on_open_shift(main, bot, user_id: int = 111):
    from services import cash_shift

    _make_kassir(user_id, branch="Filial-1")
    await _open_shift(main, bot, user_id, "0")
    shift = cash_shift.get_open_shift(user_id, company_time.today().isoformat())
    await send(main.dp, bot, user_id, text="/expense")
    await send(main.dp, bot, user_id, text="🚕 Taxi")
    return shift


async def _set_fsm_expense_shift(main, bot, user_id: int, shift_id: int) -> None:
    ctx = main.dp.fsm.get_context(bot=bot, chat_id=user_id, user_id=user_id)
    await ctx.update_data(expense_shift_id=shift_id)


def _expense_count() -> int:
    from db import get_connection

    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) AS c FROM cash_expenses").fetchone()["c"]
    finally:
        conn.close()


@pytest.mark.parametrize("kind", ["other_employee", "other_branch", "test", "closed"])
async def test_expense_with_invalid_fsm_shift_id_writes_nothing(bot_dp, kind):
    main, bot = bot_dp
    from db import get_connection
    from repositories import cash_shifts as repo

    await _start_expense_on_open_shift(main, bot)
    today = company_time.today().isoformat()
    if kind == "other_employee":
        bad = repo.open_shift(222, "Filial-1", today, 0, 0)
    elif kind == "other_branch":
        bad = repo.open_shift(333, "Filial-2", today, 0, 0)
    elif kind == "test":
        bad = repo.open_shift(444, "Filial-1", today, 0, 0, is_test=True, test_run_id="t1")
    else:
        bad = repo.open_shift(555, "Filial-1", today, 0, 0)
        conn = get_connection()
        try:
            conn.execute("UPDATE cash_shifts SET status = 'clean_closed' WHERE id = ?", (bad["id"],))
            conn.commit()
        finally:
            conn.close()

    await _set_fsm_expense_shift(main, bot, 111, bad["id"])
    sent = await send(main.dp, bot, 111, text="25000")
    assert "Ochiq smena topilmadi" in " ".join(m.text for m in sent if getattr(m, "text", None))
    assert _expense_count() == 0


async def test_expense_with_own_open_shift_id_still_writes(bot_dp):
    main, bot = bot_dp
    from services import cash_expense

    shift = await _start_expense_on_open_shift(main, bot)
    await send(main.dp, bot, 111, text="25000")
    await send(main.dp, bot, 111, text="➖ O'tkazib yuborish")

    assert cash_expense.total_expenses_for_shift(shift["id"]) == 25000


async def test_find_working_shift_ignores_other_branch_and_test_shifts(bot_dp):
    main, bot = bot_dp
    import cash_shift_bot
    from repositories import cash_shifts as repo

    _make_kassir(111, branch="Filial-1")
    today = company_time.today().isoformat()

    repo.open_shift(111, "Filial-2", today, 0, 0)  # eski filialdagi smena
    assert cash_shift_bot._find_working_shift(111) is None

    own_yesterday = repo.open_shift(111, "Filial-1", _yesterday(), 0, 0)
    assert cash_shift_bot._find_working_shift(111)["id"] == own_yesterday["id"]


async def test_find_working_shift_prefers_yesterdays_open_over_todays_closed_row(bot_dp):
    main, bot = bot_dp
    import cash_shift_bot
    from db import get_connection
    from repositories import cash_shifts as repo

    _make_kassir(111, branch="Filial-1")
    yesterday_open = repo.open_shift(111, "Filial-1", _yesterday(), 0, 0)
    today_row = repo.open_shift(111, "Filial-1", company_time.today().isoformat(), 0, 0)
    conn = get_connection()
    try:
        conn.execute("UPDATE cash_shifts SET status = 'clean_closed' WHERE id = ?", (today_row["id"],))
        conn.commit()
    finally:
        conn.close()

    assert cash_shift_bot._find_working_shift(111)["id"] == yesterday_open["id"]
