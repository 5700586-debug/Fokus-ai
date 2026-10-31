"""💰 Oyligim: xodim faqat O'ZINING maoshi to'liq tarkibini ko'radi; joriy oy "yakuniy emas", o'tgan oy aralashmaydi."""

from datetime import date

import pytest
from aiogram.methods import SendMessage

import company_time
from config import FOUNDER_ID
from tests.bot_harness import send, send_callback
from tests.test_payroll_view import EMP, _agreement, _day, _sql

pytestmark = pytest.mark.anyio

OTHER = 895002


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr(company_time, "today", lambda: date(2026, 10, 15))  # joriy 2026-10, o'tgan 2026-09


def _seed():
    from roles import set_role

    _sql("INSERT INTO employees (user_id, familiya, ism, branch, status) VALUES (?, 'Karimov', 'Vali', 'SATURN A', 'approved')",
         (EMP,))
    set_role(EMP, "kassir", set_by=FOUNDER_ID)
    set_role(OTHER, "kassir", set_by=FOUNDER_ID)
    _agreement()  # 3-tarif
    for day in range(1, 6):
        _day(f"2026-09-{day:02d}")
    _day("2026-10-02")


def _text(sent) -> str:
    return "\n".join(m.text for m in sent if isinstance(m, SendMessage))


def _buttons(sent) -> list[str]:
    return [b.callback_data for m in sent if isinstance(m, SendMessage) and m.reply_markup
            for row in m.reply_markup.inline_keyboard for b in row]


async def test_current_month_is_marked_not_final(bot_dp):
    main, bot = bot_dp
    _seed()
    sent = await send(main.dp, bot, EMP, text="/mymaosh")
    text = _text(sent)
    assert "Karimov" in text and "2026-10" in text and "yakuniy emas" in text and "JAMI (hozirgacha)" in text
    assert "Fiks oylik" in text  # amaldagi kelishuv qatorlari joriy oyda bor
    assert "⏳ 3-tarif mukofoti: oy tugagach hisoblanadi" in text and "300 000" not in text
    assert "Bonus banki" not in text
    assert _buttons(sent) == ["mypay:1"]


async def test_previous_month_does_not_mix_current_data(bot_dp):
    main, bot = bot_dp
    _seed()
    sent = await send_callback(main.dp, bot, EMP, data="mypay:1", target_chat_id=EMP)
    text = _text(sent)
    assert "2026-09" in text and "2026-10" not in text
    assert "yakuniy emas" not in text and "JAMI:" in text
    assert "Fiks oylik" not in text  # amaldagi kelishuv o'tgan oy ekraniga aralashmaydi
    assert "Ishlagan: 50 soat" in text  # faqat sentyabr kunlari (5 × 10 soat)
    assert _buttons(sent) == ["mypay:0"]


async def test_other_user_never_sees_someone_elses_salary(bot_dp):
    main, bot = bot_dp
    _seed()
    for data in ("mypay:0", "mypay:1"):
        text = _text(await send_callback(main.dp, bot, OTHER, data=data, target_chat_id=OTHER))
        assert "Karimov" not in text and "2 500 000" not in text
    assert "Karimov" not in _text(await send(main.dp, bot, OTHER, text="/mymaosh"))


async def test_unknown_callback_and_outsider_get_nothing(bot_dp):
    main, bot = bot_dp
    _seed()
    assert "Karimov" not in _text(await send_callback(main.dp, bot, EMP, data=f"mypay:{EMP}", target_chat_id=EMP))
    assert _text(await send_callback(main.dp, bot, 777_777, data="mypay:0", target_chat_id=777_777)) == ""
