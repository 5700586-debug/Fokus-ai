from types import SimpleNamespace

import pytest

import discipline_bot
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


def _set_role(user_id: int, role_key: str) -> None:
    from roles import set_role

    set_role(user_id, role_key, set_by=FOUNDER_ID)


def _mock_openai_text(monkeypatch, main, text: str) -> None:
    async def fake_create(**kwargs):
        return SimpleNamespace(output_text=text)

    monkeypatch.setattr(main.openai_client.responses, "create", fake_create)


async def test_baholash_denied_for_employee_without_permission(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="/baholash")
    _assert_denied(sent)


async def test_baholash_allowed_for_nazoratchi(bot_dp):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 1, text="/baholash")
    assert "Xodimni tanlang" in sent[0].text


async def test_grading_flow_updates_bonus_bank(bot_dp, monkeypatch):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    sent = await send_callback(main.dp, bot, 1, data="bos:emp:111:0", target_chat_id=1)
    assert "Baho tanlang" in sent[0].text

    sent = await send_callback(main.dp, bot, 1, data=f"bos:grade:111:{discipline_bot.discipline.GRADE_ALO}", target_chat_id=1)
    assert "3 ball" in sent[0].text

    from services import discipline

    assert discipline.get_salary(111)["bonus_bank"] == 3


async def test_grading_denied_for_non_supervisor_callback(bot_dp):
    main, bot = bot_dp
    _set_role(999, "kassir")
    _set_role(111, "haydovchi")

    await send_callback(
        main.dp, bot, 999, data=f"bos:grade:111:{discipline_bot.discipline.GRADE_ALO}", target_chat_id=999
    )

    from services import discipline

    assert discipline.get_salary(111)["bonus_bank"] == 0


async def test_penalty_flow_happy_path_notifies_employee(bot_dp, monkeypatch):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    from services import discipline

    discipline.add_rule(3, "Kechikish", "Ishga kechikish taqiqlanadi", created_by=FOUNDER_ID)
    _mock_openai_text(monkeypatch, main, "✅ Mos keladi.")

    await send_callback(main.dp, bot, 1, data="bos:pen:111:20", target_chat_id=1)
    sent = await send(main.dp, bot, 1, text="3-nizom")

    texts = [m.text for m in sent]
    assert any("jarima qo'llanildi" in (t or "") for t in texts)
    assert discipline.get_salary(111)["bonus_bank"] == -20

    employee_texts = [m.text for m in sent if getattr(m, "chat_id", None) == 111]
    assert any("jarima qo'llanildi" in (t or "") for t in employee_texts)


async def test_penalty_flow_unknown_rule_shows_error_and_stays_in_state(bot_dp, monkeypatch):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    await send_callback(main.dp, bot, 1, data="bos:pen:111:10", target_chat_id=1)
    sent = await send(main.dp, bot, 1, text="404-nizom")

    assert "topilmadi" in sent[0].text

    from services import discipline

    assert discipline.get_salary(111)["bonus_bank"] == 0


async def test_penalty_entry_skipped_when_already_pending_for_same_nazoratchi(bot_dp, monkeypatch):
    """Atomic guard: agar shu nazoratchi uchun jarima jarayoni allaqachon
    "band" bo'lsa (masalan deyarli bir vaqtda kelgan ikkinchi xabar hali
    AI tasdig'ini kutayotganda), keyingi xabar jarimani QAYTA
    qo'llamasligi kerak — aks holda ``bonus_bank`` ikki marta kamayib
    ketishi mumkin edi (qarang ``_PENDING_PENALTY_APPLICATIONS``).
    """
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    from services import discipline

    discipline.add_rule(3, "Kechikish", "Ishga kechikish taqiqlanadi", created_by=FOUNDER_ID)
    _mock_openai_text(monkeypatch, main, "✅ Mos keladi.")

    await send_callback(main.dp, bot, 1, data="bos:pen:111:20", target_chat_id=1)

    # "Boshqa parallel xabar" hali qayta ishlanayotganini simulyatsiya qilamiz.
    discipline_bot._PENDING_PENALTY_APPLICATIONS.add(1)
    try:
        sent = await send(main.dp, bot, 1, text="3-nizom")
    finally:
        discipline_bot._PENDING_PENALTY_APPLICATIONS.discard(1)

    assert sent == []  # hech qanday javob yuborilmadi, jarayon darhol to'xtadi
    assert discipline.get_salary(111)["bonus_bank"] == 0  # jarima qo'llanmadi


async def test_kunniyop_close_day_then_reports_already_closed(bot_dp):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 1, text="/kunniyop")
    assert "yopildi" in sent[0].text

    sent = await send(main.dp, bot, 1, text="/kunniyop")
    assert "allaqachon yopilgan" in sent[0].text


async def test_addnizom_founder_only(bot_dp):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")

    sent = await send(main.dp, bot, 1, text="/addnizom 3 Sarlavha | Matn")
    _assert_denied(sent)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/addnizom 3 Kechikish | Kechikish taqiqlanadi")
    assert "qo'shildi" in sent[0].text


async def test_appeal_full_flow_approved_refunds_bonus_bank(bot_dp, monkeypatch):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    from services import discipline

    discipline.add_rule(3, "Kechikish", "Ishga kechikish taqiqlanadi", created_by=FOUNDER_ID)
    _mock_openai_text(monkeypatch, main, "✅ Mos keladi.")

    await send_callback(main.dp, bot, 1, data="bos:pen:111:10", target_chat_id=1)
    await send(main.dp, bot, 1, text="3-nizom")
    assert discipline.get_salary(111)["bonus_bank"] == -10

    sent = await send(main.dp, bot, 111, text="/apellyatsiya")
    keyboard = sent[0].reply_markup.inline_keyboard
    penalty_callback_data = keyboard[0][0].callback_data

    _mock_openai_text(monkeypatch, main, "Tavsiya: jarima bekor qilinsin.")
    await send_callback(main.dp, bot, 111, data=penalty_callback_data, target_chat_id=111)

    sent = await send(main.dp, bot, 111, text="Men kasal edim, dalilim bor")
    founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert len(founder_messages) == 1
    decide_keyboard = founder_messages[0].reply_markup.inline_keyboard
    approve_callback_data = decide_keyboard[0][0].callback_data
    assert approve_callback_data.endswith(":approved")

    sent = await send_callback(main.dp, bot, FOUNDER_ID, data=approve_callback_data, target_chat_id=FOUNDER_ID)
    employee_messages = [m for m in sent if getattr(m, "chat_id", None) == 111]
    assert any("qondirildi" in (m.text or "") for m in employee_messages)
    assert discipline.get_salary(111)["bonus_bank"] == 0


async def test_apellyatsiya_with_no_penalties_tells_user(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="/apellyatsiya")
    assert "topilmadi" in sent[0].text


async def test_mymaosh_shows_own_balance_only(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    from services import discipline

    discipline.adjust_bonus_bank(111, 5, "sinov", "test", None)

    sent = await send(main.dp, bot, 111, text="/mymaosh")
    assert "5 ball" in sent[0].text
