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
