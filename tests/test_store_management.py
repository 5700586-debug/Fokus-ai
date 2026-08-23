import pytest

import company_time
from config import FOUNDER_ID
from tests.bot_harness import send

pytestmark = pytest.mark.anyio

_BRANCH = "Filial-1"


@pytest.fixture
def anyio_backend():
    return "asyncio"


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


async def _open_shift(main, bot, user_id: int, opening_balance: str = "0") -> None:
    await send(main.dp, bot, user_id, text="/openshift")
    await send(main.dp, bot, user_id, text=opening_balance)


async def test_store_card_shows_no_data_placeholder_when_branch_is_empty(bot_dp):
    main, bot = bot_dp

    await send(main.dp, bot, FOUNDER_ID, text="🏬 Do'konlar")
    sent = await send(main.dp, bot, FOUNDER_ID, text=f"📍 {_BRANCH}")

    assert f"🏬 {_BRANCH}" in sent[0].text
    assert "0 kishi" in sent[0].text
    assert "Ma'lumot yo'q" in sent[0].text
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert "👥 Xodimlar" in buttons
    assert "💰 Smenalar" in buttons
    assert "⬅️ Do'konlar" in buttons


async def test_store_card_shows_active_employee_count(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)

    await send(main.dp, bot, FOUNDER_ID, text="🏬 Do'konlar")
    sent = await send(main.dp, bot, FOUNDER_ID, text=f"📍 {_BRANCH}")

    assert "1 kishi" in sent[0].text


async def test_store_card_shows_todays_open_shift_status(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    await send(main.dp, bot, FOUNDER_ID, text="🏬 Do'konlar")
    sent = await send(main.dp, bot, FOUNDER_ID, text=f"📍 {_BRANCH}")

    assert "Bugungi smena" in sent[0].text
    assert "Ma'lumot yo'q" not in sent[0].text.split("Bugungi smena")[1].split("\n")[0]


async def test_store_card_employees_subview_shows_name_not_user_id(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)

    await send(main.dp, bot, FOUNDER_ID, text="🏬 Do'konlar")
    await send(main.dp, bot, FOUNDER_ID, text=f"📍 {_BRANCH}")
    sent = await send(main.dp, bot, FOUNDER_ID, text="👥 Xodimlar")

    assert "Valiyev Ali" in sent[0].text
    assert "111" not in sent[0].text
    assert "Kassir" in sent[0].text


async def test_store_card_back_returns_to_branch_list(bot_dp):
    main, bot = bot_dp

    await send(main.dp, bot, FOUNDER_ID, text="🏬 Do'konlar")
    await send(main.dp, bot, FOUNDER_ID, text=f"📍 {_BRANCH}")
    sent = await send(main.dp, bot, FOUNDER_ID, text="⬅️ Do'konlar")

    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert f"📍 {_BRANCH}" in buttons


async def test_global_employees_button_unaffected_when_not_viewing_a_branch(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)

    sent = await send(main.dp, bot, FOUNDER_ID, text="👥 Xodimlar")

    assert sent[0].text == "👥 Xodimlar:"
    buttons = [btn.text for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert any("Valiyev Ali" in text for text in buttons)


async def test_viewing_store_card_does_not_change_employee_or_shift_data(bot_dp):
    main, bot = bot_dp
    import employees
    from services import cash_shift

    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    before_count = len(employees.list_approved_by_branch(_BRANCH))
    before_status = cash_shift.get_open_shift(111, company_time.today().isoformat())["status"]

    await send(main.dp, bot, FOUNDER_ID, text="🏬 Do'konlar")
    await send(main.dp, bot, FOUNDER_ID, text=f"📍 {_BRANCH}")
    await send(main.dp, bot, FOUNDER_ID, text="👥 Xodimlar")
    await send(main.dp, bot, FOUNDER_ID, text="⬅️ Filial")
    await send(main.dp, bot, FOUNDER_ID, text="💰 Smenalar")

    after_count = len(employees.list_approved_by_branch(_BRANCH))
    after_status = cash_shift.get_open_shift(111, company_time.today().isoformat())["status"]

    assert before_count == after_count
    assert before_status == after_status
