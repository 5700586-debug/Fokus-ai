"""Davomat/kechikish holatini ko'rib chiqish: Nazoratchi tomonidan
qo'lda kiritilgan kelish vaqti + 4 ta sabab (sababsiz/rahbar ruxsati/
fors-major/boshqa) + "rahbar ruxsati" uchun Founderga Ha/Yo'q
tasdiqlash. Hech qanday avtomatik minus ball QO'LLANMAYDI — bu modul
faqat holatni saqlaydi, jarima miqdorini Nazoratchi ham, AI ham
o'ylab topmaydi (miqdor hali biznes tomonidan belgilanmagan).

Real Face ID integratsiyasi hali yo'q (``providers/attendance_provider.py``
— stub) — ``record_manual_arrival`` Nazoratchi tomonidan qo'lda
kiritilgan (masalan kechagi Face ID hisobotidan) ma'lumot uchun, xuddi
shu ``attendance_events`` jadvaliga yozadi, shuning uchun avtomatik
manba ulanganda kod o'zgarishisiz ishlashda davom etadi.
"""

from datetime import date, datetime, timedelta

import company_time
from repositories import attendance as attendance_repo

SOURCE_MANUAL_ENTRY = "manual_nazoratchi_entry"

EVENT_CHECK_IN = "check_in"

REASON_UNJUSTIFIED = "unjustified"
REASON_MANAGER_PERMISSION_PENDING = "manager_permission_pending"
REASON_MANAGER_PERMISSION_APPROVED = "manager_permission_approved"
REASON_MANAGER_PERMISSION_REJECTED = "manager_permission_rejected"
REASON_FORCE_MAJEURE = "force_majeure"
REASON_OTHER = "other_reason"

REASON_LABELS = {
    REASON_UNJUSTIFIED: "❌ Sababsiz kechikish",
    REASON_MANAGER_PERMISSION_PENDING: "⏳ Rahbar tasdig'i kutilmoqda",
    REASON_MANAGER_PERMISSION_APPROVED: "✅ Rahbar ruxsati bilan",
    REASON_MANAGER_PERMISSION_REJECTED: "🔎 Ko'rib chiqilmoqda",
    REASON_FORCE_MAJEURE: "⚠️ Fors-major holat",
    REASON_OTHER: "📝 Boshqa sabab",
}


def _parse_hhmm(text: str) -> tuple[int, int] | None:
    try:
        parsed = datetime.strptime(text.strip(), "%H:%M")
    except ValueError:
        return None
    return parsed.hour, parsed.minute


def record_manual_arrival(employee_id: int, event_date: str, arrival_time_text: str) -> bool:
    """``arrival_time_text`` — "HH:MM" formatida. Noto'g'ri format
    bo'lsa ``False`` qaytaradi (yozuv qilinmaydi)."""
    parsed = _parse_hhmm(arrival_time_text)
    if parsed is None:
        return False

    hour, minute = parsed
    event_day = date.fromisoformat(event_date)
    event_time = datetime(
        event_day.year, event_day.month, event_day.day, hour, minute, tzinfo=company_time.resolve_timezone()
    ).isoformat()

    attendance_repo.record_event(employee_id, EVENT_CHECK_IN, event_time, source=SOURCE_MANUAL_ENTRY)
    return True


def get_arrival_time(employee_id: int, event_date: str) -> str | None:
    events = attendance_repo.list_events_for_date(employee_id, event_date)
    check_ins = [e for e in events if e["event_type"] == EVENT_CHECK_IN]
    if not check_ins:
        return None

    check_ins.sort(key=lambda e: e["event_time"])
    try:
        return datetime.fromisoformat(check_ins[0]["event_time"]).strftime("%H:%M")
    except ValueError:
        return check_ins[0]["event_time"]


def get_day_summary(employee_id: int, event_date: str) -> dict:
    arrival_time = get_arrival_time(employee_id, event_date)
    reason = attendance_repo.get_reason(employee_id, event_date)
    reason_status = reason["reason_status"] if reason else None

    if arrival_time is None:
        label = "Ma'lumot yo'q"
    elif reason_status is None:
        label = "✅ Vaqtida"
    else:
        label = REASON_LABELS.get(reason_status, reason_status)

    return {
        "date": event_date,
        "arrival_time": arrival_time,
        "reason_status": reason_status,
        "note": reason["note"] if reason else None,
        "label": label,
    }


def get_yesterday_summary(employee_id: int) -> dict:
    yesterday = (company_time.today() - timedelta(days=1)).isoformat()
    return get_day_summary(employee_id, yesterday)


def get_recent_days_summary(employee_id: int, days: int = 2) -> list[dict]:
    """Faqat oxirgi ``days`` kalendar kunini qaytaradi — bu FAQAT
    ko'rsatish uchun chegara, eski ``attendance_events``/
    ``attendance_reasons`` yozuvlari DBda butunligicha qoladi."""
    today = company_time.today()
    return [get_day_summary(employee_id, (today - timedelta(days=i)).isoformat()) for i in range(days)]


def mark_unjustified(employee_id: int, event_date: str) -> None:
    attendance_repo.set_reason(employee_id, event_date, REASON_UNJUSTIFIED)


def mark_force_majeure(employee_id: int, event_date: str, note: str) -> None:
    attendance_repo.set_reason(employee_id, event_date, REASON_FORCE_MAJEURE, note)


def mark_other_reason(employee_id: int, event_date: str, note: str) -> None:
    attendance_repo.set_reason(employee_id, event_date, REASON_OTHER, note)


def request_manager_permission(employee_id: int, event_date: str) -> None:
    attendance_repo.set_reason(employee_id, event_date, REASON_MANAGER_PERMISSION_PENDING)


def decide_manager_permission(employee_id: int, event_date: str, approved: bool, decided_by: int) -> bool:
    """``True`` — shu chaqiruv qarorni yozdi. ``False`` — bu
    xodim/kun uchun so'rov allaqachon hal qilingan edi (ikkinchi
    Ha/Yo'q bosilishi hech narsani o'zgartirmaydi)."""
    new_status = REASON_MANAGER_PERMISSION_APPROVED if approved else REASON_MANAGER_PERMISSION_REJECTED
    return attendance_repo.decide_manager_permission(
        employee_id, event_date, REASON_MANAGER_PERMISSION_PENDING, new_status, decided_by
    )
