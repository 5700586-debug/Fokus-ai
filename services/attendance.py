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
from services import rules as rules_service

SOURCE_MANUAL_ENTRY = "manual_nazoratchi_entry"
SOURCE_SCHEDULE_REQUEST = "employee_schedule_request"

EVENT_CHECK_IN = "check_in"
EVENT_CHECK_OUT = "check_out"

SHIFT_STATUS_WORK = "work"
SHIFT_STATUS_OFF = "off"

SCHEDULE_MODE_FIXED_1 = "fixed_1"
SCHEDULE_MODE_FIXED_2 = "fixed_2"
SCHEDULE_MODE_FLEXIBLE = "flexible"
_KNOWN_SCHEDULE_MODES = (SCHEDULE_MODE_FIXED_1, SCHEDULE_MODE_FIXED_2, SCHEDULE_MODE_FLEXIBLE)

SCHEDULE_REQUEST_PENDING = "pending"
SCHEDULE_REQUEST_APPROVED = "approved"
SCHEDULE_REQUEST_REJECTED = "rejected"

MOBILITY_NONE = "none"
MOBILITY_BRANCH_VISIT_REQUIRED = "branch_visit_required"

VISIT_ENTER = "enter"
VISIT_EXIT = "exit"

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


def _is_overnight_shift(shift: dict | None) -> bool:
    """``planned_end < planned_start`` = keyingi kunga o'tadigan tun
    smenasi (qarang ADVANCED WORK SCHEDULE V1, 6-bo'lim). ``start ==
    end`` yozish paytida allaqachon rad etilgani uchun bu yerda faqat
    qat'iy ``<`` tekshiriladi."""
    if shift is None or shift.get("status") != SHIFT_STATUS_WORK:
        return False
    start_parsed = _parse_hhmm(shift.get("planned_start") or "")
    end_parsed = _parse_hhmm(shift.get("planned_end") or "")
    if start_parsed is None or end_parsed is None:
        return False
    start_total = start_parsed[0] * 60 + start_parsed[1]
    end_total = end_parsed[0] * 60 + end_parsed[1]
    return end_total < start_total


def record_manual_departure(employee_id: int, event_date: str, departure_time_text: str) -> bool:
    """``event_date`` -- LOGICAL SHIFT sanasi (smena boshlangan kun).
    Agar shu sana uchun strukturali schedule mavjud va tun smenasi
    bo'lsa (``planned_end < planned_start``), chiqish vaqti keyingi
    kalendar kuniga yoziladi (masalan smena 14:00->01:00, chiqish
    01:30 -> DBda ``event_date + 1``). Strukturali schedule umuman
    yo'q yoki kunduzgi bo'lsa -- eski, backward-compatible SAME-DAY
    xatti-harakat o'zgarishsiz qoladi."""
    parsed = _parse_hhmm(departure_time_text)
    if parsed is None:
        return False

    hour, minute = parsed
    shift = attendance_repo.get_shift_for_date(employee_id, event_date)
    event_day = date.fromisoformat(event_date)
    if _is_overnight_shift(shift):
        event_day = event_day + timedelta(days=1)

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


def _pair_check_in_check_out(events: list[dict], check_in_date: str) -> float | None:
    """Umumiy juftlash: BIRINCHI ``check_in`` (aynan ``check_in_date``
    kunida bo'lgani -- boshqa logical shiftning check_in'i tasodifan
    aralashib ketmasin) va undan KEYIN bo'lgan OXIRGI valid
    ``check_out``. 24 soatdan oshiq yoki manfiy/nol interval -- soxta
    deb rad etiladi."""
    check_ins = sorted(
        e["event_time"] for e in events if e["event_type"] == EVENT_CHECK_IN and e["event_time"][:10] == check_in_date
    )
    if not check_ins:
        return None

    try:
        first_check_in = datetime.fromisoformat(check_ins[0])
    except ValueError:
        return None

    valid_check_outs = []
    for event in events:
        if event["event_type"] != EVENT_CHECK_OUT:
            continue
        try:
            check_out_dt = datetime.fromisoformat(event["event_time"])
        except ValueError:
            continue
        if check_out_dt > first_check_in:
            valid_check_outs.append(check_out_dt)

    if not valid_check_outs:
        return None

    last_check_out = max(valid_check_outs)
    duration = (last_check_out - first_check_in).total_seconds() / 3600.0
    if duration <= 0 or duration > 24:
        return None

    return duration


def get_worked_hours_for_day(employee_id: int, shift_date: str) -> float | None:
    """``shift_date`` -- LOGICAL SHIFT sanasi (kalendar kuni emas).
    Kunduzgi/strukturasiz kun uchun eski xatti-harakat: check_in va
    check_out ikkalasi ham ``shift_date``ning o'z kalendar kunida
    bo'lishi kerak. Tun smenasi (``planned_end < planned_start``) uchun
    check_in ``shift_date``da, check_out esa keyingi kalendar kunida
    bo'lishi mumkin -- lekin FAQAT agar keyingi kun uchun boshqa
    strukturali WORK smena mavjud bo'lmasa cheksiz; mavjud bo'lsa,
    qidiruv oynasi o'sha smenaning boshlanishidan OLDIN to'xtaydi (ikki
    qo'shni smena eventlari bir-biriga aralashmasin)."""
    shift = attendance_repo.get_shift_for_date(employee_id, shift_date)

    if not _is_overnight_shift(shift):
        events = attendance_repo.list_events_for_date(employee_id, shift_date)
        return _pair_check_in_check_out(events, shift_date)

    shift_day = date.fromisoformat(shift_date)
    next_day = shift_day + timedelta(days=1)
    next_shift = attendance_repo.get_shift_for_date(employee_id, next_day.isoformat())

    if next_shift is not None and next_shift.get("status") == SHIFT_STATUS_WORK:
        next_start = _parse_hhmm(next_shift.get("planned_start") or "")
        if next_start is not None:
            window_end = datetime(
                next_day.year, next_day.month, next_day.day, next_start[0], next_start[1],
                tzinfo=company_time.resolve_timezone(),
            )
        else:
            window_end = datetime(next_day.year, next_day.month, next_day.day, 23, 59, 59, tzinfo=company_time.resolve_timezone())
    else:
        window_end = datetime(next_day.year, next_day.month, next_day.day, 23, 59, 59, tzinfo=company_time.resolve_timezone())

    events = attendance_repo.list_events_for_range(
        employee_id, shift_date, (next_day + timedelta(days=1)).isoformat()
    )
    window_end_iso = window_end.isoformat()
    relevant_events = [e for e in events if e["event_time"] <= window_end_iso]

    return _pair_check_in_check_out(relevant_events, shift_date)


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


# ---------------------------------------------------- grafik siyosati --


def is_valid_hhmm(text: str) -> bool:
    """Handler qatlami uchun ochiq (public) validatsiya -- ichki
    ``_parse_hhmm`` boshqa modulga to'g'ridan-to'g'ri ko'rsatilmasin."""
    return _parse_hhmm(text) is not None


def get_shift_for_date(employee_id: int, shift_date: str) -> dict | None:
    """Handler qatlami uchun ingichka o'ram -- ``repositories/``ga
    to'g'ridan-to'g'ri kirmasin (mavjud loyiha qatlamlanishi)."""
    return attendance_repo.get_shift_for_date(employee_id, shift_date)


def resolve_schedule_mode(employee_id: int) -> str | None:
    """employee override > role default > UNKNOWN (``None``). Policy
    yo'q xodimga hech qanday standart (masalan ``fixed_1``) O'YLAB
    TOPILMAYDI -- ``None`` shunchaki UNKNOWN degani."""
    override = attendance_repo.get_employee_schedule_policy(employee_id)
    if override is not None:
        return override

    profile = employees.get_profile(employee_id)
    role_key = profile.get("role_key") if profile else None
    if role_key is None:
        return None

    return attendance_repo.get_role_schedule_policy(role_key)


def set_employee_schedule_mode(employee_id: int, schedule_mode: str, updated_by: int | None = None) -> bool:
    """Xodimga aniq grafik siyosati override beradi (role defaultdan
    ustun). Noma'lum ``schedule_mode`` qiymati rad etiladi."""
    if schedule_mode not in _KNOWN_SCHEDULE_MODES:
        return False
    attendance_repo.set_employee_schedule_policy(employee_id, schedule_mode, updated_by)
    return True


def set_role_schedule_mode(role_key: str, schedule_mode: str, updated_by: int | None = None) -> bool:
    if schedule_mode not in _KNOWN_SCHEDULE_MODES:
        return False
    attendance_repo.set_role_schedule_policy(role_key, schedule_mode, updated_by)
    return True


# ------------------------------------------------- reja smena jadvali --


def _is_late_change(employee_id: int, shift_date: str) -> bool:
    """Smena ALLAQACHON (o'zining ESKI, hali o'zgartirilmagan
    ``planned_start``iga ko'ra) boshlangandan keyin o'zgartirilyaptimi
    -- faqat BELGI, avtomatik jarima/aybdorlik hukmi emas (qarang
    5-bo'lim)."""
    existing = attendance_repo.get_shift_for_date(employee_id, shift_date)
    if existing is None or existing.get("status") != SHIFT_STATUS_WORK or not existing.get("planned_start"):
        return False

    parsed = _parse_hhmm(existing["planned_start"])
    if parsed is None:
        return False

    shift_day = date.fromisoformat(shift_date)
    shift_start_dt = datetime(
        shift_day.year, shift_day.month, shift_day.day, parsed[0], parsed[1], tzinfo=company_time.resolve_timezone()
    )
    return company_time.now() >= shift_start_dt


def set_scheduled_work_shift(
    employee_id: int, shift_date: str, start_text: str, end_text: str, source: str,
    created_by: int | None = None, schedule_mode: str | None = None, reason: str | None = None,
) -> bool:
    """Kunduzgi (``end > start``) yoki tun smenasi (``end < start`` --
    keyingi kunga o'tadi) -- ikkalasi ham qabul qilinadi. ``start ==
    end`` NOTO'G'RI qiymat, rad etiladi (``False``). Bitta xodim/sana
    uchun atomik UPSERT (``repositories/attendance.py::set_work_shift``)
    -- oxirgi qonuniy chaqiruv qiymati saqlanadi, dublikat qator
    yaratmaydi. Eski qiymat (bo'lsa) audit jadvaliga yoziladi, va agar
    ESKI smena allaqachon boshlangan bo'lsa ``is_late_change`` belgisi
    bilan. ``schedule_mode`` berilmasa xodimning joriy siyosatidan
    (``resolve_schedule_mode``) olinadi -- faqat audit/ma'lumot uchun,
    UNKNOWN bo'lsa ham yozuvning o'zi baribir amalga oshadi (chunki
    aniq ``start_text``/``end_text`` berilgan)."""
    start_parsed = _parse_hhmm(start_text)
    end_parsed = _parse_hhmm(end_text)
    if start_parsed is None or end_parsed is None or start_parsed == end_parsed:
        return False

    planned_start = f"{start_parsed[0]:02d}:{start_parsed[1]:02d}"
    planned_end = f"{end_parsed[0]:02d}:{end_parsed[1]:02d}"
    mode = schedule_mode if schedule_mode is not None else resolve_schedule_mode(employee_id)
    is_late = _is_late_change(employee_id, shift_date)

    attendance_repo.set_work_shift(
        employee_id, shift_date, planned_start, planned_end, mode, source, created_by, reason, is_late,
    )
    return True


def set_scheduled_day_off(
    employee_id: int, shift_date: str, source: str, created_by: int | None = None,
    schedule_mode: str | None = None, reason: str | None = None,
) -> None:
    mode = schedule_mode if schedule_mode is not None else resolve_schedule_mode(employee_id)
    is_late = _is_late_change(employee_id, shift_date)
    attendance_repo.set_day_off(employee_id, shift_date, mode, source, created_by, reason, is_late)


def apply_daily_work_schedule(
    employee_id: int, shift_date: str, source: str, start_text: str | None = None, end_text: str | None = None,
    created_by: int | None = None, reason: str | None = None,
) -> bool:
    """Xodimning grafik SIYOSATIGA ko'ra kunlik WORK yozuvi yaratadi.
    ``fixed_1``/``fixed_2`` uchun aniq vaqt berilmasa markazlashtirilgan
    shablondan (``services/rules.py::get_fixed_shift_template``)
    foydalanadi. ``flexible`` (yoki siyosat UNKNOWN) uchun aniq
    ``start_text``/``end_text`` SHART -- berilmasa yozuv qilinmaydi
    (``False``, hech narsa DBga yozilmaydi)."""
    mode = resolve_schedule_mode(employee_id)

    if start_text is None or end_text is None:
        if mode not in (SCHEDULE_MODE_FIXED_1, SCHEDULE_MODE_FIXED_2):
            return False
        template = rules_service.get_fixed_shift_template(mode)
        if template is None:
            return False
        start_text, end_text = template

    return set_scheduled_work_shift(
        employee_id, shift_date, start_text, end_text, source,
        created_by=created_by, schedule_mode=mode, reason=reason,
    )


# -------------------------------------- grafik o'zgartirish so'rovlari --


def create_schedule_change_request(
    employee_id: int, shift_date: str, requested_status: str, start_text: str | None = None,
    end_text: str | None = None, schedule_mode: str | None = None, reason: str | None = None,
    created_by: int | None = None,
) -> int | None:
    """Xodimning bitta sanaga grafik o'zgartirish so'rovi -- ``pending``
    holatda saqlanadi, schedule'ning O'ZIGA hali tegilmaydi. So'ralgan
    qiymatlar shu yerda, tasdiqlashdan OLDIN, mavjud schedule
    qoidalari bilan (``_parse_hhmm``, ``start != end``, ma'lum
    ``schedule_mode``) tekshiriladi -- noto'g'ri so'rov umuman
    yaratilmaydi (``None``), ya'ni tasdiqlovchi validatsiyani chetlab
    o'ta olmaydi."""
    if requested_status not in (SHIFT_STATUS_WORK, SHIFT_STATUS_OFF):
        return None

    try:
        date.fromisoformat(shift_date)
    except ValueError:
        return None

    if schedule_mode is not None and schedule_mode not in _KNOWN_SCHEDULE_MODES:
        return None

    requested_start = requested_end = None
    if requested_status == SHIFT_STATUS_WORK:
        if start_text is None or end_text is None:
            return None
        start_parsed = _parse_hhmm(start_text)
        end_parsed = _parse_hhmm(end_text)
        if start_parsed is None or end_parsed is None or start_parsed == end_parsed:
            return None
        requested_start = f"{start_parsed[0]:02d}:{start_parsed[1]:02d}"
        requested_end = f"{end_parsed[0]:02d}:{end_parsed[1]:02d}"

    return attendance_repo.create_schedule_change_request(
        employee_id, shift_date, requested_status, requested_start, requested_end,
        schedule_mode, reason, created_by if created_by is not None else employee_id,
        SCHEDULE_REQUEST_PENDING,
    )


def get_schedule_change_request(request_id: int) -> dict | None:
    return attendance_repo.get_schedule_change_request(request_id)


def list_schedule_change_requests(employee_id: int | None = None, status: str | None = None) -> list[dict]:
    return attendance_repo.list_schedule_change_requests(employee_id, status)


def decide_schedule_change_request(request_id: int, approved: bool, decided_by: int) -> bool:
    """Nazoratchi/Founder qarori. ``True`` — qarorni aynan shu chaqiruv
    yozdi (va tasdiq bo'lsa schedule qo'llandi). ``False`` — so'rov yo'q
    yoki allaqachon hal qilingan: takroriy/parallel qaror hech narsani
    qayta yozmaydi va yangi revision yaratmaydi, chunki holat OLDIN
    atomik ``pending -> approved/rejected`` o'tkaziladi, schedule esa
    faqat shundan keyin qo'llanadi."""
    request = attendance_repo.get_schedule_change_request(request_id)
    if request is None:
        return False

    new_status = SCHEDULE_REQUEST_APPROVED if approved else SCHEDULE_REQUEST_REJECTED
    if not attendance_repo.decide_schedule_change_request(
        request_id, SCHEDULE_REQUEST_PENDING, new_status, decided_by
    ):
        return False

    if not approved:
        return True

    if request["requested_status"] == SHIFT_STATUS_OFF:
        set_scheduled_day_off(
            request["employee_id"], request["shift_date"], SOURCE_SCHEDULE_REQUEST,
            created_by=decided_by, schedule_mode=request["requested_schedule_mode"],
            reason=request["reason"],
        )
        return True

    return set_scheduled_work_shift(
        request["employee_id"], request["shift_date"], request["requested_start"], request["requested_end"],
        SOURCE_SCHEDULE_REQUEST, created_by=decided_by,
        schedule_mode=request["requested_schedule_mode"], reason=request["reason"],
    )


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
            "planned_hours": None, "actual_hours": 0.0, "worked_days_count": 0, "missing_days_count": 0,
            "range_start": None, "range_end": None,
        }

    range_start, range_end = date_range

    planned = get_month_to_date_planned_hours(employee_id)

    # Har bir LOGICAL shift sanasi bo'yicha (kalendar kuni bo'yicha
    # emas) -- shuning uchun tun smenasining check_out'i keyingi
    # kalendar kuniga tushsa ham, o'sha smena FAQAT o'zining haqiqiy
    # boshlanish sanasida (bir marta) hisoblanadi, keyingi oy/kunga
    # "yangi" smena sifatida sizib chiqmaydi.
    actual_hours = 0.0
    worked_days_count = 0
    current = range_start
    while current <= range_end:
        worked = get_worked_hours_for_day(employee_id, current.isoformat())
        if worked is not None:
            actual_hours += worked
            worked_days_count += 1
        current += timedelta(days=1)

    return {
        "planned_hours": planned["planned_hours"],
        "actual_hours": actual_hours,
        "worked_days_count": worked_days_count,
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


# --------------------------------------------------- mobillik siyosati --


def resolve_mobility_policy(employee_id: int) -> str | None:
    """employee override > role default > UNKNOWN (``None``) -- xuddi
    ``resolve_schedule_mode``dagi bilan bir xil naqsh, Nazoratchiga
    HARDCODE qilinmagan (kelajakda boshqa lavozimga ham berilishi
    mumkin)."""
    override = attendance_repo.get_employee_mobility_policy(employee_id)
    if override is not None:
        return override

    profile = employees.get_profile(employee_id)
    role_key = profile.get("role_key") if profile else None
    if role_key is None:
        return None

    return attendance_repo.get_role_mobility_policy(role_key)


def set_employee_mobility_mode(employee_id: int, mobility_policy: str, updated_by: int | None = None) -> None:
    attendance_repo.set_employee_mobility_policy(employee_id, mobility_policy, updated_by)


def set_role_mobility_mode(role_key: str, mobility_policy: str, updated_by: int | None = None) -> None:
    attendance_repo.set_role_mobility_policy(role_key, mobility_policy, updated_by)


# ------------------------------------------------- filial talab/tashrif --


def set_branch_visit_requirement(
    employee_id: int, req_date: str, branch: str, min_stay_minutes: int, created_by: int | None = None
) -> bool:
    """``min_stay_minutes`` har doim ANIQ kiritiladi -- global 30
    kodda hech qachon hardcode qilinmaydi (qarang 12-bo'lim). Nomusbat
    qiymat rad etiladi."""
    if min_stay_minutes <= 0:
        return False
    attendance_repo.set_branch_visit_requirement(employee_id, req_date, branch, min_stay_minutes, created_by)
    return True


def get_branch_visit_requirements(employee_id: int, req_date: str) -> list[dict]:
    return attendance_repo.get_branch_visit_requirements_for_date(employee_id, req_date)


def remove_branch_visit_requirement(employee_id: int, req_date: str, branch: str, removed_by: int | None = None) -> bool:
    """FAQAT aynan shu employee_id+req_date+branch yozuviga ishlaydi.
    ``True`` -- topilib o'chirildi (audit bilan birga). ``False`` --
    bunday requirement umuman yo'q edi."""
    return attendance_repo.remove_branch_visit_requirement(employee_id, req_date, branch, removed_by)


def record_branch_visit_event(
    employee_id: int, branch: str, event_type: str, event_time: str, source: str, raw_reference: str | None = None
) -> int | None:
    """Provider-independent -- Face ID yoki boshqa manba keyinchalik
    xuddi shu funksiyani chaqiradi. Noma'lum ``event_type`` uchun
    yozuv qilinmaydi (``None``)."""
    if event_type not in (VISIT_ENTER, VISIT_EXIT):
        return None
    return attendance_repo.record_branch_visit_event(employee_id, branch, event_type, event_time, source, raw_reference)


def _pair_enter_exit_intervals(events: list[dict]) -> tuple[list[tuple[datetime, datetime]], bool]:
    """Ketma-ket holat-mashinasi: ochiq ``enter`` paytida yana ``enter``
    kelsa e'tiborsiz qoldiriladi (allaqachon ichkarida), ochiq
    ``enter``siz ``exit`` kelsa e'tiborsiz qoldiriladi (mos kelmagan
    shovqin). Qaytaradi: (yopiq intervallar, oxirida yopilmagan
    ``enter`` bormi)."""
    sorted_events = sorted(events, key=lambda e: e["event_time"])
    intervals: list[tuple[datetime, datetime]] = []
    open_enter: datetime | None = None

    for event in sorted_events:
        try:
            timestamp = datetime.fromisoformat(event["event_time"])
        except ValueError:
            continue

        if event["event_type"] == VISIT_ENTER:
            if open_enter is None:
                open_enter = timestamp
        elif event["event_type"] == VISIT_EXIT and open_enter is not None:
            if timestamp > open_enter:
                intervals.append((open_enter, timestamp))
            open_enter = None

    return intervals, open_enter is not None


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Bir-birini qoplaydigan intervallarni birlashtiradi -- bir
    daqiqa ikki marta sanalmasin (qarang 14-bo'lim)."""
    if not intervals:
        return []

    ordered = sorted(intervals, key=lambda interval: interval[0])
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def get_branch_stay_minutes(employee_id: int, branch: str, window_start_iso: str, window_end_iso: str) -> dict:
    """``[window_start_iso, window_end_iso)`` oralig'ida shu filialda
    o'tkazilgan umumiy daqiqa. Yopilmagan ``enter`` (exit yo'q) bo'lsa
    ``status="incomplete"``, ``minutes=None`` -- FAILED deb uydirilmaydi.
    Hech qanday tashrif bo'lmasa (yoki barchasi to'liq/mos kelmagan
    shovqin) haqiqiy ``0`` daqiqa qaytariladi -- bu ham "complete"
    natija (xodim haqiqatan bormagan)."""
    events = attendance_repo.list_branch_visit_events(employee_id, branch, window_start_iso, window_end_iso)
    intervals, unclosed = _pair_enter_exit_intervals(events)
    if unclosed:
        return {"status": "incomplete", "minutes": None}

    merged = _merge_intervals(intervals)
    total_minutes = sum((end - start).total_seconds() for start, end in merged) / 60.0
    return {"status": "complete", "minutes": total_minutes}


def _mobility_window_for_logical_date(employee_id: int, req_date: str) -> tuple[str, str]:
    """Kunduzgi/strukturasiz kun uchun oddiy kalendar kuni. Agar shu
    sanada tun smenasi bo'lsa, oyna keyingi kalendar kunini ham qamrab
    oladi -- calendar midnight sabab bitta tashrif ikki kunga
    bo'linib ketmasin (qarang 15-bo'lim)."""
    shift = attendance_repo.get_shift_for_date(employee_id, req_date)
    day = date.fromisoformat(req_date)
    end = day + timedelta(days=2 if _is_overnight_shift(shift) else 1)
    return day.isoformat(), end.isoformat()


def get_daily_branch_compliance(employee_id: int, req_date: str) -> list[dict]:
    """Kunlik filial talab-bajarilishi ro'yxati. Talab UMUMAN
    belgilanmagan bo'lsa BO'SH ro'yxat qaytadi -- bu avtomatik PASS
    degani EMAS, chaqiruvchi "talab yo'q" holatini o'zi alohida
    talqin qilishi kerak."""
    requirements = attendance_repo.get_branch_visit_requirements_for_date(employee_id, req_date)
    if not requirements:
        return []

    window_start, window_end = _mobility_window_for_logical_date(employee_id, req_date)

    results = []
    for requirement in requirements:
        stay = get_branch_stay_minutes(employee_id, requirement["branch"], window_start, window_end)
        met = None if stay["status"] == "incomplete" else stay["minutes"] >= requirement["min_stay_minutes"]
        results.append(
            {
                "branch": requirement["branch"],
                "required_minutes": requirement["min_stay_minutes"],
                "actual_minutes": stay["minutes"],
                "status": stay["status"],
                "met": met,
            }
        )
    return results
