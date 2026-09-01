import pytest

from config import FOUNDER_ID
from tests.bot_harness import send

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _set_role(user_id: int, role_key: str) -> None:
    from roles import set_role

    set_role(user_id, role_key, set_by=FOUNDER_ID)


async def test_role_test_button_does_nothing_for_ordinary_user(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main, "ENVIRONMENT", "test")
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="🧪 Rol testi")

    assert sent == []


async def test_founder_sees_role_test_button_only_in_test_environment(bot_dp, monkeypatch):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/start")
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert "🧪 Rol testi" not in buttons

    monkeypatch.setattr(main, "ENVIRONMENT", "test")
    sent = await send(main.dp, bot, FOUNDER_ID, text="/start")
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert "🧪 Rol testi" in buttons


async def test_founder_can_open_role_picker_in_test_environment(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main, "ENVIRONMENT", "test")

    sent = await send(main.dp, bot, FOUNDER_ID, text="🧪 Rol testi")

    assert "TEST SANDBOX" in sent[0].text
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert "Kassir" in buttons
    assert "Nazoratchi" in buttons


async def test_selecting_preview_role_does_not_touch_real_role_or_allowed_users(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main, "ENVIRONMENT", "test")
    from roles import get_role, list_users

    await send(main.dp, bot, FOUNDER_ID, text="🧪 Rol testi")
    await send(main.dp, bot, FOUNDER_ID, text="Kassir")

    assert get_role(FOUNDER_ID) == "founder"
    assert FOUNDER_ID not in list_users()


async def test_preview_kassir_menu_shows_kassa_category(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main, "ENVIRONMENT", "test")

    await send(main.dp, bot, FOUNDER_ID, text="🧪 Rol testi")
    sent = await send(main.dp, bot, FOUNDER_ID, text="Kassir")

    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert "💰 Kassa" in buttons
    assert "⬅️ Testdan chiqish" in buttons


async def test_preview_nazoratchi_menu_shows_nazoratchi_category(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main, "ENVIRONMENT", "test")

    await send(main.dp, bot, FOUNDER_ID, text="🧪 Rol testi")
    sent = await send(main.dp, bot, FOUNDER_ID, text="Nazoratchi")

    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert "🧑‍💼 Nazoratchi" in buttons


async def test_preview_mutating_action_is_blocked_and_writes_nothing(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main, "ENVIRONMENT", "test")
    import company_time
    from services import cash_shift

    await send(main.dp, bot, FOUNDER_ID, text="🧪 Rol testi")
    await send(main.dp, bot, FOUNDER_ID, text="Kassir")
    await send(main.dp, bot, FOUNDER_ID, text="💰 Kassa")
    sent = await send(main.dp, bot, FOUNDER_ID, text="🟢 Smenani boshlash")

    assert "bazaga yozilmadi" in sent[0].text
    assert cash_shift.get_open_shift(FOUNDER_ID, company_time.today().isoformat()) is None


async def test_exit_preview_returns_real_founder_menu(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main, "ENVIRONMENT", "test")

    await send(main.dp, bot, FOUNDER_ID, text="🧪 Rol testi")
    await send(main.dp, bot, FOUNDER_ID, text="Kassir")
    sent = await send(main.dp, bot, FOUNDER_ID, text="⬅️ Testdan chiqish")

    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert "👤 Xodim qo'shish" in buttons
    assert "💰 Kassa" not in buttons


async def test_exit_from_inside_category_subview_then_start_then_dokonlar(bot_dp, monkeypatch):
    """Real E2E'da topilgan bug: kategoriya ichidan (masalan "💰 Kassa")
    "⬅️ Testdan chiqish" bosilsa, keyingi /start va "🏬 Do'konlar"
    bosilganda ham sandbox hali aktiv bo'lib qolib, haqiqiy Founder
    tugmalarini bloklashi mumkin edi.
    """
    main, bot = bot_dp
    monkeypatch.setattr(main, "ENVIRONMENT", "test")

    await send(main.dp, bot, FOUNDER_ID, text="🧪 Rol testi")
    await send(main.dp, bot, FOUNDER_ID, text="Kassir")
    await send(main.dp, bot, FOUNDER_ID, text="💰 Kassa")
    exit_sent = await send(main.dp, bot, FOUNDER_ID, text="⬅️ Testdan chiqish")

    exit_buttons = [btn.text for row in exit_sent[0].reply_markup.keyboard for btn in row]
    assert "👤 Xodim qo'shish" in exit_buttons

    start_sent = await send(main.dp, bot, FOUNDER_ID, text="/start")
    assert "Assalomu alaykum, Muhammadiy" in start_sent[0].text

    stores_sent = await send(main.dp, bot, FOUNDER_ID, text="🏬 Do'konlar")
    assert "bazaga yozilmadi" not in stores_sent[0].text
    store_buttons = [btn.text for row in stores_sent[0].reply_markup.keyboard for btn in row]
    assert "⬅️ Orqaga" in store_buttons


async def test_start_while_preview_active_safely_escapes_sandbox(bot_dp, monkeypatch):
    """Real bug: agar aynan '⬅️ Testdan chiqish' matni yetib bormasa
    (sandbox 'qotib' qolgan holatda), /start baribir xavfsiz tarzda
    sandboxdan chiqib, haqiqiy Founder salomini berishi kerak — faqat
    bitta aniq tugma emas, har qanday haqiqiy tizim navigatsiyasi
    zaxira chiqish yo'li bo'lishi kerak.
    """
    main, bot = bot_dp
    monkeypatch.setattr(main, "ENVIRONMENT", "test")

    await send(main.dp, bot, FOUNDER_ID, text="🧪 Rol testi")
    await send(main.dp, bot, FOUNDER_ID, text="Kassir")
    await send(main.dp, bot, FOUNDER_ID, text="💰 Kassa")

    sent = await send(main.dp, bot, FOUNDER_ID, text="/start")

    assert "Assalomu alaykum, Muhammadiy" in sent[0].text
    assert "bazaga yozilmadi" not in sent[0].text


async def test_founder_menu_button_while_preview_active_safely_escapes_and_runs(bot_dp, monkeypatch):
    """Founderga xos menyu tugmasi (masalan '🏬 Do'konlar') preview
    aktiv paytda bosilsa ham, faqat blok qilinmasdan sandboxni tozalab
    haqiqiy amalni bajarishi kerak (bir tugma bosishda chiqish+ishlash).
    """
    main, bot = bot_dp
    monkeypatch.setattr(main, "ENVIRONMENT", "test")

    await send(main.dp, bot, FOUNDER_ID, text="🧪 Rol testi")
    await send(main.dp, bot, FOUNDER_ID, text="Kassir")

    sent = await send(main.dp, bot, FOUNDER_ID, text="🏬 Do'konlar")

    assert "bazaga yozilmadi" not in sent[0].text
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert "⬅️ Orqaga" in buttons

    from roles import get_role
    assert get_role(FOUNDER_ID) == "founder"


async def test_slash_command_while_picking_role_safely_escapes(bot_dp, monkeypatch):
    """Rol tanlash ekranida (hali rol tanlanmagan) ham '/' buyrug'i
    xavfsiz chiqish yo'li bo'lishi kerak."""
    main, bot = bot_dp
    monkeypatch.setattr(main, "ENVIRONMENT", "test")

    await send(main.dp, bot, FOUNDER_ID, text="🧪 Rol testi")
    sent = await send(main.dp, bot, FOUNDER_ID, text="/start")

    assert "Assalomu alaykum, Muhammadiy" in sent[0].text
    assert "rollardan birini tanlang" not in sent[0].text


_EXPECTED_SHARED_PREVIEW_ROWS = [
    ["⭐ Yulduzlarim", "💰 Oyligim"],
    ["📅 Grafik so'rovi", "🏆 Bugungi o'rnim"],
    ["🏅 Oylik reyting", "📋 Nizomlar"],
    ["🙋 E'tirozim bor", "🔙 Orqaga"],
    ["⬅️ Testdan chiqish"],
]


async def test_preview_shared_category_uses_paired_friendly_buttons(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main, "ENVIRONMENT", "test")

    await send(main.dp, bot, FOUNDER_ID, text="🧪 Rol testi")
    await send(main.dp, bot, FOUNDER_ID, text="Kassir")

    sent = await send(main.dp, bot, FOUNDER_ID, text="⭐ Mening natijalarim")
    rows = [[btn.text for btn in row] for row in sent[0].reply_markup.keyboard]

    assert rows == _EXPECTED_SHARED_PREVIEW_ROWS
    assert not any("/" in btn for row in rows for btn in row)


async def test_friendly_shared_button_is_blocked_inside_preview(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main, "ENVIRONMENT", "test")

    await send(main.dp, bot, FOUNDER_ID, text="🧪 Rol testi")
    await send(main.dp, bot, FOUNDER_ID, text="Kassir")
    await send(main.dp, bot, FOUNDER_ID, text="⭐ Mening natijalarim")

    sent = await send(main.dp, bot, FOUNDER_ID, text="⭐ Yulduzlarim")

    assert "bazaga yozilmadi" in sent[0].text
    assert "Joriy yulduzlar" not in sent[0].text
    rows = [[btn.text for btn in row] for row in sent[0].reply_markup.keyboard]
    assert rows == _EXPECTED_SHARED_PREVIEW_ROWS
