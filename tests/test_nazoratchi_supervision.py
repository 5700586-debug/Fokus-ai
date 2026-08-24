"""VAZIFA + NAZORATCHI + BONUS V1 — 1-bosqich: filial -> aktiv
xodimlar -> xodim kartasi (``nazoratchi_bot.py``)."""

from types import SimpleNamespace

import pytest

from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

_BRANCH = RECRUITING_BRANCH_NAMES[0]
_NAZORATCHI_ID = 555001


def _mock_openai_text(monkeypatch, main, text: str) -> None:
    async def fake_create(**kwargs):
        return SimpleNamespace(output_text=text)

    monkeypatch.setattr(main.openai_client.responses, "create", fake_create)


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


# --------------------------------------------------- 4-bosqich: ish bahosi --


async def test_card_shows_grade_buttons_and_no_grade_placeholder(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700013)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_emp:700013", target_chat_id=_NAZORATCHI_ID)

    assert "hali qo'yilmagan" in sent[0].text
    buttons = {btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row}
    for grade_key in ("bajarilmagan", "chala", "norma", "alo"):
        assert f"nzr_grade:700013:{grade_key}" in buttons


async def test_picking_a_grade_updates_the_card(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700014)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_grade:700014:alo", target_chat_id=_NAZORATCHI_ID)

    assert "3 (A'lo)" in sent[0].text


async def test_regrading_same_day_does_not_double_count_bonus(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700015)
    from services import discipline as discipline_service

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_grade:700015:chala", target_chat_id=_NAZORATCHI_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_grade:700015:alo", target_chat_id=_NAZORATCHI_ID)

    assert discipline_service.get_salary(700015)["bonus_bank"] == 3


async def test_grading_zero_is_allowed_and_shown_as_bajarilmagan(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700016)

    sent = await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data="nzr_grade:700016:bajarilmagan", target_chat_id=_NAZORATCHI_ID
    )

    assert "0 (Bajarilmagan)" in sent[0].text


async def test_existing_baholash_flow_still_only_offers_three_grades(bot_dp):
    """Regressiya: yangi 4-darajali (0/1/2/3) tugma to'plami mavjud
    ``/baholash`` oqimidagi Chala/Norma/A'lo uchtaligini o'zgartirmasligi
    kerak (u hardcoded, ``discipline.GRADE_LABELS``dan dinamik olinmaydi)."""
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700017)

    await send(main.dp, bot, _NAZORATCHI_ID, text="/baholash")
    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="bos:emp:700017", target_chat_id=_NAZORATCHI_ID)

    buttons = [btn.text for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert buttons.count("Chala - 1") + buttons.count("Norma - 2") + buttons.count("A'lo - 3") == 3
    assert not any("Bajarilmagan" in b for b in buttons)


# --------------------------------------------------- 5-bosqich: ball ayirish --


def _add_rule_with_amount(rule_number: int, amount: int, title: str = "Telefon ishlatdi") -> None:
    from services import discipline as discipline_service

    discipline_service.add_rule(rule_number, title, "Ish vaqtida telefon ishlatish taqiqlanadi", created_by=FOUNDER_ID)
    discipline_service.set_rule_penalty_amount(rule_number, amount, updated_by=FOUNDER_ID)


async def test_penalty_menu_shows_placeholder_when_no_rule_has_amount(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700018)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_penalty:700018", target_chat_id=_NAZORATCHI_ID)

    assert "tasdiqlangan ball miqdori bilan nizom bandi yo'q" in sent[0].text
    buttons = [btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert "nzr_penalty_other:700018" in buttons


async def test_penalty_menu_shows_rule_buttons_with_preset_amount(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700019)
    _add_rule_with_amount(3, 30)

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_penalty:700019", target_chat_id=_NAZORATCHI_ID)

    buttons = {btn.text: btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row}
    assert buttons.get("Telefon ishlatdi — -30 ball") == "nzr_penalty_apply:700019:3"


async def test_penalty_apply_deducts_bonus_and_notifies_employee_with_buttons(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700020)
    _add_rule_with_amount(3, 30)
    from services import discipline as discipline_service

    sent = await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data="nzr_penalty_apply:700020:3", target_chat_id=_NAZORATCHI_ID
    )

    assert discipline_service.get_salary(700020)["bonus_bank"] == -30

    employee_texts = [m for m in sent if getattr(m, "chat_id", None) == 700020]
    assert employee_texts
    assert "-30 ball" in employee_texts[0].text
    assert "Telefon ishlatdi" in employee_texts[0].text
    buttons = [btn.callback_data for row in employee_texts[0].reply_markup.inline_keyboard for btn in row]
    assert any(b.startswith("nzr_ack:") for b in buttons)
    assert any(b.startswith("nzr_appeal:") for b in buttons)


async def test_penalty_apply_does_not_touch_fixed_salary(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700021)
    _add_rule_with_amount(3, 30)
    from services import discipline as discipline_service

    discipline_service.set_fixed_salary(700021, 3000000, updated_by=FOUNDER_ID)
    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_penalty_apply:700021:3", target_chat_id=_NAZORATCHI_ID)

    assert discipline_service.get_salary(700021)["fixed_salary"] == 3000000


async def test_penalty_other_reports_to_founder_without_deducting_bonus(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700022)
    from services import discipline as discipline_service

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_penalty_other:700022", target_chat_id=_NAZORATCHI_ID)
    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="Nazoratchini haqorat qildi")

    assert discipline_service.get_salary(700022)["bonus_bank"] == 0
    founder_texts = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert founder_texts
    assert "haqorat qildi" in founder_texts[0].text


async def test_employee_ack_removes_notice_buttons(bot_dp):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700023)
    _add_rule_with_amount(3, 30)

    penalty_sent = await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data="nzr_penalty_apply:700023:3", target_chat_id=_NAZORATCHI_ID
    )
    employee_msg = next(m for m in penalty_sent if getattr(m, "chat_id", None) == 700023)
    penalty_id = next(
        int(btn.callback_data.split(":", 1)[1])
        for row in employee_msg.reply_markup.inline_keyboard
        for btn in row
        if btn.callback_data.startswith("nzr_ack:")
    )

    sent = await send_callback(main.dp, bot, 700023, data=f"nzr_ack:{penalty_id}", target_chat_id=700023)

    from aiogram.methods import EditMessageReplyMarkup

    edits = [m for m in sent if isinstance(m, EditMessageReplyMarkup)]
    assert edits
    assert edits[0].reply_markup is None


# ------------------------------------------------- 6-bosqich: AI nizom match --


async def test_penalty_other_ai_match_asks_for_confirmation_first(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700025)
    _add_rule_with_amount(3, 30)
    from services import discipline as discipline_service

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_penalty_other:700025", target_chat_id=_NAZORATCHI_ID)
    _mock_openai_text(monkeypatch, main, "3")
    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="Ish vaqtida telefonda o'ynardi")

    # AI mos topsa ham, tasdiqlanmaguncha ball ayirilmasligi kerak.
    assert discipline_service.get_salary(700025)["bonus_bank"] == 0
    assert "mos kelishi mumkin" in sent[0].text
    buttons = {btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row}
    assert "nzr_match_yes:700025:3" in buttons
    assert "nzr_match_no:700025" in buttons


async def test_penalty_other_ai_match_confirmed_applies_penalty(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700026)
    _add_rule_with_amount(3, 30)
    from services import discipline as discipline_service

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_penalty_other:700026", target_chat_id=_NAZORATCHI_ID)
    _mock_openai_text(monkeypatch, main, "3")
    await send(main.dp, bot, _NAZORATCHI_ID, text="Ish vaqtida telefonda o'ynardi")

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_match_yes:700026:3", target_chat_id=_NAZORATCHI_ID)

    assert discipline_service.get_salary(700026)["bonus_bank"] == -30
    employee_texts = [m for m in sent if getattr(m, "chat_id", None) == 700026]
    assert employee_texts
    assert "-30 ball" in employee_texts[0].text


async def test_penalty_other_ai_match_rejected_goes_to_founder_with_original_text(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700027)
    _add_rule_with_amount(3, 30)
    from services import discipline as discipline_service

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_penalty_other:700027", target_chat_id=_NAZORATCHI_ID)
    _mock_openai_text(monkeypatch, main, "3")
    await send(main.dp, bot, _NAZORATCHI_ID, text="Aslida bu boshqa narsa edi")

    sent = await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_match_no:700027", target_chat_id=_NAZORATCHI_ID)

    assert discipline_service.get_salary(700027)["bonus_bank"] == 0
    founder_texts = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert founder_texts
    assert "Aslida bu boshqa narsa edi" in founder_texts[0].text


async def test_penalty_other_no_ai_match_falls_back_to_founder_directly(bot_dp, monkeypatch):
    """AI hech qanday bandga mos kelmasligini aytsa (yoki mavjud bandlar
    bilan bog'liq bo'lmasa), avvalgi (5-bosqich) xulq-atvor davom
    etadi — Founderga to'g'ridan-to'g'ri yuboriladi, tasdiqlash
    so'ralmaydi."""
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700028)
    _add_rule_with_amount(3, 30)
    from services import discipline as discipline_service

    await send_callback(main.dp, bot, _NAZORATCHI_ID, data="nzr_penalty_other:700028", target_chat_id=_NAZORATCHI_ID)
    _mock_openai_text(monkeypatch, main, "YOQ")
    sent = await send(main.dp, bot, _NAZORATCHI_ID, text="Mutlaqo aloqasi yo'q holat")

    assert discipline_service.get_salary(700028)["bonus_bank"] == 0
    assert "tasdiqlangan nizom bandiga mos kelmagani" in sent[0].text
    founder_texts = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert founder_texts


async def test_employee_appeal_button_starts_existing_appeal_flow(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_nazoratchi()
    _make_kassir(700024)
    _add_rule_with_amount(3, 30)
    from repositories import discipline as discipline_repo

    penalty_sent = await send_callback(
        main.dp, bot, _NAZORATCHI_ID, data="nzr_penalty_apply:700024:3", target_chat_id=_NAZORATCHI_ID
    )
    employee_msg = next(m for m in penalty_sent if getattr(m, "chat_id", None) == 700024)
    penalty_id = next(
        int(btn.callback_data.split(":", 1)[1])
        for row in employee_msg.reply_markup.inline_keyboard
        for btn in row
        if btn.callback_data.startswith("nzr_appeal:")
    )

    await send_callback(main.dp, bot, 700024, data=f"nzr_appeal:{penalty_id}", target_chat_id=700024)
    _mock_openai_text(monkeypatch, main, "Tavsiya: ko'rib chiqilsin.")
    sent = await send(main.dp, bot, 700024, text="Bu adolatsiz, men ishlatmadim")

    penalty = discipline_repo.get_penalty(penalty_id)
    assert penalty["appeal_status"] == "pending"
    assert penalty["appeal_reason"] == "Bu adolatsiz, men ishlatmadim"

    founder_texts = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert founder_texts
