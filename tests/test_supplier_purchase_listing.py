from repositories import cash_shifts as cash_shifts_repo
from repositories import supplier_purchases as supplier_purchases_repo
from services import shift_deficiency


def _open_shift(employee_id: int, branch: str, shift_date: str) -> dict:
    return cash_shifts_repo.open_shift(employee_id, branch, shift_date, opening_balance=0, tolerance=20000)


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
