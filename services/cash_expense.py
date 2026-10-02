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


LEDGER_STATUS_MATCHED = "matched"
LEDGER_STATUS_UNVERIFIED = "unverified"
LEDGER_STATUS_ACCEPTED_ITEMS_SUM = "cashier_accepted_items_sum"
LEDGER_STATUS_ACCEPTED_WRITTEN_TOTAL = "cashier_accepted_written_total"
_SAVABLE_LEDGER_STATUSES = {
    LEDGER_STATUS_MATCHED, LEDGER_STATUS_UNVERIFIED,
    LEDGER_STATUS_ACCEPTED_ITEMS_SUM, LEDGER_STATUS_ACCEPTED_WRITTEN_TOTAL,
}


def save_ledger_items(
    shift_id: int, items: list[dict], total_status: str = LEDGER_STATUS_MATCHED,
    written_total: int | None = None, accepted_total: int | None = None,
) -> int:
    """Daftardan o'qilgan qatorlarni (``raw_name``, ``normalized_name``, ``amount``) va jami
    holatini saqlaydi. ``normalized_name`` bo'sh bo'lsa ``raw_name`` yoziladi. Nomlar
    jami mos kelmagani sababli HECH QACHON tashlanmaydi — holat ``total_status`` da.
    ``accepted_total`` berilmasa qatorlar yig'indisi olinadi. Bo'sh ro'yxat eskilarini tozalaydi."""
    if total_status not in _SAVABLE_LEDGER_STATUSES:
        raise ValueError(f"Noma'lum ledger jami holati: {total_status}")

    prepared = [
        {
            "raw_name": item["raw_name"],
            "normalized_name": item.get("normalized_name") or item["raw_name"],
            "amount": int(item["amount"]),
        }
        for item in items
    ]
    summary = None
    if prepared:
        items_sum = sum(item["amount"] for item in prepared)
        summary = {
            "total_status": total_status, "items_sum": items_sum, "written_total": written_total,
            "accepted_total": accepted_total if accepted_total is not None else items_sum,
        }
    return repo.replace_ledger_expense_items(shift_id, prepared, summary)


def get_ledger_summary(shift_id: int) -> dict | None:
    return repo.get_ledger_expense_summary(shift_id)


def get_ledger_items(shift_id: int) -> list[dict]:
    return repo.get_ledger_expense_items(shift_id)


def total_ledger_expenses(shift_id: int) -> int:
    """Daftar xarajatlari jami — FAQAT ``amount`` yig'indisi (nomlar hisobga kirmaydi)."""
    return sum(row["amount"] for row in repo.get_ledger_expense_items(shift_id))


def total_expenses_for_shift(shift_id: int) -> int:
    return sum(row["amount"] for row in repo.get_expenses_for_shift(shift_id))
