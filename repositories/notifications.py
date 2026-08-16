"""Yuborilgan xabarlar jurnali — dublikat scheduled xabarlarni oldini olish."""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def try_mark_sent(job_key: str, target: str, status: str = "sent") -> bool:
    """``job_key``+``target`` juftligi allaqachon logda bo'lsa ``False``
    qaytaradi — chaqiruvchi xabarni yubormasligi kerak (idempotency).
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO notification_log (job_key, target, status, sent_at) "
            "VALUES (?, ?, ?, ?)",
            (job_key, target, status, _now()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def was_sent(job_key: str, target: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM notification_log WHERE job_key = ? AND target = ?",
            (job_key, target),
        ).fetchone()
    finally:
        conn.close()

    return row is not None


def try_reserve(job_key: str, target: str) -> bool:
    """``try_mark_sent``ga o'xshash ATOMIK ``INSERT OR IGNORE``, lekin
    ``status='pending'`` bilan — chaqiruvchi hali xabarni yubormagan,
    faqat "men bu ishni bajarmoqchiman" deb band qilmoqda. ``True``
    qaytsa, chaqiruvchi navbatdagi qimmat ishni (AI, tashqi API, rasm
    generatsiyasi, yuborish) xavfsiz bajarishi mumkin — boshqa parallel
    chaqiruv ``False`` oladi va hech narsa qilmasligi kerak.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO notification_log (job_key, target, status, sent_at) "
            "VALUES (?, ?, 'pending', ?)",
            (job_key, target, _now()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def mark_status(job_key: str, target: str, status: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE notification_log SET status = ?, sent_at = ? WHERE job_key = ? AND target = ?",
            (status, _now(), job_key, target),
        )
        conn.commit()
    finally:
        conn.close()


def release_reservation(job_key: str, target: str) -> None:
    """``try_reserve``da band qilingan, lekin yuborish xato bilan
    tugagan yozuvni o'chiradi — shu orqali keyingi urinish (masalan
    keyingi scheduler tick'i) qayta ``try_reserve`` qila oladi.
    Faqat ``pending`` holatidagi yozuv o'chiriladi — allaqachon
    ``sent`` deb belgilangan yozuvga tegilmaydi (xavfsizlik uchun).
    """
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM notification_log WHERE job_key = ? AND target = ? AND status = 'pending'",
            (job_key, target),
        )
        conn.commit()
    finally:
        conn.close()
