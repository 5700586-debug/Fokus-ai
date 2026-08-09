"""Savdo bo'limi boshlig'i kiritadigan ovqat rejasi."""

from repositories import meal_plans as meal_plans_repo


def set_meal_for_date(plan_date: str, meal_description: str, entered_by: int) -> None:
    meal_plans_repo.set_meal_for_date(plan_date, meal_description, entered_by)


def get_meal_for_date(plan_date: str) -> dict | None:
    return meal_plans_repo.get_meal_for_date(plan_date)


def is_meal_missing(plan_date: str) -> bool:
    return meal_plans_repo.get_meal_for_date(plan_date) is None
