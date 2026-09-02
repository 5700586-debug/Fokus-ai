"""Nizom o'qish auditining Telegram oqimi (`discipline_bot`).

Tekshiruv nuqtasi: UI FAQAT mavjud ``services/rule_learning.py`` qatlamini
chaqiradi — parallel mantiq yo'q, bir vaqtda faqat BITTA band ko'rsatiladi,
va chat tozalash auditga (progress qatorlariga) tegmaydi.
"""

from datetime import date

import pytest
from aiogram.methods import AnswerCallbackQuery, DeleteMessage, EditMessageText, SendMessage

import company_time
import employees
from config import FOUNDER_ID
from repositories import discipline as discipline_repo
from repositories import rule_learning as rule_learning_repo
from roles import set_role
from services import rule_learning
from tests.bot_harness import send, send_callback, texts

pytestmark = pytest.mark.anyio

EMPLOYEE_ID = 940001
OTHER_ID = 940002


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _add_rule(rule_number: int, title: str | None = None, content: str | None = None) -> None:
    discipline_repo.create_rule(
        rule_number,
        title or f"Band {rule_number}",
        content or f"Matn {rule_number}",
        created_by=FOUNDER_ID,
    )


def _make_employee(user_id: int = EMPLOYEE_ID) -> None:
    set_role(user_id, "kassir", set_by=FOUNDER_ID)


def _freeze_date(monkeypatch, value: date) -> None:
    monkeypatch.setattr(company_time, "today", lambda: value)


def _buttons(method) -> list[tuple[str, str]]:
    markup = getattr(method, "reply_markup", None)
    if markup is None:
        return []
    return [(button.text, button.callback_data) for row in markup.inline_keyboard for button in row]


def _callback_data(method, label_part: str) -> str:
    for text, data in _buttons(method):
        if label_part in text:
            return data
    raise AssertionError(f"{label_part!r} tugmasi topilmadi: {_buttons(method)}")


def _screens(sent, method_type) -> list:
    return [method for method in sent if isinstance(method, method_type)]


def _complete_via_service(employee_id: int = EMPLOYEE_ID) -> None:
    progress = rule_learning.get_current_rule(employee_id)
    assert progress is not None
    assert rule_learning.confirm_read(progress["id"]) is True
    assert rule_learning.confirm_understood(employee_id, progress["id"]) is True


async def _open_first_card(main, bot):
    sent = await send(main.dp, bot, EMPLOYEE_ID, text="/listnizom")
    cards = _screens(sent, SendMessage)
    assert len(cards) == 1
    return cards[0]


# ------------------------------------------------------------- eski oqim --


async def test_listnizom_without_enrollment_keeps_legacy_list(bot_dp):
    main, bot = bot_dp
    _make_employee()
    _add_rule(1)
    _add_rule(2)

    sent = await send(main.dp, bot, EMPLOYEE_ID, text="/listnizom")

    assert len(sent) == 1
    assert "Korxona nizomlari" in (texts(sent)[0] or "")
    assert "1. Band 1" in texts(sent)[0]
    assert "2. Band 2" in texts(sent)[0]
    assert _buttons(sent[0]) == []
    assert rule_learning_repo.list_started_rule_numbers(EMPLOYEE_ID) == []


async def test_listnizom_after_finished_enrollment_keeps_legacy_list(bot_dp):
    main, bot = bot_dp
    _make_employee()
    _add_rule(1)
    rule_learning.enroll(EMPLOYEE_ID)
    _complete_via_service()
    assert rule_learning.get_enrollment(EMPLOYEE_ID)["finished_at"] is not None

    sent = await send(main.dp, bot, EMPLOYEE_ID, text="/listnizom")

    assert "Korxona nizomlari" in (texts(sent)[0] or "")


# ------------------------------------------------------- band ko'rsatish --


async def test_listnizom_sends_only_the_next_single_rule(bot_dp):
    main, bot = bot_dp
    _make_employee()
    for number in (1, 2, 3):
        _add_rule(number)
    rule_learning.enroll(EMPLOYEE_ID)

    card = await _open_first_card(main, bot)

    assert "1-nizom" in card.text
    assert "Matn 1" in card.text
    assert "2-nizom" not in card.text
    labels = [text for text, _ in _buttons(card)]
    assert labels == ["✅ O'qidim", "📖 Hali o'qiyapman"]
    assert rule_learning_repo.list_started_rule_numbers(EMPLOYEE_ID) == [1]


async def test_pending_rule_is_resumed_from_snapshot(bot_dp):
    main, bot = bot_dp
    _make_employee()
    _add_rule(1, "Eski sarlavha", "Eski matn")
    _add_rule(2)
    rule_learning.enroll(EMPLOYEE_ID)

    first = await _open_first_card(main, bot)
    assert "Eski matn" in first.text

    import db

    conn = db.get_connection()
    try:
        conn.execute("UPDATE company_rules SET is_active = 0 WHERE rule_number = 1")
        conn.commit()
    finally:
        conn.close()

    resumed = await _open_first_card(main, bot)

    assert "1-nizom" in resumed.text
    assert "Eski matn" in resumed.text
    assert rule_learning_repo.list_started_rule_numbers(EMPLOYEE_ID) == [1]


# ------------------------------------------------------------- tugmalar --


async def test_still_reading_only_answers_callback(bot_dp):
    main, bot = bot_dp
    _make_employee()
    _add_rule(1)
    rule_learning.enroll(EMPLOYEE_ID)
    card = await _open_first_card(main, bot)
    progress_id = rule_learning.get_current_rule(EMPLOYEE_ID)["id"]

    sent = await send_callback(
        main.dp, bot, EMPLOYEE_ID, _callback_data(card, "Hali o'qiyapman"), EMPLOYEE_ID
    )

    assert all(isinstance(method, AnswerCallbackQuery) for method in sent)
    stored = rule_learning.get_progress(progress_id)
    assert stored["read_confirmed_at"] is None
    assert stored["completed_at"] is None


async def test_read_confirmation_shows_understanding_buttons(bot_dp):
    main, bot = bot_dp
    _make_employee()
    _add_rule(1)
    rule_learning.enroll(EMPLOYEE_ID)
    card = await _open_first_card(main, bot)
    progress_id = rule_learning.get_current_rule(EMPLOYEE_ID)["id"]

    sent = await send_callback(
        main.dp, bot, EMPLOYEE_ID, _callback_data(card, "O'qidim"), EMPLOYEE_ID
    )

    edits = _screens(sent, EditMessageText)
    assert len(edits) == 1
    assert "1-nizom" in edits[0].text
    assert [text for text, _ in _buttons(edits[0])] == ["✅ Tushundim", "❓ Tushunmadim"]
    assert _screens(sent, SendMessage) == []

    stored = rule_learning.get_progress(progress_id)
    assert stored["read_confirmed_at"] is not None
    assert stored["completed_at"] is None


async def test_not_understood_blocks_progress_and_reread_keeps_snapshot(bot_dp):
    main, bot = bot_dp
    _make_employee()
    _add_rule(1)
    _add_rule(2)
    rule_learning.enroll(EMPLOYEE_ID)
    card = await _open_first_card(main, bot)
    progress_id = rule_learning.get_current_rule(EMPLOYEE_ID)["id"]
    await send_callback(main.dp, bot, EMPLOYEE_ID, _callback_data(card, "O'qidim"), EMPLOYEE_ID)

    sent = await send_callback(main.dp, bot, EMPLOYEE_ID, f"rl:nu:{progress_id}", EMPLOYEE_ID)

    edits = _screens(sent, EditMessageText)
    assert len(edits) == 1
    assert [text for text, _ in _buttons(edits[0])] == ["📖 Qayta o'qiyman", "✅ Tushundim"]
    assert _screens(sent, SendMessage) == []

    stored = rule_learning.get_progress(progress_id)
    assert stored["not_understood_at"] is not None
    assert stored["completed_at"] is None
    assert rule_learning_repo.list_started_rule_numbers(EMPLOYEE_ID) == [1]

    marked_at = stored["not_understood_at"]
    reread = await send_callback(
        main.dp, bot, EMPLOYEE_ID, _callback_data(edits[0], "Qayta o'qiyman"), EMPLOYEE_ID
    )

    reread_edits = _screens(reread, EditMessageText)
    assert len(reread_edits) == 1
    assert "Matn 1" in reread_edits[0].text
    assert [text for text, _ in _buttons(reread_edits[0])] == ["✅ Tushundim", "❓ Tushunmadim"]

    after = rule_learning.get_progress(progress_id)
    assert after["not_understood_at"] == marked_at
    assert after["read_confirmed_at"] == stored["read_confirmed_at"]
    assert after["completed_at"] is None


async def test_understood_completes_and_sends_next_rule(bot_dp):
    main, bot = bot_dp
    _make_employee()
    _add_rule(1)
    _add_rule(2)
    rule_learning.enroll(EMPLOYEE_ID)
    card = await _open_first_card(main, bot)
    progress_id = rule_learning.get_current_rule(EMPLOYEE_ID)["id"]
    read = await send_callback(
        main.dp, bot, EMPLOYEE_ID, _callback_data(card, "O'qidim"), EMPLOYEE_ID
    )

    sent = await send_callback(
        main.dp,
        bot,
        EMPLOYEE_ID,
        _callback_data(_screens(read, EditMessageText)[0], "Tushundim"),
        EMPLOYEE_ID,
    )

    cards = _screens(sent, SendMessage)
    assert len(cards) == 1
    assert "2-nizom" in cards[0].text
    assert [text for text, _ in _buttons(cards[0])] == ["✅ O'qidim", "📖 Hali o'qiyapman"]

    assert rule_learning.get_progress(progress_id)["completed_at"] is not None
    assert rule_learning_repo.list_started_rule_numbers(EMPLOYEE_ID) == [1, 2]


async def test_other_user_cannot_confirm_someone_elses_rule(bot_dp):
    main, bot = bot_dp
    _make_employee()
    _make_employee(OTHER_ID)
    _add_rule(1)
    _add_rule(2)
    rule_learning.enroll(EMPLOYEE_ID)
    card = await _open_first_card(main, bot)
    progress_id = rule_learning.get_current_rule(EMPLOYEE_ID)["id"]
    await send_callback(main.dp, bot, EMPLOYEE_ID, _callback_data(card, "O'qidim"), EMPLOYEE_ID)

    sent = await send_callback(main.dp, bot, OTHER_ID, f"rl:ok:{progress_id}", EMPLOYEE_ID)

    assert all(isinstance(method, AnswerCallbackQuery) for method in sent)
    assert rule_learning.get_progress(progress_id)["completed_at"] is None
    assert rule_learning_repo.list_started_rule_numbers(EMPLOYEE_ID) == [1]


async def test_double_understood_sends_next_rule_only_once(bot_dp):
    main, bot = bot_dp
    _make_employee()
    _add_rule(1)
    _add_rule(2)
    _add_rule(3)
    rule_learning.enroll(EMPLOYEE_ID)
    card = await _open_first_card(main, bot)
    progress_id = rule_learning.get_current_rule(EMPLOYEE_ID)["id"]
    await send_callback(main.dp, bot, EMPLOYEE_ID, _callback_data(card, "O'qidim"), EMPLOYEE_ID)

    first = await send_callback(main.dp, bot, EMPLOYEE_ID, f"rl:ok:{progress_id}", EMPLOYEE_ID)
    second = await send_callback(main.dp, bot, EMPLOYEE_ID, f"rl:ok:{progress_id}", EMPLOYEE_ID)

    assert len(_screens(first, SendMessage)) == 1
    assert _screens(second, SendMessage) == []
    assert rule_learning_repo.list_started_rule_numbers(EMPLOYEE_ID) == [1, 2]


# --------------------------------------------------------- holat xabarlari --


async def test_daily_limit_message_after_five_rules(bot_dp, monkeypatch):
    main, bot = bot_dp
    _freeze_date(monkeypatch, date(2026, 9, 1))
    _make_employee()
    for number in range(1, 8):
        _add_rule(number)
    rule_learning.enroll(EMPLOYEE_ID)
    for _ in range(4):
        _complete_via_service()

    card = await _open_first_card(main, bot)
    assert "5-nizom" in card.text
    progress_id = rule_learning.get_current_rule(EMPLOYEE_ID)["id"]
    await send_callback(main.dp, bot, EMPLOYEE_ID, _callback_data(card, "O'qidim"), EMPLOYEE_ID)

    sent = await send_callback(main.dp, bot, EMPLOYEE_ID, f"rl:ok:{progress_id}", EMPLOYEE_ID)

    cards = _screens(sent, SendMessage)
    assert len(cards) == 1
    assert cards[0].text == "✅ Bugungi 5 ta nizom tugadi. Ertaga davom etamiz."
    assert rule_learning.completed_today(EMPLOYEE_ID) == 5
    assert rule_learning_repo.list_started_rule_numbers(EMPLOYEE_ID) == [1, 2, 3, 4, 5]

    # `/listnizom` ham shu holatni takrorlaydi va yangi band ochmaydi.
    again = await send(main.dp, bot, EMPLOYEE_ID, text="/listnizom")
    assert texts(_screens(again, SendMessage)) == [
        "✅ Bugungi 5 ta nizom tugadi. Ertaga davom etamiz."
    ]
    assert rule_learning_repo.list_started_rule_numbers(EMPLOYEE_ID) == [1, 2, 3, 4, 5]


async def test_all_done_message_after_last_rule(bot_dp):
    main, bot = bot_dp
    _make_employee()
    _add_rule(1)
    rule_learning.enroll(EMPLOYEE_ID)
    card = await _open_first_card(main, bot)
    progress_id = rule_learning.get_current_rule(EMPLOYEE_ID)["id"]
    await send_callback(main.dp, bot, EMPLOYEE_ID, _callback_data(card, "O'qidim"), EMPLOYEE_ID)

    sent = await send_callback(main.dp, bot, EMPLOYEE_ID, f"rl:ok:{progress_id}", EMPLOYEE_ID)

    cards = _screens(sent, SendMessage)
    assert len(cards) == 1
    assert cards[0].text == "✅ Barcha nizomlarni o'rganib bo'ldingiz."
    assert rule_learning.get_enrollment(EMPLOYEE_ID)["finished_at"] is not None


# ------------------------------------------------------------- tozalash --


async def test_cleanup_deletes_card_but_keeps_audit_row(bot_dp):
    main, bot = bot_dp
    _make_employee()
    _add_rule(1)
    _add_rule(2)
    rule_learning.enroll(EMPLOYEE_ID)
    card = await _open_first_card(main, bot)
    progress_id = rule_learning.get_current_rule(EMPLOYEE_ID)["id"]
    assert rule_learning.get_progress(progress_id)["sent_at"] is not None
    await send_callback(main.dp, bot, EMPLOYEE_ID, _callback_data(card, "O'qidim"), EMPLOYEE_ID)

    sent = await send_callback(main.dp, bot, EMPLOYEE_ID, f"rl:ok:{progress_id}", EMPLOYEE_ID)

    deletes = _screens(sent, DeleteMessage)
    assert len(deletes) == 1
    assert deletes[0].chat_id == EMPLOYEE_ID

    stored = rule_learning.get_progress(progress_id)
    assert stored["rule_number"] == 1
    assert stored["content_snapshot"] == "Matn 1"
    assert stored["read_confirmed_at"] is not None
    assert stored["understood_confirmed_at"] is not None
    assert stored["completed_at"] is not None
    assert stored["completed_company_date"] is not None
    assert rule_learning.completed_today(EMPLOYEE_ID) == 1


# ----------------------------------------------- approval integratsiyasi --

APPLICANT_ID = 940101


def _submit_profile(user_id: int, role_key: str = "kassir") -> None:
    employees.submit_profile(
        user_id,
        {"familiya": "Familiyev", "ism": "Ism", "branch": "Filial-1", "role_key": role_key, "contacts": []},
    )


def _applicant_messages(sent, user_id: int = APPLICANT_ID) -> list:
    return [m for m in sent if getattr(m, "chat_id", None) == user_id]


async def test_approval_success_enrolls_and_sends_first_rule(bot_dp):
    main, bot = bot_dp
    _add_rule(1)
    _submit_profile(APPLICANT_ID)

    sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"approve:{APPLICANT_ID}", target_chat_id=FOUNDER_ID
    )

    assert rule_learning.get_enrollment(APPLICANT_ID) is not None
    applicant_texts = texts(_applicant_messages(sent))
    assert any("1-nizom" in (t or "") for t in applicant_texts)


async def test_approval_role_failure_enrolls_but_sends_no_rule_message(bot_dp, monkeypatch):
    import approval

    main, bot = bot_dp
    _add_rule(1)
    _submit_profile(APPLICANT_ID)
    monkeypatch.setattr(approval.roles, "set_role", lambda *args, **kwargs: False)

    sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"approve:{APPLICANT_ID}", target_chat_id=FOUNDER_ID
    )

    assert rule_learning.get_enrollment(APPLICANT_ID) is not None
    assert _applicant_messages(sent) == []


async def test_setrole_resumes_pending_enrollment_after_role_failure(bot_dp, monkeypatch):
    import approval

    main, bot = bot_dp
    _add_rule(1)
    _submit_profile(APPLICANT_ID)
    monkeypatch.setattr(approval.roles, "set_role", lambda *args, **kwargs: False)
    await send_callback(main.dp, bot, FOUNDER_ID, data=f"approve:{APPLICANT_ID}", target_chat_id=FOUNDER_ID)
    assert rule_learning.get_enrollment(APPLICANT_ID) is not None

    sent = await send(main.dp, bot, FOUNDER_ID, text=f"/setrole {APPLICANT_ID} kassir")

    applicant_texts = texts(_applicant_messages(sent))
    assert any("1-nizom" in (t or "") for t in applicant_texts)


async def test_setrole_on_old_employee_does_not_create_new_enrollment(bot_dp):
    main, bot = bot_dp
    _add_rule(1)
    set_role(EMPLOYEE_ID, "kassir", set_by=FOUNDER_ID)  # eski xodim -- enrollment yo'q

    sent = await send(main.dp, bot, FOUNDER_ID, text=f"/setrole {EMPLOYEE_ID} nazoratchi")

    assert rule_learning.get_enrollment(EMPLOYEE_ID) is None
    employee_texts = texts(_applicant_messages(sent, EMPLOYEE_ID))
    assert not any("nizom" in (t or "").lower() for t in employee_texts)


async def test_duplicate_approve_does_not_duplicate_enrollment_or_message(bot_dp):
    main, bot = bot_dp
    _add_rule(1)
    _submit_profile(APPLICANT_ID)

    first = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"approve:{APPLICANT_ID}", target_chat_id=FOUNDER_ID
    )
    second = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"approve:{APPLICANT_ID}", target_chat_id=FOUNDER_ID
    )

    assert len(_applicant_messages(first)) >= 1
    assert _applicant_messages(second) == []
    assert rule_learning_repo.list_started_rule_numbers(APPLICANT_ID) == [1]
