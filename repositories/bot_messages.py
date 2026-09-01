"""``bot_workflow_messages`` uchun xom SQL qatlami — faqat chatni
tozalash uchun vaqtinchalik kuzatuv, biznes ma'lumot emas. Qulaylik
qatlami ``services/chat_cleanup.py``da.
"""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_message(workflow: str, workflow_key: str, chat_id: int, message_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO bot_workflow_messages "
            "(workflow, workflow_key, chat_id, message_id, sent_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (workflow, workflow_key, chat_id, message_id, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def pop_messages(workflow: str, workflow_key: str) -> list[dict]:
    """Shu workflow/kalitga tegishli barcha kuzatilgan xabarlarni
    qaytaradi va jurnaldan o'chiradi (bir martalik tozalash — qayta
    chaqirilsa bo'sh ro'yxat qaytadi).
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT chat_id, message_id FROM bot_workflow_messages "
            "WHERE workflow = ? AND workflow_key = ?",
            (workflow, workflow_key),
        ).fetchall()
        conn.execute(
            "DELETE FROM bot_workflow_messages WHERE workflow = ? AND workflow_key = ?",
            (workflow, workflow_key),
        )
        conn.commit()
    finally:
        conn.close()

    return [dict(row) for row in rows]
