"""Savdo bo'limi boshlig'i kiritgan kunlik ovqat rejasi."""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_meal_for_date(plan_date: str, meal_description: str, entered_by: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO meal_plans (plan_date, meal_description, entered_by, entered_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(plan_date) DO UPDATE SET "
            "meal_description = excluded.meal_description, entered_by = excluded.entered_by, "
            "entered_at = excluded.entered_at",
            (plan_date, meal_description, entered_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_meal_for_date(plan_date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM meal_plans WHERE plan_date = ?", (plan_date,)
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None
