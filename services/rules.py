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


def set_rule(rule_key: str, rule_value: str, updated_by: int) -> None:
    performance_repo.set_rule(rule_key, rule_value, updated_by)


def list_rules() -> dict[str, str]:
    return performance_repo.list_rules()
