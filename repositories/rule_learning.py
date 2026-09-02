"""Nizom o'qish auditi: xom SQL qatlami (qarang ``schema/discipline.py``).
Tartib, kunlik limit va yakunlash mantig'i ``services/rule_learning.py``da.

Nizom matni ``company_rules``dan BIR MARTA — progress qatori yaratilganda —
snapshot qilinadi, chunki keyin nizom tahrirlansa ham xodim aynan
qaysi matnni tasdiqlagani o'zgarmasligi kerak.
"""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----------------------------------------------------------- enrollments --


def ensure_enrollment(employee_id: int) -> bool:
    """``True`` — aynan shu chaqiruv yozdi; ``False`` — allaqachon bor."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO rule_learning_enrollments "
            "(employee_id, enrolled_at, finished_at) VALUES (?, ?, NULL)",
            (employee_id, _now()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_enrollment(employee_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM rule_learning_enrollments WHERE employee_id = ?",
            (employee_id,),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def finish_enrollment(employee_id: int) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE rule_learning_enrollments SET finished_at = ? "
            "WHERE employee_id = ? AND finished_at IS NULL",
            (_now(), employee_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# -------------------------------------------------------------- progress --


def ensure_progress(
    employee_id: int, rule_number: int, title: str, content: str
) -> dict | None:
    """Qator allaqachon bo'lsa MAVJUD snapshot qaytariladi — matn qayta
    yozilmaydi."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO rule_learning_progress "
            "(employee_id, rule_number, title_snapshot, content_snapshot) "
            "VALUES (?, ?, ?, ?)",
            (employee_id, rule_number, title, content),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM rule_learning_progress WHERE employee_id = ? AND rule_number = ?",
            (employee_id, rule_number),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def get_progress(progress_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM rule_learning_progress WHERE id = ?", (progress_id,)
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def get_progress_for_rule(employee_id: int, rule_number: int) -> dict | None:
    """Bitta xodim/nizom uchun yagona progress qatori (UNIQUE(employee_id,
    rule_number) — retake/eng so'nggi tanlash mantig'i shart emas)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM rule_learning_progress WHERE employee_id = ? AND rule_number = ?",
            (employee_id, rule_number),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def get_pending_progress(employee_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM rule_learning_progress WHERE employee_id = ? AND completed_at IS NULL "
            "ORDER BY rule_number ASC LIMIT 1",
            (employee_id,),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def list_started_rule_numbers(employee_id: int) -> list[int]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT rule_number FROM rule_learning_progress WHERE employee_id = ? "
            "ORDER BY rule_number ASC",
            (employee_id,),
        ).fetchall()
    finally:
        conn.close()

    return [row["rule_number"] for row in rows]


def mark_sent(progress_id: int) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE rule_learning_progress SET sent_at = ? WHERE id = ? AND sent_at IS NULL",
            (_now(), progress_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def mark_read(progress_id: int) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE rule_learning_progress SET read_confirmed_at = ? "
            "WHERE id = ? AND read_confirmed_at IS NULL",
            (_now(), progress_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def mark_not_understood(progress_id: int) -> bool:
    """Faqat belgilaydi — bandni YAKUNLAMAYDI (``completed_at`` tegilmaydi)."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE rule_learning_progress SET not_understood_at = ? "
            "WHERE id = ? AND completed_at IS NULL",
            (_now(), progress_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def mark_understood(progress_id: int, company_date: str) -> bool:
    """FAQAT band o'qilgan (``read_confirmed_at IS NOT NULL``) va hali
    tasdiqlanmagan bo'lsa yopadi — takroriy bosish ``False``."""
    now = _now()
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE rule_learning_progress SET understood_confirmed_at = ?, completed_at = ?, "
            "completed_company_date = ? WHERE id = ? AND read_confirmed_at IS NOT NULL "
            "AND understood_confirmed_at IS NULL",
            (now, now, company_date, progress_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def count_completed_for_date(employee_id: int, company_date: str) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM rule_learning_progress "
            "WHERE employee_id = ? AND completed_company_date = ?",
            (employee_id, company_date),
        ).fetchone()
    finally:
        conn.close()

    return row["total"] if row else 0
