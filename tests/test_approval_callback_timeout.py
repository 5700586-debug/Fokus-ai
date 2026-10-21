"""Approval callback javobi DB ishlari tugashini kutmasligi kerak (Telegram mock)."""

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, SendMessage

import approval
import employees
import roles
from config import FOUNDER_ID
from tests.bot_harness import send_callback

pytestmark = pytest.mark.anyio
APPLICANT = 958001


@pytest.fixture
def anyio_backend():
    return "asyncio"


def submit():
    employees.submit_profile(APPLICANT, {
        "familiya": "Test", "ism": "Nomzod", "branch": "Filial-1",
        "role_key": "kassir", "contacts": [],
    })


@pytest.mark.parametrize("already_expired", [False, True])
async def test_approval_ack_is_before_writes_and_expired_query_does_not_report_failure(bot_dp, monkeypatch, already_expired):
    main, bot = bot_dp
    submit()
    original_call = type(bot).__call__
    original_approve = employees.approve_profile
    acknowledged = []

    async def api(self, method, request_timeout=None):
        if isinstance(method, AnswerCallbackQuery):
            acknowledged.append(method)
            # Eski kod kech javob bersa ham haqiqiy Telegram singari xato chiqaradi.
            if already_expired or employees.get_profile(APPLICANT)["status"] == "approved":
                raise TelegramBadRequest(method=method, message="query is too old and response timeout expired or query ID is invalid")
        return await original_call(self, method, request_timeout)

    def approve(*args, **kwargs):
        assert len(acknowledged) == 1
        return original_approve(*args, **kwargs)

    monkeypatch.setattr(type(bot), "__call__", api)
    monkeypatch.setattr(approval.employees, "approve_profile", approve)
    sent = await send_callback(main.dp, bot, FOUNDER_ID, data=f"approve:{APPLICANT}", target_chat_id=FOUNDER_ID)

    assert employees.get_profile(APPLICANT)["status"] == "approved"
    assert roles.get_role(APPLICANT) == "kassir"
    assert len(acknowledged) == 1
    assert any(isinstance(m, SendMessage) and m.chat_id == APPLICANT and m.reply_markup for m in sent)
    assert any(isinstance(m, SendMessage) and m.chat_id == FOUNDER_ID and "Xodim qabul qilindi" in m.text for m in sent)
    assert not any("Kutilmagan" in (getattr(m, "text", "") or "") for m in sent)


async def test_role_assignment_failure_is_not_reported_as_success(bot_dp, monkeypatch):
    main, bot = bot_dp
    submit()
    monkeypatch.setattr(approval.roles, "set_role", lambda *a, **k: False)
    sent = await send_callback(main.dp, bot, FOUNDER_ID, data=f"approve:{APPLICANT}", target_chat_id=FOUNDER_ID)
    assert not any(isinstance(m, SendMessage) and m.chat_id == APPLICANT for m in sent)
    assert any("qo'lda rol bering" in (getattr(m, "text", "") or "") for m in sent)
    assert not any("Xodim qabul qilindi" in (getattr(m, "text", "") or "") for m in sent)


async def test_duplicate_approval_does_not_resend_employee_menu(bot_dp):
    main, bot = bot_dp
    submit()
    await send_callback(main.dp, bot, FOUNDER_ID, data=f"approve:{APPLICANT}", target_chat_id=FOUNDER_ID)
    sent = await send_callback(main.dp, bot, FOUNDER_ID, data=f"approve:{APPLICANT}", target_chat_id=FOUNDER_ID)
    assert not any(isinstance(m, SendMessage) and m.chat_id == APPLICANT for m in sent)


async def test_unprivileged_user_cannot_approve(bot_dp):
    main, bot = bot_dp
    submit()
    roles.set_role(APPLICANT, "kassir", set_by=FOUNDER_ID)
    await send_callback(main.dp, bot, APPLICANT, data=f"approve:{APPLICANT}", target_chat_id=APPLICANT)
    assert employees.get_profile(APPLICANT)["status"] == "submitted"
