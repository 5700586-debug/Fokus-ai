"""Xodimning o'z holatini ko'rish uchun sodda dashboard: profil,
joriy davr Bonus/Minus/Jami ball (``services/discipline`` — mavjud
``bonus_bank_ledger``dan, qarang ``get_period_point_totals``), kechagi
davomat va oxirgi 2 kunlik tafsilot (``services/attendance``). Bitta
view-model funksiyasi orqali yig'iladi — handler (``performance_bot.py``
``/mystars``) faqat shu natijani matnga aylantiradi, DB/servis
chaqiruvlarini o'zi aralashtirmaydi.
"""

import employees
from roles import role_name
from services import attendance as attendance_service
from services import discipline


def build_dashboard(user_id: int) -> dict | None:
    profile = employees.get_profile(user_id)
    if profile is None:
        return None

    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"

    return {
        "profile": {
            "full_name": full_name,
            "role_label": role_name(profile.get("role_key")),
            "branch": profile.get("branch") or "-",
            "photo_file_id": profile.get("photo_file_id"),
        },
        "points": discipline.get_period_point_totals(user_id),
        "yesterday": attendance_service.get_yesterday_summary(user_id),
        "hours": {"label": "Ma'lumot yo'q"},
        "recent_days": attendance_service.get_recent_days_summary(user_id, days=2),
    }


def format_dashboard_text(dashboard: dict) -> str:
    profile = dashboard["profile"]
    points = dashboard["points"]
    yesterday = dashboard["yesterday"]

    lines = [
        f"👤 {profile['full_name']} — {profile['role_label']}",
        f"🏬 {profile['branch']}",
        "",
        f"🟢 Bonus: {points['bonus']}",
        f"🔴 Minus: {points['minus']}",
        f"⭐ Jami: {points['net']}",
        "",
    ]

    if yesterday["arrival_time"]:
        lines.append(f"⏰ Kecha: {yesterday['arrival_time']} — {yesterday['label']}")
    else:
        lines.append("⏰ Kecha: Ma'lumot yo'q")

    lines.append(f"🕒 Oy boshidan ishlangan soat: {dashboard['hours']['label']}")
    lines.append("")
    lines.append("📅 Oxirgi 2 kun:")
    for day in dashboard["recent_days"]:
        if day["arrival_time"]:
            lines.append(f"{day['date']} — {day['arrival_time']} — {day['label']}")
        else:
            lines.append(f"{day['date']} — Ma'lumot yo'q")

    return "\n".join(lines)
