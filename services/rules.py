"""``rules`` jadvalidan tiplangan qiymatlarni o'qish/yozish.

Barcha threshold/tarif bu yerdan o'qiladi — kod ichida hardcode
qilinmaydi. Boshlang'ich qiymatlar ``schema/performance.py`` va
``schema/vehicles.py`` da seed qilingan, Founder ularni
``/setrule`` orqali o'zgartirishi mumkin (``main.py``).
"""

from repositories import performance as performance_repo


def get_bonus_for_stars(stars: int) -> int:
    if stars <= 0:
        return 0

    value = performance_repo.get_rule(f"bonus.stars.{stars}")
    return int(value) if value is not None else 0


def get_star_bounds() -> tuple[int, int]:
    min_value = performance_repo.get_rule("star.min")
    max_value = performance_repo.get_rule("star.max")
    return int(min_value or 0), int(max_value or 5)


def get_full_bonus_criteria() -> dict:
    return {
        "min_supervisor_score": int(
            performance_repo.get_rule("full_bonus_month.min_supervisor_score") or 0
        ),
        "require_attendance_ok": performance_repo.get_rule(
            "full_bonus_month.require_attendance_ok"
        )
        == "1",
        "require_no_serious_violation": performance_repo.get_rule(
            "full_bonus_month.require_no_serious_violation"
        )
        == "1",
        "require_checklist_completed": performance_repo.get_rule(
            "full_bonus_month.require_checklist_completed"
        )
        == "1",
    }


def get_oil_change_interval_km() -> int:
    value = performance_repo.get_rule("vehicle.oil_change_interval_km")
    return int(value) if value is not None else 5000


def get_cash_shift_tolerance() -> int:
    value = performance_repo.get_rule("cash_shift.tolerance")
    return int(value) if value is not None else 20000


def get_cash_shift_retry_limit() -> int:
    value = performance_repo.get_rule("cash_shift.retry_limit")
    return int(value) if value is not None else 3


def get_expense_baseline_min_observations() -> int:
    value = performance_repo.get_rule("cash_expense.baseline_min_observations")
    return int(value) if value is not None else 7


def get_expense_anomaly_multiplier() -> float:
    value = performance_repo.get_rule("cash_expense.anomaly_multiplier")
    return float(value) if value is not None else 1.5


def get_inventory_variance_threshold() -> int:
    value = performance_repo.get_rule("inventory.variance_threshold")
    return int(value) if value is not None else 1_000_000


def get_inventory_reminder_time() -> str:
    value = performance_repo.get_rule("inventory.reminder_time")
    return value if value is not None else "20:00"


def get_calibration_daily_question_time() -> str:
    value = performance_repo.get_rule("calibration.daily_question_time")
    return value if value is not None else "10:00"


def get_bos_day_close_deadline() -> str:
    value = performance_repo.get_rule("bos.day_close_deadline")
    return value if value is not None else "20:00"


def get_bos_supervisor_late_penalty() -> int:
    value = performance_repo.get_rule("bos.supervisor_late_penalty")
    return int(value) if value is not None else 40


def get_bos_grade_points() -> dict[str, int]:
    return {
        "bajarilmagan": int(performance_repo.get_rule("bos.grade_points.bajarilmagan") or 0),
        "chala": int(performance_repo.get_rule("bos.grade_points.chala") or 1),
        "norma": int(performance_repo.get_rule("bos.grade_points.norma") or 2),
        "alo": int(performance_repo.get_rule("bos.grade_points.alo") or 3),
    }


def get_bos_penalty_amounts() -> tuple[int, ...]:
    value = performance_repo.get_rule("bos.penalty_amounts")
    if not value:
        return (10, 20, 30)
    return tuple(int(part) for part in value.split(","))


def get_saturn_group_chat_id() -> int | None:
    """Founder ``/setrule saturn.group_chat_id <chat_id>`` bilan
    o'rnatadi — rule bo'sh bo'lsa (standart), Saturn guruh scheduleri
    hech narsa yubormaydi (jim o'chirilgan holat, xato emas)."""
    value = performance_repo.get_rule("saturn.group_chat_id")
    return int(value) if value else None


def get_saturn_morning_time() -> str:
    value = performance_repo.get_rule("saturn.morning_time")
    return value if value else "08:00"


def get_saturn_morning_image_enabled() -> bool:
    """Standart: yoqilgan. Founder ``/setrule saturn.morning_image_enabled 0``
    bilan tonggi rasmli xabarni o'chirishi mumkin (qayta deploy shart
    emas)."""
    value = performance_repo.get_rule("saturn.morning_image_enabled")
    return value != "0"


def get_saturn_night_image_enabled() -> bool:
    """Standart: yoqilgan. Founder ``/setrule saturn.night_image_enabled 0``
    bilan tungi rasmli xabarni o'chirishi mumkin."""
    value = performance_repo.get_rule("saturn.night_image_enabled")
    return value != "0"


def get_saturn_dashboard_times() -> list[str]:
    value = performance_repo.get_rule("saturn.dashboard_times")
    if not value:
        return ["12:00", "16:00"]
    return [part.strip() for part in value.split(",") if part.strip()]


def get_saturn_evening_time() -> str:
    value = performance_repo.get_rule("saturn.evening_time")
    return value if value else "21:00"


def get_saturn_tip_time() -> str:
    value = performance_repo.get_rule("saturn.tip_time")
    return value if value else "13:00"


def set_rule(rule_key: str, rule_value: str, updated_by: int) -> None:
    performance_repo.set_rule(rule_key, rule_value, updated_by)


def list_rules() -> dict[str, str]:
    return performance_repo.list_rules()
