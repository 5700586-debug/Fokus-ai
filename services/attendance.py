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

import employees
import company_time
from repositories import attendance as attendance_repo

SOURCE_MANUAL_ENTRY = "manual_nazoratchi_entry"

EVENT_CHECK_IN = "check_in"
EVENT_CHECK_OUT = "check_out"

SHIFT_STATUS_WORK = "work"
SHIFT_STATUS_OFF = "off"

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


def record_manual_departure(employee_id: int, event_date: str, departure_time_text: str) -> bool:
    """``record_manual_arrival``dagi bilan bir xil qat'iy "HH:MM" formati
    -- hozircha hech qanday handler bu funksiyani chaqirmaydi (Telegram
    UI o'zgartirilmagan), faqat servis qatlamida ``check_out`` eventini
    yozish qobiliyati tayyorlanadi."""
    parsed = _parse_hhmm(departure_time_text)
    if parsed is None:
        return False

    hour, minute = parsed
    event_day = date.fromisoformat(event_date)
    event_time = datetime(
        event_day.year, event_day.month, event_day.day, hour, minute, tzinfo=company_time.resolve_timezone()
    ).isoformat()

    attendance_repo.record_event(employee_id, EVENT_CHECK_OUT, event_time, source=SOURCE_MANUAL_ENTRY)
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


# ----------------------------------------------------- ishlangan soatlar --


def get_worked_hours_for_day(employee_id: int, event_date: str) -> float | None:
    """Faqat kunning BIRINCHI valid ``check_in``i va OXIRGI valid
    ``check_out``i orasidagi vaqt -- ikkalasi ham mavjud bo'lmasa yoki
    interval manfiy/mantiqsiz bo'lsa ``None`` (bu kun "to'liq ishlangan"
    deb HISOBLANMAYDI, reja soatiga ham qo'shilmaydi)."""
    events = attendance_repo.list_events_for_date(employee_id, event_date)
    check_ins = sorted(
        (e["event_time"] for e in events if e["event_type"] == EVENT_CHECK_IN)
    )
    check_outs = sorted(
        (e["event_time"] for e in events if e["event_type"] == EVENT_CHECK_OUT)
    )
    if not check_ins or not check_outs:
        return None

    try:
        first_check_in = datetime.fromisoformat(check_ins[0])
        last_check_out = datetime.fromisoformat(check_outs[-1])
    except ValueError:
        return None

    duration = (last_check_out - first_check_in).total_seconds() / 3600.0
    if duration <= 0:
        return None

    return duration


def _month_to_date_range(profile: dict) -> tuple[date, date] | None:
    """``(range_start, range_end)`` -- oy boshi (yoki ``hire_date``,
    qaysi biri keyinroq bo'lsa) dan bugungacha, ikkalasi ham kiritilgan
    holda. ``hire_date``dan oldingi va kelajakdagi kunlar HECH QACHON
    hisobga olinmaydi. ``hire_date`` kelajakda bo'lsa (haqiqiy oraliq
    yo'q) ``None``."""
    today = company_time.today()
    month_start = date(today.year, today.month, 1)

    hire_date_text = profile.get("hire_date")
    range_start = month_start
    if hire_date_text:
        try:
            hire_date = date.fromisoformat(hire_date_text)
        except ValueError:
            hire_date = None
        if hire_date is not None and hire_date > range_start:
            range_start = hire_date

    if range_start > today:
        return None

    return range_start, today


# ------------------------------------------------- reja smena jadvali --


def set_scheduled_work_shift(
    employee_id: int, shift_date: str, start_text: str, end_text: str, source: str, created_by: int | None = None
) -> bool:
    """Kunduzgi (``end > start``) yoki tun smenasi (``end < start`` --
    keyingi kunga o'tadi) -- ikkalasi ham qabul qilinadi. ``start ==
    end`` NOTO'G'RI qiymat, rad etiladi (``False``). Bitta xodim/sana
    uchun atomik UPSERT (``repositories/attendance.py::set_work_shift``)
    -- oxirgi qonuniy chaqiruv qiymati saqlanadi, dublikat qator
    yaratmaydi."""
    start_parsed = _parse_hhmm(start_text)
    end_parsed = _parse_hhmm(end_text)
    if start_parsed is None or end_parsed is None or start_parsed == end_parsed:
        return False

    planned_start = f"{start_parsed[0]:02d}:{start_parsed[1]:02d}"
    planned_end = f"{end_parsed[0]:02d}:{end_parsed[1]:02d}"
    attendance_repo.set_work_shift(employee_id, shift_date, planned_start, planned_end, source, created_by)
    return True


def set_scheduled_day_off(employee_id: int, shift_date: str, source: str, created_by: int | None = None) -> None:
    attendance_repo.set_day_off(employee_id, shift_date, source, created_by)


def _shift_duration_hours(planned_start: str, planned_end: str) -> float:
    start_hour, start_minute = _parse_hhmm(planned_start)
    end_hour, end_minute = _parse_hhmm(planned_end)
    start_total = start_hour * 60 + start_minute
    end_total = end_hour * 60 + end_minute

    if end_total > start_total:
        duration_minutes = end_total - start_total
    else:
        # Tun smenasi -- keyingi kunga o'tadi (masalan 20:00 -> 08:00).
        duration_minutes = (end_total + 24 * 60) - start_total

    return duration_minutes / 60.0


def get_month_to_date_planned_hours(employee_id: int) -> dict | None:
    """Oy boshidan (yoki ``hire_date``dan, qaysi biri keyinroq bo'lsa)
    bugungacha strukturali ``employee_scheduled_shifts``dan reja soat.
    Xodim topilmasa ``None``. Diapazondagi HAR BIR sana uchun aniq
    ``work``/``off`` yozuvi bo'lishi SHART -- birortasi yo'q (UNKNOWN,
    OFF deb taxmin qilinmaydi) bo'lsa ``planned_hours`` ``None`` va
    ``missing_days_count`` shu kunlar sonini ko'rsatadi."""
    profile = employees.get_profile(employee_id)
    if profile is None:
        return None

    date_range = _month_to_date_range(profile)
    if date_range is None:
        return {"planned_hours": None, "missing_days_count": 0, "range_start": None, "range_end": None}

    range_start, range_end = date_range
    shifts = attendance_repo.get_schedule_for_range(
        employee_id, range_start.isoformat(), (range_end + timedelta(days=1)).isoformat()
    )
    shifts_by_date = {shift["shift_date"]: shift for shift in shifts}

    total_hours = 0.0
    missing_days_count = 0
    current = range_start
    while current <= range_end:
        shift = shifts_by_date.get(current.isoformat())
        if shift is None:
            missing_days_count += 1
        elif shift["status"] == SHIFT_STATUS_WORK:
            total_hours += _shift_duration_hours(shift["planned_start"], shift["planned_end"])
        current += timedelta(days=1)

    planned_hours = None if missing_days_count > 0 else total_hours

    return {
        "planned_hours": planned_hours,
        "missing_days_count": missing_days_count,
        "range_start": range_start.isoformat(),
        "range_end": range_end.isoformat(),
    }


def get_month_to_date_hours(employee_id: int) -> dict | None:
    """Oy boshidan (yoki ``hire_date``dan, qaysi biri keyinroq bo'lsa)
    bugungacha REJA va HAQIQIY ishlangan soat. Xodim topilmasa ``None``.

    ``planned_hours`` endi FAQAT strukturali ``employee_scheduled_shifts``
    manbasidan (``get_month_to_date_planned_hours``) keladi -- eski
    ``employees.work_schedule`` erkin matni fallback sifatida umuman
    ISHLATILMAYDI. ``actual_hours`` faqat to'liq va valid (check_in+
    check_out mavjud, interval musbat) kunlarning yig'indisi -- eski
    tarixga umuman tegilmaydi, faqat o'qiladi."""
    profile = employees.get_profile(employee_id)
    if profile is None:
        return None

    date_range = _month_to_date_range(profile)
    if date_range is None:
        return {
            "planned_hours": None, "actual_hours": 0.0, "missing_days_count": 0,
            "range_start": None, "range_end": None,
        }

    range_start, range_end = date_range

    planned = get_month_to_date_planned_hours(employee_id)

    events = attendance_repo.list_events_for_range(
        employee_id, range_start.isoformat(), (range_end + timedelta(days=1)).isoformat()
    )
    events_by_date: dict[str, list[dict]] = {}
    for event in events:
        event_date = event["event_time"][:10]
        events_by_date.setdefault(event_date, []).append(event)

    actual_hours = 0.0
    for event_date in events_by_date:
        worked = get_worked_hours_for_day(employee_id, event_date)
        if worked is not None:
            actual_hours += worked

    return {
        "planned_hours": planned["planned_hours"],
        "actual_hours": actual_hours,
        "missing_days_count": planned["missing_days_count"],
        "range_start": range_start.isoformat(),
        "range_end": range_end.isoformat(),
    }


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
