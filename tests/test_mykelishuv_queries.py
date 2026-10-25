"""/mykelishuv: bitta chaqiruvda bazaga so'rovlar soni (HANDLER_METRICS) kartalar soniga bog'liq bo'lmasligi va matn/tugmalar o'zgarmasligi."""

import re

import pytest

import db
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from roles import set_role
from services import salary_agreement as sa
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

EMP, OTHER = 894001, 894002
B1 = RECRUITING_BRANCH_NAMES[0]


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _employee(user_id, surname="Valiyev"):
    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(user_id, {"familiya": surname, "ism": "Ali", "branch": B1, "role_key": "kassir", "contacts": []})
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


def _save(token, salary, date, **kw):
    return sa.save_agreement(EMP, salary, 28, 600, date, FOUNDER_ID, token, tariff=3, with_consent=True, **kw).agreement["id"]


def _text(sent):
    return "\n".join(getattr(m, "text", "") or "" for m in sent)


def _buttons(sent):
    return [b.callback_data for m in sent if getattr(m, "reply_markup", None) is not None and hasattr(m.reply_markup, "inline_keyboard")
            for row in m.reply_markup.inline_keyboard for b in row]


def _metrics(capsys):
    line = [l for l in capsys.readouterr().out.splitlines() if "handler=my_agreement" in l][-1]
    return {k: int(v) for k, v in re.findall(r"(db_queries|pool_acquires)=(\d+)", line)}


async def _open(main, bot, capsys):
    capsys.readouterr()
    sent = await send(main.dp, bot, EMP, text="/mykelishuv")
    return sent, _metrics(capsys)


def _scenario(name):
    """name: none | one | many"""
    if name == "none":
        return
    first = _save("q1", 2_000_000, "2026-01-01")
    if name == "one":
        return
    f1 = _save("q2", 2_500_000, "2027-03-01")
    f2 = _save("q3", 3_000_000, "2027-06-01")
    _save("q4", 3_500_000, "2027-09-01")
    sa.record_consent(first, EMP)  # amaldagi tasdiqlangan
    sa.ask_not_understood(f1, EMP)  # ochiq savol
    sa.ask_not_understood(f2, EMP)
    from config import FOUNDER_ID as founder

    issue = sa.issue_for_agreement(f2)
    sa.resolve_issue(issue["id"], founder, sa.ISSUE_EXPLAINED)  # yopilgan savol


BEFORE = {"none": 9, "one": 14, "many": 32}  # o'zgarishdan OLDINGI haqiqiy HANDLER_METRICS db_queries (shu stsenariylar)


@pytest.mark.parametrize("name", ["none", "one", "many"])
async def test_query_count_is_lower_and_does_not_grow_with_cards(bot_dp, capsys, name):
    main, bot = bot_dp
    _employee(EMP)
    _scenario(name)
    sent, metrics = await _open(main, bot, capsys)
    print(f"MEASURE {name}: {metrics} cards={len(sent)} oldin={BEFORE[name]}")
    if name == "none":
        assert metrics["db_queries"] <= BEFORE[name]  # kelishuvsiz yo'l o'zgarmagan (faqat profil kontaktlari so'rovi olib tashlangan)
    else:
        assert metrics["db_queries"] <= 6 < BEFORE[name]  # 14 -> 5 (bitta karta), 32 -> 5 (4 karta)
    assert len(sent) == {"none": 1, "one": 1, "many": 4}[name]


async def test_cards_do_not_add_queries(bot_dp, capsys):
    main, bot = bot_dp
    _employee(EMP)
    _save("c1", 2_000_000, "2026-01-01")
    _, one = await _open(main, bot, capsys)
    _save("c2", 2_500_000, "2027-03-01")
    _save("c3", 3_000_000, "2027-06-01")
    _save("c4", 3_500_000, "2027-09-01")
    sent, many = await _open(main, bot, capsys)
    assert len(sent) == 4
    assert many["db_queries"] == one["db_queries"]  # kartalar ko'paysa ham so'rovlar soni o'zgarmaydi


@pytest.mark.parametrize("name", ["none", "one", "many"])
async def test_text_and_buttons_equal_old_per_card_path(bot_dp, name):
    import salary_agreement_bot as bot_module

    main, bot = bot_dp
    _employee(EMP)
    _scenario(name)
    sent = await send(main.dp, bot, EMP, text="/mykelishuv")
    if name == "none":
        assert len(sent) == 1 and "Kiritilmagan" in _text(sent)
        return
    expected = []
    for agreement, status in bot_module._agreement_cards(EMP):  # eski, har karta uchun alohida so'raydigan yo'l
        text = f"{bot_module._employee_text(agreement, EMP, status, bonus_note=sa.get_consent(agreement['id']) is not None)}\n\nHolat: {sa.consent_status_text(agreement)}"
        buttons = (
            [f"sagr:ok:{agreement['id']}"] + ([f"sagr:no:{agreement['id']}"] if sa.issue_for_agreement(agreement["id"]) is None else [])
            if sa.pending_consent(agreement)
            else []
        )
        expected.append((text, buttons))
    got = [(m.text, _buttons([m])) for m in sent]
    assert got == expected  # matn, tartib va tugmalar oldingidek


async def test_callback_protections_still_check_db_freshly(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    _employee(OTHER, "Boshqa")
    first = _save("p1", 2_000_000, "2026-01-01")
    await send(main.dp, bot, EMP, text="/mykelishuv")  # ko'rsatilgan kartalar
    second = _save("p2", 2_200_000, "2026-01-01")  # shu sanaga yangi kelishuv: avvalgisi almashtirildi
    await send_callback(main.dp, bot, EMP, data=f"sagr:ok:{first}", target_chat_id=EMP)  # eski tugma
    await send_callback(main.dp, bot, OTHER, data=f"sagr:ok:{second}", target_chat_id=OTHER)  # begona
    rows = {r["agreement_id"]: r for r in _consents()}
    assert rows[first]["consented_at"] is None and rows[second]["consented_at"] is None
    await send_callback(main.dp, bot, EMP, data=f"sagr:ok:{second}", target_chat_id=EMP)
    await send_callback(main.dp, bot, EMP, data=f"sagr:ok:{second}", target_chat_id=EMP)  # takroriy
    rows = {r["agreement_id"]: r for r in _consents()}
    assert rows[second]["consented_by"] == EMP and rows[first]["consented_at"] is None and len(rows) == 2


def _consents():
    conn = db.get_connection()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM salary_agreement_consents").fetchall()]
    finally:
        conn.close()
