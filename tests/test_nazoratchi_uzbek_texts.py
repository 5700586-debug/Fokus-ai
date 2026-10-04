"""Nazoratchi ko'radigan tugma va xabar matnlarida inglizcha/texnik so'zlar bo'lmasin
(callback_data ichidagisi hisobga olinmaydi — faqat foydalanuvchiga ko'rinadigan matn)."""

import re

import pytest

import company_time
import employees
import nazoratchi_bot as nzr
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

SUPERVISOR = 1
_FORBIDDEN = re.compile(
    r"\b(score|review|pending|approve|approved|reject|rejected|time bonus|monthly|dashboard|founder\w*|"
    r"submit|cancel|confirm|oylik ball)\b",
    re.IGNORECASE,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _visible_texts(sent) -> list[str]:
    texts: list[str] = []
    for method in sent:
        if getattr(method, "text", None):
            texts.append(method.text)
        markup = getattr(method, "reply_markup", None)
        for row in getattr(markup, "inline_keyboard", None) or []:
            texts += [button.text for button in row]
        for row in getattr(markup, "keyboard", None) or []:
            texts += [button.text for button in row]
    return texts


def _assert_clean(sent, where: str) -> None:
    texts = _visible_texts(sent)
    assert texts, f"{where}: ko'rinadigan matn yo'q (oqim tekshirilmadi)"
    for text in texts:
        match = _FORBIDDEN.search(text)
        assert match is None, f"{where}: inglizcha/texnik so'z {match.group(0)!r} :: {text!r}"


def _setup() -> None:
    from roles import set_role

    set_role(SUPERVISOR, "nazoratchi", set_by=FOUNDER_ID)
    set_role(111, "sotuvchi", set_by=FOUNDER_ID)
    employees.submit_profile(
        111, {"familiya": "Alisher", "ism": "T", "branch": RECRUITING_BRANCH_NAMES[0], "role_key": "sotuvchi", "contacts": []}
    )
    employees.approve_profile(111, approved_by=FOUNDER_ID)


async def test_nazoratchi_main_menu_and_commands_use_simple_uzbek(bot_dp):
    main, bot = bot_dp
    _setup()

    sent = await send(main.dp, bot, SUPERVISOR, text="🧑‍💼 Nazoratchi")
    labels = [button.text for row in sent[0].reply_markup.keyboard for button in row]
    assert labels == ["🏬 Filialni tanlash", "📋 Baholash", "✅ Filialni yopish", "📅 Grafik so'rovlari", "🏆 Bugungi natija", "🔙 Orqaga"]
    _assert_clean(sent, "nazoratchi menyusi")

    for command in ("/baholash", "/kunniyop", "/filiallar"):
        _assert_clean(await send(main.dp, bot, SUPERVISOR, text=command), command)


async def test_baholash_and_close_screens_have_no_english_words(bot_dp):
    main, bot = bot_dp
    _setup()
    ymd = company_time.today().isoformat().replace("-", "")

    for data in (f"bos:br:0:{ymd}", f"bos:emp:111:{ymd}", "bos:penalty_menu:111", f"bos:close:0:{ymd}", "bos:today"):
        _assert_clean(await send_callback(main.dp, bot, SUPERVISOR, data=data, target_chat_id=SUPERVISOR), data)


@pytest.mark.parametrize(
    "callback",
    [
        nzr._CB_BRANCHES,
        f"{nzr._CB_BRANCH_PREFIX}0",
        f"{nzr._CB_EMPLOYEE_PREFIX}111",
        f"{nzr._CB_ATTENDANCE_PREFIX}111",
        f"{nzr._CB_SCHEDULE_PREFIX}111",
        f"{nzr._CB_MOBILITY_PREFIX}111",
        f"{nzr._CB_PENALTY_PREFIX}111",
        f"{nzr._CB_ONE_ON_ONE_PREFIX}111",
        f"{nzr._CB_OFFBOARD_PREFIX}111",
        nzr._CB_SCHEDULE_REQUESTS,
    ],
)
async def test_filiallar_employee_card_and_sections_have_no_english_words(bot_dp, callback):
    main, bot = bot_dp
    _setup()

    _assert_clean(await send_callback(main.dp, bot, SUPERVISOR, data=callback, target_chat_id=SUPERVISOR), callback)


async def test_score_is_absent_for_nazoratchi_but_founder_keeps_it(bot_dp):
    main, bot = bot_dp
    _setup()

    sent = await send(main.dp, bot, SUPERVISOR, text="/score 111 90")
    assert "qayd etildi" not in " ".join(text for text in _visible_texts(sent))
    sent = await send(main.dp, bot, FOUNDER_ID, text="/score 111 90")
    assert "qayd etildi" in sent[0].text


def test_forbidden_word_detector_catches_english_labels():
    for bad in ("Monthly score", "Review pending", "Approve", "Reject", "Time bonus", "Founderga yubor", "Oylik ball qo'yish"):
        assert _FORBIDDEN.search(bad), bad
    for good in ("Baholash", "Filialni tanlash", "Baholanmagan", "Damda", "Grafik yo'q", "Filialni yopish", "Tasdiqlash", "Rad etish", "Orqaga"):
        assert _FORBIDDEN.search(good) is None, good
