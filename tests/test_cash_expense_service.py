from repositories import cash_shifts as repo
from services import cash_expense


def _shift() -> dict:
    return repo.open_shift(1, "Filial-1", "2026-01-01", opening_balance=0, tolerance=20000)


def test_no_anomaly_without_enough_baseline():
    shift = _shift()

    # Faqat 2 ta tarixiy yozuv — min_observations(7)dan kam
    for amount in (60_000, 65_000):
        cash_expense.log_expense(shift["id"], 1, "Filial-1", "taxi", amount, None, "2025-12-30")

    result = cash_expense.log_expense(shift["id"], 1, "Filial-1", "taxi", 500_000, None, "2026-01-01")

    assert result.is_anomaly is False
    assert result.baseline_average is None


def test_anomaly_flagged_once_baseline_is_sufficient():
    shift = _shift()

    for i, amount in enumerate((60_000, 65_000, 70_000, 75_000, 80_000, 62_000, 68_000)):
        repo.add_expense(shift["id"], 1, "Filial-1", "taxi", amount, None, f"2025-12-{20 + i}")

    result = cash_expense.log_expense(shift["id"], 1, "Filial-1", "taxi", 180_000, None, "2026-01-01")

    assert result.is_anomaly is True
    assert result.baseline_average is not None


def test_normal_amount_not_flagged_with_sufficient_baseline():
    shift = _shift()

    for i, amount in enumerate((60_000, 65_000, 70_000, 75_000, 80_000, 62_000, 68_000)):
        repo.add_expense(shift["id"], 1, "Filial-1", "taxi", amount, None, f"2025-12-{20 + i}")

    result = cash_expense.log_expense(shift["id"], 1, "Filial-1", "taxi", 72_000, None, "2026-01-01")

    assert result.is_anomaly is False


def test_baseline_is_per_category():
    shift = _shift()

    for i, amount in enumerate((60_000,) * 7):
        repo.add_expense(shift["id"], 1, "Filial-1", "taxi", amount, None, f"2025-12-{20 + i}")

    # "delivery" kategoriyasida tarix yo'q — taxi baseline unga ta'sir qilmasligi kerak
    result = cash_expense.log_expense(shift["id"], 1, "Filial-1", "delivery", 500_000, None, "2026-01-01")

    assert result.is_anomaly is False
    assert result.baseline_average is None


def test_total_expenses_for_shift():
    shift = _shift()
    cash_expense.log_expense(shift["id"], 1, "Filial-1", "taxi", 10_000, None, "2026-01-01")
    cash_expense.log_expense(shift["id"], 1, "Filial-1", "service", 20_000, None, "2026-01-01")

    assert cash_expense.total_expenses_for_shift(shift["id"]) == 30_000
