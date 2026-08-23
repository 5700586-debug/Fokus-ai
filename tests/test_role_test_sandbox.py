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
