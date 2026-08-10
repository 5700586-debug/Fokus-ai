"""60 kunlik kalibratsiyada yig'ilgan RoleBaseline va yangi xodim
adaptatsiya profillari.
"""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_role_baseline(role_key: str, dimension: str, description: str, source_note: str | None = None) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO role_baselines (role_key, dimension, description, source_note, established_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (role_key, dimension, description, source_note, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_role_baselines(role_key: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM role_baselines WHERE role_key = ? ORDER BY established_at",
            (role_key,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def record_adaptation_rating(
    user_id: int,
    role_key: str,
    start_date: str,
    day_number: int,
    dimension: str,
    rating: str,
    note: str | None = None,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO employee_adaptation_profiles "
            "(user_id, role_key, start_date, day_number, dimension, rating, note, evaluated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, role_key, start_date, day_number, dimension, rating, note, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_adaptation_profile(user_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM employee_adaptation_profiles WHERE user_id = ? ORDER BY evaluated_at",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


# ------------------------------------------------------- calibration_sessions --


def create_session(user_id: int, role_key: str, start_date: str) -> dict:
    """``user_id`` uchun sessiya allaqachon mavjud bo'lsa, yangisini
    yaratmasdan mavjudini qaytaradi (idempotent — ``cross_check_repo.
    get_or_create_session`` bilan bir xil uslub).
    """
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO calibration_sessions "
            "(user_id, role_key, start_date, status, created_at) VALUES (?, ?, ?, 'active', ?)",
            (user_id, role_key, start_date, _now()),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM calibration_sessions WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()

    return dict(row)


def get_session(user_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM calibration_sessions WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


# ------------------------------------------------------ calibration_questions --


def record_question(
    session_id: int, user_id: int, role_key: str, question_date: str, dimension: str,
    question_text: str, is_cross_check: bool = False, parent_question_id: int | None = None,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO calibration_questions "
            "(session_id, user_id, role_key, question_date, dimension, question_text, "
            "is_cross_check, parent_question_id, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id, user_id, role_key, question_date, dimension, question_text,
                int(is_cross_check), parent_question_id, _now(),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_active_question(user_id: int) -> dict | None:
    """Javob kutayotgan (``answer_text IS NULL``) eng so'nggi savol."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM calibration_questions WHERE user_id = ? AND answer_text IS NULL "
            "ORDER BY sent_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def get_question(question_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM calibration_questions WHERE id = ?", (question_id,)
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def get_questions_for_date(user_id: int, question_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM calibration_questions WHERE user_id = ? AND question_date = ? "
            "ORDER BY sent_at",
            (user_id, question_date),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def record_answer(question_id: int, answer_text: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE calibration_questions SET answer_text = ?, answered_at = ? WHERE id = ?",
            (answer_text, _now(), question_id),
        )
        conn.commit()
    finally:
        conn.close()


def increment_follow_up(question_id: int) -> int:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE calibration_questions SET follow_up_count = follow_up_count + 1 WHERE id = ?",
            (question_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT follow_up_count FROM calibration_questions WHERE id = ?", (question_id,)
        ).fetchone()
    finally:
        conn.close()

    return row["follow_up_count"]
