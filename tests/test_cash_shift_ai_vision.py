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
    texts = [t for t in _texts(sent) if t != _WAIT_TEXT]
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
    texts = [t for t in _texts(sent) if t != _WAIT_TEXT]
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
    texts = [t for t in _texts(sent) if t != _WAIT_TEXT]
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
    await _clear_deficiency_gate(main, bot, 111)
    await _clear_daily_report_gate(main, bot, 111)
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
    await _clear_deficiency_gate(main, bot, 111)
    await _clear_daily_report_gate(main, bot, 111)
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
    await _clear_deficiency_gate(main, bot, 111)
    await _clear_daily_report_gate(main, bot, 111)
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


def _ledger_provider(items, written_total="598000", balance="100000", mismatch=False, items_sum=None):
    values = {"actual_cash_balance": balance} if balance is not None else {}
    return _FakeVisionProvider({
        CASH_SHIFT_SALES_REPORT: ExtractionResult(
            confident=True, values={"cash_sales": "100000", "card_sales": "0", "other_payments": "0"}
        ),
        CASH_SHIFT_CASH_REPORT: ExtractionResult(
            confident=True, values=values, expense_items=items,
            written_expense_total=written_total, expense_total_mismatch=mismatch, expense_items_sum=items_sum,
        ),
    })


_LEDGER_ITEMS_2 = [
    {"raw_name": "abinon", "normalized_name": "Obinon", "amount": 198000},
    {"raw_name": "Sadaf", "normalized_name": "Sadaf", "amount": 400000},
]


def _ledger_rows(shift_id: int):
    from services import cash_expense

    return [(r["line_no"], r["raw_name"], r["normalized_name"], r["amount"]) for r in cash_expense.get_ledger_items(shift_id)]


async def test_ledger_items_not_written_when_ai_reads_only_after_confirm(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, _ledger_provider(_LEDGER_ITEMS_2))

    sent = await _start_closeshift_with_photos(main, bot, 111)
    assert any("AI o'qigan qiymatlar" in t for t in _texts(sent))

    from services import cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert _ledger_rows(shift["id"]) == []  # AI o'qidi, lekin tasdiqlanmagan — DBda yo'q

    await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)
    assert _ledger_rows(shift["id"]) == [
        (1, "abinon", "Obinon", 198000), (2, "Sadaf", "Sadaf", 400000),  # original line_no ketma-ketligi
    ]


async def test_ledger_items_not_written_when_cashier_presses_correct(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, _ledger_provider(_LEDGER_ITEMS_2))
    await _start_closeshift_with_photos(main, bot, 111)

    await send_callback(main.dp, bot, 111, data="csui_close_amount_retry", target_chat_id=111)

    from services import cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert _ledger_rows(shift["id"]) == []  # "Tuzatish" — DBga yozilmaydi


async def test_ledger_items_reconfirm_replaces_old_rows_without_duplicates(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    from services import cash_expense, cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    cash_expense.save_ledger_items(shift["id"], [{"raw_name": "eski", "normalized_name": "Eski", "amount": 1}])

    _enable_ai(monkeypatch, _ledger_provider(_LEDGER_ITEMS_2))
    await _start_closeshift_with_photos(main, bot, 111)
    await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)
    assert _ledger_rows(shift["id"]) == [(1, "abinon", "Obinon", 198000), (2, "Sadaf", "Sadaf", 400000)]

    # Qayta tasdiq (masalan farq chiqqach) — dublikat bo'lmaydi.
    ledger = cash_expense.get_ledger_items(shift["id"])
    cash_expense.save_ledger_items(shift["id"], [{k: r[k] for k in ("raw_name", "normalized_name", "amount")} for r in ledger])
    assert len(_ledger_rows(shift["id"])) == 2


async def test_confirmed_empty_ledger_items_clear_old_rows(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    from services import cash_expense, cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    cash_expense.save_ledger_items(shift["id"], _LEDGER_ITEMS_2)

    _enable_ai(monkeypatch, _ledger_provider([]))  # qayta rasm: expense_items bo'sh
    await _start_closeshift_with_photos(main, bot, 111)
    assert len(_ledger_rows(shift["id"])) == 2  # tasdiqdan oldin eski qatorlar tegilmagan

    await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)
    assert _ledger_rows(shift["id"]) == []  # tasdiqlangan bo'sh natija eskilarini tozaladi


async def test_ledger_items_untouched_when_ai_fails_and_manual_flow_used(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    from services import cash_expense, cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    cash_expense.save_ledger_items(shift["id"], _LEDGER_ITEMS_2)

    _enable_ai(monkeypatch, _FakeVisionProvider(error=RuntimeError("AI xatosi")))
    await _start_closeshift_with_photos(main, bot, 111)
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    await _confirm_close_amount(main, bot, 111, "100000")

    assert len(_ledger_rows(shift["id"])) == 2  # daftar o'qilmadi — mavjud qatorlar o'zgarmadi


async def test_ledger_items_save_failure_does_not_break_close_flow(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, _ledger_provider([{"raw_name": "x", "normalized_name": "x", "amount": 1}], written_total="1"))
    await _start_closeshift_with_photos(main, bot, 111)

    from services import cash_expense

    def _boom(*args, **kwargs):
        raise RuntimeError("DB xatosi")

    monkeypatch.setattr(cash_expense, "save_ledger_items", _boom)
    sent = await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)
    assert any("KASSA — KUN YAKUNI" in t for t in _texts(sent))  # smena yopilishi to'xtamadi


async def test_ledger_items_dropped_on_correct_then_manual_balance_confirm_writes_nothing(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, _ledger_provider(_LEDGER_ITEMS_2))
    await _start_closeshift_with_photos(main, bot, 111)  # AI expense_items o'qidi (FSMda)

    await send_callback(main.dp, bot, 111, data="csui_close_amount_retry", target_chat_id=111)  # "Tuzatish"
    await send(main.dp, bot, 111, text="100000")  # qoldiq qo'lda
    sent = await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)
    assert any("KASSA — KUN YAKUNI" in t for t in _texts(sent))  # smena yopildi

    from repositories import cash_shifts as repo
    from services import cash_shift

    shift = cash_shift.get_shift(repo.get_last_closed_shift("Filial-1")["id"])
    assert repo.get_ledger_expense_items(shift["id"]) == []  # eski AI qatorlari yozilmadi


async def test_ledger_items_correct_does_not_clear_existing_rows_either(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    from services import cash_expense, cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    cash_expense.save_ledger_items(shift["id"], _LEDGER_ITEMS_2)  # avval tasdiqlangan qatorlar
    _enable_ai(monkeypatch, _ledger_provider([]))
    await _start_closeshift_with_photos(main, bot, 111)

    await send_callback(main.dp, bot, 111, data="csui_close_amount_retry", target_chat_id=111)
    await send(main.dp, bot, 111, text="100000")
    await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)

    assert len(_ledger_rows(shift["id"])) == 2  # "Tuzatish" None -> mavjud qatorlarga tegilmaydi


async def test_ledger_items_written_when_no_mismatch(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, _ledger_provider(_LEDGER_ITEMS_2, written_total="598000", mismatch=False))
    await _start_closeshift_with_photos(main, bot, 111)
    await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)

    from repositories import cash_shifts as repo

    closed = repo.get_last_closed_shift("Filial-1")
    assert [(r["line_no"], r["raw_name"], r["amount"]) for r in repo.get_ledger_expense_items(closed["id"])] == [
        (1, "abinon", 198000), (2, "Sadaf", 400000),
    ]


async def test_ledger_match_shows_no_warning_and_writes_items(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, _ledger_provider(_LEDGER_ITEMS_2, written_total="598000", mismatch=False, items_sum=598000))

    sent = await _start_closeshift_with_photos(main, bot, 111)
    assert not any("mos kelmadi" in t for t in _texts(sent))
    await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)

    from repositories import cash_shifts as repo

    closed = repo.get_last_closed_shift("Filial-1")
    assert len(repo.get_ledger_expense_items(closed["id"])) == 2




def _mismatch_provider(balance=None):
    return _ledger_provider(_LEDGER_ITEMS_2, written_total="900000", balance=balance, mismatch=True, items_sum=598000)


def _ledger_summary(shift_id: int):
    from repositories import cash_shifts as repo

    return repo.get_ledger_expense_summary(shift_id)


async def _close_shift_id(main, bot):
    from repositories import cash_shifts as repo

    return repo.get_last_closed_shift("Filial-1")["id"]


async def test_ledger_match_writes_items_with_status_matched(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, _ledger_provider(_LEDGER_ITEMS_2, written_total="598000", items_sum=598000))

    sent = await _start_closeshift_with_photos(main, bot, 111)
    assert not any("mos kelmadi" in t for t in _texts(sent))
    await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)

    shift_id = await _close_shift_id(main, bot)
    summary = _ledger_summary(shift_id)
    assert summary["total_status"] == "matched" and summary["accepted_total"] == 598000
    assert [(r["line_no"], r["raw_name"], r["normalized_name"], r["amount"]) for r in _ledger_rows_by_id(shift_id)] == [
        (1, "abinon", "Obinon", 198000), (2, "Sadaf", "Sadaf", 400000),
    ]


def _ledger_rows_by_id(shift_id: int):
    from repositories import cash_shifts as repo

    return repo.get_ledger_expense_items(shift_id)


async def test_ledger_mismatch_asks_cashier_with_three_buttons_and_waits(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, _mismatch_provider())

    sent = await _start_closeshift_with_photos(main, bot, 111)
    message = next(m for m in sent if getattr(m, "text", None) and "mos kelmadi" in m.text)
    assert message.text == (
        "⚠️ Xarajatlar jami mos kelmadi.\nMen qatorlarni sanasam: 598 000 so'm\n"
        "Daftardagi ‘Jami xarajat’: 900 000 so'm\n\nQaysi biri to'g'ri?"
    )
    labels = [b.text for row in message.reply_markup.inline_keyboard for b in row]
    assert labels == ["✅ 598 000 to'g'ri", "✏️ 900 000 to'g'ri", "🔁 Qayta rasm yuborish"]
    assert not any("tushunmadim" in t for t in _texts(sent))  # kassir tanlamaguncha davom etilmaydi

    from services import cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert _ledger_rows_by_id(shift["id"]) == []  # tanlovgacha DBga yozilmaydi


async def test_ledger_mismatch_items_sum_accepted_writes_items_with_status(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, _mismatch_provider())
    await _start_closeshift_with_photos(main, bot, 111)

    sent = await send_callback(main.dp, bot, 111, data="csui_ledger_items", target_chat_id=111)
    assert any("tushunmadim" in t for t in _texts(sent))  # mavjud oqim: qoldiq so'raladi
    await send(main.dp, bot, 111, text="100000")
    await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)

    shift_id = await _close_shift_id(main, bot)
    summary = _ledger_summary(shift_id)
    assert summary["total_status"] == "cashier_accepted_items_sum"
    assert (summary["items_sum"], summary["written_total"], summary["accepted_total"]) == (598000, 900000, 598000)
    assert [(r["line_no"], r["raw_name"], r["amount"]) for r in _ledger_rows_by_id(shift_id)] == [
        (1, "abinon", 198000), (2, "Sadaf", 400000),  # nomlar mismatch sababli tashlanmadi, line_no saqlandi
    ]


async def test_ledger_mismatch_written_total_accepted_writes_items_with_status(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, _mismatch_provider())
    await _start_closeshift_with_photos(main, bot, 111)

    await send_callback(main.dp, bot, 111, data="csui_ledger_written", target_chat_id=111)
    await send(main.dp, bot, 111, text="100000")
    await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)

    shift_id = await _close_shift_id(main, bot)
    summary = _ledger_summary(shift_id)
    assert summary["total_status"] == "cashier_accepted_written_total"
    assert (summary["items_sum"], summary["written_total"], summary["accepted_total"]) == (598000, 900000, 900000)
    assert len(_ledger_rows_by_id(shift_id)) == 2  # qatorlar baribir yozildi


async def test_ledger_mismatch_resend_photo_clears_temp_results_and_writes_nothing(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, _mismatch_provider())
    await _start_closeshift_with_photos(main, bot, 111)

    sent = await send_callback(main.dp, bot, 111, data="csui_ledger_resend", target_chat_id=111)
    assert any("rasmini qayta yuboring" in t for t in _texts(sent))

    from services import cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert _ledger_rows_by_id(shift["id"]) == [] and _ledger_summary(shift["id"]) is None
    ctx = main.dp.fsm.get_context(bot=bot, chat_id=111, user_id=111)
    data = await ctx.get_data()
    assert data["ledger_expense_items"] is None and data["ledger_total_status"] is None
    assert data["cash_sales"] is None and data["actual_cash_balance"] is None
    assert await ctx.get_state() == "CloseShiftStates:cash_photo"

    # Yangi rasm (endi jami mos) alohida bosqich sifatida qayta o'qiladi.
    _enable_ai(monkeypatch, _ledger_provider(_LEDGER_ITEMS_2, written_total="598000", items_sum=598000))
    sent = await send(main.dp, bot, 111, photo_file_id="cash_photo_2")
    assert any("AI o'qigan qiymatlar" in t for t in _texts(sent))
    await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)
    assert _ledger_summary(await _close_shift_id(main, bot))["total_status"] == "matched"


async def test_ledger_mismatch_buttons_not_accepted_after_choice_made(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, _mismatch_provider())
    await _start_closeshift_with_photos(main, bot, 111)

    await send_callback(main.dp, bot, 111, data="csui_ledger_items", target_chat_id=111)
    sent = await send_callback(main.dp, bot, 111, data="csui_ledger_written", target_chat_id=111)  # eski tugma
    assert not [m for m in sent if getattr(m, "text", None)]

    ctx = main.dp.fsm.get_context(bot=bot, chat_id=111, user_id=111)
    assert (await ctx.get_data())["ledger_total_status"] == "cashier_accepted_items_sum"


async def test_correct_after_ledger_choice_clears_ai_ledger_data_and_writes_nothing(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, _mismatch_provider(balance="100000"))
    await _start_closeshift_with_photos(main, bot, 111)
    await send_callback(main.dp, bot, 111, data="csui_ledger_items", target_chat_id=111)

    await send_callback(main.dp, bot, 111, data="csui_close_amount_retry", target_chat_id=111)  # "Tuzatish"
    ctx = main.dp.fsm.get_context(bot=bot, chat_id=111, user_id=111)
    data = await ctx.get_data()
    assert data["ledger_expense_items"] is None and data["ledger_total_status"] is None

    await send(main.dp, bot, 111, text="100000")
    await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)
    shift_id = await _close_shift_id(main, bot)
    assert _ledger_rows_by_id(shift_id) == [] and _ledger_summary(shift_id) is None


_WAIT_TEXT = "⏳ Rasmlarni o'qiyapman, biroz kuting…"


class _DelayedProvider(_FakeVisionProvider):
    def __init__(self, results=None, delay: float = 0.0, enabled: bool = True):
        super().__init__(results)
        self._delay = delay
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    async def extract(self, file_id: str, document_type: str):
        import asyncio

        await asyncio.sleep(self._delay)
        return await super().extract(file_id, document_type)


def _clear_results():
    return {
        CASH_SHIFT_SALES_REPORT: ExtractionResult(
            confident=True, values={"cash_sales": "100000", "card_sales": "0", "other_payments": "0"}
        ),
        CASH_SHIFT_CASH_REPORT: ExtractionResult(confident=True, values={"actual_cash_balance": "100000"}),
    }


def _unconfident_results():
    return {
        CASH_SHIFT_SALES_REPORT: ExtractionResult(confident=False, values={}),
        CASH_SHIFT_CASH_REPORT: ExtractionResult(confident=False, values={}),
    }


def _wait_message_cleaned_up(sent) -> bool:
    """Kutish xabari yuborilgan va aynan shu xabar keyin o'chirilgan."""
    for index, method in enumerate(sent):
        if getattr(method, "text", None) == _WAIT_TEXT:
            message_id = index + 1
            return any(
                type(later).__name__ == "DeleteMessage" and later.message_id == message_id
                for later in sent[index + 1:]
            )
    return False


async def _open_and_enable(main, bot, monkeypatch, provider):
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    _enable_ai(monkeypatch, provider)


async def test_vision_timeout_is_60_seconds_and_late_answer_is_accepted(bot_dp, monkeypatch):
    main, bot = bot_dp
    import asyncio

    import cash_shift_bot

    assert cash_shift_bot._VISION_EXTRACTION_TIMEOUT_SECONDS == 60
    await _open_and_enable(main, bot, monkeypatch, _DelayedProvider(_clear_results(), delay=0.2))

    limits = []
    real_wait_for = asyncio.wait_for

    async def _spy(awaitable, timeout=None):
        limits.append(timeout)
        return await real_wait_for(awaitable, timeout=None)  # haqiqiy 60 s kutilmaydi

    monkeypatch.setattr(cash_shift_bot.asyncio, "wait_for", _spy)
    sent = await _start_closeshift_with_photos(main, bot, 111)

    assert 60 in limits  # AI chaqiruvi 60 soniyalik cheklov bilan (oldin 20)
    assert any("AI o'qigan qiymatlar" in t for t in _texts(sent))  # kech (lekin cheklovdan oldin) javob qabul qilindi
    assert _wait_message_cleaned_up(sent)


async def test_vision_timeout_falls_back_to_manual_flow_logs_reason_and_removes_wait_message(
    bot_dp, monkeypatch, capsys
):
    main, bot = bot_dp
    import cash_shift_bot

    await _open_and_enable(main, bot, monkeypatch, _DelayedProvider(_clear_results(), delay=1.0))
    monkeypatch.setattr(cash_shift_bot, "_VISION_EXTRACTION_TIMEOUT_SECONDS", 0.05)

    sent = await _start_closeshift_with_photos(main, bot, 111)
    assert any("Bugungi naqd savdo summasini kiriting" in t for t in _texts(sent))  # qo'lda oqim ishladi
    assert _wait_message_cleaned_up(sent)  # timeoutda ham kutish xabari qolmadi

    from services import cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    log = capsys.readouterr().out
    assert f"cash_vision_fallback reason=timeout shift_id={shift['id']} elapsed=" in log
    assert "data:image" not in log and "base64" not in log  # rasm/kalit/AI javobi logga yozilmaydi


async def test_wait_message_is_sent_and_removed_when_analysis_succeeds(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _open_and_enable(main, bot, monkeypatch, _DelayedProvider(_clear_results()))

    sent = await _start_closeshift_with_photos(main, bot, 111)
    assert _WAIT_TEXT in _texts(sent) and _wait_message_cleaned_up(sent)
    assert any("AI o'qigan qiymatlar" in t for t in _texts(sent))


async def test_wait_message_not_sent_and_reason_logged_when_provider_disabled(bot_dp, monkeypatch, capsys):
    main, bot = bot_dp
    await _open_and_enable(main, bot, monkeypatch, _DelayedProvider(_clear_results(), enabled=False))

    sent = await _start_closeshift_with_photos(main, bot, 111)
    assert _WAIT_TEXT not in _texts(sent)  # tahlil bo'lmaydi — kutish xabari ham yo'q
    assert any("Bugungi naqd savdo summasini kiriting" in t for t in _texts(sent))

    from services import cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    assert f"cash_vision_fallback reason=disabled shift_id={shift['id']} elapsed=" in capsys.readouterr().out


@pytest.mark.parametrize("reason", ["download", "both_unconfident", "exception", "no_sales_ref"])
async def test_manual_fallback_reason_is_logged_and_wait_message_never_left_behind(
    bot_dp, monkeypatch, capsys, reason
):
    main, bot = bot_dp
    import cash_shift_bot

    if reason == "exception":
        provider = _FakeVisionProvider(error=RuntimeError("AI xatosi"))
    elif reason == "both_unconfident":
        provider = _DelayedProvider(_unconfident_results())
    else:
        provider = _DelayedProvider(_clear_results())
    await _open_and_enable(main, bot, monkeypatch, provider)

    if reason == "download":
        async def _no_download(bot_, file_id):
            return None

        monkeypatch.setattr(cash_shift_bot, "_download_photo_data_uri", _no_download)
    if reason == "no_sales_ref":
        from repositories import cash_shifts as repo

        monkeypatch.setattr(repo, "set_sales_report_photo", lambda shift_id, file_id: None)

    sent = await _start_closeshift_with_photos(main, bot, 111)
    assert any("Bugungi naqd savdo summasini kiriting" in t for t in _texts(sent))  # qo'lda oqim ishladi
    if reason == "no_sales_ref":
        assert _WAIT_TEXT not in _texts(sent)  # tahlil boshlanmadi
    else:
        assert _wait_message_cleaned_up(sent)

    from services import cash_shift

    shift = cash_shift.get_open_shift(111, company_time.today().isoformat())
    log = capsys.readouterr().out
    assert f"cash_vision_fallback reason={reason} shift_id={shift['id']} elapsed=" in log
    assert "data:image" not in log
