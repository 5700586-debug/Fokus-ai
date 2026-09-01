"""Founder uchun "🚨 Bugungi muammolar" — V1, faqat grafik bo'yicha
ikkita haqiqiy muammoni READ-ONLY ko'rsatadi:

1. Bugungi kun uchun grafik hali kiritilmagan FAOL (``approved``)
   xodimlar (``services.attendance.get_shift_for_date`` ``None``
   qaytarsa — grafik yo'q; ``status='off'`` esa reja BOR degani, dam
   olish rejalashtirilgan, muammo emas).
2. Hozircha ``pending`` holatdagi grafik o'zgartirish so'rovlari.

Hech qanday yozuv qilinmaydi, yangi DB jadval/migratsiya/repository
yo'q — faqat mavjud ``employees``/``services.attendance``dan o'qiydi.
Kechikish, vazifa, filial tashrifi, apellyatsiya, 1:1, nomzodlar va
harakat tugmalari ATAYLAB bu yerda YO'Q — keyingi, alohida bosqichlar."""

from datetime import date

import company_time
import employees
from config import RECRUITING_BRANCH_NAMES
from services import attendance

MAX_ENTRIES_PER_SECTION = 10


def _full_name(profile: dict) -> str:
    return " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"


def _active_employees() -> list[dict]:
    """Barcha filiallardagi FAOL (``employees.list_approved_by_branch``
    — ``status='approved'``, ishdan chiqarilganlar shu bilan avtomatik
    chiqib qoladi) xodimlar, ``user_id`` bo'yicha dublikatsiz."""
    seen_user_ids: set[int] = set()
    result: list[dict] = []
    for branch in RECRUITING_BRANCH_NAMES:
        for profile in employees.list_approved_by_branch(branch):
            user_id = profile["user_id"]
            if user_id in seen_user_ids:
                continue
            seen_user_ids.add(user_id)
            result.append(profile)
    return result


def employees_missing_todays_schedule(today: date | None = None) -> list[dict]:
    """``[{"full_name", "branch", "date"}]`` — bugun uchun grafik hali
    yo'q FAOL xodimlar."""
    today = today or company_time.today()
    today_iso = today.isoformat()

    missing = []
    for profile in _active_employees():
        shift = attendance.get_shift_for_date(profile["user_id"], today_iso)
        if shift is not None:
            continue
        missing.append(
            {"full_name": _full_name(profile), "branch": profile.get("branch") or "-", "date": today_iso}
        )
    return missing


def pending_schedule_change_requests() -> list[dict]:
    """``[{"full_name", "branch", "date"}]`` — hozircha ``pending``
    holatdagi grafik o'zgartirish so'rovlari. Profil topilmasa yoki
    xodim endi faol ('approved') bo'lmasa (masalan ishdan chiqarilgan)
    — bu yozuv o'tkazib yuboriladi."""
    requests = attendance.list_schedule_change_requests(status=attendance.SCHEDULE_REQUEST_PENDING)

    result = []
    for request in requests:
        profile = employees.get_profile(request["employee_id"])
        if profile is None or profile.get("status") != "approved":
            continue
        result.append(
            {"full_name": _full_name(profile), "branch": profile.get("branch") or "-", "date": request["shift_date"]}
        )
    return result


def _section_summary(items: list[dict]) -> dict:
    return {"total": len(items), "items": items[:MAX_ENTRIES_PER_SECTION]}


def build_today_problems_summary(today: date | None = None) -> dict:
    """``{"missing_schedule": {...}, "pending_requests": {...}}`` — har
    bo'lim ``{"total": int, "items": list[dict]}`` (``items`` ko'pi
    bilan ``MAX_ENTRIES_PER_SECTION`` ta, qolgani ``total`` orqali
    hisoblanadi)."""
    return {
        "missing_schedule": _section_summary(employees_missing_todays_schedule(today)),
        "pending_requests": _section_summary(pending_schedule_change_requests()),
    }
