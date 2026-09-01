from repositories import cash_shifts as cash_shifts_repo
from repositories import shift_deficiencies as deficiency_repo
from services import shift_deficiency


def _open_shift(employee_id: int, branch: str, shift_date: str) -> dict:
    return cash_shifts_repo.open_shift(employee_id, branch, shift_date, opening_balance=0, tolerance=20000)


def test_add_market_item_and_add_company_item_stay_separate():
    shift = _open_shift(1, "Filial-1", "2026-01-05")

    market_id = shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 10, "kg")
    company_id = shift_deficiency.add_company_item(shift["id"], 1, "Un", 5, "quti")

    assert market_id is not None
    assert company_id is not None

    stats = shift_deficiency.get_supplier_stats("2026-01-05", "2026-01-05")
    assert stats["total"] == 1  # faqat market hisoblanadi, company kirmaydi


def test_add_item_rejects_unknown_unit():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    assert shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 10, "tonna") is None


def test_add_item_rejects_non_positive_quantity():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    assert shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 0, "kg") is None
    assert shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", -5, "kg") is None


def test_add_item_rejects_empty_name():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    assert shift_deficiency.add_market_item(shift["id"], 1, "   ", 10, "kg") is None


def test_add_item_unknown_shift_returns_none():
    assert shift_deficiency.add_market_item(999999, 1, "Pomidor", 10, "kg") is None


def test_item_stores_quantity_and_unit():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 10, "kg")

    tomorrow_shift = _open_shift(2, "Filial-1", "2026-01-06")
    items = shift_deficiency.get_yesterday_open_items(tomorrow_shift["id"])

    assert len(items) == 1
    assert items[0]["product_name"] == "Pomidor"
    assert items[0]["quantity"] == 10
    assert items[0]["unit"] == "kg"


def test_get_next_step_progresses_through_market_company_yesterday():
    shift = _open_shift(1, "Filial-1", "2026-01-05")

    assert shift_deficiency.get_next_step(shift["id"]) == shift_deficiency.STEP_MARKET
    shift_deficiency.mark_market_step_done(shift["id"])

    assert shift_deficiency.get_next_step(shift["id"]) == shift_deficiency.STEP_COMPANY
    shift_deficiency.mark_company_step_done(shift["id"])

    assert shift_deficiency.get_next_step(shift["id"]) == shift_deficiency.STEP_YESTERDAY
    shift_deficiency.mark_yesterday_step_done(shift["id"])

    assert shift_deficiency.get_next_step(shift["id"]) == shift_deficiency.STEP_DONE
    assert shift_deficiency.is_flow_complete(shift["id"]) is True


def test_is_flow_complete_false_until_all_three_steps_done():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    assert shift_deficiency.is_flow_complete(shift["id"]) is False

    shift_deficiency.mark_market_step_done(shift["id"])
    shift_deficiency.mark_company_step_done(shift["id"])
    assert shift_deficiency.is_flow_complete(shift["id"]) is False  # kechagi hali yo'q


def test_yesterday_open_items_only_from_before_shift_date_same_branch():
    yesterday_shift = _open_shift(1, "Filial-1", "2026-01-04")
    shift_deficiency.add_market_item(yesterday_shift["id"], 1, "Suzma", 5, "kg")

    today_other_shift = _open_shift(2, "Filial-1", "2026-01-05")
    shift_deficiency.add_market_item(today_other_shift["id"], 2, "Zelen", 2, "dona")

    today_shift = _open_shift(3, "Filial-1", "2026-01-05")

    open_items = shift_deficiency.get_yesterday_open_items(today_shift["id"])

    names = {item["product_name"] for item in open_items}
    assert names == {"Suzma"}  # bugun (boshqa smena) yozgan "Zelen" ko'rinmaydi


def test_yesterday_open_items_scoped_to_branch():
    other_branch_shift = _open_shift(1, "Filial-2", "2026-01-04")
    shift_deficiency.add_market_item(other_branch_shift["id"], 1, "Olma", 3, "kg")

    today_shift = _open_shift(2, "Filial-1", "2026-01-05")

    assert shift_deficiency.get_yesterday_open_items(today_shift["id"]) == []


def test_confirm_yesterday_review_completes_gate_and_keeps_still_missing_open():
    yesterday_shift = _open_shift(1, "Filial-1", "2026-01-04")
    suzma_id = shift_deficiency.add_market_item(yesterday_shift["id"], 1, "Suzma", 5, "kg")
    shift_deficiency.add_market_item(yesterday_shift["id"], 1, "Olma", 3, "kg")

    today_shift = _open_shift(2, "Filial-1", "2026-01-05")
    shift_deficiency.mark_market_step_done(today_shift["id"])
    shift_deficiency.mark_company_step_done(today_shift["id"])

    shift_deficiency.confirm_yesterday_review(today_shift["id"], still_missing_item_ids=[suzma_id])

    assert shift_deficiency.get_next_step(today_shift["id"]) == shift_deficiency.STEP_DONE

    tomorrow_shift = _open_shift(3, "Filial-1", "2026-01-06")
    still_open = {item["product_name"] for item in shift_deficiency.get_yesterday_open_items(tomorrow_shift["id"])}
    assert still_open == {"Suzma"}  # Olma "keldi" deb yopildi, Suzma ochiq qoldi (ertaga o'tadi)


def test_confirm_yesterday_review_all_arrived_leaves_nothing_open():
    yesterday_shift = _open_shift(1, "Filial-1", "2026-01-04")
    suzma_id = shift_deficiency.add_market_item(yesterday_shift["id"], 1, "Suzma", 5, "kg")

    today_shift = _open_shift(2, "Filial-1", "2026-01-05")
    shift_deficiency.confirm_yesterday_review(today_shift["id"], still_missing_item_ids=[])

    item = deficiency_repo.get_open_items_for_branch_before("Filial-1", "2026-01-06")
    assert item == []

    tomorrow_shift = _open_shift(3, "Filial-1", "2026-01-06")
    assert shift_deficiency.get_yesterday_open_items(tomorrow_shift["id"]) == []


def test_get_supplier_stats_counts_only_market_and_computes_completion_rate():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    arrived_id = shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 10, "kg")
    shift_deficiency.add_market_item(shift["id"], 1, "Bodring", 5, "kg")
    shift_deficiency.add_company_item(shift["id"], 1, "Un", 2, "quti")  # market emas, hisobga kirmaydi

    deficiency_repo.mark_item_resolved(arrived_id, "2026-01-05T10:00:00+00:00")

    stats = shift_deficiency.get_supplier_stats("2026-01-05", "2026-01-05")

    assert stats["total"] == 2
    assert stats["arrived"] == 1
    assert stats["missing"] == 1
    assert stats["completion_rate"] == 50.0


def test_get_supplier_stats_empty_range_has_zero_percent_not_crash():
    stats = shift_deficiency.get_supplier_stats("2026-01-05", "2026-01-05")
    assert stats == {"total": 0, "arrived": 0, "missing": 0, "completion_rate": 0.0}
