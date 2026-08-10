"""Kassir kunlik smena nazorati — kutilayotgan vs real kassa qoldig'i
farqini hisoblash, tolerance/retry/supervisor-eskalatsiya mantig'i.

Formula (spec bo'yicha):
    total_sales = cash_sales + card_sales + other_payments
    expected_cash_balance = opening_balance + cash_sales - cash_expenses
    difference = actual_cash_balance - expected_cash_balance

Kechagi smenaning ``actual_cash_balance``i ertangi ``opening_balance``
bo'ladi — bu SAVDO emas, shuning uchun ``total_sales``ga qo'shilmaydi.
"""

from dataclasses import dataclass

from repositories import cash_shifts as repo
from services import rules as rules_service

STATUS_OPEN = "open"
STATUS_CLEAN_CLOSED = "clean_closed"
STATUS_WITHIN_TOLERANCE = "within_tolerance"
STATUS_RECHECK_REQUIRED = "recheck_required"
STATUS_NEEDS_SUPERVISOR_APPROVAL = "needs_supervisor_approval"
STATUS_APPROVED_BY_SUPERVISOR = "approved_by_supervisor"
STATUS_REJECTED_BY_SUPERVISOR = "rejected_by_supervisor"

_FINAL_STATUSES = (STATUS_CLEAN_CLOSED, STATUS_WITHIN_TOLERANCE)


@dataclass
class CloseAttemptResult:
    shift_id: int
    total_sales: int
    expected_cash_balance: int
    difference: int
    status: str
    finalized: bool
    needs_supervisor: bool
    retries_left: int | None = None


def open_shift_for_today(
    employee_id: int, branch: str | None, shift_date: str, manual_opening_balance: int | None = None
) -> dict:
    """Kechagi yopilgan smenaning ``actual_cash_balance``i bugungi
    ``opening_balance`` sifatida avtomatik olinadi. Agar bu xodim uchun
    hali birorta ham yopilgan smena bo'lmasa (birinchi smena),
    ``manual_opening_balance`` ishlatiladi (berilmasa 0).
    """
    last_closed = repo.get_last_closed_shift(employee_id)
    if last_closed is not None:
        opening_balance = last_closed["actual_cash_balance"]
    else:
        opening_balance = manual_opening_balance if manual_opening_balance is not None else 0

    tolerance = rules_service.get_cash_shift_tolerance()
    return repo.open_shift(employee_id, branch, shift_date, opening_balance, tolerance)


def is_first_ever_shift(employee_id: int) -> bool:
    return repo.get_last_closed_shift(employee_id) is None


def _compute(
    opening_balance: int, cash_sales: int, card_sales: int, other_payments: int,
    cash_expenses: int, actual_cash_balance: int, tolerance: int,
) -> tuple[int, int, int, str]:
    total_sales = cash_sales + card_sales + other_payments
    expected_cash_balance = opening_balance + cash_sales - cash_expenses
    difference = actual_cash_balance - expected_cash_balance

    if difference == 0:
        status = STATUS_CLEAN_CLOSED
    elif abs(difference) <= tolerance:
        status = STATUS_WITHIN_TOLERANCE
    else:
        status = STATUS_RECHECK_REQUIRED

    return total_sales, expected_cash_balance, difference, status


def submit_close_attempt(
    shift_id: int, cash_sales: int, card_sales: int, other_payments: int,
    cash_expenses: int, actual_cash_balance: int,
) -> CloseAttemptResult:
    """Smenani yopishga bir urinish. Natija toza yoki tolerance ichida
    bo'lsa smena yopiladi. Aks holda ``retry_count`` oshiriladi;
    ``cash_shift.retry_limit``dan oshsa ``NEEDS_SUPERVISOR_APPROVAL``ga
    o'tadi (kassir endi qayta urinolmaydi, Nazoratchi/Founder qaror
    qilishi kerak).
    """
    shift = repo.get_shift(shift_id)

    if shift["status"] in (*_FINAL_STATUSES, STATUS_APPROVED_BY_SUPERVISOR, STATUS_REJECTED_BY_SUPERVISOR):
        raise ValueError("Bu smena allaqachon yopilgan — qayta topshirib bo'lmaydi.")
    if shift["status"] == STATUS_NEEDS_SUPERVISOR_APPROVAL:
        raise ValueError("Bu smena hozir Nazoratchi/Founder tekshiruvida — kassir qayta urinolmaydi.")

    total_sales, expected_cash_balance, difference, status = _compute(
        shift["opening_balance"], cash_sales, card_sales, other_payments,
        cash_expenses, actual_cash_balance, shift["tolerance"],
    )

    attempt_number = len(repo.get_difference_reviews(shift_id)) + 1
    repo.record_difference_review(shift_id, attempt_number, actual_cash_balance, difference, status)

    if status in _FINAL_STATUSES:
        repo.update_shift_result(
            shift_id, cash_sales, card_sales, other_payments, total_sales,
            cash_expenses, expected_cash_balance, actual_cash_balance, difference,
            status, close=True,
        )
        return CloseAttemptResult(
            shift_id, total_sales, expected_cash_balance, difference, status,
            finalized=True, needs_supervisor=False,
        )

    retry_limit = rules_service.get_cash_shift_retry_limit()
    new_retry_count = repo.increment_retry_count(shift_id)

    if new_retry_count >= retry_limit:
        repo.update_shift_result(
            shift_id, cash_sales, card_sales, other_payments, total_sales,
            cash_expenses, expected_cash_balance, actual_cash_balance, difference,
            STATUS_NEEDS_SUPERVISOR_APPROVAL, close=False,
        )
        return CloseAttemptResult(
            shift_id, total_sales, expected_cash_balance, difference,
            STATUS_NEEDS_SUPERVISOR_APPROVAL, finalized=False, needs_supervisor=True,
        )

    repo.update_shift_result(
        shift_id, cash_sales, card_sales, other_payments, total_sales,
        cash_expenses, expected_cash_balance, actual_cash_balance, difference,
        STATUS_RECHECK_REQUIRED, close=False,
    )
    return CloseAttemptResult(
        shift_id, total_sales, expected_cash_balance, difference, STATUS_RECHECK_REQUIRED,
        finalized=False, needs_supervisor=False, retries_left=retry_limit - new_retry_count,
    )


def apply_supervisor_decision(shift_id: int, reviewed_by: int, decision: str, comment: str | None) -> str:
    """``decision``: ``"approved"`` | ``"rejected"`` | ``"recheck"``.

    ``recheck`` — kassirga yana urinish imkoniyati beriladi (retry_count
    nolga tushiriladi, cheksiz emas — supervisor har safar ongli
    ravishda qayta ochadi).
    """
    repo.record_shift_approval(shift_id, reviewed_by, decision, comment)

    if decision == "approved":
        repo.set_shift_status(shift_id, STATUS_APPROVED_BY_SUPERVISOR, close=True)
    elif decision == "rejected":
        repo.set_shift_status(shift_id, STATUS_REJECTED_BY_SUPERVISOR, close=True)
    elif decision == "recheck":
        repo.set_shift_status(shift_id, STATUS_RECHECK_REQUIRED, close=False, reset_retry=True)
    else:
        raise ValueError(f"Noma'lum qaror: {decision}")

    return decision


def get_shift(shift_id: int) -> dict | None:
    return repo.get_shift(shift_id)


def get_open_shift(employee_id: int, shift_date: str) -> dict | None:
    return repo.get_open_shift(employee_id, shift_date)
