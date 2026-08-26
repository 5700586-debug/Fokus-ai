"""Davomat: xom SQL qatlami. Bugun hech qanday real event provider
ulanmagan — bu funksiyalar keyingi bosqichda ``AttendanceEventProvider``
implementatsiyalari (Face ID, webhook, qo'lda kiritish) tomonidan
chaqiriladi.
"""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_event(employee_id: int, event_type: str, event_time: str, source: str, raw_reference: str | None = None) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO attendance_events "
            "(employee_id, event_type, event_time, source, raw_reference, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (employee_id, event_type, event_time, source, raw_reference, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_events_for_date(employee_id: int, date_str: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM attendance_events WHERE employee_id = ? AND event_time LIKE ? "
            "ORDER BY event_time",
            (employee_id, f"{date_str}%"),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def set_reason(employee_id: int, event_date: str, reason_status: str, note: str | None = None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO attendance_reasons (employee_id, event_date, reason_status, note, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(employee_id, event_date) DO UPDATE SET "
            "reason_status = excluded.reason_status, note = excluded.note",
            (employee_id, event_date, reason_status, note, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def confirm_reason(employee_id: int, event_date: str, confirmed_by: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE attendance_reasons SET confirmed_by = ?, confirmed_at = ? "
            "WHERE employee_id = ? AND event_date = ?",
            (confirmed_by, _now(), employee_id, event_date),
        )
        conn.commit()
    finally:
        conn.close()


def get_reason(employee_id: int, event_date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM attendance_reasons WHERE employee_id = ? AND event_date = ?",
            (employee_id, event_date),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def decide_manager_permission(
    employee_id: int, event_date: str, expected_status: str, new_status: str, confirmed_by: int
) -> bool:
    """FAQAT ``reason_status`` hali ``expected_status`` (odatda
    ``manager_permission_pending``) bo'lsa yangilaydi — atomik
    ``UPDATE ... WHERE reason_status = ?`` orqali, ikkinchi/parallel
    "Ha"/"Yo'q" bosilishi birinchi qarorni bosib o'tmasligi uchun
    (qarang ``employees.approve_profile``dagi bir xil naqsh)."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE attendance_reasons SET reason_status = ?, confirmed_by = ?, confirmed_at = ? "
            "WHERE employee_id = ? AND event_date = ? AND reason_status = ?",
            (new_status, confirmed_by, _now(), employee_id, event_date, expected_status),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
