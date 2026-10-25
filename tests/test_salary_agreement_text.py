"""/kelishuv namunasi va erkin matnni tushunish: kirill/lotin/aralash, imlo xatosi, noaniqlik, o'xshash ismlar. Telegram mock."""

import pytest

import db
import employees
import salary_agreement_bot as bot_module
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from roles import set_role
from services import salary_agreement_text as sat
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

EMP, EMP2, EMP3 = 892001, 892002, 892003
B1, B2 = RECRUITING_BRANCH_NAMES[0], RECRUITING_BRANCH_NAMES[1]
SAMPLE = (
    "Yusufov Sultonxon — Saturn Charhiy\nTarif: 3\nFiks: 1 800 000\nOyiga: 28 kun\nKuniga: 11 soat\n"
    "Natija bonusi: 700 000\nBoshlanishi: 01.10.2026"
)
EXPECTED = {"tariff": 3, "fixed_salary": 1_800_000, "work_days": 28, "daily_minutes": 660, "effective_from": "2026-10-01"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _employee(user_id, surname="Yusufov", ism="Sultonxon", branch=B1):
    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(user_id, {"familiya": surname, "ism": ism, "branch": branch, "role_key": "kassir", "contacts": []})
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


def _text(sent):
    return "\n".join(getattr(m, "text", "") or "" for m in sent)


def _buttons(sent):
    return [b.callback_data for m in sent if getattr(m, "reply_markup", None) is not None and hasattr(m.reply_markup, "inline_keyboard")
            for row in m.reply_markup.inline_keyboard for b in row]


def _count(table):
    conn = db.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
    finally:
        conn.close()


async def _pick(main, bot, user_id):
    await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    return await send_callback(main.dp, bot, FOUNDER_ID, data=f"sagr:new:{user_id}", target_chat_id=FOUNDER_ID)


def _values(text):
    result = sat.parse_text(text)
    assert not result.problems, result.problems
    return {k: v for k, v in result.values.items() if k not in ("employee", "result_bonus_cap", "bonus_none")}, result.values.get("employee")


def test_sample_text_is_exact_and_old_name_removed():
    assert bot_module.SAMPLE == "Tarif: 3\nFiks: 2 500 000\nOyiga: 28 kun\nKuniga: 10 soat\nBoshlanishi: 01.10.2026"
    assert "onus" not in bot_module.SAMPLE and "700" not in bot_module.SAMPLE
    import inspect

    assert "Eshmat" not in inspect.getsource(bot_module) and "Shermatov" not in inspect.getsource(bot_module)
    values, employee = _values(SAMPLE)
    assert values == EXPECTED and sat.norm(employee["name"]) == "yusufov sultonxon" and sat.norm(employee["branch_hint"]) == "saturn charhiy"


@pytest.mark.parametrize(
    "text",
    [
        "Юсуфов Султонхон — Сатурн Чархий\nТариф: 3\nФикс: 1 800 000 сўм\nОйига: 28 кун\nКунига: 11 соат\nНатижа бонуси: 700 000\nБошланиши: 01.10.2026",
        "Юсуфов Sultonxon — Saturn Charhiy\nТариф 3\nFiks 1,8 mln\nOyiga 28 кун\nКуниga: 11 soat\nНатижа бонуси: 700 минг\nBoshlanishi: 1.10.2026",
        "Boshlanishi: 01.10.2026\nNatija bonusi: 700.000\nKuniga: 11 soat\nOyiga: 28 kun\nFiks: 1800000\nTarif: 3\nYusufov Sultonxon — Saturn Charhiy",
    ],
)
def test_cyrillic_latin_mixed_and_any_order(text):
    values, employee = _values(text)
    assert values == EXPECTED
    assert sat.norm(employee["name"]) == "yusufov sultonxon" and B1 in sat._branch_matches(employee["branch_hint"])


def test_common_spelling_mistakes_and_formats():
    values, _ = _values(
        "Yusufov Sultonxon, Saturn Charhiy\nTarf: 3\nfix: 1800000 som\noyiga 28 kunn\nkuniga 11\nbunus: 700 ming\nboshlanishi 1 oktabr 2026"
    )
    assert values == EXPECTED
    values, employee = _values("Yusufov Sultonxon Saturn Charhiy\nTarif 3\nFiks 1.800.000\n28 ish kuni\n11 soat\nNatija bonusi 700 000\n01/10/2026")
    assert values == EXPECTED and B1 in sat._branch_matches(employee["branch_hint"])


def test_ambiguous_amount_and_date_are_asked_not_guessed():
    result = sat.parse_text("Fiks: 1800\nNatija bonusi: 700\nBoshlanishi: 01.10\nOyiga: 28 kun")
    assert "fixed_salary" not in result.values and "fixed_salary" in result.problems
    assert "effective_from" not in result.values and result.values["work_days"] == 28


def test_similar_and_misspelled_names_offer_candidates_never_pick_alone(temp_db):
    _employee(EMP, "Yusufov", "Sultonxon", B1)
    _employee(EMP2, "Yusufov", "Sultonxon", B2)
    _employee(EMP3, "Yusupov", "Sultonbek", B1)
    found, exact = sat.find_employees("Yusufov Sultonxon", None)
    assert {p["user_id"] for p in found} == {EMP, EMP2} and not exact  # bir xil ism — tanlanadi
    found, exact = sat.find_employees("Yusufov Sultonxon", B1)
    assert {p["user_id"] for p in found} == {EMP, EMP2} and not exact
    found, exact = sat.find_employees("Юсуфов Султонхон", None)  # kirill — lotin bilan mos
    assert {p["user_id"] for p in found} == {EMP, EMP2}
    found, exact = sat.find_employees("Yusufof Sultanxon", None)  # imlo xatosi
    assert EMP in {p["user_id"] for p in found} and not exact
    found, exact = sat.find_employees("Karimov Bobur", None)
    assert found == [] and not exact
    found, exact = sat.find_employees("Yusupov Sultonbek", "Saturn Charxiy")  # filial imlosi xato, ism aniq
    assert [p["user_id"] for p in found] == [EMP3] and exact


async def test_list_does_not_pick_employee_or_create_agreement_and_nothing_saved_before_confirm(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    sent = await send(main.dp, bot, FOUNDER_ID, text="/kelishuv")
    assert "xodimni tanlang" in _text(sent) and not any(b.startswith("sagr:save:") for b in _buttons(sent))
    assert _count("salary_agreements") == 0
    prompt = await _pick(main, bot, EMP)
    assert "Yusufov Sultonxon" in _text(prompt) and "Tarif: 3" in _text(prompt)
    card = await send(main.dp, bot, FOUNDER_ID, text=SAMPLE.replace("Yusufov Sultonxon", "Юсуфов Султонхон").replace("Saturn Charhiy", "Сатурн Чархий"))
    text = _text(card)
    assert "Yusufov Sultonxon" in text and "1 800 000" in text and "700 000" not in text and "Natija bonusi" not in text
    assert any(b.startswith("sagr:save:") for b in _buttons(card))
    assert _count("salary_agreements") == 0 and _count("salary_agreement_consents") == 0
    assert not [m for m in bot.sent if getattr(m, "chat_id", None) == EMP]  # xodimga hech narsa ketmagan


async def test_ambiguous_amount_is_asked_then_short_answer_completes_card(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    await _pick(main, bot, EMP)
    asked = await send(main.dp, bot, FOUNDER_ID, text=SAMPLE.replace("1 800 000", "1800"))
    assert "Fiks oylik qancha" in _text(asked) and "1800" in _text(asked)
    assert not any(b.startswith("sagr:save:") for b in _buttons(asked))
    card = await send(main.dp, bot, FOUNDER_ID, text="1,8 mln")
    assert any(b.startswith("sagr:save:") for b in _buttons(card)) and "1 800 000" in _text(card)
    assert _count("salary_agreements") == 0


# ------------------------------------------- ism qatori istalgan o'rinda --

_BODY = ["Tarif 3", "Fiks 1 800 000", "Oyiga 28 kun", "Kuniga 11", "Natija bonusi 700 000", "Boshlanishi 01.10.2026"]
_NAME = "Yusufov Sultonxon — Saturn Charhiy"


def _compose(position, colons=False, transform=lambda t: t):
    body = [line.replace(" ", ": ", 1) if colons and line.split(" ", 1)[0] != "Natija" else line for line in _BODY]
    if colons:
        body[4] = "Natija bonusi: 700 000"
    lines = list(body)
    lines.insert({"start": 0, "middle": 3, "end": len(lines)}[position], _NAME)
    return transform("\n".join(lines))


@pytest.mark.parametrize("position", ["start", "middle", "end"])
@pytest.mark.parametrize("colons", [False, True])
def test_name_line_anywhere_with_or_without_colons(position, colons):
    values, employee = _values(_compose(position, colons))
    assert values == EXPECTED
    assert employee is not None and sat.norm(employee["name"]) == "yusufov sultonxon"
    assert B1 in sat._branch_matches(employee["branch_hint"])


_CYR_TEXT = "Тариф 3\nФикс 1 800 000 сўм\nОйига 28 кун\nКунига 11 соат\nНатижа бонуси 700 000\nБошланиши 01.10.2026\nЮсуфов Султонхон — Сатурн Чархий"
_MIXED_TYPO = "Tarf: 3\nfix 1800000\nOyiga 28 kunn\nkuniga: 11\nBunus 700 ming\nboshlanishi 1 oktabr 2026\nЮсуфов Sultonxon — Saturn Charhiy"


@pytest.mark.parametrize("text", [_CYR_TEXT, _MIXED_TYPO])
def test_cyrillic_mixed_and_typo_labels_are_not_taken_as_name(text):
    values, employee = _values(text)
    assert values == EXPECTED
    assert sat.norm(employee["name"]) == "yusufov sultonxon"


def test_label_lines_with_typos_never_become_the_name():
    for line in ("Tarf 3", "Bunus 700 000", "Tarif", "Natija bonusi", "Boshlanishi", "Kuniga", "Fiks"):
        assert "employee" not in sat.parse_text(line, name_words=1).values, line
    assert sat.norm(sat.parse_text("Sanaev Bek", name_words=2).values["employee"]["name"]) == "sanaev bek"


async def test_reordered_text_makes_card_without_extra_questions(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    await _pick(main, bot, EMP)
    card = await send(main.dp, bot, FOUNDER_ID, text=_compose("end"))
    text = _text(card)
    assert "Yusufov Sultonxon" in text and B1 in text and "1 800 000" in text and "28 kun" in text
    assert "11 soat" in text and "700 000" not in text and "01.10.2026" in text
    assert any(b.startswith("sagr:save:") for b in _buttons(card))
    assert _count("salary_agreements") == 0 and _count("salary_agreement_consents") == 0
    assert not [m for m in bot.sent if getattr(m, "chat_id", None) == EMP]


async def test_short_amount_answer_completes_card_and_keeps_other_data(bot_dp):
    main, bot = bot_dp
    _employee(EMP)
    await _pick(main, bot, EMP)
    text = _compose("middle").replace("Fiks 1 800 000", "Fiks 1800")
    asked = await send(main.dp, bot, FOUNDER_ID, text=text)
    assert "Fiks oylik qancha" in _text(asked) and not any(b.startswith("sagr:save:") for b in _buttons(asked))
    card = await send(main.dp, bot, FOUNDER_ID, text="1 800 000")
    out = _text(card)
    assert "Yusufov Sultonxon" in out and "1 800 000" in out and "28 kun" in out and "11 soat" in out
    assert "700 000" not in out and "01.10.2026" in out and "Tarif: 3" in out
    assert any(b.startswith("sagr:save:") for b in _buttons(card))
    assert _count("salary_agreements") == 0 and not [m for m in bot.sent if getattr(m, "chat_id", None) == EMP]
