"""Izolyatsiya tekshiruvi: E2E test (``Sinovchi``) yozuvlari real
ma'lumot bilan HECH QACHON aralashmaydi (qarang
``services/e2e_test_access.py``).
"""

import pytest

import roles
from repositories import cash_shifts as cash_shifts_repo
from repositories import shift_deficiencies as shift_deficiencies_repo
from services import e2e_test_access, shift_deficiency

_TESTER_ID = roles.E2E_TESTER_TELEGRAM_ID
_OTHER_USER_ID = 111222333


def _open_real_shift(employee_id: int, branch: str, shift_date: str) -> dict:
    return cash_shifts_repo.open_shift(employee_id, branch, shift_date, opening_balance=0, tolerance=20000)


def test_normal_market_shortage_query_excludes_test_rows():
    real_shift = _open_real_shift(1, "Filial-1", "2026-01-05")
    shift_deficiency.add_market_item(real_shift["id"], 1, "Pomidor", 10, "kg")

    result = e2e_test_access.start_test_shift(_TESTER_ID)
    assert result is not None
    test_shift, test_run_id = result
    e2e_test_access.add_test_market_items(
        _TESTER_ID, test_shift["id"], test_run_id,
        [{"product_name": "Sinov Mahsuloti", "quantity": 5, "unit": "kg"}],
    )

    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert "Pomidor" in products
    assert "Sinov Mahsuloti" not in products


def test_tester_view_excludes_real_rows_and_other_runs():
    real_shift = _open_real_shift(2, "Filial-1", "2026-01-05")
    shift_deficiency.add_market_item(real_shift["id"], 2, "Karam", 3, "dona")

    result_a = e2e_test_access.start_test_shift(_TESTER_ID)
    shift_a, run_a = result_a
    e2e_test_access.add_test_market_items(
        _TESTER_ID, shift_a["id"], run_a, [{"product_name": "Run A mahsuloti", "quantity": 1, "unit": "dona"}]
    )

    result_b = e2e_test_access.start_test_shift(_TESTER_ID)
    shift_b, run_b = result_b
    e2e_test_access.add_test_market_items(
        _TESTER_ID, shift_b["id"], run_b, [{"product_name": "Run B mahsuloti", "quantity": 2, "unit": "dona"}]
    )

    run_b_view = {item["product_name"] for item in e2e_test_access.get_test_run_market_items(_TESTER_ID, run_b)}
    assert run_b_view == {"Run B mahsuloti"}
    assert "Run A mahsuloti" not in run_b_view
    assert "Karam" not in run_b_view


def test_non_tester_id_gets_no_test_run_data():
    result = e2e_test_access.start_test_shift(_TESTER_ID)
    shift, test_run_id = result
    e2e_test_access.add_test_market_items(
        _TESTER_ID, shift["id"], test_run_id, [{"product_name": "Sinov", "quantity": 1, "unit": "dona"}]
    )

    assert e2e_test_access.get_test_run_market_items(_OTHER_USER_ID, test_run_id) == []
    assert e2e_test_access.add_test_market_items(
        _OTHER_USER_ID, shift["id"], test_run_id, [{"product_name": "Hack", "quantity": 1, "unit": "dona"}]
    ) == []
    assert e2e_test_access.start_test_shift(_OTHER_USER_ID) is None


def test_cleanup_deletes_only_exact_run_id_never_real_rows():
    real_shift = _open_real_shift(3, "Filial-1", "2026-01-05")
    shift_deficiency.add_market_item(real_shift["id"], 3, "Piyoz", 4, "kg")

    result_a = e2e_test_access.start_test_shift(_TESTER_ID)
    shift_a, run_a = result_a
    e2e_test_access.add_test_market_items(
        _TESTER_ID, shift_a["id"], run_a, [{"product_name": "Run A mahsuloti", "quantity": 1, "unit": "dona"}]
    )

    result_b = e2e_test_access.start_test_shift(_TESTER_ID)
    shift_b, run_b = result_b
    e2e_test_access.add_test_market_items(
        _TESTER_ID, shift_b["id"], run_b, [{"product_name": "Run B mahsuloti", "quantity": 1, "unit": "dona"}]
    )

    outcome = e2e_test_access.cleanup_test_run(_TESTER_ID, run_a)
    assert outcome["items_deleted"] == 1

    # Run A o'chirildi, Run B va real qator TEGILMAGAN.
    assert e2e_test_access.get_test_run_market_items(_TESTER_ID, run_a) == []
    run_b_view = {item["product_name"] for item in e2e_test_access.get_test_run_market_items(_TESTER_ID, run_b)}
    assert run_b_view == {"Run B mahsuloti"}

    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert products["Piyoz"]["total_quantity"] == 4


def test_cleanup_with_non_tester_id_deletes_nothing():
    result = e2e_test_access.start_test_shift(_TESTER_ID)
    shift, test_run_id = result
    e2e_test_access.add_test_market_items(
        _TESTER_ID, shift["id"], test_run_id, [{"product_name": "Sinov", "quantity": 1, "unit": "dona"}]
    )

    outcome = e2e_test_access.cleanup_test_run(_OTHER_USER_ID, test_run_id)
    assert outcome == {"items_deleted": 0, "shifts_deleted": 0}

    still_there = {item["product_name"] for item in e2e_test_access.get_test_run_market_items(_TESTER_ID, test_run_id)}
    assert still_there == {"Sinov"}


def test_cleanup_with_wrong_run_id_does_not_touch_real_data():
    real_shift = _open_real_shift(4, "Filial-1", "2026-01-05")
    shift_deficiency.add_market_item(real_shift["id"], 4, "Bodring", 6, "kg")

    outcome = e2e_test_access.cleanup_test_run(_TESTER_ID, "no-such-run-id")
    assert outcome == {"items_deleted": 0, "shifts_deleted": 0}

    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert products["Bodring"]["total_quantity"] == 6


def test_repo_get_open_market_items_defaults_exclude_test_rows():
    """``services/shift_deficiency.py`` o'zgarishsiz qoladi -- repo
    darajasidagi ``is_test`` standart qiymati buni ta'minlaydi."""
    real_shift = _open_real_shift(5, "Filial-1", "2026-01-05")
    shift_deficiencies_repo.add_items_bulk(
        real_shift["id"], 5, "Filial-1", "market",
        [{"product_name": "Real qator", "quantity": 1, "unit": "dona"}], "2026-01-05",
    )
    shift_deficiencies_repo.add_items_bulk(
        real_shift["id"], 5, "Filial-1", "market",
        [{"product_name": "Test qator", "quantity": 1, "unit": "dona"}], "2026-01-05",
        is_test=True, test_run_id="run-x",
    )

    default_view = {row["product_name"] for row in shift_deficiencies_repo.get_open_market_items_through("2026-01-05")}
    assert default_view == {"Real qator"}

    test_view = {row["product_name"] for row in shift_deficiencies_repo.get_open_market_items_through("2026-01-05", is_test=True)}
    assert test_view == {"Test qator"}
