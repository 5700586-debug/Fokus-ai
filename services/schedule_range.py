"""Bugundan oy oxirigacha bitta oddiy grafik: ish kunlariga work shift, haftalik dam kuniga day off.

Yozuv mavjud ``services/attendance`` (``set_scheduled_work_shift``/``set_scheduled_day_off``) orqali ketadi:
parallel grafik tizimi yo'q, har kun alohida atomik UPSERT, shuning uchun keyin bitta kunni qo'lda
o'zgartirish qolgan kunlarga tegmaydi."""

import calendar
from datetime import date, timedelta

from services import attendance as attendance_service

WEEKDAY_NAMES = ("Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba")


def month_range(today: date) -> tuple[date, date]:
    return today, today.replace(day=calendar.monthrange(today.year, today.month)[1])


def dates_in_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _label(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def confirm_text(full_name: str, start: date, end: date, shift: dict, off_weekday: int | None) -> str:
    off_label = "yo'q" if off_weekday is None else WEEKDAY_NAMES[off_weekday]
    return (
        f"👤 {full_name}\n"
        f"{_label(start)} dan {_label(end)} gacha\n"
        f"{shift['start']}–{shift['end']}\n"
        f"Dam kuni: {off_label}\n\n"
        "Tasdiqlaysizmi?"
    )


def apply_range(
    employee_id: int, start: date, end: date, shift: dict, off_weekday: int | None, source: str, created_by: int,
) -> tuple[int, int]:
    """(ish kunlari soni, dam kunlari soni). Vaqt yozishdan OLDIN tekshiriladi: noto'g'ri bo'lsa
    ``ValueError`` va hech narsa yozilmaydi (yarim grafik qolmaydi)."""
    if not (
        attendance_service.is_valid_hhmm(shift["start"])
        and attendance_service.is_valid_hhmm(shift["end"])
        and shift["start"] != shift["end"]
    ):
        raise ValueError("noto'g'ri smena vaqti")

    work_days = off_days = 0
    for day in dates_in_range(start, end):
        iso = day.isoformat()
        if off_weekday is not None and day.weekday() == off_weekday:
            attendance_service.set_scheduled_day_off(
                employee_id, iso, source, created_by=created_by, schedule_mode=shift.get("mode")
            )
            off_days += 1
            continue
        attendance_service.set_scheduled_work_shift(
            employee_id, iso, shift["start"], shift["end"], source,
            created_by=created_by, schedule_mode=shift.get("mode"),
        )
        work_days += 1
    return work_days, off_days
