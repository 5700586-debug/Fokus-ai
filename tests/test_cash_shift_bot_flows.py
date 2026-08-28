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


async def _confirm_received_amount(main, bot, user_id: int, amount: str):
    """``counted_cash_balance`` holatida: summa yoziladi, "To'g'ri"
    bosiladi — natijadagi matnli xabarlar qaytadi."""
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
    assert "avval /openshift" in sent[0].text.lower()


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


async def test_receiving_cashier_does_not_see_previous_real_cash_amount(bot_dp, monkeypatch):
    main, bot = bot_dp
    from datetime import timedelta

    from services import cash_shift
    _make_kassir(111)

    # Topshiruvchi kassir birinchi smenani ochib-yopadi, real kassa
    # summasi sifatida 777777 kiritadi (actual_cash_balance).
    await _open_shift(main, bot, 111, "500000")
    await _close_shift_happy_path(main, bot, 111, actual="777777")

    # Ertangi kun — qabul qiluvchi (shu foydalanuvchi, ikkinchi smena)
    # /openshift chaqiradi. Topshiruvchining 777777 summasi hech qanday
    # xabarda ko'rinmasin, kassir mustaqil sanashga yo'naltirilsin.
    tomorrow = company_time.today() + timedelta(days=1)
    monkeypatch.setattr(company_time, "today", lambda: tomorrow)

    sent = await send(main.dp, bot, 111, text="/openshift")
    joined = " ".join(m.text for m in sent)
    assert "777777" not in joined
    assert "o'zingiz sanang" in joined.lower()

    sent = await _confirm_received_amount(main, bot, 111, "333333")
    joined = " ".join(m.text for m in sent)
    assert "777777" not in joined
    assert "Kassa farqi" in joined

    # Ikkala summa bazada alohida saqlanadi: opening_balance — topshiruvchi
    # sanagan real summa, received_cash_balance — qabul qiluvchi sanagan summa.
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
    assert "o'zingiz sanang" in joined.lower()

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
    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    sent = await send(main.dp, bot, 111, text="0")  # "Smenani topshirasizmi?" darvozasi

    rows = sent[0].reply_markup.inline_keyboard
    assert len(rows) == 1
    assert [b.text for b in rows[0]] == ["✅ Ha, topshiraman", "❌ Orqaga"]
