"""Kassa pul tafsilotlari maxfiyligi: nazoratchi pul summalarini ko'rmaydi, Founder/Moliyachi
to'liq ko'radi; filial kartalari Founder-only. ``_notify_branch_shortage`` (filial rahbari +
moliyachi) hozircha o'zgarmagan — shu xatti-harakat testda qayd etilgan."""

from types import SimpleNamespace

import pytest

import company_time
from config import FOUNDER_ID
from tests.bot_harness import send
from tests.test_cash_shift_bot_flows import _make_kassir, _open_shift

pytestmark = pytest.mark.anyio

NAZORATCHI_ID = 555
MOLIYACHI_ID = 666
SAVDO_BOSHLIGI_ID = 777

# Pul summalari — xabarda alohida tanib olinadigan raqamlar.
_MONEY = {
    "opening_balance": 5123456, "cash_sales": 1115000, "card_sales": 234567, "other_payments": 7000,
    "total_sales": 1356567, "cash_expenses": 1615000, "expected_cash_balance": 4623456,
    "actual_cash_balance": 123456, "difference": -4500000, "tolerance": 20000,
}
_MONEY_NUMBERS = ["5123456", "1115000", "234567", "1615000", "4623456", "123456", "4500000"]


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_roles() -> None:
    from roles import set_role

    set_role(NAZORATCHI_ID, "nazoratchi", set_by=FOUNDER_ID)
    set_role(MOLIYACHI_ID, "moliyachi", set_by=FOUNDER_ID)


def _seed_shift(status: str = "needs_supervisor_approval") -> dict:
    from db import get_connection
    from repositories import cash_shifts as repo

    shift = repo.open_shift(111, "Filial-1", company_time.today().isoformat(), 0, 20000)
    assignments = ", ".join(f"{column} = ?" for column in _MONEY)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE cash_shifts SET {assignments}, status = ?, received_cash_balance = ? WHERE id = ?",
            (*_MONEY.values(), status, 0, shift["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return repo.get_shift(shift["id"])


def _texts_for(bot, chat_id: int) -> list[str]:
    return [m.text for m in bot.sent if getattr(m, "chat_id", None) == chat_id and getattr(m, "text", None)]


def _has_money(text: str) -> bool:
    digits = text.replace(" ", "")
    return any(number in digits for number in _MONEY_NUMBERS)


async def test_review_message_hides_money_from_nazoratchi_but_founder_sees_full(bot_dp):
    main, bot = bot_dp
    import cash_shift_bot
    _make_kassir(111, branch="Filial-1")
    _make_roles()
    shift = _seed_shift()

    bot.sent = []
    await cash_shift_bot._send_shift_for_review(SimpleNamespace(bot=bot), shift)

    nazoratchi_text = _texts_for(bot, NAZORATCHI_ID)[0]
    assert not _has_money(nazoratchi_text)  # savdo/qoldiq/xarajat/farq summalari yo'q
    assert "Kassir:" in nazoratchi_text and "Filial-1" in nazoratchi_text
    assert "Tafovut bor" in nazoratchi_text and "Tekshiruv kerak" in nazoratchi_text

    founder_text = _texts_for(bot, FOUNDER_ID)[0]
    assert _has_money(founder_text)
    assert "5123456" in founder_text.replace(" ", "") and "-4500000" in founder_text.replace(" ", "")


async def test_discrepancy_alert_hides_money_from_nazoratchi_but_founder_sees_full(bot_dp):
    main, bot = bot_dp
    import cash_shift_bot
    _make_kassir(111, branch="Filial-1")
    _make_kassir(222, branch="Filial-1")
    _make_roles()
    shift = _seed_shift(status="open")
    from repositories import cash_shifts as repo

    repo.set_received_cash_balance(shift["id"], 580000)
    shift = repo.get_shift(shift["id"])

    bot.sent = []
    await cash_shift_bot._send_discrepancy_alert(SimpleNamespace(bot=bot), shift, 222, "Qaytimda xato")

    nazoratchi_text = _texts_for(bot, NAZORATCHI_ID)[0]
    assert "KASSA TAFOVUTI" in nazoratchi_text and "Tafovut bor" in nazoratchi_text
    assert "Sabab kiritilgan. Tafsilot Founder/Moliyachi uchun." in nazoratchi_text
    assert "Qaytimda xato" not in nazoratchi_text  # kassir sababi nazoratchiga ko'rinmaydi
    assert not _has_money(nazoratchi_text) and "580000" not in nazoratchi_text.replace(" ", "")
    assert "so'm" not in nazoratchi_text

    founder_text = _texts_for(bot, FOUNDER_ID)[0]
    assert "Topshirilgan summa: 5123456 so'm" in founder_text
    assert "Qabul qilingan summa: 580000 so'm" in founder_text and "Tafovut:" in founder_text
    assert "Sabab: Qaytimda xato" in founder_text  # Founder sababni to'liq ko'radi


async def test_cashsummary_other_employee_hidden_for_nazoratchi_full_for_founder_and_moliyachi(bot_dp):
    main, bot = bot_dp
    _make_kassir(111, branch="Filial-1")
    _make_roles()
    _seed_shift(status="clean_closed")

    sent = await send(main.dp, bot, NAZORATCHI_ID, text="/cashsummary 111")
    nazoratchi_text = " ".join(m.text for m in sent if getattr(m, "text", None))
    assert "KASSA — TEKSHIRUV" in nazoratchi_text and not _has_money(nazoratchi_text)

    for viewer in (FOUNDER_ID, MOLIYACHI_ID):
        sent = await send(main.dp, bot, viewer, text="/cashsummary 111")
        text = " ".join(m.text for m in sent if getattr(m, "text", None))
        assert "KASSA — KUN YAKUNI" in text and "5123456" in text.replace(" ", "")


async def test_cashsummary_own_shift_shows_full_money_to_the_cashier(bot_dp):
    main, bot = bot_dp
    _make_kassir(111, branch="Filial-1")
    _seed_shift(status="clean_closed")

    sent = await send(main.dp, bot, 111, text="/cashsummary")
    text = " ".join(m.text for m in sent if getattr(m, "text", None))
    assert "KASSA — KUN YAKUNI" in text and "5123456" in text.replace(" ", "")


async def test_store_branch_card_cannot_be_opened_by_ordinary_authorized_employee(bot_dp):
    main, bot = bot_dp
    _make_kassir(111, branch="Filial-1")
    _make_roles()
    _seed_shift(status="clean_closed")
    branch_button = next(iter(main._BRANCH_BUTTON_TEXT_TO_NAME))
    branch = main._BRANCH_BUTTON_TEXT_TO_NAME[branch_button]

    for user_id in (111, NAZORATCHI_ID, MOLIYACHI_ID):
        sent = await send(main.dp, bot, user_id, text=branch_button)  # tugma matnini qo'lda yuborish
        text = " ".join(m.text for m in sent if getattr(m, "text", None))
        assert "Aktiv xodimlar" not in text and "Bugungi smena" not in text

    sent = await send(main.dp, bot, FOUNDER_ID, text=branch_button)
    assert "Aktiv xodimlar" in " ".join(m.text for m in sent if getattr(m, "text", None))


async def test_store_branch_shifts_detail_requires_founder_even_with_viewing_branch_in_fsm(bot_dp):
    main, bot = bot_dp
    _make_kassir(111, branch="Filial-1")
    _seed_shift(status="clean_closed")
    branch = next(iter(main._BRANCH_BUTTON_TEXT_TO_NAME.values()))

    ctx = main.dp.fsm.get_context(bot=bot, chat_id=111, user_id=111)
    await ctx.update_data(viewing_branch=branch)  # FSM'ni qo'lda to'ldirish ham yordam bermaydi
    sent = await send(main.dp, bot, 111, text=main._STORE_CARD_SHIFTS_TEXT)
    text = " ".join(m.text for m in sent if getattr(m, "text", None))
    assert "Bugungi smenalar" not in text and not _has_money(text)


async def test_branch_shortage_notice_to_branch_head_and_moliyachi_still_full_card(bot_dp):
    """Hozircha o'zgarmagan xatti-harakat (filial rahbari masalasi alohida hal qilinadi): savdo_boshligi
    va moliyachi to'liq karta oladi, nazoratchi/Founder bu xabarni olmaydi."""
    main, bot = bot_dp
    import cash_shift_bot
    from tests.test_cash_shift_ai_vision import _make_moliyachi, _make_savdo_boshligi

    _make_kassir(111, branch="Filial-1")
    _make_savdo_boshligi(SAVDO_BOSHLIGI_ID, "Filial-1")
    _make_moliyachi(MOLIYACHI_ID)
    _make_roles()
    shift = _seed_shift()

    bot.sent = []
    await cash_shift_bot._notify_branch_shortage(SimpleNamespace(bot=bot), shift)

    assert _has_money(_texts_for(bot, SAVDO_BOSHLIGI_ID)[0]) and _has_money(_texts_for(bot, MOLIYACHI_ID)[0])
    assert _texts_for(bot, NAZORATCHI_ID) == [] and _texts_for(bot, FOUNDER_ID) == []


def test_money_free_summary_has_no_amounts_and_full_summary_unchanged(temp_db):
    import cash_shift_bot

    _make_kassir_profile()
    shift = _seed_shift_sync()
    masked = cash_shift_bot._format_shift_summary(shift, include_money=False)
    full = cash_shift_bot._format_shift_summary(shift)
    assert not _has_money(masked) and "so'm" not in masked
    assert "Jami savdo:" in full and "Farq:" in full and full == cash_shift_bot._format_shift_summary(shift, include_money=True)


def _make_kassir_profile() -> None:
    _make_kassir(111, branch="Filial-1")


def _seed_shift_sync() -> dict:
    return _seed_shift()


async def test_reason_with_money_text_hidden_from_nazoratchi_but_full_for_founder_and_moliyachi(bot_dp, monkeypatch):
    main, bot = bot_dp
    import cash_shift_bot
    import roles
    _make_kassir(111, branch="Filial-1")
    _make_kassir(222, branch="Filial-1")
    _make_roles()
    shift = _seed_shift(status="open")
    reason = "500000 so'm kassadan Aliga berildi, 1 mln qarz"

    bot.sent = []
    await cash_shift_bot._send_discrepancy_alert(SimpleNamespace(bot=bot), shift, 222, reason)
    nazoratchi_text = _texts_for(bot, NAZORATCHI_ID)[0]
    assert "500000" not in nazoratchi_text and "1 mln" not in nazoratchi_text and "qarz" not in nazoratchi_text
    assert f"Sabab: {reason}" in _texts_for(bot, FOUNDER_ID)[0]

    # Moliyachi qabul qiluvchi bo'lsa ham sababni to'liq ko'radi (``_can_see_cash_money``).
    original = roles.find_user_by_role
    monkeypatch.setattr(roles, "find_user_by_role", lambda role_key: MOLIYACHI_ID if role_key == "nazoratchi" else original(role_key))
    bot.sent = []
    await cash_shift_bot._send_discrepancy_alert(SimpleNamespace(bot=bot), shift, 222, reason)
    assert f"Sabab: {reason}" in _texts_for(bot, MOLIYACHI_ID)[0]


async def test_review_message_never_shows_stored_reason_to_nazoratchi(bot_dp):
    main, bot = bot_dp
    import cash_shift_bot
    from repositories import cash_shifts as repo
    _make_kassir(111, branch="Filial-1")
    _make_roles()
    shift = _seed_shift()
    repo.set_discrepancy_reason(shift["id"], "500000 so'm Aliga berildi")
    shift = repo.get_shift(shift["id"])

    bot.sent = []
    await cash_shift_bot._send_shift_for_review(SimpleNamespace(bot=bot), shift)
    nazoratchi_text = _texts_for(bot, NAZORATCHI_ID)[0]
    assert "500000" not in nazoratchi_text and "Aliga" not in nazoratchi_text
