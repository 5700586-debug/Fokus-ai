"""Haftalik 1:1 suhbat (rahbar <-> xodim) CORE V1 — yagona kanonik
yozish/o'qish yo'li. Telegram UI, bildirishnoma, scheduler, ball/bonus/
minus va har qanday psixologik baholash bu qatlamda ATAYLAB YO'Q.

Xodim mavjud kanonik manba orqali aniqlanadi (``employees.get_profile``
+ ``status == approved``) — parallel xodim modeli yaratilmaydi.
"""

from datetime import date, timedelta

import company_time
import employees
from repositories import one_on_one as one_on_one_repo

OUTCOME_OK = "ok"
OUTCOME_DIFFICULTY = "difficulty"
OUTCOME_SUGGESTION = "suggestion"
OUTCOME_SERIOUS_ISSUE = "serious_issue"
OUTCOME_OTHER = "other"

# Faqat shu beshta natija — erkin matn natija sifatida qabul qilinmaydi
# (qisqa izoh ``summary``ga yoziladi).
KNOWN_OUTCOMES = (
    OUTCOME_OK,
    OUTCOME_DIFFICULTY,
    OUTCOME_SUGGESTION,
    OUTCOME_SERIOUS_ISSUE,
    OUTCOME_OTHER,
)

FOLLOWUP_OPEN = "open"
FOLLOWUP_RESOLVED = "resolved"


def week_start_for(meeting_date: str | date) -> str | None:
    """Hafta kalitining YAGONA kanonik qoidasi: suhbat sanasi tushgan
    haftaning dushanba sanasi. Takroriylik tekshiruvi ham, o'qish ham
    faqat shu kalit orqali ketadi."""
    if isinstance(meeting_date, date):
        parsed = meeting_date
    else:
        try:
            parsed = date.fromisoformat(meeting_date)
        except (TypeError, ValueError):
            return None

    return (parsed - timedelta(days=parsed.weekday())).isoformat()


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def create_one_on_one(
    employee_id: int, manager_id: int, outcome: str, meeting_date: str | date | None = None,
    summary: str | None = None, followup_text: str | None = None,
) -> int | None:
    """Bitta xodimga bitta haftada bitta suhbat yozuvi. ``None`` —
    yozuv YARATILMADI: xodim topilmadi/tasdiqlanmagan/ishdan chiqarilgan,
    natija turi noma'lum, sana noto'g'ri, yoki shu hafta uchun yozuv
    allaqachon bor."""
    if outcome not in KNOWN_OUTCOMES:
        return None

    profile = employees.get_profile(employee_id)
    if profile is None or profile.get("status") != employees.STATUS_APPROVED:
        return None

    meeting = meeting_date if meeting_date is not None else company_time.today()
    week_start = week_start_for(meeting)
    if week_start is None:
        return None
    meeting_iso = meeting.isoformat() if isinstance(meeting, date) else meeting

    if one_on_one_repo.get_for_week(employee_id, week_start) is not None:
        return None

    followup = _clean_text(followup_text)
    return one_on_one_repo.create(
        employee_id, manager_id, profile.get("branch"), week_start, meeting_iso, outcome,
        _clean_text(summary), followup, FOLLOWUP_OPEN if followup else None,
    )


def get_one_on_one(record_id: int) -> dict | None:
    return one_on_one_repo.get(record_id)


def get_one_on_one_for_week(employee_id: int, meeting_date: str | date) -> dict | None:
    week_start = week_start_for(meeting_date)
    if week_start is None:
        return None
    return one_on_one_repo.get_for_week(employee_id, week_start)


def list_one_on_ones(employee_id: int) -> list[dict]:
    return one_on_one_repo.list_for_employee(employee_id)


def get_open_followup(employee_id: int) -> dict | None:
    """Keyingi suhbatga o'tishi kerak bo'lgan hal qilinmagan masala
    (eng so'nggisi) — yo'q bo'lsa ``None``."""
    return one_on_one_repo.get_open_followup(employee_id, FOLLOWUP_OPEN)


def resolve_followup(record_id: int, resolved_by: int) -> bool:
    """``True`` — masalani aynan shu chaqiruv yopdi. ``False`` — yozuv
    yo'q, masala umuman yo'q edi yoki allaqachon yopilgan."""
    return one_on_one_repo.resolve_followup(
        record_id, FOLLOWUP_OPEN, FOLLOWUP_RESOLVED, resolved_by
    )
