"""AI orqali kassa daftarini o'qish (PHASE2 — kamomadni xavfsiz aniqlash).

Real OpenAI/Telegram/production DB HECH QACHON ishlatilmaydi — Vision
provider ``cash_shift_bot.get_vision_extraction_provider``ni fake
implementatsiya bilan almashtirib (monkeypatch), rasm yuklab olish esa
``cash_shift_bot._download_photo_data_uri``ni identity-fake bilan
almashtirib sinaladi. Mavjud ``bot_dp``/``temp_db`` test infratuzilmasi
ishlatiladi (tests/conftest.py).
"""

import pytest

import company_time
from config import FOUNDER_ID
from providers.vision_extraction_provider import (
    CASH_SHIFT_CASH_REPORT,
    CASH_SHIFT_SALES_REPORT,
    ExtractionResult,
)
from tests.bot_harness import send, send_callback
from tests.test_cash_shift_bot_flows import (
    _clear_daily_report_gate,
    _clear_deficiency_gate,
    _confirm_close_amount,
    _make_kassir,
    _open_shift,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeVisionProvider:
    def __init__(self, results: dict[str, ExtractionResult] | None = None, error: Exception | None = None):
        self._results = results or {}
        self._error = error

    def is_enabled(self) -> bool:
        return True

    async def extract(self, file_id: str, document_type: str) -> ExtractionResult:
        if self._error is not None:
            raise self._error
        return self._results[document_type]


async def _fake_download(bot, file_id: str) -> str:
    return file_id


def _enable_ai(monkeypatch, provider) -> None:
    import cash_shift_bot

    monkeypatch.setattr(cash_shift_bot, "get_vision_extraction_provider", lambda *a, **k: provider)
    monkeypatch.setattr(cash_shift_bot, "_download_photo_data_uri", _fake_download)


def _make_savdo_boshligi(user_id: int, branch: str) -> None:
    import employees

    employees.submit_profile(
        user_id,
        {
            "familiya": "Boshliqov", "ism": "Sardor", "otasining_ismi": "Vali",
            "branch": branch, "role_key": "savdo_boshligi", "contacts": [],
        },
    )
    employees.approve_profile(user_id, FOUNDER_ID)


def _make_moliyachi(user_id: int) -> None:
    from roles import set_role

    set_role(user_id, "moliyachi", set_by=FOUNDER_ID)


async def _start_closeshift_with_photos(main, bot, user_id: int):
    await send(main.dp, bot, user_id, text="/closeshift")
    await _clear_deficiency_gate(main, bot, user_id)
    await _clear_daily_report_gate(main, bot, user_id)
    await send(main.dp, bot, user_id, photo_file_id="sales_photo")
    return await send(main.dp, bot, user_id, photo_file_id="cash_photo")


def _texts(sent):
    return [m.text for m in sent if getattr(m, "text", None)]


async def test_ai_all_fields_clear_skips_manual_questions_and_shows_summary(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    provider = _FakeVisionProvider({
        CASH_SHIFT_SALES_REPORT: ExtractionResult(
            confident=True, values={"cash_sales": "100000", "card_sales": "0", "other_payments": "0"}
        ),
        CASH_SHIFT_CASH_REPORT: ExtractionResult(confident=True, values={"actual_cash_balance": "100000"}),
    })
    _enable_ai(monkeypatch, provider)

    sent = await _start_closeshift_with_photos(main, bot, 111)
    texts = _texts(sent)
    assert not any("tushunmadim" in t for t in texts)
    assert not any("Bugungi naqd savdo summasini kiriting" in t for t in texts)
    assert any("AI o'qigan qiymatlar" in t for t in texts)

    summary_message = next(m for m in sent if getattr(m, "text", None) and "AI o'qigan qiymatlar" in m.text)
    buttons = summary_message.reply_markup.inline_keyboard[0]
    assert [b.text for b in buttons] == ["✅ Tasdiqlash", "✏️ Tuzatish"]

    sent = await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)
    assert any("KASSA — KUN YAKUNI" in t for t in _texts(sent))

    from services import cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert shift["cash_sales"] == 100000
    assert shift["actual_cash_balance"] == 100000


async def test_ai_asks_only_the_one_unclear_field(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    provider = _FakeVisionProvider({
        # other_payments yo'q -> unclear
        CASH_SHIFT_SALES_REPORT: ExtractionResult(
            confident=True, values={"cash_sales": "100000", "card_sales": "0"}
        ),
        CASH_SHIFT_CASH_REPORT: ExtractionResult(confident=True, values={"actual_cash_balance": "100000"}),
    })
    _enable_ai(monkeypatch, provider)

    sent = await _start_closeshift_with_photos(main, bot, 111)
    texts = _texts(sent)
    assert texts == ["⚠️ Boshqa to'lovlar summasini tushunmadim. Faqat shu summani yozing."]

    # Tushunilgan maydonlar qayta so'ralmaydi — faqat shu bitta qator.
    sent = await send(main.dp, bot, 111, text="0")
    assert any("AI o'qigan qiymatlar" in t for t in _texts(sent))

    sent = await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)
    assert any("KASSA — KUN YAKUNI" in t for t in _texts(sent))


async def test_ai_conflicting_cross_photo_value_becomes_unclear(bot_dp, monkeypatch):
    """PHASE2 #9 (oxirgi shart): ikki rasm bir xil maydonni turlicha
    o'qisa, o'sha maydon unclear bo'lishi kerak."""
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    provider = _FakeVisionProvider({
        CASH_SHIFT_SALES_REPORT: ExtractionResult(
            confident=True,
            values={"cash_sales": "100000", "card_sales": "0", "other_payments": "0"},
        ),
        CASH_SHIFT_CASH_REPORT: ExtractionResult(
            confident=True,
            # Ataylab ziddiyat: cash_sales bu rasmda ham "o'qilgan", boshqacha qiymat bilan.
            values={"actual_cash_balance": "100000", "cash_sales": "999999"},
        ),
    })
    _enable_ai(monkeypatch, provider)

    sent = await _start_closeshift_with_photos(main, bot, 111)
    texts = _texts(sent)
    assert texts == ["⚠️ Bugungi naqd savdo summasini tushunmadim. Faqat shu summani yozing."]


async def test_ai_expense_line_sum_mismatch_makes_balance_unclear(bot_dp, monkeypatch):
    """Providerning o'zi (fake OpenAI javobi orqali) xarajat qatorlari
    yig'indisi yozilgan jami bilan mos kelmasa, actual_cash_balance'ni
    unclear deb belgilashini tekshiradi — AI hisob-kitob qilmaydi, bu
    shunchaki bitta ichki mos kelish tekshiruvi."""
    import json

    from providers.vision_extraction_provider import OpenAIVisionExtractionProvider

    class _FakeResponse:
        output_text = json.dumps(
            {"actual_cash_balance": "50000", "expense_lines": [10000, 10000], "written_total": "30000"}
        )

    class _FakeResponses:
        async def create(self, **kwargs):
            return _FakeResponse()

    class _FakeClient:
        responses = _FakeResponses()

    import config

    monkeypatch.setattr(config, "VISION_EXTRACTION_ENABLED", True)
    provider = OpenAIVisionExtractionProvider(_FakeClient())

    result = await provider.extract("data:fake", CASH_SHIFT_CASH_REPORT)
    assert result.confident is True
    assert "actual_cash_balance" not in result.values


async def test_ai_total_failure_falls_back_to_original_manual_flow(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    provider = _FakeVisionProvider(error=RuntimeError("boom"))
    _enable_ai(monkeypatch, provider)

    sent = await _start_closeshift_with_photos(main, bot, 111)
    texts = _texts(sent)
    assert texts == ["Bugungi naqd savdo summasini kiriting:"]

    # Smena yopish to'xtab qolmaydi — mavjud qo'lda kiritish oqimi
    # to'liq ishlaydi.
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    sent = await _confirm_close_amount(main, bot, 111, "100000")
    assert any("KASSA — KUN YAKUNI" in t for t in _texts(sent))


async def test_shortage_over_tolerance_notifies_only_branch_supervisor_and_finance(bot_dp):
    main, bot = bot_dp
    _make_kassir(111, branch="Filial-1")
    _make_savdo_boshligi(501, branch="Filial-1")
    _make_moliyachi(601)
    await _open_shift(main, bot, 111, "0")

    await send(main.dp, bot, 111, text="/closeshift")
    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    sent = await _confirm_close_amount(main, bot, 111, "50000")  # 50_000 farq > 20_000 tolerance

    branch_messages = [m for m in sent if getattr(m, "chat_id", None) == 501]
    finance_messages = [m for m in sent if getattr(m, "chat_id", None) == 601]
    founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]

    assert len(branch_messages) == 1
    assert "tolerance" in branch_messages[0].text.lower()
    assert len(finance_messages) == 1
    assert len(founder_messages) == 0  # QARORLAR #2: Founder bu bosqichda xabar OLMAYDI


async def test_shortage_within_tolerance_sends_no_supervisor_notification(bot_dp):
    main, bot = bot_dp
    _make_kassir(111, branch="Filial-1")
    _make_savdo_boshligi(501, branch="Filial-1")
    _make_moliyachi(601)
    await _open_shift(main, bot, 111, "0")

    await send(main.dp, bot, 111, text="/closeshift")
    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    sent = await _confirm_close_amount(main, bot, 111, "99990")  # 10 farq, tolerance ichida

    branch_messages = [m for m in sent if getattr(m, "chat_id", None) == 501]
    finance_messages = [m for m in sent if getattr(m, "chat_id", None) == 601]
    assert branch_messages == []
    assert finance_messages == []


async def test_shortage_notification_respects_branch_isolation(bot_dp):
    main, bot = bot_dp
    _make_kassir(111, branch="Filial-1")
    _make_savdo_boshligi(501, branch="Filial-1")
    _make_savdo_boshligi(502, branch="Filial-2")  # BOSHQA filial rahbari — xabar olmasligi kerak
    _make_moliyachi(601)
    await _open_shift(main, bot, 111, "0")

    await send(main.dp, bot, 111, text="/closeshift")
    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    sent = await _confirm_close_amount(main, bot, 111, "50000")

    filial1_messages = [m for m in sent if getattr(m, "chat_id", None) == 501]
    filial2_messages = [m for m in sent if getattr(m, "chat_id", None) == 502]
    assert len(filial1_messages) == 1
    assert filial2_messages == []


async def test_escalation_after_retry_limit_still_notifies_branch_supervisor_too(bot_dp):
    """QARORLAR #5: retry tugab NEEDS_SUPERVISOR_APPROVAL bo'lganda ham
    mavjud Founder/nazoratchi yo'li (``_send_shift_for_review``)
    O'ZGARISHSIZ ishlaydi — YANGI filial rahbari xabari qo'shimcha
    ravishda yuboriladi, eskisini almashtirmaydi."""
    main, bot = bot_dp
    _make_kassir(111, branch="Filial-1")
    _make_savdo_boshligi(501, branch="Filial-1")
    _make_moliyachi(601)
    await _open_shift(main, bot, 111, "0")

    for i in range(3):
        await send(main.dp, bot, 111, text="/closeshift")
        if i == 0:
            await _clear_deficiency_gate(main, bot, 111)
            await _clear_daily_report_gate(main, bot, 111)
            await send(main.dp, bot, 111, photo_file_id="sales_photo")
            await send(main.dp, bot, 111, photo_file_id="cash_photo")
        await send(main.dp, bot, 111, text="100000")
        await send(main.dp, bot, 111, text="0")
        await send(main.dp, bot, 111, text="0")
        sent = await _confirm_close_amount(main, bot, 111, "50000")

    founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    branch_messages = [m for m in sent if getattr(m, "chat_id", None) == 501]
    finance_messages = [m for m in sent if getattr(m, "chat_id", None) == 601]

    assert len(founder_messages) == 1
    assert "tekshiruvi kerak" in founder_messages[0].text.lower()
    assert len(branch_messages) == 1
    assert len(finance_messages) == 1
