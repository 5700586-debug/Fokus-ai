"""Xodimning o'z holatini ko'rish uchun sodda dashboard: profil,
joriy oy Bonus/Minus/Jami ball (``services/discipline.get_period_point_totals``:
kunlik baho baho sanasi — ``eval_date`` — oyi bo'yicha), kechagi
davomat va oxirgi 2 kunlik tafsilot (``services/attendance``). Bitta
view-model funksiyasi orqali yig'iladi — handler (``performance_bot.py``
``/mystars``) faqat shu natijani matnga aylantiradi, DB/servis
chaqiruvlarini o'zi aralashtirmaydi.
"""

from datetime import timedelta

import company_time
import employees
from roles import role_name
from services import attendance as attendance_service
from services import discipline


def build_dashboard(user_id: int) -> dict | None:
    profile = employees.get_profile(user_id)
    if profile is None:
        return None

    full_name = " ".join(part for part in (profile.get("familiya"), profile.get("ism")) if part) or "-"

    # "Kecha" va "oxirgi 2 kun" bir xil kunni o'z ichiga oladi: kun bir marta o'qiladi.
    recent_days = attendance_service.get_recent_days_summary(user_id, days=2)
    yesterday_iso = (company_time.today() - timedelta(days=1)).isoformat()
    yesterday = next((day for day in recent_days if day["date"] == yesterday_iso), None)
    if yesterday is None:
        yesterday = attendance_service.get_yesterday_summary(user_id)

    return {
        "profile": {
            "full_name": full_name,
            "role_label": role_name(profile.get("role_key")),
            "branch": profile.get("branch") or "-",
            "photo_file_id": profile.get("photo_file_id"),
        },
        "points": discipline.get_period_point_totals(user_id),
        "yesterday": yesterday,
        "hours": attendance_service.get_month_to_date_hours(user_id, profile=profile),
        "recent_days": recent_days,
    }


def _format_hours(value: float) -> str:
    """180.0 -> "180", 172.5 -> "172.5" -- inson o'qishi uchun sodda,
    ortiqcha nol/floating-point dumisiz."""
    return f"{value:g}"


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

    hours = dashboard["hours"]
    planned_hours = hours["planned_hours"]
    if planned_hours is None:
        lines.append("📋 Reja soati: Ma'lumot yo'q")
        if hours["missing_days_count"] > 0:
            lines.append(f"📅 Grafik kiritilmagan: {hours['missing_days_count']} kun")
    else:
        lines.append(f"📋 Reja soati: {_format_hours(planned_hours)} soat")

    if hours["worked_days_count"] == 0:
        lines.append("🕒 Ishlangan soat: Ma'lumot yo'q")
    else:
        lines.append(f"🕒 Ishlangan soat: {_format_hours(hours['actual_hours'])} soat")

    lines.append("")
    lines.append("📅 Oxirgi 2 kun:")
    for day in dashboard["recent_days"]:
        if day["arrival_time"]:
            lines.append(f"{day['date']} — {day['arrival_time']} — {day['label']}")
        else:
            lines.append(f"{day['date']} — Ma'lumot yo'q")

    return "\n".join(lines)
