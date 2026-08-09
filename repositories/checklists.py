"""Lavozim checklist/nizom matnlari va xodim o'quv progressi."""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_checklist(role_key: str | None, title: str, content: str, created_by: int) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO checklists (role_key, title, content, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (role_key, title, content, created_by, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_active_checklists(role_key: str | None = None) -> list[dict]:
    conn = get_connection()
    try:
        if role_key is None:
            rows = conn.execute(
                "SELECT * FROM checklists WHERE is_active = 1 ORDER BY created_at"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM checklists WHERE is_active = 1 AND (role_key = ? OR role_key IS NULL) "
                "ORDER BY created_at",
                (role_key,),
            ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def assign_checklist(user_id: int, checklist_id: int) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO learning_progress (user_id, checklist_id, status, assigned_at) "
            "VALUES (?, ?, 'assigned', ?)",
            (user_id, checklist_id, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def mark_understood(progress_id: int, understanding_note: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE learning_progress SET status = 'understood', understanding_note = ?, "
            "completed_at = ? WHERE id = ?",
            (understanding_note, _now(), progress_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_progress_for_user(user_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM learning_progress WHERE user_id = ? ORDER BY assigned_at",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]
