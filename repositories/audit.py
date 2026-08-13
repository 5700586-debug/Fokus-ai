"""``security_audit_log`` uchun xom SQL qatlami. Biznes/chaqiruv qulayligi
``services/audit.py``da.
"""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_event(
    event_type: str,
    request_id: str,
    actor_id: int | None = None,
    actor_role: str | None = None,
    chat_id: int | None = None,
    target_id: int | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    reason: str | None = None,
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO security_audit_log "
            "(event_type, actor_id, actor_role, chat_id, target_id, old_value, "
            "new_value, reason, request_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_type,
                actor_id,
                actor_role,
                chat_id,
                target_id,
                old_value,
                new_value,
                reason,
                request_id,
                _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_events(limit: int = 100) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM security_audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def list_events_for_actor(actor_id: int, limit: int = 100) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM security_audit_log WHERE actor_id = ? ORDER BY id DESC LIMIT ?",
            (actor_id, limit),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]
