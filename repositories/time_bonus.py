"""Vaqt bonusi tarixi: xom SQL qatlami.

``time_bonus_grants`` — ``UNIQUE(employee_id, grant_date)`` bilan bitta
xodim uchun bitta kunda faqat BITTA yozuv bo'lishi kafolatlanadi
(AUTO yoki MANUAL, farqi yo'q) — ``INSERT ... ON CONFLICT DO NOTHING``
orqali ikkinchi (masalan ikki marta bosilgan tugma yoki avtomatik
tizim allaqachon yozgandan keyingi qo'lda urinish) yozuv jimgina rad
etiladi, birinchisini bosib o'tmaydi."""

from datetime import datetime, timezone

from db import get_connection

SOURCE_AUTO = "auto"
SOURCE_MANUAL = "manual"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def grant(employee_id: int, grant_date: str, source: str, confirmed_by: int | None) -> bool:
    """``True`` — shu chaqiruv yozdi (bonus band qildi), ``False`` —
    shu xodim/kun uchun allaqachon yozuv bor edi (AUTO yoki MANUAL,
    farqi yo'q) — hech narsa qayta yozilmadi."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO time_bonus_grants (employee_id, grant_date, source, confirmed_by, confirmed_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(employee_id, grant_date) DO NOTHING",
            (employee_id, grant_date, source, confirmed_by, _now()),
        )
        conn.commit()
        granted = cursor.rowcount > 0
    finally:
        conn.close()

    return granted


def get_for_date(employee_id: int, grant_date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM time_bonus_grants WHERE employee_id = ? AND grant_date = ?",
            (employee_id, grant_date),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None
