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


def replace_menu_messages(
    workflow: str, keys: tuple[str, str], target_key: str, chat_id: int,
    new_ids: list[int], *, protected_id: int | None = None, protect_all: bool = False,
) -> list[dict]:
    """Atomically exchange only this chat's menu tracking; preserve keyboard owners in place.

    RETURNING avoids a separate SELECT. The insert's CTE avoids the adapter's
    lastval() lookup: this caller never needs tracking-row primary keys.
    """
    conn = get_connection()
    try:
        rows = []
        if not protect_all:
            sql = (
                "DELETE FROM bot_workflow_messages WHERE workflow = ? "
                "AND workflow_key IN (?, ?) AND chat_id = ?"
            )
            params = (workflow, *keys, chat_id)
            if protected_id is not None:
                sql += " AND message_id != ?"
                params += (protected_id,)
            rows = conn.execute(sql + " RETURNING chat_id, message_id", params).fetchall()
        ids = list(dict.fromkeys(new_ids))
        if ids:
            values = ", ".join("(?, ?, ?, ?, ?)" for _ in ids)
            params = tuple(value for mid in ids for value in (workflow, target_key, chat_id, mid, _now()))
            conn.execute(
                "WITH tracked(workflow, workflow_key, chat_id, message_id, sent_at) AS (VALUES "
                + values + ") INSERT INTO bot_workflow_messages "
                "(workflow, workflow_key, chat_id, message_id, sent_at) "
                "SELECT workflow, workflow_key, chat_id, message_id, sent_at FROM tracked", params,
            )
        conn.commit()
        return [dict(row) for row in rows]
    finally:
        conn.close()
