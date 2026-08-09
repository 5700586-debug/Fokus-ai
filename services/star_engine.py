"""Yulduzli intizom bonus tizimi — barqaror intizom/to'liq bonus seriyasi.

Yulduz "eng yaxshi xodim" degani emas, balki har oy to'liq bonus
mezonini bajarish ketma-ketligi. Oy to'liq muvaffaqiyatli bo'lsa
``stars += 1`` (5 dan oshmaydi), bo'lmasa ``stars -= 1`` (0 dan
kamaymaydi). ``year_month`` allaqachon qayta ishlangan bo'lsa, funksiya
hech narsani o'zgartirmaydi (idempotent — bir oy ikki marta qayta
ishlansa ham yulduz ikki marta o'zgarmaydi).
"""

from dataclasses import dataclass

from repositories import performance as performance_repo
from services import rules as rules_service


@dataclass
class MonthInputs:
    avg_supervisor_score: float | None
    attendance_ok: bool
    no_serious_violation: bool
    checklist_completed: bool


@dataclass
class MonthResult:
    already_processed: bool
    full_bonus_month: bool = False
    previous_stars: int = 0
    new_stars: int = 0
    bonus_amount: int = 0


def _is_full_bonus_month(inputs: MonthInputs) -> bool:
    criteria = rules_service.get_full_bonus_criteria()

    if criteria["require_attendance_ok"] and not inputs.attendance_ok:
        return False
    if criteria["require_no_serious_violation"] and not inputs.no_serious_violation:
        return False
    if criteria["require_checklist_completed"] and not inputs.checklist_completed:
        return False
    if inputs.avg_supervisor_score is None:
        return False
    if inputs.avg_supervisor_score < criteria["min_supervisor_score"]:
        return False

    return True


def process_month(user_id: int, year_month: str, inputs: MonthInputs) -> MonthResult:
    full_bonus_month = _is_full_bonus_month(inputs)

    inserted = performance_repo.try_insert_monthly_performance(
        user_id=user_id,
        year_month=year_month,
        avg_supervisor_score=inputs.avg_supervisor_score,
        attendance_ok=inputs.attendance_ok,
        no_serious_violation=inputs.no_serious_violation,
        checklist_completed=inputs.checklist_completed,
        full_bonus_month=full_bonus_month,
    )
    if not inserted:
        return MonthResult(already_processed=True)

    star_min, star_max = rules_service.get_star_bounds()
    previous_stars = performance_repo.get_current_stars(user_id)

    if full_bonus_month:
        new_stars = min(previous_stars + 1, star_max)
        reason = "To'liq bonusli oy"
    else:
        new_stars = max(previous_stars - 1, star_min)
        reason = "Oy mezoni bajarilmadi"

    performance_repo.try_record_star_change(user_id, year_month, previous_stars, new_stars, reason)

    bonus_amount = rules_service.get_bonus_for_stars(new_stars)
    performance_repo.try_record_bonus(user_id, year_month, new_stars, bonus_amount)

    return MonthResult(
        already_processed=False,
        full_bonus_month=full_bonus_month,
        previous_stars=previous_stars,
        new_stars=new_stars,
        bonus_amount=bonus_amount,
    )


def get_current_stars(user_id: int) -> int:
    return performance_repo.get_current_stars(user_id)


def get_star_history(user_id: int) -> list[dict]:
    return performance_repo.get_star_history(user_id)


def get_bonus_history(user_id: int) -> list[dict]:
    return performance_repo.get_bonus_history(user_id)


def format_star_progress(stars: int) -> str:
    filled = "⭐" * stars
    return filled if filled else "(hali yulduz yo'q)"
