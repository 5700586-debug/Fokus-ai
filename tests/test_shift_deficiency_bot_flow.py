import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

import company_time
from config import FOUNDER_ID
from repositories import cash_shifts as cash_shifts_repo
from services import shift_deficiency
from tests.bot_harness import send, send_callback, texts

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_kassir(user_id: int, branch: str = "Filial-1") -> None:
    from roles import set_role
    import employees

    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {
            "familiya": "Kassirov", "ism": "Ali", "otasining_ismi": "Vali",
            "branch": branch, "role_key": "kassir", "contacts": [],
        },
    )


async def _open_shift(main, bot, user_id: int, opening_balance: str = "0") -> None:
    await send(main.dp, bot, user_id, text="/openshift")
    await send(main.dp, bot, user_id, text=opening_balance)


async def _finish_daily_report(main, bot, user_id: int):
    """Deficiency gate'dan keyin ataylab qo'shilgan Daily Report qadamini
    (prixod -> narx -> xodim shikoyati) yopadi."""
    await send_callback(main.dp, bot, user_id, data="csdr_prixod:0", target_chat_id=user_id)
    await send_callback(main.dp, bot, user_id, data="csdr_price:0", target_chat_id=user_id)
    return await send_callback(main.dp, bot, user_id, data="csdr_staff_no", target_chat_id=user_id)


def _seed_market_item(employee_id: int, branch: str, shift_date: str, product_name: str) -> dict:
    shift = cash_shifts_repo.open_shift(employee_id, branch, shift_date, opening_balance=0, tolerance=20000)
    shift_deficiency.add_market_item(shift["id"], employee_id, product_name, 1, "kg")
    return shift


async def test_closeshift_starts_market_step_instead_of_photo(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)

    sent = await send(main.dp, bot, 111, text="/closeshift")

    combined = " ".join(texts(sent))
    assert "Bozor" in combined
    assert "rasmini yuboring" not in combined


async def test_market_none_then_company_step_shown(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")

    sent = await send_callback(main.dp, bot, 111, data="csdef_none", target_chat_id=111)

    combined = " ".join(t for t in texts(sent) if t)
    assert "Firmaga zakaz" in combined


async def test_full_gate_with_no_prior_items_reaches_photo_prompt(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")

    await send_callback(main.dp, bot, 111, data="csdef_none", target_chat_id=111)  # bozor yo'q
    sent = await send_callback(main.dp, bot, 111, data="csdef_none", target_chat_id=111)  # firma yo'q

    # kechagi ro'yxat bo'sh -> avtomatik o'tdi va navbatdagi Daily Report boshlandi
    combined = " ".join(t for t in texts(sent) if t)
    assert "prixodi chiqmagan" in combined

    sent = await _finish_daily_report(main, bot, 111)
    assert "rasmini yuboring" in " ".join(t for t in texts(sent) if t)


async def test_add_market_item_then_finish_moves_to_company_step(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")

    await send(main.dp, bot, 111, text="Pomidor")
    sent = await send(main.dp, bot, 111, text="10 kg")
    assert "Qo'shildi" in " ".join(t for t in texts(sent) if t)

    sent = await send_callback(main.dp, bot, 111, data="csdef_done", target_chat_id=111)
    combined = " ".join(t for t in texts(sent) if t)
    assert "Firmaga zakaz" in combined

    shift = cash_shifts_repo.get_open_shift(111, company_time.today().isoformat())
    assert shift_deficiency.get_next_step(shift["id"]) == shift_deficiency.STEP_COMPANY


async def test_invalid_quantity_format_is_rejected_and_reprompted(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await send(main.dp, bot, 111, text="Pomidor")

    sent = await send(main.dp, bot, 111, text="o'n kg")
    assert "❌" in " ".join(t for t in texts(sent) if t)

    sent = await send(main.dp, bot, 111, text="5 dona")
    assert "Qo'shildi" in " ".join(t for t in texts(sent) if t)


async def test_yesterday_list_excludes_other_branch_and_todays_other_shift(bot_dp):
    main, bot = bot_dp
    yesterday = (company_time.today() - timedelta(days=1)).isoformat()
    today = company_time.today().isoformat()

    _seed_market_item(501, "Filial-1", yesterday, "Suzma")
    _seed_market_item(502, "Filial-2", yesterday, "BoshqaFilialMahsuloti")
    _seed_market_item(503, "Filial-1", today, "Zelen")

    _make_kassir(111, branch="Filial-1")
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")

    await send_callback(main.dp, bot, 111, data="csdef_none", target_chat_id=111)  # bozor yo'q
    sent = await send_callback(main.dp, bot, 111, data="csdef_none", target_chat_id=111)  # firma yo'q

    combined = " ".join(t for t in texts(sent) if t)
    assert "Suzma" in combined
    assert "BoshqaFilialMahsuloti" not in combined
    assert "Zelen" not in combined


async def test_yesterday_review_confirm_keeps_still_missing_open(bot_dp):
    main, bot = bot_dp
    yesterday = (company_time.today() - timedelta(days=1)).isoformat()

    _seed_market_item(501, "Filial-1", yesterday, "Suzma")
    _seed_market_item(501, "Filial-1", yesterday, "Olma")

    _make_kassir(111, branch="Filial-1")
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await send_callback(main.dp, bot, 111, data="csdef_none", target_chat_id=111)
    await send_callback(main.dp, bot, 111, data="csdef_none", target_chat_id=111)

    # Ro'yxatda 1 — Suzma, 2 — Olma (add tartibida) — faqat 1-raqam hali kelmagan.
    sent = await send(main.dp, bot, 111, text="1")
    combined = " ".join(t for t in texts(sent) if t)
    assert "Kelmagan: Suzma" in combined
    assert "To'g'rimi?" in combined

    sent = await send_callback(main.dp, bot, 111, data="csdef_yesterday_confirm", target_chat_id=111)
    combined = " ".join(t for t in texts(sent) if t)
    assert "prixodi chiqmagan" in combined  # gate yopildi -> Daily Report boshlandi

    shift = cash_shifts_repo.get_open_shift(111, company_time.today().isoformat())
    assert shift_deficiency.is_flow_complete(shift["id"]) is True


# ------------------------------------------------- ko'p qatorli AI ro'yxat --


async def test_multiline_list_all_deterministic_no_ai_call(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")

    async def _fail_if_called(**kwargs):
        raise AssertionError("Barcha qatorlar deterministik parse bo'lishi kerak — AI chaqirilmasin")

    monkeypatch.setattr(main.openai_client.responses, "create", _fail_if_called)

    sent = await send(main.dp, bot, 111, text="Pomidor 10 kg\nMilter iriska 500 gr 4 dona")
    combined = " ".join(t for t in texts(sent) if t)
    assert "Ro'yxat tayyor" in combined
    assert "Pomidor — 10 kg" in combined
    assert "Milter iriska 500 gr — 4 dona" in combined
    assert "Tasdiqlaysizmi?" in combined

    # 10-band: tasdiqlashdan OLDIN hech narsa DBga yozilmaydi.
    assert shift_deficiency.get_daily_market_shortage() == []

    sent = await send_callback(main.dp, bot, 111, data="csdef_list_confirm", target_chat_id=111)
    assert "2 ta mahsulot qo'shildi" in " ".join(t for t in texts(sent) if t)

    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert products["Pomidor"]["total_quantity"] == 10
    assert products["Pomidor"]["unit"] == "kg"
    assert products["Milter iriska 500 gr"]["total_quantity"] == 4
    assert products["Milter iriska 500 gr"]["unit"] == "dona"


async def test_multiline_list_unclear_lines_use_single_batched_ai_call(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")

    call_count = 0

    async def _fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        payload = [
            {"line": "Sabzi biroz", "product_name": "Sabzi", "quantity": 3, "unit": "kg"},
            {"line": "Un karobka", "product_name": "Un", "quantity": 1, "unit": "karobka"},
        ]
        return SimpleNamespace(output_text=json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr(main.openai_client.responses, "create", _fake_create)

    sent = await send(main.dp, bot, 111, text="Pomidor 10 kg\nSabzi biroz\nUn karobka")
    combined = " ".join(t for t in texts(sent) if t)

    assert call_count == 1  # 3-band: bitta qator uchun emas, butun ro'yxat uchun BITTA chaqiruv
    assert "Ro'yxat tayyor" in combined
    assert "Pomidor — 10 kg" in combined
    assert "Sabzi — 3 kg" in combined
    assert "Un — 1 quti" in combined  # karobka -> quti normalizatsiya


async def test_multiline_list_ai_uncertain_line_asks_manual_clarification(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")

    async def _fake_create(**kwargs):
        payload = [{"line": "nimadir tushunarsiz", "product_name": None, "quantity": None, "unit": None}]
        return SimpleNamespace(output_text=json.dumps(payload))

    monkeypatch.setattr(main.openai_client.responses, "create", _fake_create)

    sent = await send(main.dp, bot, 111, text="Pomidor 10 kg\nnimadir tushunarsiz")
    combined = " ".join(t for t in texts(sent) if t)
    assert "tushunmadim" in combined.lower()
    assert "nimadir tushunarsiz" in combined

    sent = await send(main.dp, bot, 111, text="Karam 2 dona")
    combined = " ".join(t for t in texts(sent) if t)
    assert "Ro'yxat tayyor" in combined
    assert "Pomidor — 10 kg" in combined
    assert "Karam — 2 dona" in combined


async def test_multiline_list_ai_failure_preserves_list_and_requests_manual_clarification(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")

    async def _boom(**kwargs):
        raise RuntimeError("API xatosi")

    monkeypatch.setattr(main.openai_client.responses, "create", _boom)

    sent = await send(main.dp, bot, 111, text="Pomidor 10 kg\nnoaniq qator")
    combined = " ".join(t for t in texts(sent) if t)
    assert "tushunmadim" in combined.lower()
    assert "noaniq qator" in combined

    sent = await send(main.dp, bot, 111, text="Karam 2 dona")
    combined = " ".join(t for t in texts(sent) if t)
    assert "Pomidor — 10 kg" in combined
    assert "Karam — 2 dona" in combined


async def test_multiline_list_confirm_twice_does_not_duplicate(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await send(main.dp, bot, 111, text="Pomidor 10 kg\nKaram 2 dona")

    await send_callback(main.dp, bot, 111, data="csdef_list_confirm", target_chat_id=111)
    sent = await send_callback(main.dp, bot, 111, data="csdef_list_confirm", target_chat_id=111)

    assert "qo'shildi" not in " ".join(t for t in texts(sent) if t)

    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert products["Pomidor"]["total_quantity"] == 10
    assert products["Karam"]["total_quantity"] == 2


async def test_multiline_list_confirm_db_failure_preserves_list_for_retry(bot_dp, monkeypatch):
    """7-band: DB yozuvi muvaffaqiyatsiz bo'lsa, ro'yxat/tugma yo'qolmaydi
    va kassir qayta urinib ko'rganda hech narsa yo'qotilmasdan saqlanadi
    (dublikat ham hosil bo'lmaydi)."""
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await send(main.dp, bot, 111, text="Pomidor 10 kg\nKaram 2 dona")

    from services import shift_deficiency as shift_deficiency_module

    original_add_items_bulk = shift_deficiency_module.add_items_bulk
    call_count = 0

    def _fails_once(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("DB xatosi")
        return original_add_items_bulk(*args, **kwargs)

    monkeypatch.setattr(shift_deficiency_module, "add_items_bulk", _fails_once)

    sent = await send_callback(main.dp, bot, 111, data="csdef_list_confirm", target_chat_id=111)
    assert "xatolik" in " ".join(t for t in texts(sent) if t).lower()
    assert shift_deficiency.get_daily_market_shortage() == []

    sent = await send_callback(main.dp, bot, 111, data="csdef_list_confirm", target_chat_id=111)
    assert "2 ta mahsulot qo'shildi" in " ".join(t for t in texts(sent) if t)

    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert products["Pomidor"]["total_quantity"] == 10
    assert products["Karam"]["total_quantity"] == 2


async def test_multiline_list_edit_button_lets_user_retype(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await send(main.dp, bot, 111, text="Pomidor 10 kg\nKaram 2 dona")

    sent = await send_callback(main.dp, bot, 111, data="csdef_list_edit", target_chat_id=111)
    assert "qaytadan yozing" in " ".join(t for t in texts(sent) if t).lower()

    sent = await send(main.dp, bot, 111, text="Bodring 5 kg\nSholg'om 1 dona")
    combined = " ".join(t for t in texts(sent) if t)
    assert "Bodring — 5 kg" in combined
    assert "Sholg'om — 1 dona" in combined

    await send_callback(main.dp, bot, 111, data="csdef_list_confirm", target_chat_id=111)
    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert "Pomidor" not in products
    assert products["Bodring"]["total_quantity"] == 5
    assert products["Sholg'om"]["total_quantity"] == 1


async def test_single_product_flow_still_works_unchanged(bot_dp):
    """1-band: mavjud bitta-mahsulot oqimi (nom, keyin alohida miqdor)
    yangi ko'p qatorli AI oqimidan keyin ham o'zgarishsiz qolishi kerak."""
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")

    await send(main.dp, bot, 111, text="Pomidor")
    sent = await send(main.dp, bot, 111, text="10 kg")
    assert "Qo'shildi" in " ".join(t for t in texts(sent) if t)

    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert products["Pomidor"]["total_quantity"] == 10


async def test_full_closeshift_still_succeeds_after_clearing_deficiency_gate(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await send_callback(main.dp, bot, 111, data="csdef_none", target_chat_id=111)
    await send_callback(main.dp, bot, 111, data="csdef_none", target_chat_id=111)
    await _finish_daily_report(main, bot, 111)

    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    await send_callback(main.dp, bot, 111, data="csui_close_start_yes", target_chat_id=111)
    await send(main.dp, bot, 111, text="100000")
    sent = await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)

    combined = " ".join(t for t in texts(sent) if t)
    assert "KASSA — KUN YAKUNI" in combined
