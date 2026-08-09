"""Ta'minotchi/haydovchi javoblarini mustaqil taqqoslash sessiyalari."""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_or_create_session(session_date: str, employee_a_id: int, employee_b_id: int) -> dict:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO cross_check_sessions "
            "(session_date, employee_a_id, employee_b_id, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (session_date, employee_a_id, employee_b_id, _now()),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM cross_check_sessions "
            "WHERE session_date = ? AND employee_a_id = ? AND employee_b_id = ?",
            (session_date, employee_a_id, employee_b_id),
        ).fetchone()
    finally:
        conn.close()

    return dict(row)


def record_answer(session_id: int, employee_id: int, question: str, answer: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO cross_check_answers (session_id, employee_id, question, answer, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, employee_id, question, answer, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_answers(session_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM cross_check_answers WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def set_status(session_id: int, status: str, summary: str | None = None) -> None:
    conn = get_connection()
    try:
        resolved_at = _now() if status == "resolved" else None
        conn.execute(
            "UPDATE cross_check_sessions SET status = ?, summary = ?, resolved_at = COALESCE(?, resolved_at) "
            "WHERE id = ?",
            (status, summary, resolved_at, session_id),
        )
        conn.commit()
    finally:
        conn.close()
