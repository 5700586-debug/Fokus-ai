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


def list_events_for_range(employee_id: int, start_date: str, end_date_exclusive: str) -> list[dict]:
    """``[start_date, end_date_exclusive)`` oralig'idagi barcha eventlar —
    ``event_time`` doim ``YYYY-MM-DD``dan boshlanadigan ISO satr sifatida
    saqlanadi (qarang ``record_event``), shuning uchun oddiy satr
    solishtiruvi sana chegarasini to'g'ri ushlaydi."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM attendance_events WHERE employee_id = ? AND event_time >= ? AND event_time < ? "
            "ORDER BY event_time",
            (employee_id, start_date, end_date_exclusive),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


# ------------------------------------------------- reja smena jadvali --

_SHIFT_UPSERT_COLUMNS = (
    "employee_id", "shift_date", "planned_start", "planned_end", "status", "source", "created_by", "created_at"
)
_SHIFT_UPDATE_CLAUSE = ", ".join(f"{col} = excluded.{col}" for col in _SHIFT_UPSERT_COLUMNS if col not in ("employee_id", "shift_date"))


def set_work_shift(
    employee_id: int, shift_date: str, planned_start: str, planned_end: str, source: str, created_by: int | None = None
) -> None:
    """Bitta xodim/sana uchun ATOMIK UPSERT (``ON CONFLICT`` -- SQLite
    3.24+ va Postgres ikkalasida ham tarjimasiz ishlaydigan naqsh) --
    parallel yoki takroriy chaqiruv dublikat qator yaratmaydi, oxirgi
    chaqiruvning qiymati deterministik saqlanadi. Vaqt/interval
    validatsiyasi (masalan ``start == end``) BU YERDA emas, chaqiruvchi
    (``services/attendance.py``) tomonida."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO employee_scheduled_shifts "
            "(employee_id, shift_date, planned_start, planned_end, status, source, created_by, created_at) "
            "VALUES (?, ?, ?, ?, 'work', ?, ?, ?) "
            f"ON CONFLICT(employee_id, shift_date) DO UPDATE SET {_SHIFT_UPDATE_CLAUSE}",
            (employee_id, shift_date, planned_start, planned_end, source, created_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def set_day_off(employee_id: int, shift_date: str, source: str, created_by: int | None = None) -> None:
    """``set_work_shift``dagi bilan bir xil atomik UPSERT naqshi --
    ``planned_start``/``planned_end`` doim NULL (dam olish kuni)."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO employee_scheduled_shifts "
            "(employee_id, shift_date, planned_start, planned_end, status, source, created_by, created_at) "
            "VALUES (?, ?, NULL, NULL, 'off', ?, ?, ?) "
            f"ON CONFLICT(employee_id, shift_date) DO UPDATE SET {_SHIFT_UPDATE_CLAUSE}",
            (employee_id, shift_date, source, created_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_schedule_for_range(employee_id: int, start_date: str, end_date_exclusive: str) -> list[dict]:
    """``[start_date, end_date_exclusive)`` oralig'idagi reja smenalari
    -- shu oraliqda yozuvi yo'q sana ro'yxatda umuman ko'rinmaydi
    (chaqiruvchi buni UNKNOWN deb talqin qilishi kerak, OFF emas)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM employee_scheduled_shifts WHERE employee_id = ? AND shift_date >= ? AND shift_date < ? "
            "ORDER BY shift_date",
            (employee_id, start_date, end_date_exclusive),
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
