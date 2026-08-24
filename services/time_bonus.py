"""Vaqt bonusi — avtomatik davomat (Face ID va h.k.) ulanguncha, faqat
Nazoratchi uchun QO'LDA FALLBACK. Avtomatik manba ulanganda
(``providers/attendance_provider.py``) xuddi shu ``grant()`` funksiyasi
``source=SOURCE_AUTO`` bilan chaqiriladi — ikkalasi ham bir xil
``UNIQUE(employee_id, grant_date)`` orqali bir-birini ustidan
yozib yubormaydi (qarang ``repositories/time_bonus.py``)."""

import company_time
from repositories import time_bonus as time_bonus_repo

SOURCE_AUTO = time_bonus_repo.SOURCE_AUTO
SOURCE_MANUAL = time_bonus_repo.SOURCE_MANUAL


def confirm_manual(employee_id: int, confirmed_by: int) -> bool:
    """``True`` — bugungi kun uchun qo'lda tasdiqlandi (yangi yozuv),
    ``False`` — bugun uchun allaqachon (AUTO yoki MANUAL) yozuv bor edi."""
    today = company_time.today().isoformat()
    return time_bonus_repo.grant(employee_id, today, SOURCE_MANUAL, confirmed_by)


def get_today_status(employee_id: int) -> dict | None:
    today = company_time.today().isoformat()
    return time_bonus_repo.get_for_date(employee_id, today)
