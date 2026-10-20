"""Nazoratchi "kun yopilmadi" muddati: ish kuni (work_date) va aniq sana+vaqtli muddat (deadline_at), kompaniya vaqt zonasida.

HH:MM satrlari bevosita solishtirilmaydi. Ish kuni chegarasi (``bos.work_day_start``) standart ``00:00`` — ya'ni ish kuni
kalendar kun (avvalgi xulq). Chegaradan KICHIK muddat (masalan chegara 08:00, muddat 01:30) ish kuniga ERTASI kalendar
kunda tushadi. Yangi muddat/chegara faqat muddat vaqtidan OLDIN kuchga kirgan bo'lsagina qo'llanadi (orqaga minus yo'q)."""

from datetime import date, datetime, time, timedelta, timezone


def parse_hhmm(value: str) -> time:
    hour, minute = value.strip().split(":")
    return time(int(hour), int(minute))


def work_date_at(now: datetime, boundary: time) -> date:
    return now.date() if now.timetz().replace(tzinfo=None) >= boundary else now.date() - timedelta(days=1)


def deadline_at(work_date: date, deadline: time, boundary: time, tz) -> datetime:
    base = work_date if deadline >= boundary else work_date + timedelta(days=1)
    return datetime(base.year, base.month, base.day, deadline.hour, deadline.minute, tzinfo=tz)


def _parse_stamp(stamp: str) -> datetime:
    parsed = datetime.fromisoformat(stamp)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def due_work_date(now: datetime, deadline_text: str, boundary_text: str, policy_effective_at: str | None):
    """Qaytadi ``(work_date, deadline_at)`` — muddat o'tgan va sozlama muddatdan oldin kuchda bo'lgan bo'lsa; aks holda ``None``.
    Noto'g'ri HH:MM bo'lsa ``ValueError``."""
    boundary = parse_hhmm(boundary_text)
    deadline = parse_hhmm(deadline_text)
    work_date = work_date_at(now, boundary)
    due_at = deadline_at(work_date, deadline, boundary, now.tzinfo)
    if now < due_at:
        return None
    if policy_effective_at and _parse_stamp(policy_effective_at) > due_at:
        return None  # sozlama muddatdan keyin o'zgargan: eski kunga orqaga qo'llanmaydi
    return work_date, due_at
