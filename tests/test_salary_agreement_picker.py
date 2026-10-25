"""/kelishuv: xodimni ro'yxatdan tanlash (➕ / ✅ / 🔄), tanlangan xodim bilan kiritish, himoyalar. Telegram mock."""

import pytest

import db
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from roles import set_role
from services import salary_agreement as sa
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

A, B, C, D, E = 893001, 893002, 893003, 893004, 893005
B1, B2 = RECRUITING_BRANCH_NAMES[0], RECRUITING_BRANCH_NAMES[1]
TERMS = "Tarif: 3\nFiks: 1 800 000\nOyiga: 28 kun\nKuniga: 11 soat\nNatija bonusi: 700 000\nBoshlanishi: 01.10.2026"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _employee(user_id, surname, ism="Sultonxon", branch=B1, role="kassir", status="approved"):
    set_role(user_id, role, set_by=FOUNDER_ID)
    employees.submit_profile(user_id, {"familiya": surname, "ism": ism, "branch": branch, "role_key": role, "contacts": []})
    if status == "approved":
        employees.approve_profile(user_id, approved_by=FOUNDER_ID)
    if branch is None:  # filialga biriktirilmagan (ma'lumot sun'iy o'zgartirilmaydi — to'g'ridan-to'g'ri NULL)
        conn = db.get_connection()
        try:
            conn.execute("UPDATE employees SET branch = NULL WHERE user_id = ?", (user_id,))
            conn.commit()
        finally:
            conn.close()


def _text(sent):
    return "\n".join(getattr(m, "text", "") or "" for m in sent)


def _rows(sent):
    for m in sent:
        markup = getattr(m, "reply_markup", None)
        if markup is not None and hasattr(markup, "inline_keyboard"):
            return [[(b.text, b.callback_data) for b in row] for row in markup.inline_keyboard]
    return []


def _buttons(sent):
    return [d for row in _rows(sent) for _, d in row]


def _count(table):
    conn = db.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
    finally:
        conn.close()


async def _cb(main, bot, data, user=FOUNDER_ID):
    return await send_callback(main.dp, bot, user, data=data, target_chat_id=user)


def _to(bot, chat):
    return [m for m in bot.sent if getattr(m, "chat_id", None) == chat]


def _seed(bot=None):
    _employee(A, "Yusufov")  # kelishuvi yo'q
    _employee(B, "Karimov", "Bobur", branch=B2)  # kelishuvi bor
    _employee(C, "Nomalum", "Filialsiz", branch=None)  # filialsiz
    _employee(D, "Kutilmoqda", "Pending", status="pending")  # tasdiqlanmagan — chiqmaydi
    sa.save_agreement(B, 2_000_000, 26, 600, "2026-01-01", FOUNDER_ID, "seed-b", tariff=2, with_consent=True)


async def test_list_has_all_approved_incl_unassigned_new_on_top_existing_below_with_two_buttons(bot_dp):
    main, bot = bot_dp
    _seed()
    sent = await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    rows = _rows(sent)
    flat = [t for row in rows for t, _ in row]
    assert any("Yusufov" in t for t in flat) and any("Filialsiz" in t for t in flat) and any("Karimov" in t for t in flat)
    assert not any("Pending" in t for t in flat)
    names = [row[0][0] for row in rows if row[0][1].startswith(("sagr:new", "sagr:show"))]
    assert [n[0] for n in names] == ["➕", "➕", "✅"]  # kelishuvi yo'qlar tepada
    existing = next(row for row in rows if row[0][1].startswith("sagr:show"))
    assert [t for t, _ in existing][1] == "🔄" and existing[0][1] == f"sagr:show:{B}" and existing[1][1] == f"sagr:new:{B}"
    assert f"sagr:new:{A}" in _buttons(sent) and f"sagr:new:{C}" in _buttons(sent) and f"sagr:new:{D}" not in _buttons(sent)
    assert _count("salary_agreements") == 1


async def test_same_names_are_told_apart_but_selected_by_employee_id(bot_dp):
    main, bot = bot_dp
    _employee(A, "Yusufov", branch=B1)
    _employee(E, "Yusufov", branch=B2)
    _employee(B, "Yusufov", branch=B2)
    sent = await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    labels = {d: t for row in _rows(sent) for t, d in row if d.startswith("sagr:new")}
    assert len(set(labels.values())) == 3 and f"#{E}" in labels[f"sagr:new:{E}"] and f"#{B}" in labels[f"sagr:new:{B}"]
    assert B1 in labels[f"sagr:new:{A}"]


async def test_pagination(bot_dp):
    main, bot = bot_dp
    for i in range(13):
        _employee(A + 100 + i, f"Familiya{i:02d}")
    first = await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    assert len([d for d in _buttons(first) if d.startswith("sagr:new")]) == 10 and "sagr:pg:1" in _buttons(first)
    second = await _cb(main, bot, "sagr:pg:1")
    assert len([d for d in _buttons(second) if d.startswith("sagr:new")]) == 3 and "sagr:pg:0" in _buttons(second)


async def test_show_is_readonly_and_shows_current_future_and_consent_status(bot_dp):
    main, bot = bot_dp
    _seed()
    sa.save_agreement(B, 2_500_000, 28, 660, "2027-06-01", FOUNDER_ID, "seed-b2", tariff=3, with_consent=True)
    sa.save_legacy_fixed_salary(C, 3_000_000, FOUNDER_ID)
    before = (_count("salary_agreements"), _count("salary_agreement_consents"))
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    shown = await _cb(main, bot, f"sagr:show:{B}")
    text = _text(shown)
    assert "Amaldagi kelishuv" in text and "2 000 000" in text and "Kelajakdagi kelishuv" in text and "2 500 000" in text
    assert "01.06.2027" in text and "Xodim tasdig'i kutilmoqda" in text
    assert f"sagr:new:{B}" in _buttons(shown)
    legacy = await _cb(main, bot, f"sagr:show:{C}")
    assert "3 000 000" in _text(legacy) and "Kiritilmagan" in _text(legacy)  # kun/soat taxmin qilinmaydi
    assert (_count("salary_agreements"), _count("salary_agreement_consents")) == before
    assert _to(bot, B) == [] and _to(bot, C) == []


async def test_new_for_existing_creates_new_version_keeps_history_and_cancel_keeps_old(bot_dp):
    main, bot = bot_dp
    _seed()
    old_rows = sa.list_history(B)
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    prompt = await _cb(main, bot, f"sagr:new:{B}")
    assert "Karimov Bobur" in _text(prompt) and "Tarif: 3" in _text(prompt)
    card = await send(main.dp, bot, FOUNDER_ID, text=TERMS.replace("01.10.2026", "01.06.2027"))
    assert "Karimov Bobur" in _text(card) and "1 800 000" in _text(card)
    assert sa.list_history(B) == old_rows and _to(bot, B) == []  # tasdiqlashgacha yozuv/xabar yo'q
    save = next(d for d in _buttons(card) if d.startswith("sagr:save:"))
    await _cb(main, bot, "sagr:cancel")
    await _cb(main, bot, save)  # bekor qilingan kartaning tugmasi
    assert sa.list_history(B) == old_rows
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{B}")
    card = await send(main.dp, bot, FOUNDER_ID, text=TERMS.replace("01.10.2026", "01.06.2027"))
    saved = await _cb(main, bot, next(d for d in _buttons(card) if d.startswith("sagr:save:")))
    history = sa.list_history(B)
    assert len(history) == 2 and history[0] == old_rows[0] and history[1]["fixed_salary"] == 1_800_000
    assert _to(bot, B) and "Xodim tasdig'i kutilmoqda" in _text(saved)
    assert _count("salary_agreement_consents") == 2


async def test_selected_employee_is_not_replaced_by_name_in_text_and_other_data_kept(bot_dp):
    main, bot = bot_dp
    _seed()
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{A}")
    asked = await send(main.dp, bot, FOUNDER_ID, text=f"Karimov Bobur — {B2}\n" + TERMS.replace("1 800 000", "1800"))
    assert "Fiks oylik qancha" in _text(asked) and not any(d.startswith("sagr:pick") for d in _buttons(asked))
    card = await send(main.dp, bot, FOUNDER_ID, text="1,8 mln")
    out = _text(card)
    assert "Yusufov Sultonxon" in out and "Karimov" not in out and "1 800 000" in out
    assert "28 kun" in out and "11 soat" in out and "700 000" in out and "01.10.2026" in out
    await _cb(main, bot, next(d for d in _buttons(card) if d.startswith("sagr:save:")))
    assert [r["employee_id"] for r in sa.list_history(A)] == [A] and sa.list_history(B)[0]["fixed_salary"] == 2_000_000


async def test_switching_employee_voids_old_draft_and_old_card(bot_dp):
    main, bot = bot_dp
    _seed()
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{A}")
    card = await send(main.dp, bot, FOUNDER_ID, text=TERMS)
    old_save = next(d for d in _buttons(card) if d.startswith("sagr:save:"))
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{C}")
    await _cb(main, bot, old_save)
    assert sa.list_history(A) == [] and sa.list_history(C) == []
    card2 = await send(main.dp, bot, FOUNDER_ID, text=TERMS)
    assert "Filialsiz" in _text(card2) and "Biriktirilmagan" in _text(card2)
    save2 = next(d for d in _buttons(card2) if d.startswith("sagr:save:"))
    await _cb(main, bot, save2)
    await _cb(main, bot, save2)  # takroriy
    assert len(sa.list_history(C)) == 1 and sa.list_history(A) == []


async def test_unauthorized_and_unapproved_are_rejected(bot_dp):
    main, bot = bot_dp
    _seed()
    await send(main.dp, bot, A, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{B}", user=A)
    await _cb(main, bot, f"sagr:show:{B}", user=A)
    assert "2 000 000" not in _text([m for m in bot.sent if getattr(m, "chat_id", None) == A])
    state_probe = await _cb(main, bot, f"sagr:new:{D}")  # tasdiqlanmagan xodim
    assert "Karimov" not in _text(state_probe) and "Tarif:" not in _text(state_probe)
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    employees.offboard_profile(A)  # tanlangandan keyin xodim endi tasdiqlanmagan
    gone = await _cb(main, bot, f"sagr:new:{A}")
    assert "Tarif:" not in _text(gone) and sa.list_history(A) == []
