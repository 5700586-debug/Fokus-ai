import os

import pytest

import db

EXPECTED_TABLES = {
    "invites",
    "employees",
    "employee_contacts",
    "fsm_storage",
    "rules",
    "supervisor_scores",
    "monthly_performance",
    "star_history",
    "bonus_history",
    "vehicles",
    "vehicle_daily_checks",
    "vehicle_service_history",
    "market_observations",
    "meal_plans",
    "cash_shifts",
    "cash_expenses",
    "cash_difference_reviews",
    "cash_shift_approvals",
    "inventory_daily_snapshots",
    "inventory_variance_explanations",
    "inventory_variance_reviews",
    "calibration_sessions",
    "calibration_questions",
}


@pytest.mark.skipif(bool(os.getenv("DATABASE_URL")), reason="sqlite_master SQLite'ga xos")
def test_init_db_creates_all_tables():
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    finally:
        conn.close()

    table_names = {row["name"] for row in rows}
    assert EXPECTED_TABLES <= table_names


def test_init_db_is_idempotent():
    db.init_db()
    db.init_db()


def test_seed_rules_present():
    from repositories import performance as performance_repo

    rules = performance_repo.list_rules()
    assert rules["star.max"] == "5"
    assert rules["bonus.stars.5"] == "500000"
    assert rules["vehicle.oil_change_interval_km"] == "5000"
    assert rules["cash_shift.tolerance"] == "20000"
    assert rules["cash_shift.retry_limit"] == "3"
    assert rules["cash_expense.baseline_min_observations"] == "7"
    assert rules["inventory.variance_threshold"] == "1000000"
