"""Xodimga biriktirilgan doimiy vazifalar/hududlar: xom SQL qatlami.

Bitta vazifa (masalan "Ombor") bir yoki bir nechta xodimga
biriktirilishi mumkin — ``task_assignments`` ko'p-ko'pga jadval,
``UNIQUE(task_id, employee_id)`` bilan ikki marta bir xil
biriktirishning oldini oladi (``INSERT OR IGNORE`` bilan xavfsiz)."""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_task(title: str, created_by: int) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO tasks (title, created_by, created_at) VALUES (?, ?, ?)",
            (title, created_by, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_active_tasks() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE is_active = 1 ORDER BY title"
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_task_by_title(title: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE title = ?", (title,)).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def assign_task(task_id: int, employee_id: int, assigned_by: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO task_assignments (task_id, employee_id, assigned_by, assigned_at, is_active) "
            "VALUES (?, ?, ?, ?, 1) "
            "ON CONFLICT(task_id, employee_id) DO UPDATE SET is_active = 1, assigned_by = excluded.assigned_by, "
            "assigned_at = excluded.assigned_at",
            (task_id, employee_id, assigned_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def unassign_task(task_id: int, employee_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE task_assignments SET is_active = 0 WHERE task_id = ? AND employee_id = ?",
            (task_id, employee_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_tasks_for_employee(employee_id: int) -> list[dict]:
    """Xodimga hozir biriktirilgan (aktiv) vazifalar — xodim kartasida
    ko'rsatish uchun."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT t.id, t.title FROM task_assignments ta "
            "JOIN tasks t ON t.id = ta.task_id "
            "WHERE ta.employee_id = ? AND ta.is_active = 1 AND t.is_active = 1 "
            "ORDER BY t.title",
            (employee_id,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]
