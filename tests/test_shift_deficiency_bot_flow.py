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

    # So'z bilan yozilgan son ("o'n kg") endi qisman javob sifatida o'qiladi (qarang
    # test_followup_partial_*); bu yerda haqiqatan noto'g'ri format tekshiriladi.
    sent = await send(main.dp, bot, 111, text="juda ko'p")
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
    assert "Un — 1 karobka" in combined  # karobka alohida birlik (quti'ga o'girilmaydi)


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

    sent = await send(main.dp, bot, 111, text="2. yangi: Karam 2 dona")
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

    sent = await send(main.dp, bot, 111, text="2. yangi: Karam 2 dona")
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


async def test_multiline_cola_blok_and_flesh_karobka_accepted_without_ai(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")

    async def _no_ai(**kwargs):
        raise AssertionError("AI chaqirilmasligi kerak — ikkala qator deterministik")

    monkeypatch.setattr(main.openai_client.responses, "create", _no_ai)

    sent = await send(main.dp, bot, 111, text="Cola 2L 10 blok\nFlesh 1 karobka")
    combined = " ".join(t for t in texts(sent) if t)

    assert "Bu qatorni tushunmadim" not in combined
    assert "1. Cola 2L — 10 blok" in combined
    assert "2. Flesh — 1 karobka" in combined


def _company_items() -> list[tuple]:
    from db import get_connection

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT product_name, quantity, unit FROM shift_deficiency_items WHERE category = 'company'"
        ).fetchall()
    finally:
        conn.close()
    return [(r["product_name"], r["quantity"], r["unit"]) for r in rows]


async def _to_company_step(main, bot):
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await send_callback(main.dp, bot, 111, data="csdef_none", target_chat_id=111)  # bozor yo'q


async def test_company_single_line_is_accepted_via_parse_shopping_list_without_ai(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_company_step(main, bot)

    async def _no_ai(**kwargs):
        raise AssertionError("AI chaqirilmasligi kerak — qator deterministik")

    monkeypatch.setattr(main.openai_client.responses, "create", _no_ai)

    sent = await send(main.dp, bot, 111, text="Cola 2L 10 blok")
    combined = " ".join(t for t in texts(sent) if t)
    assert "Bu qatorni tushunmadim" not in combined
    assert "1. Cola 2L — 10 blok" in combined

    await send_callback(main.dp, bot, 111, data="csdef_list_confirm", target_chat_id=111)
    assert _company_items() == [("Cola 2L", 10.0, "blok")]


async def test_company_single_unclear_line_uses_existing_ai_fallback(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_company_step(main, bot)

    call_count = 0

    async def _fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        payload = [{"line": "Cola 2L 10 blokcha", "product_name": "Cola 2L", "quantity": 10, "unit": "blok"}]
        return SimpleNamespace(output_text=json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr(main.openai_client.responses, "create", _fake_create)

    sent = await send(main.dp, bot, 111, text="Cola 2L 10 blokcha")
    combined = " ".join(t for t in texts(sent) if t)

    assert call_count == 1
    assert "1. Cola 2L — 10 blok" in combined


async def test_company_single_line_ai_unsure_falls_back_to_old_stepwise_flow(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_company_step(main, bot)

    async def _unsure(**kwargs):
        payload = [{"line": "Cola 2L", "product_name": None, "quantity": None, "unit": None}]
        return SimpleNamespace(output_text=json.dumps(payload))

    monkeypatch.setattr(main.openai_client.responses, "create", _unsure)

    sent = await send(main.dp, bot, 111, text="Cola 2L")
    assert "Miqdorini kiriting" in " ".join(t for t in texts(sent) if t)

    sent = await send(main.dp, bot, 111, text="10 blok")
    assert "Qo'shildi" in " ".join(t for t in texts(sent) if t)
    assert _company_items() == [("Cola 2L", 10.0, "blok")]


_ORDER_MESSAGE = (
    "pomidor 1 yashig\nbodring 10 kg\nkola 2 litr 5 blok\nzira\nolma qizil 1karopka\ntuz\nolma 3 kg"
)


async def _to_order_entry(main, bot, monkeypatch, ai_payload=None, ai_error=False):
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")

    async def _fake_create(**kwargs):
        if ai_error:
            raise TimeoutError("AI timeout")
        return SimpleNamespace(output_text=json.dumps(ai_payload or []))

    monkeypatch.setattr(main.openai_client.responses, "create", _fake_create)


def _joined(sent) -> str:
    return " ".join(t for t in texts(sent) if t)


async def test_order_missing_info_asked_in_one_numbered_message_and_short_answers_merge(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)

    sent = await send(main.dp, bot, 111, text=_ORDER_MESSAGE)
    questions = [t for t in texts(sent) if t and "tushunmadim" in t]
    assert len(questions) == 1  # barcha savollar BITTA xabarda
    assert "4. zira — miqdor va birlik kerak" in questions[0]  # raqam = ro'yxatdagi doimiy o'rni
    assert "6. tuz — miqdor va birlik kerak" in questions[0]

    sent = await send(main.dp, bot, 111, text="4. 2 blok\n6. 1 kg")
    combined = _joined(sent)
    assert "Ro'yxat tayyor" in combined
    assert "pomidor — 1 yashik" in combined
    assert "bodring — 10 kg" in combined
    assert "kola 2 litr — 5 blok" in combined  # hajm miqdorga aralashmadi
    assert "olma qizil — 1 karobka" in combined
    assert "zira — 2 blok" in combined
    assert "tuz — 1 kg" in combined
    assert shift_deficiency.get_daily_market_shortage() == []  # tasdiqdan oldin DBga yozilmaydi


async def test_order_partial_answer_keeps_accepted_and_numbers_stay_permanent(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="bodring 10 kg\nzira\ntuz\nolma")

    sent = await send(main.dp, bot, 111, text="2. 2 blok\n4. kotta")
    combined = _joined(sent)
    assert "3. tuz — miqdor va birlik kerak" in combined  # qayta raqamlanmadi
    assert "4. olma katta — miqdor va birlik kerak" in combined  # sifat saqlandi, taxmin qilinmadi
    assert "zira" not in combined

    sent = await send(main.dp, bot, 111, text="3. 1 kg\n4. 4 kg")
    combined = _joined(sent)
    assert "bodring — 10 kg" in combined and "zira — 2 blok" in combined
    assert "tuz — 1 kg" in combined and "olma katta — 4 kg" in combined


async def test_order_old_number_still_hits_same_product_after_first_is_resolved(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="zira\ntuz\nolma")

    await send(main.dp, bot, 111, text="1. 2 blok")  # birinchisi yechildi
    sent = await send(main.dp, bot, 111, text="3. kotta")  # eski 3-raqam aynan uchinchi (olma)
    combined = _joined(sent)
    assert "3. olma katta — miqdor va birlik kerak" in combined
    assert "2. tuz — miqdor va birlik kerak" in combined

    sent = await send(main.dp, bot, 111, text="1. 99 kg\n2. 1 kg\n2. 9 kg")
    combined = _joined(sent)
    assert "1-qator allaqachon yakunlangan" in combined
    assert "2-raqam takrorlandi" in combined
    assert "3. olma katta — miqdor va birlik kerak" in combined

    sent = await send(main.dp, bot, 111, text="3. bilmayman")
    assert "javobni tushunmadim" in _joined(sent).lower()
    sent = await send(main.dp, bot, 111, text="3. 4 kg")
    combined = _joined(sent)
    assert "zira — 2 blok" in combined and "tuz — 1 kg" in combined
    assert "olma katta — 4 kg" in combined and "bilmayman" not in combined


async def test_order_ambiguous_unnumbered_answer_is_not_guessed(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="zira\ntuz")

    sent = await send(main.dp, bot, 111, text="2 blok")
    combined = _joined(sent)
    assert "noaniq" in combined and "Ro'yxat tayyor" not in combined

    sent = await send(main.dp, bot, 111, text="1. 2 blok\n7. 1 kg")
    combined = _joined(sent)
    assert "7-raqamli qator yo'q" in combined
    assert "2. tuz — miqdor va birlik kerak" in combined


async def test_order_ai_timeout_keeps_list_and_manual_entry_works(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)

    sent = await send(main.dp, bot, 111, text="Pomidor 10 kg\nQandaydir narsa")
    combined = _joined(sent)
    assert "tushunmadim" in combined and "Qandaydir narsa" in combined

    sent = await send(main.dp, bot, 111, text="2. yangi: Karam 2 dona")  # ixtiyoriy aniq tahrir
    combined = _joined(sent)
    assert "Pomidor — 10 kg" in combined and "Karam — 2 dona" in combined

    await send_callback(main.dp, bot, 111, data="csdef_list_confirm", target_chat_id=111)
    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert products["Karam"]["total_quantity"] == 2


async def test_order_plain_bodring_and_tuzlangan_bodring_stay_separate_names(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)

    sent = await send(main.dp, bot, 111, text="bodring 10 kg\ntuzlangan bodring 3 kg")
    combined = _joined(sent)
    assert "bodring — 10 kg" in combined and "tuzlangan bodring — 3 kg" in combined
    assert "salyon" not in combined.lower() and "svej" not in combined.lower()


async def test_order_single_line_without_digit_can_use_existing_ai(bot_dp, monkeypatch):
    main, bot = bot_dp
    payload = [{"line": "pomidor ikki yashiqda", "product_name": "pomidor", "quantity": 2, "unit": "yashik"}]
    await _to_order_entry(main, bot, monkeypatch, ai_payload=payload)

    sent = await send(main.dp, bot, 111, text="pomidor ikki yashiqda")  # raqamsiz, deterministik tushunmaydi
    assert "pomidor — 2 yashik" in _joined(sent)


async def test_order_free_quality_words_resolved_by_existing_ai_with_context(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="olma\nnok")
    inputs = []

    async def _quality_ai(**kwargs):
        inputs.append(kwargs["input"])
        word = kwargs["input"].rsplit(": ", 1)[-1]
        return SimpleNamespace(output_text=json.dumps({"quality": word, "product": None}))

    monkeypatch.setattr(main.openai_client.responses, "create", _quality_ai)

    sent = await send(main.dp, bot, 111, text="1. pishgan\n2. yirikroq")
    combined = _joined(sent)
    assert "1. olma pishgan — miqdor va birlik kerak" in combined  # miqdor/birlik/brend to'qilmadi
    assert "2. nok yirikroq — miqdor va birlik kerak" in combined
    assert "Mahsulot: olma" in inputs[0] and "miqdor va birlik kerak" in inputs[0]

    sent = await send(main.dp, bot, 111, text="1. 3 kg\n2. 2 kg")
    combined = _joined(sent)
    assert "olma pishgan — 3 kg" in combined and "nok yirikroq — 2 kg" in combined


async def test_order_non_answer_skips_ai_and_changes_nothing(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="olma\nnok")
    await send(main.dp, bot, 111, text="1. kotta")
    calls = 0

    async def _count(**kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(output_text=json.dumps({"quality": "bilmayman", "product": None}))

    monkeypatch.setattr(main.openai_client.responses, "create", _count)

    sent = await send(main.dp, bot, 111, text="1. bilmayman")
    assert "javobni tushunmadim" in _joined(sent).lower() and calls == 0

    sent = await send(main.dp, bot, 111, text="1. 2 kg\n2. 1 kg")
    combined = _joined(sent)
    assert "olma katta — 2 kg" in combined and "nok — 1 kg" in combined


async def test_order_ai_error_or_invented_word_leaves_previous_info_unchanged(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="olma\nnok")
    await send(main.dp, bot, 111, text="1. kotta")

    sent = await send(main.dp, bot, 111, text="1. pishgan")  # AI xatosi — rad etiladi
    assert "javobni tushunmadim" in _joined(sent).lower()

    async def _invented(**kwargs):
        return SimpleNamespace(output_text=json.dumps({"quality": "Saturn", "product": None}))

    monkeypatch.setattr(main.openai_client.responses, "create", _invented)
    sent = await send(main.dp, bot, 111, text="1. pishgan")
    assert "javobni tushunmadim" in _joined(sent).lower()

    sent = await send(main.dp, bot, 111, text="1. 2 kg\n2. 1 kg")
    combined = _joined(sent)
    assert "olma katta — 2 kg" in combined and "Saturn" not in combined and "pishgan" not in combined


async def test_order_mixed_answer_ai_error_keeps_2kg_and_blocks_confirmation_until_resolved(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="olma\nnok")

    sent = await send(main.dp, bot, 111, text="1. 2 kg pishgan")
    combined = _joined(sent)
    assert "1. olma — 2 kg qabul qilindi; “pishgan” — mahsulotni almashtirishmi yoki tavsif qo'shishmi?" in combined
    assert "2. nok — miqdor va birlik kerak" in combined
    assert "Ro'yxat tayyor" not in combined

    sent = await send(main.dp, bot, 111, text="2. 1 kg")
    combined = _joined(sent)
    assert "Ro'yxat tayyor" not in combined  # noaniqlik hal bo'lmaguncha tasdiq chiqmaydi
    assert "1. olma — 2 kg qabul qilindi; “pishgan”" in combined

    sent = await send(main.dp, bot, 111, text="1. nima")
    assert "Ro'yxat tayyor" not in _joined(sent)

    sent = await send(main.dp, bot, 111, text="1. tavsif")
    combined = _joined(sent)
    assert "Ro'yxat tayyor" in combined and "olma pishgan — 2 kg" in combined and "nok — 1 kg" in combined
    assert shift_deficiency.get_daily_market_shortage() == []


async def test_order_mixed_answer_unclassified_word_can_be_dropped_or_resolved_by_ai_retry(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="olma\nnok")
    await send(main.dp, bot, 111, text="1. 2 kg pishgan\n2. 3 kg yirikroq")

    sent = await send(main.dp, bot, 111, text="1. yo'q")  # "pishgan" tashlanadi
    combined = _joined(sent)
    assert "Ro'yxat tayyor" not in combined
    assert "2. nok — 3 kg qabul qilindi; “yirikroq” — mahsulotni almashtirishmi yoki tavsif qo'shishmi?" in combined

    async def _ai_ok(**kwargs):
        return SimpleNamespace(output_text=json.dumps({"quality": "yirikroq", "product": None}))

    monkeypatch.setattr(main.openai_client.responses, "create", _ai_ok)
    sent = await send(main.dp, bot, 111, text="2. yirikroq")  # AI qayta urinish muvaffaqiyatli
    combined = _joined(sent)
    assert "Ro'yxat tayyor" in combined and "olma — 2 kg" in combined and "pishgan" not in combined
    assert "nok yirikroq — 3 kg" in combined


async def test_order_single_pending_short_answer_never_replaces_product_name(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="bodring 10 kg\nolma")

    async def _ai_ok(**kwargs):
        return SimpleNamespace(output_text=json.dumps({"quality": "pishgan", "product": None}))

    monkeypatch.setattr(main.openai_client.responses, "create", _ai_ok)
    sent = await send(main.dp, bot, 111, text="pishgan 2 kg")
    combined = _joined(sent)
    assert "2. olma pishgan — 2 kg" in combined and "bodring — 10 kg" in combined


async def test_order_single_pending_short_answer_with_ai_error_keeps_old_name_and_quantity(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="bodring 10 kg\nolma")

    sent = await send(main.dp, bot, 111, text="pishgan 2 kg")
    combined = _joined(sent)
    assert "Ro'yxat tayyor" not in combined
    assert "2. olma — 2 kg qabul qilindi; “pishgan”" in combined


async def test_order_examples_match_what_is_missing(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)

    sent = await send(main.dp, bot, 111, text="tuz 5\nzira kg\nbodring\nolma")
    text = [t for t in texts(sent) if t and "tushunmadim" in t][0]
    assert "1. tuz — birlik kerak (miqdor: 5)" in text
    assert "1. kg" in text and "1. 2 kg" not in text  # miqdor ma'lum — qayta miqdor ko'rsatilmaydi
    assert "2. zira — miqdor kerak (birlik: kg)" in text
    assert "\n2. 2\n" in text
    assert "3. 2 kg" in text and "4. 2 kg" in text


async def test_order_unclassified_word_example_shows_replace_or_describe_choice(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="olma\nnok")

    sent = await send(main.dp, bot, 111, text="1. 2 kg pishgan")
    text = _joined(sent)
    assert "1. almashtirish / 1. tavsif" in text
    assert "1. ha" not in text
    assert "1. kg" not in text and "1. 2 kg" not in text  # miqdor va birlik ma'lum — qayta so'ralmaydi


async def test_order_other_product_answer_asks_replace_confirmation_and_keeps_name_until_yes(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="bodring 10 kg\nolma")

    async def _ai_product(**kwargs):
        return SimpleNamespace(output_text=json.dumps({"quality": None, "product": "Karam"}))

    monkeypatch.setattr(main.openai_client.responses, "create", _ai_product)

    sent = await send(main.dp, bot, 111, text="Karam 2 dona")  # "yangi:" yozish shart emas
    combined = _joined(sent)
    assert "Olmani karamga almashtirasizmi?" in combined
    assert "2. olma —" in combined  # tasdiqlanmaguncha nom o'zgarmadi
    assert "tavsif" not in combined and "2. ha / 2. yo'q" in combined
    assert "Ro'yxat tayyor" not in combined

    sent = await send(main.dp, bot, 111, text="2. yo'q")
    assert "2. olma — miqdor va birlik kerak" in _joined(sent)

    await send(main.dp, bot, 111, text="Karam 2 dona")
    sent = await send(main.dp, bot, 111, text="2. ha")
    combined = _joined(sent)
    assert "Ro'yxat tayyor" in combined and "Karam — 2 dona" in combined and "olma" not in combined
    assert "bodring — 10 kg" in combined


async def test_order_quality_answer_still_extends_previous_name_without_ai(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="bodring 10 kg\nolma")
    calls = 0

    async def _count(**kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(output_text=json.dumps({"quality": None, "product": None}))

    monkeypatch.setattr(main.openai_client.responses, "create", _count)

    sent = await send(main.dp, bot, 111, text="katta 2 kg")  # aniq sifat: kod o'zi qo'shadi
    combined = _joined(sent)
    assert "olma katta — 2 kg" in combined and "Ro'yxat tayyor" in combined and calls == 0


async def test_order_ai_timeout_unclassified_word_plain_ha_never_makes_olma_karam(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)  # AI timeout
    await send(main.dp, bot, 111, text="bodring 10 kg\nolma")

    sent = await send(main.dp, bot, 111, text="Karam 2 dona")
    combined = _joined(sent)
    assert "2. olma — 2 dona qabul qilindi; “Karam” — mahsulotni almashtirishmi yoki tavsif qo'shishmi?" in combined
    assert "sifat" not in combined.split("masalan")[0]  # noma'lum so'z "sifat" deb atalmaydi
    assert "Ro'yxat tayyor" not in combined

    sent = await send(main.dp, bot, 111, text="2. ha")  # oddiy "ha" hal qilmaydi
    combined = _joined(sent)
    assert "olma Karam" not in combined and "Ro'yxat tayyor" not in combined
    assert "javobni tushunmadim" in combined.lower()

    sent = await send(main.dp, bot, 111, text="ha")  # raqamsiz yagona "ha" ham hal qilmaydi
    assert "olma Karam" not in _joined(sent) and "Ro'yxat tayyor" not in _joined(sent)

    sent = await send(main.dp, bot, 111, text="2. tavsif")  # faqat aniq tanlov
    assert "olma Karam — 2 dona" in _joined(sent)


async def test_order_ai_timeout_unclassified_word_explicit_replace_choice(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="bodring 10 kg\nolma")
    await send(main.dp, bot, 111, text="Karam 2 dona")

    sent = await send(main.dp, bot, 111, text="2. almashtirish")
    combined = _joined(sent)
    assert "Karam — 2 dona" in combined and "olma" not in combined and "bodring — 10 kg" in combined


async def test_order_plain_quantity_answer_keeps_replace_proposal_and_blocks_confirmation(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="bodring 10 kg\nolma")

    async def _ai_product(**kwargs):
        return SimpleNamespace(output_text=json.dumps({"quality": None, "product": "Karam"}))

    monkeypatch.setattr(main.openai_client.responses, "create", _ai_product)
    sent = await send(main.dp, bot, 111, text="Karam 2 dona")
    assert "Olmani karamga almashtirasizmi?" in _joined(sent)

    sent = await send(main.dp, bot, 111, text="2. 3 dona")  # oddiy miqdor/birlik javobi
    combined = _joined(sent)
    assert "avval almashtirish savoliga" in combined
    assert "Ro'yxat tayyor" not in combined

    # Taklif saqlangan: keyingi aniq "ha" to'g'ri ishlaydi (Karam — 2 dona, 3 dona emas).
    sent = await send(main.dp, bot, 111, text="2. ha")
    combined = _joined(sent)
    assert "Ro'yxat tayyor" in combined
    assert "Karam — 2 dona" in combined and "olma" not in combined and "3 dona" not in combined


async def test_order_plain_quantity_answer_then_no_keeps_olma(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="bodring 10 kg\nolma")

    async def _ai_product(**kwargs):
        return SimpleNamespace(output_text=json.dumps({"quality": None, "product": "Karam"}))

    monkeypatch.setattr(main.openai_client.responses, "create", _ai_product)
    await send(main.dp, bot, 111, text="Karam 2 dona")
    await send(main.dp, bot, 111, text="2. 3 dona")

    sent = await send(main.dp, bot, 111, text="2. yo'q")
    assert "2. olma — miqdor va birlik kerak" in _joined(sent)  # taklif yopildi, olma qoldi, 3 dona saqlanmadi
    sent = await send(main.dp, bot, 111, text="2. 3 dona")
    combined = _joined(sent)
    assert "Ro'yxat tayyor" in combined and "olma — 3 dona" in combined


async def _typo_line_then_asked_for_amount(main, bot, monkeypatch, ai_payload=None, ai_error=True):
    await _to_order_entry(main, bot, monkeypatch, ai_payload=ai_payload, ai_error=ai_error)
    sent = await send(main.dp, bot, 111, text="Kola 2litr 20blol")
    assert "Miqdorini kiriting" in _joined(sent)  # eski bosqichli oqimga tushdi


def _market_products() -> dict:
    return {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}


async def test_item_amount_followup_short_answer_keeps_clean_product_name(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _typo_line_then_asked_for_amount(main, bot, monkeypatch)

    sent = await send(main.dp, bot, 111, text="20 blok")
    assert "Kola 2 litr — 20 blok" in _joined(sent)  # hajm miqdorga aralashmadi, xato matn nomda qolmadi

    products = _market_products()
    assert list(products) == ["Kola 2 litr"]
    assert products["Kola 2 litr"]["total_quantity"] == 20 and products["Kola 2 litr"]["unit"] == "blok"


@pytest.mark.parametrize("corrected", ["Kola 2litr 20blok", "Kola 2lit 20 blok"])
async def test_item_amount_followup_full_corrected_line_is_accepted(bot_dp, monkeypatch, corrected):
    main, bot = bot_dp
    await _typo_line_then_asked_for_amount(main, bot, monkeypatch)

    sent = await send(main.dp, bot, 111, text=corrected)
    combined = _joined(sent)
    assert "1. Kola 2 litr — 20 blok" in combined and "blol" not in combined
    assert _market_products() == {}  # tasdiqdan oldin DBga yozilmaydi

    await send_callback(main.dp, bot, 111, data="csdef_list_confirm", target_chat_id=111)
    products = _market_products()
    assert list(products) == ["Kola 2 litr"] and products["Kola 2 litr"]["total_quantity"] == 20


async def test_item_amount_followup_uses_existing_ai_fallback_for_unclear_corrected_line(bot_dp, monkeypatch):
    main, bot = bot_dp
    payload = [{"line": "Kola 2lit 20 blk", "product_name": "Kola 2 litr", "quantity": 20, "unit": "blok"}]
    await _typo_line_then_asked_for_amount(main, bot, monkeypatch, ai_payload=payload, ai_error=False)

    sent = await send(main.dp, bot, 111, text="Kola 2lit 20 blk")
    assert "1. Kola 2 litr — 20 blok" in _joined(sent)


async def test_item_amount_followup_ai_error_asks_only_what_is_missing_and_invents_nothing(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _typo_line_then_asked_for_amount(main, bot, monkeypatch)  # AI timeout

    sent = await send(main.dp, bot, 111, text="yigirma tayoq")
    combined = _joined(sent)
    assert "Miqdor va birlik kerak" in combined and "Ro'yxat tayyor" not in combined
    assert _market_products() == {}

    sent = await send(main.dp, bot, 111, text="20 blok")  # aniq ma'lumot keyingi urinishda baribir ishlaydi
    assert "Kola 2 litr — 20 blok" in _joined(sent)


async def test_item_amount_followup_other_product_goes_through_replace_confirmation(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _typo_line_then_asked_for_amount(main, bot, monkeypatch)

    sent = await send(main.dp, bot, 111, text="Karam 2 dona")
    combined = _joined(sent)
    assert "almashtirasizmi?" in combined and "Ro'yxat tayyor" not in combined
    assert _market_products() == {}  # tasdiqlanmaguncha hech narsa yozilmaydi

    sent = await send(main.dp, bot, 111, text="1. ha")
    assert "1. Karam — 2 dona" in _joined(sent)


async def test_item_amount_plain_product_then_quantity_still_works_as_before(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)

    sent = await send(main.dp, bot, 111, text="Pomidor")
    assert "Miqdorini kiriting" in _joined(sent)
    sent = await send(main.dp, bot, 111, text="10 kg")
    assert "Qo'shildi" in _joined(sent)
    assert _market_products()["Pomidor"]["total_quantity"] == 10


async def test_followup_same_full_name_after_normalization_needs_no_replace_question(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _typo_line_then_asked_for_amount(main, bot, monkeypatch)

    sent = await send(main.dp, bot, 111, text="Kola 2lit 20 blok")  # xato token tozalanib, "2lit" -> "2 litr"
    combined = _joined(sent)
    assert "almashtirasizmi" not in combined
    assert "1. Kola 2 litr — 20 blok" in combined


@pytest.mark.parametrize(
    "first, corrected, expected_question",
    [
        ("ketchup kichik", "ketchup katta 2 dona", "ketchup kattaga almashtirasizmi?"),
        ("tuz Russ", "tuz Orzu 2 blok", "tuz orzuga almashtirasizmi?"),
    ],
)
async def test_followup_different_full_name_is_not_replaced_without_confirmation(
    bot_dp, monkeypatch, first, corrected, expected_question
):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    sent = await send(main.dp, bot, 111, text=first)
    assert "Miqdorini kiriting" in _joined(sent)

    sent = await send(main.dp, bot, 111, text=corrected)
    combined = _joined(sent)
    assert expected_question in combined and "Ro'yxat tayyor" not in combined
    assert _market_products() == {}  # tasdiqsiz hech narsa yozilmaydi

    sent = await send(main.dp, bot, 111, text="1. yo'q")  # nom o'zgarmaydi
    assert first.lower().split()[0] in _joined(sent).lower() and "Ro'yxat tayyor" not in _joined(sent)


async def test_followup_replacement_confirmed_with_ha_uses_new_full_line(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="tuz Russ")
    await send(main.dp, bot, 111, text="tuz Orzu 2 blok")

    sent = await send(main.dp, bot, 111, text="1. ha")
    assert "1. tuz Orzu — 2 blok" in _joined(sent)


@pytest.mark.parametrize("answer", ["20 blk", "20"])
async def test_followup_partial_answer_with_ai_error_keeps_quantity_and_asks_only_unit(bot_dp, monkeypatch, answer):
    main, bot = bot_dp
    await _typo_line_then_asked_for_amount(main, bot, monkeypatch)  # AI timeout

    sent = await send(main.dp, bot, 111, text=answer)
    combined = _joined(sent)
    assert "1. Kola 2 litr — birlik kerak (miqdor: 20)" in combined  # 20 saqlandi, faqat birlik so'raladi
    assert "Miqdor va birlik kerak" not in combined and "Ro'yxat tayyor" not in combined
    assert _market_products() == {}

    sent = await send(main.dp, bot, 111, text="1. blok")
    combined = _joined(sent)
    assert "Ro'yxat tayyor" in combined and "1. Kola 2 litr — 20 blok" in combined


async def test_followup_unit_only_answer_asks_only_quantity(bot_dp, monkeypatch):
    main, bot = bot_dp
    await _to_order_entry(main, bot, monkeypatch, ai_error=True)
    await send(main.dp, bot, 111, text="Pomidor")

    sent = await send(main.dp, bot, 111, text="kg")
    assert "1. Pomidor — miqdor kerak (birlik: kg)" in _joined(sent)
    sent = await send(main.dp, bot, 111, text="1. 10")
    assert "1. Pomidor — 10 kg" in _joined(sent)
