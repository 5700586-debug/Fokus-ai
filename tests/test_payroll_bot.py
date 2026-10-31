"""💰 Xodim maoshi: Founder ro'yxatdan tanlaydi va to'liq tarkibni ko'radi; boshqalarga yopiq."""

import pytest
from aiogram.methods import SendMessage

from config import FOUNDER_ID
from tests.bot_harness import send_callback
from tests.test_payroll_view import EMP, _agreement, _day, _sql

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_founder_sees_salary_breakdown(bot_dp):
    main, bot = bot_dp
    _sql("INSERT INTO employees (user_id, familiya, ism, branch, status) VALUES (?, 'Karimov', 'Vali', 'SATURN A', 'approved')", (EMP,))
    _agreement()
    _day("2026-09-02")
    listing = await send_callback(main.dp, bot, FOUNDER_ID, data="pay:list:0", target_chat_id=FOUNDER_ID)
    assert any(isinstance(m, SendMessage) and "Xodim maoshi" in m.text for m in listing)
    sent = await send_callback(main.dp, bot, FOUNDER_ID, data=f"pay:emp:{EMP}:1", target_chat_id=FOUNDER_ID)
    text = next(m.text for m in sent if isinstance(m, SendMessage) and "Karimov" in m.text)
    assert "Fiks" in text and "JAMI" in text and "Vaqt bonusi" in text


async def test_employee_cannot_open_salaries(bot_dp):
    main, bot = bot_dp
    sent = await send_callback(main.dp, bot, 999_999, data="pay:list:0", target_chat_id=999_999)
    assert not any(isinstance(m, SendMessage) and "Xodim maoshi" in m.text for m in sent)
