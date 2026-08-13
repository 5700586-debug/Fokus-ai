import pytest

from config import FOUNDER_ID
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _set_role(user_id: int, role_key: str) -> None:
    from roles import set_role

    set_role(user_id, role_key, set_by=FOUNDER_ID)


# ------------------------------------------------ FSM-holatdan qochish --


async def test_stale_penalty_state_does_not_swallow_a_different_command(bot_dp):
    """Regression: nazoratchi jarima uchun nizom raqamini kutayotgan
    holatda (``PenaltyStates.waiting_rule``) boshqa buyruq (``/kunniyop``)
    yuborsa, u eski holat tomonidan "nizom raqami" deb noto'g'ri
    talqin qilinmasdan, o'zining haqiqiy buyrug'i sifatida ishlashi kerak.
    """
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    await send_callback(main.dp, bot, 1, data="bos:pen:111:10", target_chat_id=1)

    sent = await send(main.dp, bot, 1, text="/kunniyop")
    assert any("yopildi" in (m.text or "") for m in sent), [m.text for m in sent]

    from services import discipline

    assert discipline.get_salary(111)["bonus_bank"] == 0  # jarima qo'llanmadi


async def test_stale_penalty_state_does_not_swallow_start(bot_dp):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    await send_callback(main.dp, bot, 1, data="bos:pen:111:10", target_chat_id=1)

    sent = await send(main.dp, bot, 1, text="/start")
    assert any("Rolingiz" in (m.text or "") or "Asoschi" in (m.text or "") for m in sent)


async def test_cancel_button_clears_stale_state(bot_dp):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    await send_callback(main.dp, bot, 1, data="bos:pen:111:10", target_chat_id=1)

    sent = await send(main.dp, bot, 1, text="❌ Bekor qilish")
    assert "bekor qilindi" in sent[0].text.lower()

    # Holat tozalangani uchun "3-nizom" endi hech qanday jarima
    # oqimiga tegishli emas — oddiy matn sifatida e'tiborsiz qolishi kerak.
    sent = await send(main.dp, bot, 1, text="3-nizom")
    assert sent == []

    from services import discipline

    assert discipline.get_salary(111)["bonus_bank"] == 0


# ------------------------------------------------------------- menyu --


async def test_start_shows_role_specific_category_for_kassir(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="/start")
    buttons = {btn.text for row in sent[0].reply_markup.keyboard for btn in row}

    assert "💰 Kassa" in buttons
    assert "⭐ Mening natijalarim" in buttons
    assert "👑 Asoschi" not in buttons


async def test_start_shows_founder_category_for_founder(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/start")
    buttons = {btn.text for row in sent[0].reply_markup.keyboard for btn in row}

    assert "👑 Asoschi" in buttons
    assert "💰 Kassa" not in buttons


async def test_category_button_lists_commands_and_back(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="💰 Kassa")
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]

    assert any(b.startswith("/openshift") for b in buttons)
    assert any(b.startswith("/closeshift") for b in buttons)
    assert any(b.startswith("/expense") for b in buttons)
    assert "🔙 Orqaga" in buttons


async def test_category_command_button_triggers_real_command(bot_dp):
    """Bo'lim ichidagi tugma matni haqiqiy buyruq bilan boshlanadi va
    bosilganda o'zining mavjud handleri ishga tushishi kerak (yangi
    biznes mantiq emas, faqat navigatsiya).
    """
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="/openshift 0")
    assert sent != []


async def test_back_button_returns_to_main_menu(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    await send(main.dp, bot, 111, text="💰 Kassa")
    sent = await send(main.dp, bot, 111, text="🔙 Orqaga")

    buttons = {btn.text for row in sent[0].reply_markup.keyboard for btn in row}
    assert "💰 Kassa" in buttons
    assert "⭐ Mening natijalarim" in buttons


async def test_sotuvchi_menu_has_no_role_category_button(bot_dp):
    """``sotuvchi`` rolida ``ROLE_PERMISSIONS``da bironta amal yo'q —
    menyu markaziy permission-matrixdan shakllangani uchun uning uchun
    HECH QANDAY bo'lim tugmasi chiqmasligi kerak (faqat AI/umumiy/
    sozlamalar), moliya/kassa/savdo tugmalari umuman ko'rinmaydi.
    """
    main, bot = bot_dp
    _set_role(222, "sotuvchi")

    sent = await send(main.dp, bot, 222, text="/start")
    buttons = {btn.text for row in sent[0].reply_markup.keyboard for btn in row}

    role_category_buttons = set(main._CATEGORY_LABELS.values())
    assert buttons & role_category_buttons == set()
    assert "⭐ Mening natijalarim" in buttons
    assert "🤖 AI Tahlil" in buttons


async def test_stale_category_button_after_role_change_is_rejected(bot_dp):
    """Foydalanuvchi "💰 Kassa" bo'limini ko'rgandan keyin roli
    o'zgartirilsa (endi kassir emas), mijozda keshlangan eski tugma
    matnini qayta yuborsa ham backend uni endi bermasligi kerak — bo'sh
    bo'lim o'rniga asosiy menyuga xushmuomalalik bilan qaytariladi.
    """
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="💰 Kassa")
    assert any(b.startswith("/openshift") for row in sent[0].reply_markup.keyboard for b in [row[0].text])

    _set_role(111, "sotuvchi")

    sent = await send(main.dp, bot, 111, text="💰 Kassa")
    assert "Asosiy menyu" in sent[0].text
    buttons = {btn.text for row in sent[0].reply_markup.keyboard for btn in row}
    assert "💰 Kassa" not in buttons
