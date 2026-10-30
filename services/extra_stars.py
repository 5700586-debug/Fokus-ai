"""Qo'shimcha ish yulduzlari (Muhammadiy qarori, 2026-10-30).

Rejadan ortiq o'tirish pul emas: qo'shimcha ish faqat oldindan kelishilib, beruvchi (Founder yoki ruxsatli rahbar)
yulduzcha bilan to'laydi. Yulduzlar oy davomida yig'iladi, oy oxirida maoshga qo'shiladi (1 yulduz = 5 000 so'm) va
ULARDAN MINUS AYRILMAYDI. Har yozuv bir martalik ``request_token`` bilan — takroriy bosish ikkinchi yozuv yaratmaydi.
"""

from __future__ import annotations

from datetime import datetime, timezone

import company_time
from db import get_connection

MAX_STARS_PER_ENTRY = 20
MIN_REASON_CHARS = 5
# Kim bera oladi: Founder har doim; qo'shimcha rollar Muhammadiy qaroridan keyin shu yerga qo'shiladi.
GIVER_ROLES: frozenset[str] = frozenset()


class ExtraStarsError(ValueError):
    """Foydalanuvchiga ko'rsatiladigan tushunarli xato."""


def can_give(user_id: int) -> bool:
    from config import FOUNDER_ID
    from roles import get_role

    return user_id == FOUNDER_ID or (get_role(user_id) or "") in GIVER_ROLES


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
        row = conn.execute("SELECT status FROM employees WHERE user_id = ?", (employee_id,)).fetchone()
        if row is None or row["status"] != "approved":
            raise ExtraStarsError("Xodim topilmadi.")
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
