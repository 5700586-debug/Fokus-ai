"""Nomzod ma'lumotlarini saqlash muddati (retention) va o'chirish.

Standart muddat ``config.RECRUITING_RETENTION_DAYS`` (standart 90 kun)
— har bir ariza yaratilganda ``retention_expires_at`` shu muddatga
qarab hisoblanadi (qarang ``recruiting_bot.py``). Bu modul muddati
o'tgan arizalarni topish va (admin so'rovi bo'yicha yoki avtomatik)
butunlay o'chirish uchun."""

from datetime import datetime, timedelta, timezone

from config import RECRUITING_RETENTION_DAYS
from repositories import recruiting as recruiting_repo


def compute_retention_expiry(days: int | None = None) -> str:
    days = days if days is not None else RECRUITING_RETENTION_DAYS
    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    return expires_at.isoformat()


def purge_expired_applications() -> int:
    """Saqlash muddati o'tgan barcha arizalarni (javoblar, tahlil,
    ariza qatori bilan birga) o'chiradi. O'chirilgan arizalar sonini
    qaytaradi."""
    expired = recruiting_repo.list_applications_past_retention()
    for application in expired:
        recruiting_repo.purge_application(application["id"])
    return len(expired)


def delete_application_now(application_id: int) -> bool:
    """Admin/Founder so'rovi bo'yicha — muddatidan qat'i nazar, bitta
    nomzod ma'lumotini darhol o'chiradi."""
    application = recruiting_repo.get_application(application_id)
    if application is None:
        return False
    recruiting_repo.purge_application(application_id)
    return True
