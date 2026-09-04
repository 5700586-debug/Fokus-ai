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
