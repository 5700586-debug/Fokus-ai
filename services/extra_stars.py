"""Qo'shimcha ish yulduzlari (Muhammadiy qarori, 2026-10-30).

Rejadan ortiq o'tirish pul emas: qo'shimcha ish faqat oldindan kelishilib, filial rahbari (savdo bo'limi boshlig'i,
o'z filialiga) yoki Founder yulduzcha bilan to'laydi. Yulduzlar oy davomida yig'iladi, oy oxirida maoshga qo'shiladi (1 yulduz = 5 000 so'm) va
ULARDAN MINUS AYRILMAYDI. Har yozuv bir martalik ``request_token`` bilan — takroriy bosish ikkinchi yozuv yaratmaydi.
"""

from __future__ import annotations

from datetime import datetime, timezone

import company_time
from db import get_connection

MAX_STARS_PER_ENTRY = 20
MIN_REASON_CHARS = 5


class ExtraStarsError(ValueError):
    """Foydalanuvchiga ko'rsatiladigan tushunarli xato."""


def can_give(user_id: int) -> bool:
    """Founder (har kimga) yoki filial rahbari — savdo bo'limi boshlig'i (faqat o'z filialiga)."""
    from services import permissions

    return permissions.has_permission(user_id, permissions.ACTION_GIVE_EXTRA_STARS)


def giver_branch(user_id: int) -> str | None:
    """``None`` — cheklovsiz (Founder). Aks holda beruvchi faqat shu filial xodimlariga bera oladi."""
    from config import FOUNDER_ID

    if user_id == FOUNDER_ID:
        return None
    import employees

    profile = employees.get_profile(user_id) or {}
    return profile.get("branch") or ""


def can_give_to(giver_id: int, employee: dict | None) -> bool:
    if employee is None or not can_give(giver_id):
        return False
    branch = giver_branch(giver_id)
    return branch is None or (bool(branch) and employee.get("branch") == branch)


def give(employee_id: int, stars: int, reason: str, given_by: int, request_token: str) -> bool:
    """``True`` — yangi yozuv; ``False`` — shu token bilan allaqachon yozilgan (takroriy bosish)."""
    if not can_give(given_by):
        raise ExtraStarsError("Ruxsat yo'q.")
    if employee_id == given_by:
        raise ExtraStarsError("O'zingizga yulduz yozib bo'lmaydi.")
    if not isinstance(stars, int) or isinstance(stars, bool) or not 1 <= stars <= MAX_STARS_PER_ENTRY:
        raise ExtraStarsError(f"Yulduz soni 1 dan {MAX_STARS_PER_ENTRY} gacha bo'lishi kerak.")
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON_CHARS:
        raise ExtraStarsError("Sababini aniqroq yozing (kamida 5 belgi).")
    if not request_token:
        raise ExtraStarsError("Tasdiq eskirgan.")
    conn = get_connection()
    try:
        row = conn.execute("SELECT status, branch FROM employees WHERE user_id = ?", (employee_id,)).fetchone()
        if row is None or row["status"] != "approved":
            raise ExtraStarsError("Xodim topilmadi.")
        if not can_give_to(given_by, dict(row)):
            raise ExtraStarsError("Faqat o'z filialingiz xodimlariga yulduz bera olasiz.")
        cursor = conn.execute(
            "INSERT OR IGNORE INTO extra_work_stars (employee_id, work_date, stars, reason, given_by, request_token, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (employee_id, company_time.today().isoformat(), stars, reason[:500], given_by, request_token,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def month_total(employee_id: int, year_month: str) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(stars), 0) AS n FROM extra_work_stars WHERE employee_id = ? AND work_date >= ? AND work_date < ?",
            (employee_id, f"{year_month}-01", f"{year_month}-99"),
        ).fetchone()
        return int(row["n"])
    finally:
        conn.close()
