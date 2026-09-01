"""Nizom o'qish auditi CORE V1 — xodim korxona nizomini band-band
o'qib, "o'qidim" va "tushundim" bilan tasdiqlaydi.

Nizomning yagona manbasi — ``company_rules`` (``repositories.discipline``).
Eski ``services/learning.py`` checklist tizimiga tegilmaydi.

Telegram UI, bildirishnoma, scheduler va tasdiqlash/approval bu
qatlamda ATAYLAB YO'Q.
"""

import company_time
from repositories import discipline as discipline_repo
from repositories import rule_learning as rule_learning_repo

DAILY_LIMIT = 5


def _company_date() -> str:
    return company_time.today().isoformat()


def enroll(employee_id: int) -> bool:
    """``True`` — xodim aynan shu chaqiruvda audit ro'yxatiga qo'shildi."""
    return rule_learning_repo.ensure_enrollment(employee_id)


def get_enrollment(employee_id: int) -> dict | None:
    return rule_learning_repo.get_enrollment(employee_id)


def _remaining_active_rules(employee_id: int) -> list[dict]:
    started = set(rule_learning_repo.list_started_rule_numbers(employee_id))
    return [
        rule
        for rule in discipline_repo.list_active_rules()
        if rule["rule_number"] not in started
    ]


def _maybe_finish(employee_id: int) -> bool:
    """Aktiv nizom umuman bo'lmasa yakunlamaydi — bu "hammasini o'qib
    bo'ldi" degani emas, shunchaki nizom hali kiritilmagan."""
    if not discipline_repo.list_active_rules():
        return False
    if rule_learning_repo.get_pending_progress(employee_id) is not None:
        return False
    if _remaining_active_rules(employee_id):
        return False
    return rule_learning_repo.finish_enrollment(employee_id)


def get_current_rule(employee_id: int) -> dict | None:
    """Xodimga hozir ko'rsatilishi kerak bo'lgan progress qatori.

    ``None`` — ro'yxatga qo'shilmagan, audit yakunlangan, aktiv nizom
    yo'q yoki bugungi limit tugagan.
    """
    enrollment = rule_learning_repo.get_enrollment(employee_id)
    if enrollment is None or enrollment.get("finished_at"):
        return None

    # Yopilmagan band har doim birinchi: nizom keyin nofaol qilinsa ham
    # xodim saqlangan snapshot bo'yicha davom etadi.
    pending = rule_learning_repo.get_pending_progress(employee_id)
    if pending is not None:
        return pending

    remaining = _remaining_active_rules(employee_id)
    if not remaining:
        _maybe_finish(employee_id)
        return None

    if rule_learning_repo.count_completed_for_date(employee_id, _company_date()) >= DAILY_LIMIT:
        return None

    rule = min(remaining, key=lambda item: item["rule_number"])
    return rule_learning_repo.ensure_progress(
        employee_id, rule["rule_number"], rule["title"], rule["content"]
    )


def mark_sent(progress_id: int) -> bool:
    return rule_learning_repo.mark_sent(progress_id)


def confirm_read(progress_id: int) -> bool:
    return rule_learning_repo.mark_read(progress_id)


def report_not_understood(progress_id: int) -> bool:
    return rule_learning_repo.mark_not_understood(progress_id)


def confirm_understood(employee_id: int, progress_id: int) -> bool:
    """``True`` — band aynan shu chaqiruvda yopildi. Band o'qilmagan
    bo'lsa yoki allaqachon yopilgan bo'lsa ``False``."""
    if not rule_learning_repo.mark_understood(progress_id, _company_date()):
        return False

    _maybe_finish(employee_id)
    return True


def completed_today(employee_id: int) -> int:
    return rule_learning_repo.count_completed_for_date(employee_id, _company_date())


def get_progress(progress_id: int) -> dict | None:
    return rule_learning_repo.get_progress(progress_id)
