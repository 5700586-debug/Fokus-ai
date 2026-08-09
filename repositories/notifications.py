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
