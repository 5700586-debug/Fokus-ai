"""Haftalik 1:1 suhbat: xom SQL qatlami (qarang
``schema/one_on_one.py``). Validatsiya va xodim holati tekshiruvi
``services/one_on_one.py``da — bu yerda faqat yozish/o'qish.
"""

from datetime import datetime, timezone

from db import IntegrityError, get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(
    employee_id: int, manager_id: int, branch: str | None, week_start: str, meeting_date: str,
    outcome: str, summary: str | None, followup_text: str | None, followup_status: str | None,
) -> int | None:
    """``None`` — shu xodim/hafta uchun yozuv ALLAQACHON bor
    (``UNIQUE(employee_id, week_start)``). Servisdagi oldindan
    tekshiruv poyga (race) holatini ushlay olmaydi, DB cheklovi esa
    ushlaydi — shuning uchun xato shu yerda ``None``ga aylantiriladi."""
    now = _now()
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO employee_one_on_ones "
            "(employee_id, manager_id, branch, week_start, meeting_date, outcome, summary, "
            "followup_text, followup_status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                employee_id, manager_id, branch, week_start, meeting_date, outcome, summary,
                followup_text, followup_status, now, now,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    except IntegrityError:
        return None
    finally:
        conn.close()


def get(record_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM employee_one_on_ones WHERE id = ?", (record_id,)
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def get_for_week(employee_id: int, week_start: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM employee_one_on_ones WHERE employee_id = ? AND week_start = ?",
            (employee_id, week_start),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def list_for_employee(employee_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM employee_one_on_ones WHERE employee_id = ? ORDER BY week_start, id",
            (employee_id,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_open_followup(employee_id: int, followup_status: str) -> dict | None:
    """Xodimning eng so'nggi HAL QILINMAGAN masalasi — keyingi suhbat
    shu yerdan boshlanadi."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM employee_one_on_ones WHERE employee_id = ? AND followup_status = ? "
            "ORDER BY week_start DESC, id DESC LIMIT 1",
            (employee_id, followup_status),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def resolve_followup(
    record_id: int, expected_status: str, new_status: str, resolved_by: int
) -> bool:
    """FAQAT masala hali ``expected_status`` (``open``) bo'lsa yopadi —
    atomik ``UPDATE ... WHERE followup_status = ?`` (mavjud
    ``decide_schedule_change_request`` naqshi), ya'ni takroriy chaqiruv
    kim/qachon yopganini qayta yozmaydi."""
    now = _now()
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE employee_one_on_ones SET followup_status = ?, followup_resolved_by = ?, "
            "followup_resolved_at = ?, updated_at = ? WHERE id = ? AND followup_status = ?",
            (new_status, resolved_by, now, now, record_id, expected_status),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
