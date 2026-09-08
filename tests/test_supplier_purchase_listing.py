import pytest

from config import FOUNDER_ID
from repositories import cash_shifts as cash_shifts_repo
from repositories import supplier_purchases as supplier_purchases_repo
from services import shift_deficiency
from tests.bot_harness import send, send_callback, texts

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _open_shift(employee_id: int, branch: str, shift_date: str) -> dict:
    return cash_shifts_repo.open_shift(employee_id, branch, shift_date, opening_balance=0, tolerance=20000)


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


def _make_taminotchi(user_id: int) -> None:
    from roles import set_role

    set_role(user_id, "taminotchi", set_by=FOUNDER_ID)


def test_add_purchase_and_get_price_history_round_trip():
    purchase_id = supplier_purchases_repo.add_purchase(
        "Pomidor", 10.0, "kg", 12000, 999, "2026-01-05", False, None
    )
    assert purchase_id is not None

    last = supplier_purchases_repo.get_price_history("Pomidor", "kg")
    assert last["unit_price"] == 12000
    assert last["quantity"] == 10.0


def test_get_price_history_none_for_never_purchased_product():
    assert supplier_purchases_repo.get_price_history("Karam", "kg") is None


def test_get_price_history_returns_most_recent():
    supplier_purchases_repo.add_purchase("Pomidor", 5.0, "kg", 10000, 999, "2026-01-04", False, None)
    supplier_purchases_repo.add_purchase("Pomidor", 5.0, "kg", 12000, 999, "2026-01-05", False, None)

    last = supplier_purchases_repo.get_price_history("Pomidor", "kg")
    assert last["unit_price"] == 12000
    assert last["purchase_date"] == "2026-01-05"


def test_get_price_history_scoped_to_unit():
    supplier_purchases_repo.add_purchase("Pomidor", 5.0, "kg", 12000, 999, "2026-01-05", False, None)
    assert supplier_purchases_repo.get_price_history("Pomidor", "dona") is None


def test_daily_market_shortage_aggregates_across_branches_by_product_and_unit():
    shift_a = _open_shift(1, "Filial-1", "2026-01-05")
    shift_b = _open_shift(2, "Filial-2", "2026-01-05")
    shift_deficiency.add_market_item(shift_a["id"], 1, "Pomidor", 30, "kg")
    shift_deficiency.add_market_item(shift_b["id"], 2, "Pomidor", 70, "kg")

    products = shift_deficiency.get_daily_market_shortage()

    assert len(products) == 1
    product = products[0]
    assert product["product_name"] == "Pomidor"
    assert product["unit"] == "kg"
    assert product["total_quantity"] == 100
    assert product["by_branch"]["Filial-1"]["quantity"] == 30
    assert product["by_branch"]["Filial-2"]["quantity"] == 70


def test_daily_market_shortage_excludes_arrived_items():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    item_id = shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 10, "kg")

    from repositories import shift_deficiencies as deficiency_repo

    deficiency_repo.mark_item_resolved(item_id, "2026-01-05T10:00:00+00:00")

    products = shift_deficiency.get_daily_market_shortage()
    assert products == []


def test_daily_market_shortage_includes_previous_days_still_open_items():
    yesterday_shift = _open_shift(1, "Filial-1", "2026-01-04")
    shift_deficiency.add_market_item(yesterday_shift["id"], 1, "Suzma", 5, "kg")

    products = shift_deficiency.get_daily_market_shortage()
    assert len(products) == 1
    assert products[0]["product_name"] == "Suzma"


def test_daily_market_shortage_excludes_company_category():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    shift_deficiency.add_company_item(shift["id"], 1, "Un", 5, "quti")

    assert shift_deficiency.get_daily_market_shortage() == []


# ------------------------------------------------- ko'p qatorli AI ro'yxat --
# 13-band: kassirning ko'p qatorli AI ro'yxati orqali tasdiqlangan
# pozitsiyalar ham get_daily_market_shortage()da, ham ta'minotchining
# /xarid ro'yxatida AYNAN BIR MARTA ko'rinishi kerak.


async def test_confirmed_multiline_list_items_appear_once_in_market_shortage_and_xarid(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    _make_taminotchi(777)

    await send(main.dp, bot, 111, text="/openshift")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="/closeshift")
    await send(main.dp, bot, 111, text="Pomidor 10 kg\nKaram 2 dona")
    await send_callback(main.dp, bot, 111, data="csdef_list_confirm", target_chat_id=111)

    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert products["Pomidor"]["total_quantity"] == 10
    assert products["Karam"]["total_quantity"] == 2

    sent = await send(main.dp, bot, 777, text="/xarid")
    combined = " ".join(t for t in texts(sent) if t)
    assert combined.count("Pomidor") == 1
    assert combined.count("Karam") == 1
    assert "kerak: 10 kg" in combined
    assert "kerak: 2 dona" in combined


# --------------------------------------------- price-history batch lookup --
# ``/xarid`` N+1 muammosi: har bir mahsulot uchun alohida
# ``get_price_history()`` chaqirish o'rniga, endi butun ro'yxat uchun
# BITTA ``get_price_history_batch()`` chaqiriladi (qarang
# ``repositories/supplier_purchases.py``, ``performance_bot.py``dagi
# ``_load_products_with_price``/``_load_test_products_with_price``).


def test_get_price_history_batch_empty_input_returns_empty_without_connection(monkeypatch):
    def _fail_if_called():
        raise AssertionError("bo'sh kirish uchun get_connection() chaqirilmasligi kerak")

    monkeypatch.setattr(supplier_purchases_repo, "get_connection", _fail_if_called)

    assert supplier_purchases_repo.get_price_history_batch([]) == {}


def test_get_price_history_batch_uses_one_connection_and_one_select(monkeypatch):
    supplier_purchases_repo.add_purchase("Pomidor", 5.0, "kg", 12000, 999, "2026-01-05", False, None)
    supplier_purchases_repo.add_purchase("Karam", 2.0, "dona", 3000, 999, "2026-01-05", False, None)

    real_get_connection = supplier_purchases_repo.get_connection
    connect_calls: list = []
    execute_calls: list = []

    class _CountingConnProxy:
        def __init__(self, real_conn):
            self._real_conn = real_conn

        def execute(self, sql, params=()):
            execute_calls.append(sql)
            return self._real_conn.execute(sql, params)

        def close(self):
            return self._real_conn.close()

    def _counting_get_connection():
        connect_calls.append(1)
        return _CountingConnProxy(real_get_connection())

    monkeypatch.setattr(supplier_purchases_repo, "get_connection", _counting_get_connection)

    result = supplier_purchases_repo.get_price_history_batch(
        [("Pomidor", "kg"), ("Karam", "dona"), ("Sabzi", "kg")]
    )

    assert len(connect_calls) == 1
    assert len(execute_calls) == 1
    assert result[("Pomidor", "kg")]["unit_price"] == 12000
    assert result[("Karam", "dona")]["unit_price"] == 3000
    assert ("Sabzi", "kg") not in result


def test_get_price_history_batch_returns_latest_by_date_then_id():
    supplier_purchases_repo.add_purchase("Pomidor", 5.0, "kg", 10000, 999, "2026-01-04", False, None)
    supplier_purchases_repo.add_purchase("Pomidor", 5.0, "kg", 12000, 999, "2026-01-05", False, None)
    # Bir xil sanada ikkinchi (keyinroq id'li) yozuv g'olib chiqishi kerak.
    supplier_purchases_repo.add_purchase("Pomidor", 5.0, "kg", 11000, 999, "2026-01-05", False, None)

    result = supplier_purchases_repo.get_price_history_batch([("Pomidor", "kg")])
    assert result[("Pomidor", "kg")]["unit_price"] == 11000
    assert result[("Pomidor", "kg")]["purchase_date"] == "2026-01-05"


def test_get_price_history_batch_separates_same_name_different_units():
    supplier_purchases_repo.add_purchase("Pomidor", 5.0, "kg", 12000, 999, "2026-01-05", False, None)
    supplier_purchases_repo.add_purchase("Pomidor", 3.0, "dona", 4000, 999, "2026-01-05", False, None)

    result = supplier_purchases_repo.get_price_history_batch([("Pomidor", "kg"), ("Pomidor", "dona")])
    assert result[("Pomidor", "kg")]["unit_price"] == 12000
    assert result[("Pomidor", "dona")]["unit_price"] == 4000


def test_get_price_history_batch_missing_product_has_no_entry():
    assert supplier_purchases_repo.get_price_history_batch([("Sabzi", "kg")]) == {}


def test_get_price_history_batch_deduplicates_input_pairs(monkeypatch):
    supplier_purchases_repo.add_purchase("Pomidor", 5.0, "kg", 12000, 999, "2026-01-05", False, None)

    real_get_connection = supplier_purchases_repo.get_connection
    execute_params: list = []

    class _CapturingConnProxy:
        def __init__(self, real_conn):
            self._real_conn = real_conn

        def execute(self, sql, params=()):
            execute_params.append(list(params))
            return self._real_conn.execute(sql, params)

        def close(self):
            return self._real_conn.close()

    monkeypatch.setattr(
        supplier_purchases_repo, "get_connection",
        lambda: _CapturingConnProxy(real_get_connection()),
    )

    result = supplier_purchases_repo.get_price_history_batch(
        [("Pomidor", "kg"), ("Pomidor", "kg"), ("Pomidor", "kg")]
    )

    assert result[("Pomidor", "kg")]["unit_price"] == 12000
    assert len(execute_params) == 1
    # Duplikat kiritilgan uch juftlik BITTA (product_name, unit) jufti
    # sifatida so'ralishi kerak -- parametrlar ro'yxati 2ta, 6ta emas.
    assert execute_params[0] == ["Pomidor", "kg"]


async def test_xarid_real_supplier_uses_batch_lookup_not_per_item_loop(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_kassir(111)
    _make_taminotchi(777)

    await send(main.dp, bot, 111, text="/openshift")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="/closeshift")
    await send(main.dp, bot, 111, text="Pomidor 10 kg\nKaram 2 dona")
    await send_callback(main.dp, bot, 111, data="csdef_list_confirm", target_chat_id=111)

    single_calls: list = []
    monkeypatch.setattr(
        supplier_purchases_repo, "get_price_history",
        lambda *args, **kwargs: single_calls.append((args, kwargs)) or None,
    )

    batch_calls: list = []
    real_batch = supplier_purchases_repo.get_price_history_batch

    def _spy_batch(product_keys):
        batch_calls.append(list(product_keys))
        return real_batch(product_keys)

    monkeypatch.setattr(supplier_purchases_repo, "get_price_history_batch", _spy_batch)

    await send(main.dp, bot, 777, text="/xarid")

    assert single_calls == [], "eski N+1 yo'li (get_price_history loop) hali ham chaqirilmoqda"
    assert len(batch_calls) == 1
    assert set(batch_calls[0]) == {("Pomidor", "kg"), ("Karam", "dona")}


async def test_xarid_e2e_tester_uses_batch_lookup_not_per_item_loop(bot_dp, monkeypatch):
    import roles

    main, bot = bot_dp
    tester_id = roles.E2E_TESTER_TELEGRAM_ID

    await send(main.dp, bot, tester_id, text="/sinovsmena")
    await send(main.dp, bot, tester_id, text="Pomidor 10 kg\nKaram 2 dona")
    await send_callback(main.dp, bot, tester_id, data="csdef_list_confirm", target_chat_id=tester_id)

    single_calls: list = []
    monkeypatch.setattr(
        supplier_purchases_repo, "get_price_history",
        lambda *args, **kwargs: single_calls.append((args, kwargs)) or None,
    )

    batch_calls: list = []
    real_batch = supplier_purchases_repo.get_price_history_batch

    def _spy_batch(product_keys):
        batch_calls.append(list(product_keys))
        return real_batch(product_keys)

    monkeypatch.setattr(supplier_purchases_repo, "get_price_history_batch", _spy_batch)

    sent = await send(main.dp, bot, tester_id, text="/xarid")

    assert single_calls == [], "eski N+1 yo'li (get_price_history loop) hali ham chaqirilmoqda"
    assert len(batch_calls) == 1
    assert set(batch_calls[0]) == {("Pomidor", "kg"), ("Karam", "dona")}

    combined = " ".join(t for t in texts(sent) if t)
    assert combined.count("Pomidor") == 1
    assert combined.count("Karam") == 1

    await send(main.dp, bot, tester_id, text="/sinovtugat")


async def test_xarid_reply_text_and_price_display_unchanged_after_batch_fix(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    _make_taminotchi(777)

    supplier_purchases_repo.add_purchase("Pomidor", 5.0, "kg", 12000, 777, "2026-01-04", False, None)

    await send(main.dp, bot, 111, text="/openshift")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="/closeshift")
    await send(main.dp, bot, 111, text="Pomidor 10 kg\nKaram 2 dona")
    await send_callback(main.dp, bot, 111, data="csdef_list_confirm", target_chat_id=111)

    sent = await send(main.dp, bot, 777, text="/xarid")
    combined = " ".join(t for t in texts(sent) if t)

    # Pomidor -- oldingi narx tarixi bor, Karam -- yo'q. Ikkalasi ham
    # mavjud ``_supplier_summary_text`` formatida, matn/maydonlar
    # o'zgarishsiz.
    assert "Pomidor" in combined and "Karam" in combined
    assert "Oxirgi xarid narxi: 12 000 so'm" in combined
    assert "Oldingi narx yo'q" in combined


async def test_xarid_test_isolation_still_excludes_real_products_after_batch_fix(bot_dp):
    import roles

    main, bot = bot_dp
    _make_kassir(111)
    tester_id = roles.E2E_TESTER_TELEGRAM_ID

    # Real kassir -- real mahsulot (1 qatorli kirim REAL bitta-
    # mahsulot oqimini -- alohida miqdor so'rovi -- ishga tushiradi).
    await send(main.dp, bot, 111, text="/openshift")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="/closeshift")
    await send(main.dp, bot, 111, text="Baqlajon")
    await send(main.dp, bot, 111, text="4 kg")

    # Sinovchi -- alohida, izolyatsiyalangan TEST mahsulot.
    await send(main.dp, bot, tester_id, text="/sinovsmena")
    await send(main.dp, bot, tester_id, text="Pomidor 5 kg\nKaram 1 dona")
    await send_callback(main.dp, bot, tester_id, data="csdef_list_confirm", target_chat_id=tester_id)

    sent = await send(main.dp, bot, tester_id, text="/xarid")
    combined = " ".join(t for t in texts(sent) if t)
    assert "Pomidor" in combined and "Karam" in combined
    assert "Baqlajon" not in combined

    await send(main.dp, bot, tester_id, text="/sinovtugat")
