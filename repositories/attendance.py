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
    "employee_id", "shift_date", "planned_start", "planned_end", "status", "schedule_mode",
    "source", "created_by", "created_at",
)
_SHIFT_UPDATE_CLAUSE = ", ".join(f"{col} = excluded.{col}" for col in _SHIFT_UPSERT_COLUMNS if col not in ("employee_id", "shift_date"))


def get_shift_for_date(employee_id: int, shift_date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM employee_scheduled_shifts WHERE employee_id = ? AND shift_date = ?",
            (employee_id, shift_date),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def _record_schedule_revision(
    conn, employee_id: int, shift_date: str, existing: dict | None,
    new_status: str, new_planned_start: str | None, new_planned_end: str | None,
    changed_by: int | None, reason: str | None, is_late_change: bool,
) -> None:
    """Har bir yozish/o'zgartirishda ESKI qiymatni (mavjud bo'lsa) audit
    jadvaliga yozadi -- ``employee_scheduled_shifts``ning o'zi doim
    faqat JORIY qiymatni saqlaydi, tarix shu yerda saqlanib qoladi."""
    conn.execute(
        "INSERT INTO employee_schedule_revisions "
        "(employee_id, shift_date, old_status, old_planned_start, old_planned_end, "
        "new_status, new_planned_start, new_planned_end, changed_by, changed_at, reason, is_late_change) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            employee_id, shift_date,
            existing["status"] if existing else None,
            existing["planned_start"] if existing else None,
            existing["planned_end"] if existing else None,
            new_status, new_planned_start, new_planned_end,
            changed_by, _now(), reason, int(is_late_change),
        ),
    )


def set_work_shift(
    employee_id: int, shift_date: str, planned_start: str, planned_end: str, schedule_mode: str, source: str,
    created_by: int | None = None, reason: str | None = None, is_late_change: bool = False,
) -> None:
    """Bitta xodim/sana uchun ATOMIK UPSERT (``ON CONFLICT`` -- SQLite
    3.24+ va Postgres ikkalasida ham tarjimasiz ishlaydigan naqsh) --
    parallel yoki takroriy chaqiruv dublikat qator yaratmaydi, oxirgi
    chaqiruvning qiymati deterministik saqlanadi. Vaqt/interval
    validatsiyasi (masalan ``start == end``) BU YERDA emas, chaqiruvchi
    (``services/attendance.py``) tomonida. Eski qiymat (bo'lsa) yozuv
    o'zgartirilishidan OLDIN audit jadvaliga yoziladi -- bitta
    connection/transaction ichida, atomik."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT status, planned_start, planned_end FROM employee_scheduled_shifts "
            "WHERE employee_id = ? AND shift_date = ?",
            (employee_id, shift_date),
        ).fetchone()
        existing = dict(existing) if existing else None

        _record_schedule_revision(
            conn, employee_id, shift_date, existing, "work", planned_start, planned_end,
            created_by, reason, is_late_change,
        )

        conn.execute(
            "INSERT INTO employee_scheduled_shifts "
            "(employee_id, shift_date, planned_start, planned_end, status, schedule_mode, source, created_by, created_at) "
            "VALUES (?, ?, ?, ?, 'work', ?, ?, ?, ?) "
            f"ON CONFLICT(employee_id, shift_date) DO UPDATE SET {_SHIFT_UPDATE_CLAUSE}",
            (employee_id, shift_date, planned_start, planned_end, schedule_mode, source, created_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def set_day_off(
    employee_id: int, shift_date: str, schedule_mode: str, source: str,
    created_by: int | None = None, reason: str | None = None, is_late_change: bool = False,
) -> None:
    """``set_work_shift``dagi bilan bir xil atomik UPSERT + audit naqshi
    -- ``planned_start``/``planned_end`` doim NULL (dam olish kuni)."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT status, planned_start, planned_end FROM employee_scheduled_shifts "
            "WHERE employee_id = ? AND shift_date = ?",
            (employee_id, shift_date),
        ).fetchone()
        existing = dict(existing) if existing else None

        _record_schedule_revision(
            conn, employee_id, shift_date, existing, "off", None, None, created_by, reason, is_late_change,
        )

        conn.execute(
            "INSERT INTO employee_scheduled_shifts "
            "(employee_id, shift_date, planned_start, planned_end, status, schedule_mode, source, created_by, created_at) "
            "VALUES (?, ?, NULL, NULL, 'off', ?, ?, ?, ?) "
            f"ON CONFLICT(employee_id, shift_date) DO UPDATE SET {_SHIFT_UPDATE_CLAUSE}",
            (employee_id, shift_date, schedule_mode, source, created_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def list_schedule_revisions(employee_id: int, shift_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM employee_schedule_revisions WHERE employee_id = ? AND shift_date = ? ORDER BY id",
            (employee_id, shift_date),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


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


# ---------------------------------------------------- grafik siyosati --


def set_employee_schedule_policy(employee_id: int, schedule_mode: str, updated_by: int | None = None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO employee_schedule_policy (employee_id, schedule_mode, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(employee_id) DO UPDATE SET "
            "schedule_mode = excluded.schedule_mode, updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            (employee_id, schedule_mode, updated_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_employee_schedule_policy(employee_id: int) -> str | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT schedule_mode FROM employee_schedule_policy WHERE employee_id = ?", (employee_id,)
        ).fetchone()
    finally:
        conn.close()

    return row["schedule_mode"] if row else None


def set_role_schedule_policy(role_key: str, schedule_mode: str, updated_by: int | None = None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO role_schedule_policy (role_key, schedule_mode, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(role_key) DO UPDATE SET "
            "schedule_mode = excluded.schedule_mode, updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            (role_key, schedule_mode, updated_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_role_schedule_policy(role_key: str) -> str | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT schedule_mode FROM role_schedule_policy WHERE role_key = ?", (role_key,)
        ).fetchone()
    finally:
        conn.close()

    return row["schedule_mode"] if row else None


# --------------------------------------------------- mobillik siyosati --


def set_employee_mobility_policy(employee_id: int, mobility_policy: str, updated_by: int | None = None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO employee_mobility_policy (employee_id, mobility_policy, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(employee_id) DO UPDATE SET "
            "mobility_policy = excluded.mobility_policy, updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            (employee_id, mobility_policy, updated_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_employee_mobility_policy(employee_id: int) -> str | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT mobility_policy FROM employee_mobility_policy WHERE employee_id = ?", (employee_id,)
        ).fetchone()
    finally:
        conn.close()

    return row["mobility_policy"] if row else None


def set_role_mobility_policy(role_key: str, mobility_policy: str, updated_by: int | None = None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO role_mobility_policy (role_key, mobility_policy, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(role_key) DO UPDATE SET "
            "mobility_policy = excluded.mobility_policy, updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            (role_key, mobility_policy, updated_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_role_mobility_policy(role_key: str) -> str | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT mobility_policy FROM role_mobility_policy WHERE role_key = ?", (role_key,)
        ).fetchone()
    finally:
        conn.close()

    return row["mobility_policy"] if row else None


# ------------------------------------------------- filial talab/tashrif --


def set_branch_visit_requirement(
    employee_id: int, req_date: str, branch: str, min_stay_minutes: int, created_by: int | None = None
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO branch_visit_requirements "
            "(employee_id, req_date, branch, min_stay_minutes, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(employee_id, req_date, branch) DO UPDATE SET "
            "min_stay_minutes = excluded.min_stay_minutes, created_by = excluded.created_by, "
            "created_at = excluded.created_at",
            (employee_id, req_date, branch, min_stay_minutes, created_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_branch_visit_requirements_for_date(employee_id: int, req_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM branch_visit_requirements WHERE employee_id = ? AND req_date = ? ORDER BY branch",
            (employee_id, req_date),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def record_branch_visit_event(
    employee_id: int, branch: str, event_type: str, event_time: str, source: str, raw_reference: str | None = None
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO branch_visit_events "
            "(employee_id, branch, event_type, event_time, source, raw_reference, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (employee_id, branch, event_type, event_time, source, raw_reference, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_branch_visit_events(employee_id: int, branch: str, start_iso: str, end_iso_exclusive: str) -> list[dict]:
    """``[start_iso, end_iso_exclusive)`` oralig'idagi, FAQAT shu
    filialga tegishli eventlar -- boshqa filialdagi eventlar bu
    ro'yxatga umuman kirmaydi."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM branch_visit_events WHERE employee_id = ? AND branch = ? "
            "AND event_time >= ? AND event_time < ? ORDER BY event_time",
            (employee_id, branch, start_iso, end_iso_exclusive),
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
