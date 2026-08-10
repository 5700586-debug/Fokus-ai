"""Kassir xarajatlari — kategoriya bo'yicha yozish va odatiy diapazondan
sezilarli chetlanishni (baseline) aniqlash.

Baseline alohida jadvalda saqlanmaydi — har safar ``cash_expenses``
tarixidan on-the-fly hisoblanadi, shuning uchun eskirish (staleness)
muammosi bo'lmaydi. Tarix ``cash_expense.baseline_min_observations``dan
kam bo'lsa, hech qanday anomaliya hukmi chiqarilmaydi (spec 12-bo'lim).
"""

from dataclasses import dataclass

from repositories import cash_shifts as repo
from services import rules as rules_service

EXPENSE_CATEGORIES = [
    "taxi",
    "delivery",
    "transport",
    "mayda_xarajat",
    "service",
    "purchase_related",
    "other",
]


@dataclass
class ExpenseResult:
    expense_id: int
    is_anomaly: bool
    baseline_average: float | None


def check_anomaly(employee_id: int, category: str, amount: int, expense_date: str) -> tuple[bool, float | None]:
    """Yozishdan oldin oldindan ko'rish — bot xarajatni saqlashdan avval
    sababini so'rash kerakligini shu orqali biladi.
    """
    history = repo.get_expense_history(employee_id, category, before_date=expense_date)
    min_observations = rules_service.get_expense_baseline_min_observations()

    if len(history) < min_observations:
        return False, None

    baseline_average = sum(row["amount"] for row in history) / len(history)
    multiplier = rules_service.get_expense_anomaly_multiplier()
    is_anomaly = amount > baseline_average * multiplier

    return is_anomaly, baseline_average


def log_expense(
    shift_id: int, employee_id: int, branch: str | None, category: str, amount: int,
    description: str | None, expense_date: str,
) -> ExpenseResult:
    is_anomaly, baseline_average = check_anomaly(employee_id, category, amount, expense_date)

    expense_id = repo.add_expense(shift_id, employee_id, branch, category, amount, description, expense_date)

    return ExpenseResult(expense_id, is_anomaly, baseline_average)


def get_expenses_for_shift(shift_id: int) -> list[dict]:
    return repo.get_expenses_for_shift(shift_id)


def total_expenses_for_shift(shift_id: int) -> int:
    return sum(row["amount"] for row in repo.get_expenses_for_shift(shift_id))
