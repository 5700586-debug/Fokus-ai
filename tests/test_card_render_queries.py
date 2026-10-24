"""Xodim kartasi bir chizilishida faol ish kuni va vaqt bonusi holati BIR marta hisoblanadi; matn va baho tugmalari
bir xil work_date'dan yaratiladi."""

import pytest

import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from services import nazoratchi_day, time_bonus
from tests.bot_harness import send_callback

pytestmark = pytest.mark.anyio

SUP = 1
EMP = 880001


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _setup() -> None:
    from roles import set_role

    set_role(SUP, "nazoratchi", set_by=FOUNDER_ID)
    set_role(EMP, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        EMP, {"familiya": "Valiyev", "ism": "Ali", "branch": RECRUITING_BRANCH_NAMES[0], "role_key": "kassir", "contacts": []}
    )
    employees.approve_profile(EMP, approved_by=FOUNDER_ID)


async def test_one_render_computes_active_day_and_time_bonus_once_with_matching_dates(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup()
    calls = {"active_day": 0, "time_bonus": 0}
    real_active, real_status = nazoratchi_day.active_day, time_bonus.get_today_status

    def counting_active(*args, **kwargs):
        calls["active_day"] += 1
        return real_active(*args, **kwargs)

    def counting_status(*args, **kwargs):
        calls["time_bonus"] += 1
        return real_status(*args, **kwargs)

    monkeypatch.setattr(nazoratchi_day, "active_day", counting_active)
    monkeypatch.setattr(time_bonus, "get_today_status", counting_status)

    sent = await send_callback(main.dp, bot, SUP, data=f"nzr_emp:{EMP}", target_chat_id=SUP)

    assert calls == {"active_day": 1, "time_bonus": 1}
    card = next(m for m in sent if getattr(m, "reply_markup", None) is not None)
    day, month, year = card.text.split("\n")[0].removeprefix("📅 Ish kuni: ").split(".")
    grade_buttons = [b.callback_data for row in card.reply_markup.inline_keyboard for b in row if b.callback_data.startswith("nzr_grade:")]
    assert len(grade_buttons) == 4 and all(data.endswith(f"{year}{month}{day}") for data in grade_buttons)


async def test_grade_press_still_validates_on_the_server_and_rerenders_once(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup()
    sent = await send_callback(main.dp, bot, SUP, data=f"nzr_emp:{EMP}", target_chat_id=SUP)
    card = next(m for m in sent if getattr(m, "reply_markup", None) is not None)
    button = next(b.callback_data for row in card.reply_markup.inline_keyboard for b in row if ":alo:" in b.callback_data)

    stale = await send_callback(main.dp, bot, SUP, data=button[:-1] + "9", target_chat_id=SUP)  # boshqa sana
    assert "Bu tugma eskirgan" in " ".join(getattr(m, "text", "") or "" for m in stale)

    calls = {"n": 0}
    real = time_bonus.get_today_status
    monkeypatch.setattr(time_bonus, "get_today_status", lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), real(*a, **k))[1])
    await send_callback(main.dp, bot, SUP, data=button, target_chat_id=SUP)

    from services import discipline
    from datetime import date

    assert discipline.get_daily_grade(EMP, button.rsplit(":", 1)[1] and f"{button[-8:-4]}-{button[-4:-2]}-{button[-2:]}") is not None
    assert calls["n"] == 1  # grade_pick qayta chizishida bir marta (xabar yuborish yo'lida ichki o'qishlar bundan mustasno)
