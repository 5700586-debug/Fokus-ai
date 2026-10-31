"""Qo'shimcha ish yulduzi: faqat ruxsatli beruvchi, sabab majburiy, takroriy tasdiq ikki marta yozmaydi, xodimga xabar."""

import pytest
from aiogram.methods import SendMessage

from config import FOUNDER_ID
from db import get_connection
from services import extra_stars
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

EMP, OTHER, BOSS, FAR = 701, 702, 703, 704


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _seed() -> None:
    conn = get_connection()
    try:
        for uid, branch in ((EMP, "SATURN A"), (OTHER, "SATURN A"), (BOSS, "SATURN A"), (FAR, "SATURN B")):
            conn.execute("INSERT INTO employees (user_id, familiya, ism, branch, status) VALUES (?, 'Karimov', 'Vali', ?, "
                         "'approved')", (uid, branch))
        conn.commit()
    finally:
        conn.close()


def _rows() -> list[dict]:
    conn = get_connection()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM extra_work_stars").fetchall()]
    finally:
        conn.close()


def test_service_validation_and_idempotency():
    _seed()
    with pytest.raises(extra_stars.ExtraStarsError):
        extra_stars.give(EMP, 3, "2 soat qoldi", OTHER, "t0")  # ruxsat yo'q
    with pytest.raises(extra_stars.ExtraStarsError):
        extra_stars.give(EMP, 0, "2 soat qoldi", FOUNDER_ID, "t1")
    with pytest.raises(extra_stars.ExtraStarsError):
        extra_stars.give(EMP, 3, "ok", FOUNDER_ID, "t2")
    with pytest.raises(extra_stars.ExtraStarsError):
        extra_stars.give(999_999, 3, "2 soat qoldi", FOUNDER_ID, "t3")
    assert extra_stars.give(EMP, 3, "2 soat qoldi", FOUNDER_ID, "t4") is True
    assert extra_stars.give(EMP, 3, "2 soat qoldi", FOUNDER_ID, "t4") is False
    assert len(_rows()) == 1


async def test_founder_flow_writes_once_and_notifies_employee(bot_dp):
    main, bot = bot_dp
    _seed()
    await send_callback(main.dp, bot, FOUNDER_ID, data="xs:list:0", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, data=f"xs:pick:{EMP}", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, data=f"xs:n:{EMP}:4", target_chat_id=FOUNDER_ID)
    assert _rows() == []
    sent = await send(main.dp, bot, FOUNDER_ID, text="Inventarizatsiyada 2 soat qoldi")
    confirm = next(m for m in sent if isinstance(m, SendMessage) and "Tekshiring" in m.text)
    token_data = confirm.reply_markup.inline_keyboard[0][0].callback_data
    assert _rows() == []

    sent = await send_callback(main.dp, bot, FOUNDER_ID, data=token_data, target_chat_id=FOUNDER_ID)
    rows = _rows()
    assert len(rows) == 1 and rows[0]["stars"] == 4 and rows[0]["employee_id"] == EMP and rows[0]["given_by"] == FOUNDER_ID
    assert any(isinstance(m, SendMessage) and m.chat_id == EMP and "+4 yulduz" in m.text for m in sent)

    await send_callback(main.dp, bot, FOUNDER_ID, data=token_data, target_chat_id=FOUNDER_ID)  # takroriy bosish
    assert len(_rows()) == 1


async def test_employee_cannot_give_stars(bot_dp):
    main, bot = bot_dp
    _seed()
    sent = await send_callback(main.dp, bot, EMP, data=f"xs:n:{OTHER}:10", target_chat_id=EMP)
    assert not any(isinstance(m, SendMessage) and "Qanday qo'shimcha ish" in m.text for m in sent)
    assert _rows() == []


async def test_cancel_writes_nothing(bot_dp):
    main, bot = bot_dp
    _seed()
    await send_callback(main.dp, bot, FOUNDER_ID, data=f"xs:n:{EMP}:2", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, data="xs:cancel", target_chat_id=FOUNDER_ID)
    stale = await send_callback(main.dp, bot, FOUNDER_ID, data="xs:ok:deadbeef", target_chat_id=FOUNDER_ID)
    assert any(isinstance(m, SendMessage) and "eskirgan" in m.text for m in stale)
    assert _rows() == []


def test_branch_manager_gives_only_to_own_branch():
    from roles import set_role

    _seed()
    set_role(BOSS, "savdo_boshligi", set_by=FOUNDER_ID)
    assert extra_stars.give(EMP, 2, "Kechki yuk tushirishda qoldi", BOSS, "b1") is True
    with pytest.raises(extra_stars.ExtraStarsError):
        extra_stars.give(FAR, 2, "Kechki yuk tushirishda qoldi", BOSS, "b2")
    assert extra_stars.give(FAR, 2, "Rahbar yo'qligida Founder berdi", FOUNDER_ID, "b3") is True
    assert len(_rows()) == 2


async def test_branch_manager_list_shows_only_own_branch(bot_dp):
    from aiogram.methods import SendMessage as _SM
    from roles import set_role

    main, bot = bot_dp
    _seed()
    set_role(BOSS, "savdo_boshligi", set_by=FOUNDER_ID)
    sent = await send(main.dp, bot, BOSS, text="/qoshimchaish")
    listing = next(m for m in sent if isinstance(m, _SM) and "Qo'shimcha ish yulduzi" in m.text)
    targets = {b.callback_data for row in listing.reply_markup.inline_keyboard for b in row}
    assert f"xs:pick:{EMP}" in targets and f"xs:pick:{FAR}" not in targets
