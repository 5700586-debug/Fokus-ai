"""VAZIFA + NAZORATCHI + BONUS V1 — 1-bosqich: filial -> aktiv
xodimlar -> xodim kartasi (``nazoratchi_bot.py``)."""

import pytest

from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

_BRANCH = RECRUITING_BRANCH_NAMES[0]
_NAZORATCHI_ID = 555001


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


async def test_filiallar_command_shows_a_button_per_configured_branch(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()

    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="/filiallar")

    buttons = [btn.text for row in sent[0].reply_markup.inline_keyboard for btn in row]
    for name in RECRUITING_BRANCH_NAMES:
        assert f"📍 {name}" in buttons


async def test_ordinary_employee_cannot_use_filiallar(bot_dp):
    main, bot = bot_dp
    _make_kassir(700001)

    sent = await send(main.dp, bot, 700001, text="/filiallar")

    assert not any("Filiallar" in (getattr(m, "text", "") or "") for m in sent)


async def test_empty_branch_shows_no_data_placeholder(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_branch:0", target_chat_id=_NAZORATCHI_ID)

    assert _BRANCH in sent[0].text
    assert "Ma'lumot yo'q" in sent[0].text


async def test_branch_with_employee_shows_paired_employee_buttons(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700002)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_branch:0", target_chat_id=_NAZORATCHI_ID)

    rows = sent[0].reply_markup.inline_keyboard
    employee_row = rows[0]
    assert any("Valiyev" in btn.text for btn in employee_row)
    assert any(btn.callback_data == "nzr_emp:700002" for btn in employee_row)
    assert any(btn.callback_data == "nzr_branches" for row in rows for btn in row)


async def test_tapping_employee_shows_simple_card(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700003)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_emp:700003", target_chat_id=_NAZORATCHI_ID)

    assert "Valiyev" in sent[0].text
    assert _BRANCH in sent[0].text
    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert "nzr_branch:0" in buttons


async def test_card_back_button_returns_to_the_employees_own_branch(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    second_branch = RECRUITING_BRANCH_NAMES[1] if len(RECRUITING_BRANCH_NAMES) > 1 else RECRUITING_BRANCH_NAMES[0]
    _make_kassir(700004, branch=second_branch)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_emp:700004", target_chat_id=_NAZORATCHI_ID)

    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    expected_index = RECRUITING_BRANCH_NAMES.index(second_branch)
    assert f"nzr_branch:{expected_index}" in buttons


async def test_unknown_employee_id_shows_alert_not_crash(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_emp:999999", target_chat_id=_NAZORATCHI_ID)

    assert sent


# --------------------------------------------------- 2-bosqich: vazifalar --


async def test_card_shows_no_data_placeholder_when_no_tasks_assigned(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700005)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_emp:700005", target_chat_id=_NAZORATCHI_ID)

    assert "Doimiy vazifalar: Ma'lumot yo'q" in sent[0].text


async def test_card_shows_assigned_tasks(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700006)
    from services import tasks as tasks_service

    tasks_service.assign_task_to_employee("Ombor", 700006, assigned_by=FOUNDER_ID)
    tasks_service.assign_task_to_employee("Suv to'ldirish", 700006, assigned_by=FOUNDER_ID)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_emp:700006", target_chat_id=_NAZORATCHI_ID)

    assert "Ombor" in sent[0].text
    assert "Suv to'ldirish" in sent[0].text


async def test_vazifabiriktir_founder_only(bot_dp):
    main, bot = bot_dp
    _make_kassir(700007)

    sent = await send(main.dp, bot, 700007, text="/vazifabiriktir 700007 Ombor")

    assert not any("biriktirildi" in (getattr(m, "text", "") or "") for m in sent)


async def test_vazifabiriktir_assigns_task_visible_on_card(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700008)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/vazifabiriktir 700008 Ombor")
    assert "biriktirildi" in sent[0].text

    card = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_emp:700008", target_chat_id=_NAZORATCHI_ID)
    assert "Ombor" in card[0].text


async def test_vazifabekor_removes_task_from_card(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700009)
    from services import tasks as tasks_service

    tasks_service.assign_task_to_employee("Ombor", 700009, assigned_by=FOUNDER_ID)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/vazifabekor 700009 Ombor")
    assert "olib tashlandi" in sent[0].text


# --------------------------------------------------- 3-bosqich: vaqt bonusi --


async def test_card_shows_time_bonus_button_when_not_yet_confirmed(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700010)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_emp:700010", target_chat_id=_NAZORATCHI_ID)

    assert "hali tasdiqlanmagan" in sent[0].text
    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert "nzr_timebonus:700010" in buttons


async def test_confirming_time_bonus_updates_card_and_hides_button(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700011)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_timebonus:700011", target_chat_id=_NAZORATCHI_ID)

    assert "✅ berildi" in sent[0].text
    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert "nzr_timebonus:700011" not in buttons


async def test_double_click_on_time_bonus_button_does_not_duplicate(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700012)
    from services import time_bonus as time_bonus_service

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_timebonus:700012", target_chat_id=_NAZORATCHI_ID)
    first_confirmed_by = time_bonus_service.get_today_status(700012)["confirmed_by"]

    second = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_timebonus:700012", target_chat_id=_NAZORATCHI_ID)

    status = time_bonus_service.get_today_status(700012)
    assert status["confirmed_by"] == first_confirmed_by
    assert second  # ikkinchi bosish ham javob beradi (masalan "allaqachon" toast)

    card = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_emp:700009", target_chat_id=_NAZORATCHI_ID)
    assert "Ma'lumot yo'q" in card[0].text
