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


def _approved_profile(user_id: int, branch: str | None = None) -> None:
    import employees
    from config import RECRUITING_BRANCH_NAMES

    employees.submit_profile(
        user_id,
        {"familiya": "Karimov", "ism": "Vali", "branch": branch or RECRUITING_BRANCH_NAMES[0],
         "role_key": "kassir", "contacts": []},
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


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
    assert "Filialni tanlang" in sent[0].text and "📅 Ish kuni:" in sent[0].text  # hamma xodim emas — avval filial


async def test_grading_flow_updates_bonus_bank(bot_dp, monkeypatch):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")
    _approved_profile(111)

    today_ymd = company_time.today().strftime("%Y%m%d")
    sent = await send_callback(main.dp, bot, 1, data=f"bos:emp:111:{today_ymd}", target_chat_id=1)
    assert "Baho tanlang" in sent[0].text

    sent = await send_callback(
        main.dp, bot, 1, data=f"bos:grade:111:{discipline_bot.discipline.GRADE_ALO}:{today_ymd}", target_chat_id=1
    )
    assert "3 ball" in next(m for m in sent if m.__class__.__name__ == "EditMessageText").text

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
    assert any("ball ayirildi" in (t or "") for t in texts)
    assert discipline.get_salary(111)["bonus_bank"] == -20

    employee_texts = [m.text for m in sent if getattr(m, "chat_id", None) == 111]
    assert any("ball ayirildi" in (t or "") for t in employee_texts)


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


# --------------------------------------------- nizom holati (rule learning) --

_RULE_LEARNING_EMPLOYEE_ID = 111
_RULE_NUMBER = 3


def _add_penalty_rule() -> None:
    from services import discipline as discipline_service

    discipline_service.add_rule(_RULE_NUMBER, "Kechikish", "Ishga kechikish taqiqlanadi", created_by=FOUNDER_ID)


def _create_penalty(employee_id: int = _RULE_LEARNING_EMPLOYEE_ID) -> int:
    from services import discipline as discipline_service

    result = discipline_service.apply_penalty(
        employee_id, 1, "2026-09-02", 10, _RULE_NUMBER, comment=None, ai_note=None
    )
    return result["penalty_id"]


def _set_progress_completed_at(progress_id: int, value: str) -> None:
    import db

    conn = db.get_connection()
    try:
        conn.execute(
            "UPDATE rule_learning_progress SET completed_at = ?, understood_confirmed_at = ? WHERE id = ?",
            (value, value, progress_id),
        )
        conn.commit()
    finally:
        conn.close()


def _set_penalty_created_at(penalty_id: int, value: str) -> None:
    import db

    conn = db.get_connection()
    try:
        conn.execute("UPDATE discipline_penalties SET created_at = ? WHERE id = ?", (value, penalty_id))
        conn.commit()
    finally:
        conn.close()


def test_rule_learning_status_not_learned():
    _add_penalty_rule()
    penalty_id = _create_penalty()

    context, line = discipline_bot._rule_learning_status(penalty_id)

    assert context["status"] == "not_learned"
    assert line == "\n📚 Nizom holati: nizom o'rganilishi boshlanmagan"


def test_rule_learning_status_learning_incomplete():
    from services import rule_learning

    _add_penalty_rule()
    rule_learning.enroll(_RULE_LEARNING_EMPLOYEE_ID)
    rule_learning.get_current_rule(_RULE_LEARNING_EMPLOYEE_ID)  # progress yaratiladi, tugallanmagan
    penalty_id = _create_penalty()

    context, line = discipline_bot._rule_learning_status(penalty_id)

    assert context["status"] == "learning_incomplete"
    assert line == "\n📚 Nizom holati: o'rganish tugallanmagan"


def test_rule_learning_status_understood_before_penalty():
    from services import rule_learning

    _add_penalty_rule()
    rule_learning.enroll(_RULE_LEARNING_EMPLOYEE_ID)
    progress = rule_learning.get_current_rule(_RULE_LEARNING_EMPLOYEE_ID)
    assert rule_learning.confirm_read(progress["id"]) is True
    assert rule_learning.confirm_understood(_RULE_LEARNING_EMPLOYEE_ID, progress["id"]) is True
    _set_progress_completed_at(progress["id"], "2026-01-01T00:00:00+00:00")

    penalty_id = _create_penalty()
    _set_penalty_created_at(penalty_id, "2026-01-02T00:00:00+00:00")

    context, line = discipline_bot._rule_learning_status(penalty_id)

    assert context["status"] == "understood_before_penalty"
    assert line == "\n📚 Nizom holati: ball ayirilishidan oldin tushunilgan"


def test_rule_learning_status_understood_after_penalty():
    from services import rule_learning

    _add_penalty_rule()
    penalty_id = _create_penalty()
    _set_penalty_created_at(penalty_id, "2026-01-01T00:00:00+00:00")

    rule_learning.enroll(_RULE_LEARNING_EMPLOYEE_ID)
    progress = rule_learning.get_current_rule(_RULE_LEARNING_EMPLOYEE_ID)
    assert rule_learning.confirm_read(progress["id"]) is True
    assert rule_learning.confirm_understood(_RULE_LEARNING_EMPLOYEE_ID, progress["id"]) is True
    _set_progress_completed_at(progress["id"], "2026-01-02T00:00:00+00:00")

    context, line = discipline_bot._rule_learning_status(penalty_id)

    assert context["status"] == "understood_after_penalty"
    assert line == "\n📚 Nizom holati: ball ayirilishidan keyin tushunilgan"


def test_rule_learning_status_lookup_error_returns_none_and_empty_line(monkeypatch):
    def _raise(*args, **kwargs):
        raise RuntimeError("simulyatsiya")

    monkeypatch.setattr(discipline_bot.discipline, "get_penalty_learning_context", _raise)

    context, line = discipline_bot._rule_learning_status(999999)

    assert context is None
    assert line == ""


async def test_rule_learning_line_appears_in_both_penalty_messages(bot_dp, monkeypatch):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    from services import discipline

    discipline.add_rule(_RULE_NUMBER, "Kechikish", "Ishga kechikish taqiqlanadi", created_by=FOUNDER_ID)
    _mock_openai_text(monkeypatch, main, "✅ Mos keladi.")

    await send_callback(main.dp, bot, 1, data="bos:pen:111:20", target_chat_id=1)
    sent = await send(main.dp, bot, 1, text=f"{_RULE_NUMBER}-nizom")

    expected_line = "\n📚 Nizom holati: nizom o'rganilishi boshlanmagan"
    supervisor_texts = [m.text for m in sent if getattr(m, "chat_id", None) == 1 and m.text]
    employee_texts = [m.text for m in sent if getattr(m, "chat_id", None) == 111 and m.text]

    assert any(t.endswith(expected_line) for t in supervisor_texts)
    assert any(t.endswith(expected_line) for t in employee_texts)


async def test_rule_learning_lookup_error_does_not_break_penalty_flow(bot_dp, monkeypatch):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    from services import discipline

    discipline.add_rule(_RULE_NUMBER, "Kechikish", "Ishga kechikish taqiqlanadi", created_by=FOUNDER_ID)
    _mock_openai_text(monkeypatch, main, "✅ Mos keladi.")

    def _raise(*args, **kwargs):
        raise RuntimeError("simulyatsiya")

    monkeypatch.setattr(discipline_bot.discipline, "get_penalty_learning_context", _raise)

    await send_callback(main.dp, bot, 1, data="bos:pen:111:20", target_chat_id=1)
    sent = await send(main.dp, bot, 1, text=f"{_RULE_NUMBER}-nizom")

    texts = [m.text for m in sent if m.text]
    assert any("ball ayirildi" in t for t in texts)
    assert not any("Nizom holati" in t for t in texts)
    assert discipline.get_salary(111)["bonus_bank"] == -20

    employee_texts = [m.text for m in sent if getattr(m, "chat_id", None) == 111 and m.text]
    assert any("ball ayirildi" in t for t in employee_texts)


def _understand_rule_before_penalty() -> None:
    from services import rule_learning

    rule_learning.enroll(_RULE_LEARNING_EMPLOYEE_ID)
    progress = rule_learning.get_current_rule(_RULE_LEARNING_EMPLOYEE_ID)
    assert rule_learning.confirm_read(progress["id"]) is True
    assert rule_learning.confirm_understood(_RULE_LEARNING_EMPLOYEE_ID, progress["id"]) is True
    _set_progress_completed_at(progress["id"], "2026-01-01T00:00:00+00:00")


async def test_founder_alert_sent_once_when_understood_before_penalty(bot_dp, monkeypatch):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    from services import discipline

    discipline.add_rule(_RULE_NUMBER, "Kechikish", "Ishga kechikish taqiqlanadi", created_by=FOUNDER_ID)
    _mock_openai_text(monkeypatch, main, "✅ Mos keladi.")
    _understand_rule_before_penalty()

    call_count = 0
    original_get_context = discipline.get_penalty_learning_context

    def _counting_get_context(penalty_id):
        nonlocal call_count
        call_count += 1
        return original_get_context(penalty_id)

    monkeypatch.setattr(discipline_bot.discipline, "get_penalty_learning_context", _counting_get_context)

    await send_callback(main.dp, bot, 1, data="bos:pen:111:20", target_chat_id=1)
    sent = await send(main.dp, bot, 1, text=f"{_RULE_NUMBER}-nizom")

    assert call_count == 1

    founder_texts = [m.text for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID and m.text]
    assert founder_texts == [
        "🚨 Nizom buzilishi\nXodim: 111\n"
        f"Nizom: {_RULE_NUMBER} — Kechikish\n"
        "Ball: -20\n📚 Xodim bu nizomni oldin tushunganini tasdiqlagan."
    ]


async def test_no_founder_alert_when_not_learned(bot_dp, monkeypatch):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    from services import discipline

    discipline.add_rule(_RULE_NUMBER, "Kechikish", "Ishga kechikish taqiqlanadi", created_by=FOUNDER_ID)
    _mock_openai_text(monkeypatch, main, "✅ Mos keladi.")

    await send_callback(main.dp, bot, 1, data="bos:pen:111:20", target_chat_id=1)
    sent = await send(main.dp, bot, 1, text=f"{_RULE_NUMBER}-nizom")

    founder_texts = [m.text for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID and m.text]
    assert founder_texts == []


async def test_no_founder_alert_when_learning_incomplete(bot_dp, monkeypatch):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    from services import discipline
    from services import rule_learning

    discipline.add_rule(_RULE_NUMBER, "Kechikish", "Ishga kechikish taqiqlanadi", created_by=FOUNDER_ID)
    _mock_openai_text(monkeypatch, main, "✅ Mos keladi.")
    rule_learning.enroll(_RULE_LEARNING_EMPLOYEE_ID)
    rule_learning.get_current_rule(_RULE_LEARNING_EMPLOYEE_ID)  # progress bor, tugallanmagan

    await send_callback(main.dp, bot, 1, data="bos:pen:111:20", target_chat_id=1)
    sent = await send(main.dp, bot, 1, text=f"{_RULE_NUMBER}-nizom")

    founder_texts = [m.text for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID and m.text]
    assert founder_texts == []


async def test_no_founder_alert_when_founder_is_the_actor(bot_dp, monkeypatch):
    main, bot = bot_dp
    _set_role(111, "kassir")

    from services import discipline

    discipline.add_rule(_RULE_NUMBER, "Kechikish", "Ishga kechikish taqiqlanadi", created_by=FOUNDER_ID)
    _mock_openai_text(monkeypatch, main, "✅ Mos keladi.")
    _understand_rule_before_penalty()

    await send_callback(main.dp, bot, FOUNDER_ID, data="bos:pen:111:20", target_chat_id=FOUNDER_ID)
    sent = await send(main.dp, bot, FOUNDER_ID, text=f"{_RULE_NUMBER}-nizom")

    founder_texts = [m.text for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID and m.text]
    assert not any("Nizom buzilishi" in t for t in founder_texts)


async def test_founder_alert_send_error_does_not_break_penalty_flow(bot_dp, monkeypatch):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    from services import discipline

    discipline.add_rule(_RULE_NUMBER, "Kechikish", "Ishga kechikish taqiqlanadi", created_by=FOUNDER_ID)
    _mock_openai_text(monkeypatch, main, "✅ Mos keladi.")
    _understand_rule_before_penalty()

    original_send_message = bot.send_message

    async def _selective_fail(chat_id, *args, **kwargs):
        if chat_id == FOUNDER_ID:
            raise RuntimeError("simulyatsiya")
        return await original_send_message(chat_id, *args, **kwargs)

    monkeypatch.setattr(bot, "send_message", _selective_fail)

    await send_callback(main.dp, bot, 1, data="bos:pen:111:20", target_chat_id=1)
    sent = await send(main.dp, bot, 1, text=f"{_RULE_NUMBER}-nizom")

    texts = [m.text for m in sent if m.text]
    assert any("ball ayirildi" in t for t in texts)
    assert discipline.get_salary(111)["bonus_bank"] == -20

    employee_texts = [m.text for m in sent if getattr(m, "chat_id", None) == 111 and m.text]
    assert any("ball ayirildi" in t for t in employee_texts)

    founder_texts = [m.text for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID and m.text]
    assert founder_texts == []


async def test_kunniyop_asks_branch_then_closes_branch_session_then_reports_already_closed(bot_dp):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    from config import RECRUITING_BRANCH_NAMES

    sent = await send(main.dp, bot, 1, text="/kunniyop")
    assert "Qaysi filial nazoratini yopamiz" in sent[0].text
    ymd = discipline_bot._ymd(discipline_bot._today().isoformat())

    sent = await send_callback(main.dp, bot, 1, data=f"bos:close:0:{ymd}", target_chat_id=1)
    assert "yopildi" in sent[0].text and RECRUITING_BRANCH_NAMES[0] in sent[0].text

    sent = await send_callback(main.dp, bot, 1, data=f"bos:close:0:{ymd}", target_chat_id=1)
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


# ------------------------------------------- baho qo'yilgach xodimga xabar --

import asyncio  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError  # noqa: E402
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage  # noqa: E402

import company_time  # noqa: E402
from db import get_connection  # noqa: E402
from services import discipline  # noqa: E402

NAZORATCHI, EMPLOYEE = 1, 111


def _setup() -> None:
    _set_role(NAZORATCHI, "nazoratchi")
    _set_role(EMPLOYEE, "kassir")
    _approved_profile(EMPLOYEE)


def _ymd() -> str:
    return company_time.today().strftime("%Y%m%d")


def discipline_bot_branch() -> str:
    import employees

    return employees.get_profile(EMPLOYEE)["branch"]


async def _bos(main, bot, grade_key: str, actor: int = NAZORATCHI):
    return await send_callback(main.dp, bot, actor, data=f"bos:grade:{EMPLOYEE}:{grade_key}:{_ymd()}", target_chat_id=actor)


async def _nzr(main, bot, grade_key: str, actor: int = NAZORATCHI):
    return await send_callback(main.dp, bot, actor, data=f"nzr_grade:{EMPLOYEE}:{grade_key}:{_ymd()}", target_chat_id=actor)


def _notices(sent, chat_id: int = EMPLOYEE) -> list:
    return [m for m in sent if isinstance(m, SendMessage) and m.chat_id == chat_id]


def _answers(sent) -> list[str]:
    return [m.text for m in sent if isinstance(m, AnswerCallbackQuery)]


def _count(table: str, where: str = "1=1") -> int:
    conn = get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}").fetchone()["n"]
    finally:
        conn.close()


@pytest.mark.parametrize("entry", ["bos", "nzr"])
async def test_new_grade_notifies_only_that_employee_with_date_grade_and_month_totals(bot_dp, entry):
    main, bot = bot_dp
    _setup()
    _approved_profile(222)  # boshqa xodim — xabar olmasligi kerak

    sent = await (_bos if entry == "bos" else _nzr)(main, bot, discipline.GRADE_ALO)

    notices = _notices(sent)
    assert len(notices) == 1
    day = company_time.today().strftime("%d.%m.%Y")
    assert notices[0].text == (
        f"📅 Sana: {day}\n⭐ Baho: 3 — A'lo\nShu oy bonus: 3\nShu oy minus: 0\nShu oy jami: 3"
    )
    assert not [m for m in sent if isinstance(m, SendMessage) and m.chat_id not in (EMPLOYEE, NAZORATCHI)]
    assert any(isinstance(m, EditMessageText) for m in sent)  # nazoratchi ekrani saqlangan
    assert "Saqlandi" in _answers(sent)[0] or "Baho qayd etildi" in _answers(sent)[0]


@pytest.mark.parametrize("first, second", [(_bos, _bos), (_nzr, _nzr), (_bos, _nzr), (_nzr, _bos)])
async def test_repeating_the_same_grade_adds_no_notice_ledger_or_history(bot_dp, first, second):
    main, bot = bot_dp
    _setup()

    await first(main, bot, discipline.GRADE_ALO)
    sent = await second(main, bot, discipline.GRADE_ALO)

    assert _notices(sent) == []
    assert "Bu baho allaqachon saqlangan." in _answers(sent)
    assert _count("bonus_bank_ledger", f"user_id = {EMPLOYEE}") == 1
    assert _count("daily_evaluation_history", f"employee_id = {EMPLOYEE}") == 1
    assert discipline.get_salary(EMPLOYEE)["bonus_bank"] == 3


async def test_correction_sends_one_correction_message_and_not_a_minus(bot_dp):
    main, bot = bot_dp
    _setup()
    await _bos(main, bot, discipline.GRADE_ALO)

    sent = await _bos(main, bot, discipline.GRADE_NORMA)

    notices = _notices(sent)
    assert len(notices) == 1
    assert "✏️ Tuzatildi: 3 → 2" in notices[0].text and "⭐ Baho" not in notices[0].text
    assert notices[0].text.endswith("Shu oy bonus: 2\nShu oy minus: 0\nShu oy jami: 2")
    assert [row["grade_points"] for row in discipline.get_grade_history(EMPLOYEE, company_time.today().isoformat())] == [3, 2]


async def test_real_minus_and_other_bonus_are_kept_in_the_notice(bot_dp):
    main, bot = bot_dp
    _setup()
    discipline.adjust_bonus_bank(EMPLOYEE, -1, "nizom", "penalty", 1)
    discipline.adjust_bonus_bank(EMPLOYEE, 4, "boshqa bonus", "other_bonus", None)
    await _nzr(main, bot, discipline.GRADE_ALO)

    sent = await _nzr(main, bot, discipline.GRADE_NORMA)

    assert _notices(sent)[0].text.endswith("Shu oy bonus: 6\nShu oy minus: 1\nShu oy jami: 5")


async def test_zero_grade_is_notified_once_and_not_repeated_and_three_to_zero_works(bot_dp):
    main, bot = bot_dp
    _setup()

    first = await _nzr(main, bot, discipline.GRADE_BAJARILMAGAN)
    assert "⭐ Baho: 0 — Bajarilmagan" in _notices(first)[0].text
    again = await _bos(main, bot, discipline.GRADE_BAJARILMAGAN)
    assert _notices(again) == [] and "Bu baho allaqachon saqlangan." in _answers(again)
    assert _count("daily_evaluation_history", f"employee_id = {EMPLOYEE}") == 1

    await _bos(main, bot, discipline.GRADE_ALO)
    down = await _bos(main, bot, discipline.GRADE_BAJARILMAGAN)
    assert "✏️ Tuzatildi: 3 → 0" in _notices(down)[0].text
    assert discipline.get_daily_grade(EMPLOYEE, company_time.today().isoformat())["grade_points"] == 0


@pytest.mark.parametrize("entry", [_bos, _nzr])
async def test_send_failure_keeps_the_saved_grade_and_the_supervisor_flow(bot_dp, entry, monkeypatch):
    main, bot = bot_dp
    _setup()
    real_call = bot.__class__.__call__

    async def failing(self, method, request_timeout=None):
        if isinstance(method, SendMessage) and method.chat_id == EMPLOYEE:
            raise TelegramNetworkError(method=method, message="kutilmagan tarmoq xatosi")
        return await real_call(self, method, request_timeout)

    monkeypatch.setattr(bot.__class__, "__call__", failing)

    sent = await entry(main, bot, discipline.GRADE_ALO)

    assert discipline.get_daily_grade(EMPLOYEE, company_time.today().isoformat())["grade_points"] == 3
    assert discipline.get_salary(EMPLOYEE)["bonus_bank"] == 3
    assert any(isinstance(m, EditMessageText) for m in sent)
    assert "Baho saqlandi, lekin xodimga xabar yuborib bo'lmadi." in _answers(sent)


async def test_blocked_bot_is_reported_as_not_linked_and_grade_is_kept(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup()
    real_call = bot.__class__.__call__

    async def blocked(self, method, request_timeout=None):
        if isinstance(method, SendMessage) and method.chat_id == EMPLOYEE:
            raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
        return await real_call(self, method, request_timeout)

    monkeypatch.setattr(bot.__class__, "__call__", blocked)

    sent = await _bos(main, bot, discipline.GRADE_ALO)

    assert "Xodim botga ulanmagan — baho saqlandi, xabar yuborilmadi." in _answers(sent)
    assert discipline.get_salary(EMPLOYEE)["bonus_bank"] == 3


@pytest.mark.parametrize("entry", [_bos, _nzr])
async def test_send_is_skipped_when_chat_id_resolves_to_none_UNIT_ONLY(bot_dp, entry, monkeypatch):
    """FAQAT yuborishni tashlab o'tish unit testi (`employee_telegram_chat_id` mock). Bu haqiqiy
    "Telegram ID'siz xodim" sinovi EMAS: mavjud modelda bunday xodim saqlanmaydi/baholanmaydi
    (qarang tests/test_discipline_service.py::test_employee_model_has_no_telegram_less_employee_unit_proof)."""
    main, bot = bot_dp
    _setup()
    monkeypatch.setattr(discipline, "employee_telegram_chat_id", lambda employee_id, **kwargs: None)

    sent = await entry(main, bot, discipline.GRADE_ALO)

    assert _notices(sent) == []
    assert [m for m in sent if isinstance(m, SendMessage) and m.chat_id != NAZORATCHI] == []
    assert "Xodim botga ulanmagan — baho saqlandi, xabar yuborilmadi." in _answers(sent)
    assert discipline.get_salary(EMPLOYEE)["bonus_bank"] == 3
    assert discipline.get_daily_grade(EMPLOYEE, company_time.today().isoformat())["grade_points"] == 3


async def test_unknown_employee_is_neither_graded_nor_called_unlinked(bot_dp):
    main, bot = bot_dp
    _set_role(NAZORATCHI, "nazoratchi")

    sent = await send_callback(
        main.dp, bot, NAZORATCHI, data=f"bos:grade:99999:{discipline.GRADE_ALO}:{_ymd()}", target_chat_id=NAZORATCHI
    )

    assert "Xodim topilmadi." in _answers(sent)
    assert _count("daily_evaluations") == 0 and _count("bonus_bank_ledger") == 0
    assert _notices(sent, 99999) == []


@pytest.mark.parametrize("entry", [_bos, _nzr])
async def test_unauthorised_callback_writes_nothing_and_sends_nothing(bot_dp, entry):
    main, bot = bot_dp
    _setup()
    _set_role(999, "kassir")

    sent = await entry(main, bot, discipline.GRADE_ALO, actor=999)

    assert _count("daily_evaluations") == 0 and _count("bonus_bank_ledger") == 0
    assert _notices(sent) == []


async def test_simultaneous_identical_presses_from_both_entry_points_do_not_duplicate(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup()
    delivered = []
    real_call = bot.__class__.__call__

    async def counting(self, method, request_timeout=None):
        if isinstance(method, SendMessage) and method.chat_id == EMPLOYEE:
            delivered.append(method.text)
        return await real_call(self, method, request_timeout)

    monkeypatch.setattr(bot.__class__, "__call__", counting)

    await asyncio.gather(
        _bos(main, bot, discipline.GRADE_ALO), _nzr(main, bot, discipline.GRADE_ALO),
        _bos(main, bot, discipline.GRADE_ALO), _nzr(main, bot, discipline.GRADE_ALO),
    )

    assert len(delivered) == 1
    assert _count("bonus_bank_ledger", f"user_id = {EMPLOYEE}") == 1
    assert _count("daily_evaluation_history", f"employee_id = {EMPLOYEE}") == 1
    assert discipline.get_salary(EMPLOYEE)["bonus_bank"] == 3


async def test_send_failure_does_not_lock_later_presses(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup()
    real_call = bot.__class__.__call__
    state = {"fail": True}

    async def flaky(self, method, request_timeout=None):
        if isinstance(method, SendMessage) and method.chat_id == EMPLOYEE and state["fail"]:
            raise TelegramNetworkError(method=method, message="vaqtincha xato")
        return await real_call(self, method, request_timeout)

    monkeypatch.setattr(bot.__class__, "__call__", flaky)
    await _bos(main, bot, discipline.GRADE_ALO)
    state["fail"] = False

    sent = await _bos(main, bot, discipline.GRADE_NORMA)  # keyingi haqiqiy tuzatish oddiy ishlaydi

    assert len(_notices(sent)) == 1 and "✏️ Tuzatildi: 3 → 2" in _notices(sent)[0].text


@pytest.mark.parametrize(
    "hour, minute, silent",
    [(21, 59, False), (22, 0, True), (6, 59, True), (7, 0, False)],
)
@pytest.mark.parametrize("correction", [False, True])
async def test_notice_is_silent_only_during_local_night(bot_dp, monkeypatch, hour, minute, silent, correction):
    main, bot = bot_dp
    _setup()
    tz = company_time.resolve_timezone()
    fixed = datetime.now(tz).replace(hour=hour, minute=minute, second=0, microsecond=0)
    monkeypatch.setattr(company_time, "now", lambda: fixed)
    if correction:
        await _nzr(main, bot, discipline.GRADE_ALO)

    sent = await _nzr(main, bot, discipline.GRADE_NORMA if correction else discipline.GRADE_ALO)

    notice = _notices(sent)[0]
    assert bool(notice.disable_notification) is silent
    assert ("✏️ Tuzatildi" in notice.text) is correction


# ------------------------------- eski oy bahosi: xabar va hisob o'sha oyga tegishli --


def _freeze_now(monkeypatch, year: int, month: int, day: int, hour: int = 12) -> None:
    fixed = datetime(year, month, day, hour, 0, tzinfo=company_time.resolve_timezone())
    monkeypatch.setattr(company_time, "now", lambda: fixed)


async def _bos_on(main, bot, grade_key: str, ymd: str):
    # Eski sanaga baho faqat o'sha kun faol (yakunlanmagan sessiya) bo'lgandagina yoziladi.
    from services import nazoratchi_day

    nazoratchi_day.open_session(NAZORATCHI, discipline_bot_branch(), f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}")
    return await send_callback(
        main.dp, bot, NAZORATCHI, data=f"bos:grade:{EMPLOYEE}:{grade_key}:{ymd}", target_chat_id=NAZORATCHI
    )


async def test_old_month_callback_cannot_create_a_grade_or_notice(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup()
    _freeze_now(monkeypatch, 2026, 11, 5)
    sent = await _bos_on(main, bot, discipline.GRADE_ALO, "20261028")
    assert _notices(sent) == [] and any("eskirgan" in text for text in _answers(sent))
    assert discipline.get_daily_grade(EMPLOYEE, "2026-10-28") is None
    assert discipline.get_period_point_totals(EMPLOYEE)["bonus"] == 0


async def test_old_month_callback_cannot_correct_history_or_current_balance(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup()
    discipline.record_daily_grade(EMPLOYEE, NAZORATCHI, "2026-10-28", discipline.GRADE_ALO)
    _freeze_now(monkeypatch, 2026, 11, 5)
    await _nzr(main, bot, discipline.GRADE_ALO)
    sent = await _bos_on(main, bot, discipline.GRADE_NORMA, "20261028")
    assert _notices(sent) == [] and any("eskirgan" in text for text in _answers(sent))
    assert discipline.get_period_point_totals(EMPLOYEE, "2026-10")["bonus"] == 3
    assert discipline.get_period_point_totals(EMPLOYEE, "2026-11")["bonus"] == 3


async def test_current_month_notice_is_silent_but_old_month_callback_is_rejected(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup()
    _freeze_now(monkeypatch, 2026, 11, 5, hour=23)
    current = await _nzr(main, bot, discipline.GRADE_ALO)
    assert _notices(current)[0].text.endswith("Shu oy bonus: 3\nShu oy minus: 0\nShu oy jami: 3")
    assert bool(_notices(current)[0].disable_notification) is True
    old = await _bos_on(main, bot, discipline.GRADE_NORMA, "20261028")
    assert _notices(old) == [] and any("eskirgan" in text for text in _answers(old))


@pytest.fixture(autouse=True)
def _daytime_clock_for_non_boundary_tests(monkeypatch):
    # Boundary/night tests explicitly override this; ordinary callbacks use one stable work day.
    fixed = company_time.now().replace(hour=12, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(company_time, "now", lambda: fixed)
