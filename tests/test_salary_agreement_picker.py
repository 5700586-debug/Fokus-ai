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
TERMS = "Tarif: 3\nFiks: 2 500 000\nOyiga: 28 kun\nKuniga: 10 soat\nBoshlanishi: 01.10.2026"


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
    assert "Karimov Bobur" in _text(card) and "2 500 000" in _text(card)
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
    assert len(history) == 2 and history[0] == old_rows[0] and history[1]["fixed_salary"] == 2_500_000
    assert _to(bot, B) and "Xodim tasdig'i kutilmoqda" in _text(saved)
    assert _count("salary_agreement_consents") == 2


async def test_selected_employee_is_not_replaced_by_name_in_text_and_other_data_kept(bot_dp):
    main, bot = bot_dp
    _seed()
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{A}")
    asked = await send(main.dp, bot, FOUNDER_ID, text=f"Karimov Bobur — {B2}\n" + TERMS.replace("2 500 000", "2500"))
    assert "Fiks oylik qancha" in _text(asked)
    card = await send(main.dp, bot, FOUNDER_ID, text="2,5 mln")
    out = _text(card)
    assert "Yusufov Sultonxon" in out and "Karimov" not in out and "2 500 000" in out
    assert "28 kun" in out and "10 soat" in out and "700 000" not in out and "01.10.2026" in out
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


# ------------------------------------------------------- navigatsiya --


def _no_agreement_reaction(sent):
    text = _text(sent)
    return not any(d.startswith("sagr:save:") for d in _buttons(sent)) and "Tarif raqami" not in text and "Qaysi xodim" not in text and "Fiks oylik qancha" not in text


async def _draft(main, bot, user_id=A):
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{user_id}")
    card = await send(main.dp, bot, FOUNDER_ID, text=TERMS)
    return next(d for d in _buttons(card) if d.startswith("sagr:save:"))


def _nothing_written_or_sent(bot):
    return sa.list_history(A) == [] and _to(bot, A) == []


async def test_start_removes_old_reply_keyboard_and_collecting_is_not_active_while_list_shown(bot_dp):
    from aiogram.types import ReplyKeyboardRemove

    main, bot = bot_dp
    _seed()
    sent = await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    assert isinstance(sent[0].reply_markup, ReplyKeyboardRemove) and "xodimni tanlang" in _text(sent)
    for text in ("Tarif 3", "Fiks 2 500 000", "Yusufov Sultonxon"):
        reaction = await send(main.dp, bot, FOUNDER_ID, text=text)
        assert _no_agreement_reaction(reaction), text
    assert sa.list_history(A) == []


@pytest.mark.parametrize("stale", ["⬅️ Filial", "⬅️ Orqaga", "⬅️ Do'konlar", "📍 " + B1, "💰 Smenalar"])
async def test_stale_navigation_buttons_are_not_read_as_agreement_text(bot_dp, stale):
    main, bot = bot_dp
    _seed()
    old_save = await _draft(main, bot)
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{A}")
    reaction = await send(main.dp, bot, FOUNDER_ID, text=stale)
    assert _no_agreement_reaction(reaction) and "xodimni tanlang" in _text(reaction)
    follow = await send(main.dp, bot, FOUNDER_ID, text="Fiks 2 500 000")
    assert _no_agreement_reaction(follow)  # qoralama bekor, kiritish davom etmaydi
    await _cb(main, bot, old_save)
    assert _nothing_written_or_sent(bot)


async def test_xodimlar_button_voids_draft_and_token_and_returns_to_list(bot_dp):
    main, bot = bot_dp
    _seed()
    old_save = await _draft(main, bot)
    back = await _cb(main, bot, "sagr:list")
    assert "xodimni tanlang" in _text(back) and f"sagr:new:{A}" in _buttons(back)
    await _cb(main, bot, old_save)
    reaction = await send(main.dp, bot, FOUNDER_ID, text=TERMS)
    assert _no_agreement_reaction(reaction) and _nothing_written_or_sent(bot)
    prompt = await _cb(main, bot, f"sagr:new:{A}")  # qayta kirish toza boshlanadi
    assert "Tarif: 3" in _text(prompt)
    card = await send(main.dp, bot, FOUNDER_ID, text="Fiks 2 000 000")
    assert "Tarif raqami" in _text(card)  # eski draft ma'lumotlari qolmagan


async def test_cancel_clears_draft_and_opens_list(bot_dp):
    main, bot = bot_dp
    _seed()
    old_save = await _draft(main, bot)
    cancelled = await _cb(main, bot, "sagr:cancel")
    assert "xodimni tanlang" in _text(cancelled)
    await _cb(main, bot, old_save)
    assert _no_agreement_reaction(await send(main.dp, bot, FOUNDER_ID, text=TERMS)) and _nothing_written_or_sent(bot)


async def test_leaving_to_other_menu_clears_draft(bot_dp):
    main, bot = bot_dp
    _seed()
    old_save = await _draft(main, bot)
    await send(main.dp, bot, FOUNDER_ID, text="🏬 Do'konlar")
    reaction = await send(main.dp, bot, FOUNDER_ID, text="Fiks 2 500 000")
    assert _no_agreement_reaction(reaction)
    await _cb(main, bot, old_save)
    assert _nothing_written_or_sent(bot)
    again = await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    assert "xodimni tanlang" in _text(again)


async def test_home_button_returns_menu_and_clears_state(bot_dp):
    main, bot = bot_dp
    _seed()
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    sent = await _cb(main, bot, "sagr:home")
    assert "Asosiy menyu" in _text(sent) and _nothing_written_or_sent(bot)


async def test_navigation_from_non_founder_is_rejected(bot_dp):
    main, bot = bot_dp
    _seed()
    await _cb(main, bot, "sagr:list", user=A)
    await _cb(main, bot, "sagr:cancel", user=A)
    assert "xodimni tanlang" not in _text(_to(bot, A))


# ------------------------------------------- navigatsiya himoyasi: qolgan ikki xato --


async def _pick_and_send(main, bot, text, user_id=A):
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{user_id}")
    return await send(main.dp, bot, FOUNDER_ID, text=text)


@pytest.mark.parametrize("line", ["💵 Fiks: 2 500 000", "• Fiks: 2 500 000", "— Fiks 2 500 000", "✅ fiks: 2.500.000"])
async def test_symbol_prefixed_input_is_not_navigation_and_keeps_draft(bot_dp, line):
    main, bot = bot_dp
    _seed()
    asked = await _pick_and_send(main, bot, TERMS.replace("Fiks: 2 500 000\n", ""))
    assert "Fiks oylik qancha" in _text(asked)
    card = await send(main.dp, bot, FOUNDER_ID, text=line)
    out = _text(card)
    assert "xodimni tanlang" not in out and "2 500 000" in out and "Yusufov" in out
    assert any(d.startswith("sagr:save:") for d in _buttons(card))
    assert "28 kun" in out and "700 000" not in out  # oldingi maydonlar saqlangan
    assert sa.list_history(A) == []


async def test_bullet_tariff_line_is_input(bot_dp):
    main, bot = bot_dp
    _seed()
    asked = await _pick_and_send(main, bot, TERMS.replace("Tarif: 3\n", ""))
    assert "Tarif raqami" in _text(asked)
    card = await send(main.dp, bot, FOUNDER_ID, text="• Tarif: 3")
    assert any(d.startswith("sagr:save:") for d in _buttons(card)) and "Tarif: 3" in _text(card)


async def test_not_understood_reply_keeps_draft_and_short_answer_continues(bot_dp):
    main, bot = bot_dp
    _seed()
    await _pick_and_send(main, bot, TERMS.replace("Fiks: 2 500 000\n", ""))
    again = await send(main.dp, bot, FOUNDER_ID, text="🤷 bilmayman")
    assert "Fiks oylik qancha" in _text(again) and "xodimni tanlang" not in _text(again)
    card = await send(main.dp, bot, FOUNDER_ID, text="2,5 mln")
    out = _text(card)
    assert any(d.startswith("sagr:save:") for d in _buttons(card))
    assert "Yusufov" in out and "2 500 000" in out and "28 kun" in out and "10 soat" in out and "700 000" not in out


async def test_page_button_from_old_message_clears_draft_and_token(bot_dp):
    main, bot = bot_dp
    _seed()
    old_save = await _draft(main, bot)  # tekshirish kartasi (confirming)
    listing = await _cb(main, bot, "sagr:pg:0")  # oldingi xabardagi sahifa tugmasi
    assert "xodimni tanlang" in _text(listing)
    await _cb(main, bot, old_save)
    assert _nothing_written_or_sent(bot)
    reaction = await send(main.dp, bot, FOUNDER_ID, text=TERMS)
    assert _no_agreement_reaction(reaction)


async def test_page_button_during_collecting_clears_draft(bot_dp):
    main, bot = bot_dp
    _seed()
    await _pick_and_send(main, bot, TERMS.replace("Fiks: 2 500 000\n", ""))
    await _cb(main, bot, "sagr:pg:0")
    reaction = await send(main.dp, bot, FOUNDER_ID, text="2 500 000")
    assert _no_agreement_reaction(reaction) and sa.list_history(A) == []


@pytest.mark.parametrize("stale", ["⬅️ Filial", "⬅️ Orqaga", "⬅️ Do'konlar", "💰 Smenalar", "📍 " + B1, "🔙 Orqaga", "❌ Bekor qilish"])
async def test_exact_navigation_texts_still_leave_the_draft(bot_dp, stale):
    main, bot = bot_dp
    _seed()
    old_save = await _draft(main, bot)
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{A}")
    await send(main.dp, bot, FOUNDER_ID, text=TERMS.replace("Fiks: 2 500 000\n", ""))
    await send(main.dp, bot, FOUNDER_ID, text=stale)
    follow = await send(main.dp, bot, FOUNDER_ID, text="2 500 000")
    assert _no_agreement_reaction(follow)
    await _cb(main, bot, old_save)
    assert _nothing_written_or_sent(bot)


# ------------------------------------------------ natija bonusi olib tashlandi --

NOTE = "Oylik bonus: 140 ⭐ — 700 000 so'mgacha ishlab topishingiz mumkin. 1 ⭐ = 5 000 so'm."


async def test_pick_then_five_fields_card_has_no_bonus_and_nothing_saved_or_sent(bot_dp):
    main, bot = bot_dp
    _seed()
    prompt = await _pick_and_send_prompt(main, bot)
    assert "Natija bonusi" not in prompt and "700" not in prompt and "eng ko'pi" not in prompt
    card = await send(main.dp, bot, FOUNDER_ID, text=TERMS)
    out = _text(card)
    assert "Yusufov" in out and "Tarif: 3" in out and "2 500 000" in out and "28 kun" in out and "10 soat" in out and "01.10.2026" in out
    assert "onus" not in out and "⭐" not in out and "700" not in out
    assert any(d.startswith("sagr:save:") for d in _buttons(card))
    assert sa.list_history(A) == [] and _to(bot, A) == [] and _count("salary_agreement_consents") == 1


async def _pick_and_send_prompt(main, bot):
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    return _text(await _cb(main, bot, f"sagr:new:{A}"))


async def test_bonus_text_in_input_is_ignored_and_saved_value_is_null_and_employee_gets_exact_note(bot_dp):
    main, bot = bot_dp
    _seed()
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{A}")
    card = await send(main.dp, bot, FOUNDER_ID, text=TERMS + "\nNatija bonusi: 700 000")
    assert "onus" not in _text(card) and "700" not in _text(card)
    saved = await _cb(main, bot, next(d for d in _buttons(card) if d.startswith("sagr:save:")))
    row = sa.list_history(A)[0]
    assert row["result_bonus_cap"] is None and row["fixed_salary"] == 2_500_000 and row["daily_minutes"] == 600
    employee_msgs = _to(bot, A)
    assert employee_msgs and NOTE in _text(employee_msgs)
    assert NOTE not in _text([m for m in bot.sent if getattr(m, "chat_id", None) == FOUNDER_ID])
    mine = await send(main.dp, bot, A, text="/mykelishuv")
    assert NOTE in _text(mine)
    shown = await _cb(main, bot, f"sagr:show:{A}")  # Founder ko'rinishida bonus matni yo'q
    assert NOTE not in _text(shown) and "700 000" not in _text(shown)


@pytest.mark.parametrize("line", ["Fiks oylik 2.500.000", "Oylik fiks: 2 500 000", "Fiks: 2500000"])
async def test_three_fixed_spellings_read_as_same_amount(bot_dp, line):
    main, bot = bot_dp
    _seed()
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{A}")
    text = f"Tarif: 3\n{line}\nOyiga: 28 kun\nKuniga: 10 soat\nBoshlanishi: 01.10.2026"
    card = await send(main.dp, bot, FOUNDER_ID, text=text)
    assert "2 500 000" in _text(card) and any(d.startswith("sagr:save:") for d in _buttons(card))


async def test_long_labels_and_days_are_not_taken_as_amount(bot_dp):
    main, bot = bot_dp
    _seed()
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{A}")
    text = "Oylik ish kunlari 28 kun\nKunlik ish soati 10 soat\nAmal qilish sanasi 01.10.2026\nFiks oylik 2.500.000\nAmaldagi kelishuv 3"
    asked = await send(main.dp, bot, FOUNDER_ID, text=text)
    out = _text(asked)
    assert "Tarif raqami" in out and "⚠️" not in out  # faqat tarif so'raladi; boshqa maydon xatosi ko'rsatilmaydi
    card = await send(main.dp, bot, FOUNDER_ID, text="3")
    c = _text(card)
    assert "2 500 000" in c and "28 kun" in c and "10 soat" in c and "01.10.2026" in c and "Tarif: 3" in c


async def test_each_question_shows_only_its_own_field_error(bot_dp):
    main, bot = bot_dp
    _seed()
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    await _cb(main, bot, f"sagr:new:{A}")
    asked = await send(main.dp, bot, FOUNDER_ID, text="Fiks: 2500\nOyiga: 40 kun\nKuniga: 10 soat\nTarif: 3")
    out = _text(asked)
    assert "Aniq yozing" in out and "1 dan 31 gacha" not in out and "Fiks oylik qancha" in out
    asked = await send(main.dp, bot, FOUNDER_ID, text="2,5 mln")
    out = _text(asked)
    assert "1 dan 31 gacha" in out and "Aniq yozing" not in out and "Oyiga necha ish kuni" in out
    asked = await send(main.dp, bot, FOUNDER_ID, text="28")
    assert "sanadan boshlanadi" in _text(asked) and "⚠️" not in _text(asked)
