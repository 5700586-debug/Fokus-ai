"""BOS (Business Operating System): kunlik baholash, intizomiy jarima/bonus
banki, nazoratchi mas'uliyati va apellyatsiya.

Fiks oylik (``salaries.fixed_salary``) hech qachon bu modul orqali
o'zgartirilmaydi — faqat Founder ``set_fixed_salary`` bilan belgilaydi.
Jarima va kunlik baho FAQAT ``bonus_bank``ga ta'sir qiladi
(``adjust_bonus_bank`` orqali, har bir o'zgarish ``bonus_bank_ledger``da
audit sifatida qoladi).
"""

import re
from dataclasses import dataclass

from repositories import discipline as discipline_repo

GRADE_CHALA = "chala"
GRADE_NORMA = "norma"
GRADE_ALO = "alo"

GRADE_POINTS = {GRADE_CHALA: 1, GRADE_NORMA: 2, GRADE_ALO: 3}
GRADE_LABELS = {GRADE_CHALA: "Chala", GRADE_NORMA: "Norma", GRADE_ALO: "A'lo"}

PENALTY_AMOUNTS = (10, 20, 30)

APPEAL_NONE = "none"
APPEAL_PENDING = "pending"
APPEAL_RESOLVED = "resolved"

DECISION_APPROVED = "approved"
DECISION_REJECTED = "rejected"

_RULE_NUMBER_RE = re.compile(r"\d+")


# ------------------------------------------------------------- salaries --


def set_fixed_salary(user_id: int, fixed_salary: int, updated_by: int) -> None:
    discipline_repo.upsert_fixed_salary(user_id, fixed_salary, updated_by)


def get_salary(user_id: int) -> dict:
    salary = discipline_repo.get_salary(user_id)
    if salary is None:
        return {"user_id": user_id, "fixed_salary": 0, "bonus_bank": 0}
    return salary


def adjust_bonus_bank(user_id: int, delta: int, reason: str, ref_type: str, ref_id: int | None = None) -> int:
    return discipline_repo.adjust_bonus_bank(user_id, delta, reason, ref_type, ref_id)


def get_bonus_ledger(user_id: int, limit: int = 20) -> list[dict]:
    return discipline_repo.get_bonus_ledger(user_id, limit)


# --------------------------------------------------------- company rules --


def add_rule(rule_number: int, title: str, content: str, created_by: int) -> bool:
    return discipline_repo.create_rule(rule_number, title, content, created_by)


def get_rule(rule_number: int) -> dict | None:
    return discipline_repo.get_rule_by_number(rule_number)


def list_rules() -> list[dict]:
    return discipline_repo.list_active_rules()


def extract_rule_number(text: str) -> int | None:
    """"3-nizom", "3 nizom", "nizom 3", "3" kabi matndan nizom raqamini
    ajratib oladi — birinchi topilgan butun sonni qaytaradi.
    """
    match = _RULE_NUMBER_RE.search(text)
    return int(match.group()) if match else None


# ------------------------------------------------------------ evaluation --


@dataclass
class EvaluationResult:
    grade_key: str
    grade_points: int
    bonus_bank_balance: int


def record_daily_grade(employee_id: int, supervisor_id: int, eval_date: str, grade_key: str) -> EvaluationResult:
    if grade_key not in GRADE_POINTS:
        raise ValueError(f"noma'lum baho: {grade_key}")

    grade_points = GRADE_POINTS[grade_key]
    previous = discipline_repo.get_daily_evaluation(employee_id, eval_date)
    discipline_repo.upsert_daily_evaluation(employee_id, supervisor_id, eval_date, grade_key, grade_points)

    delta = grade_points - (previous["grade_points"] if previous else 0)
    if delta:
        balance = discipline_repo.adjust_bonus_bank(
            employee_id, delta, f"Kunlik baho: {GRADE_LABELS[grade_key]}", "daily_evaluation", None
        )
    else:
        balance = get_salary(employee_id)["bonus_bank"]

    return EvaluationResult(grade_key=grade_key, grade_points=grade_points, bonus_bank_balance=balance)


def get_daily_leaderboard(eval_date: str) -> list[dict]:
    rows = discipline_repo.get_evaluations_for_date(eval_date)
    return [{"employee_id": row["employee_id"], "grade_points": row["grade_points"]} for row in rows]


def get_monthly_leaderboard(year_month: str) -> list[dict]:
    start_date = f"{year_month}-01"
    end_date = f"{year_month}-31"

    points = discipline_repo.get_points_totals(start_date, end_date)
    penalties = discipline_repo.get_penalty_totals(start_date, end_date)
    penalty_by_employee = {row["employee_id"]: row["total_penalty"] for row in penalties}

    board: dict[int, int] = {}
    for row in points:
        board[row["employee_id"]] = row["total_points"] - penalty_by_employee.get(row["employee_id"], 0)
    for employee_id, total_penalty in penalty_by_employee.items():
        board.setdefault(employee_id, -total_penalty)

    ranked = sorted(board.items(), key=lambda pair: pair[1], reverse=True)
    return [{"employee_id": employee_id, "net_score": score} for employee_id, score in ranked]


# ------------------------------------------------------------- penalties --


def apply_penalty(
    employee_id: int,
    supervisor_id: int,
    penalty_date: str,
    amount: int,
    rule_number: int,
    comment: str | None,
    ai_note: str | None,
) -> dict:
    if amount not in PENALTY_AMOUNTS:
        raise ValueError(f"jarima miqdori noto'g'ri: {amount}")

    rule = discipline_repo.get_rule_by_number(rule_number)
    if rule is None:
        raise ValueError(f"{rule_number}-nizom topilmadi")

    penalty_id = discipline_repo.create_penalty(
        employee_id, supervisor_id, penalty_date, amount, rule_number, comment, ai_note
    )
    balance = discipline_repo.adjust_bonus_bank(
        employee_id, -amount, f"Jarima: {rule_number}-nizom", "penalty", penalty_id
    )

    return {"penalty_id": penalty_id, "bonus_bank_balance": balance, "rule": rule}


def list_appealable_penalties(employee_id: int, limit: int = 10) -> list[dict]:
    return discipline_repo.list_penalties_by_status(employee_id, APPEAL_NONE, limit)


def submit_appeal(penalty_id: int, reason_text: str, voice_file_id: str | None) -> dict | None:
    penalty = discipline_repo.get_penalty(penalty_id)
    if penalty is None or penalty["appeal_status"] != APPEAL_NONE:
        return None

    discipline_repo.set_penalty_appeal(penalty_id, reason_text, voice_file_id)
    return discipline_repo.get_penalty(penalty_id)


def save_appeal_brief(penalty_id: int, brief: str) -> None:
    discipline_repo.set_penalty_appeal_brief(penalty_id, brief)


def decide_appeal(penalty_id: int, decision: str, decided_by: int) -> dict:
    if decision not in (DECISION_APPROVED, DECISION_REJECTED):
        raise ValueError(f"noma'lum qaror: {decision}")

    penalty = discipline_repo.get_penalty(penalty_id)
    if penalty is None or penalty["appeal_status"] != APPEAL_PENDING:
        raise ValueError("apellyatsiya topilmadi yoki allaqachon hal qilingan")

    discipline_repo.decide_penalty_appeal(penalty_id, decision, decided_by)

    if decision == DECISION_APPROVED:
        discipline_repo.adjust_bonus_bank(
            penalty["employee_id"],
            penalty["amount"],
            "Apellyatsiya qondirildi — jarima qaytarildi",
            "appeal_refund",
            penalty_id,
        )

    return penalty


# ---------------------------------------------------------- day closure --


def close_day(supervisor_id: int, closure_date: str, total_employees: int) -> bool:
    evaluated_count = len(discipline_repo.get_evaluations_for_date(closure_date))
    return discipline_repo.try_close_day(supervisor_id, closure_date, evaluated_count, total_employees)


def get_closure(supervisor_id: int, closure_date: str) -> dict | None:
    return discipline_repo.get_closure(supervisor_id, closure_date)


def penalize_supervisor_for_late_close(supervisor_id: int, audit_date: str, penalty_amount: int) -> bool:
    recorded = discipline_repo.try_record_supervisor_audit(
        supervisor_id, audit_date, "day_not_closed", penalty_amount
    )
    if recorded:
        discipline_repo.adjust_bonus_bank(
            supervisor_id, -penalty_amount, "Kun o'z vaqtida yopilmadi", "supervisor_audit", None
        )
    return recorded
