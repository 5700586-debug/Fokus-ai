"""``salary_agreements`` (fiks oylik kelishuvi tarixi) uchun xom SQL. Yozish yo'li faqat ``services/salary_agreement.py`` orqali."""

from db import get_connection


def insert_agreement(conn, row: dict) -> int | None:
    """Yangi kelishuv qatori (COMMIT QILMASDAN). ``request_token`` allaqachon mavjud bo'lsa hech narsa yozilmaydi va
    ``None`` qaytadi (takroriy/parallel "Saqlash"). Yangi qator ``id``si qaytadi."""
    cursor = conn.execute(
        "INSERT INTO salary_agreements "
        "(employee_id, fixed_salary, work_days, daily_minutes, effective_from, created_by, created_at, source, request_token) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(request_token) DO NOTHING",
        (
            row["employee_id"], row["fixed_salary"], row["work_days"], row["daily_minutes"], row["effective_from"],
            row["created_by"], row["created_at"], row["source"], row["request_token"],
        ),
    )
    if cursor.rowcount <= 0:
        return None
    return cursor.lastrowid


def current_agreement(employee_id: int, on_date: str, conn=None) -> dict | None:
    owns = conn is None
    if owns:
        conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM salary_agreements WHERE employee_id = ? AND effective_from <= ? "
            "ORDER BY effective_from DESC, id DESC LIMIT 1",
            (employee_id, on_date),
        ).fetchone()
    finally:
        if owns:
            conn.close()
    return dict(row) if row else None


def upcoming_agreement(employee_id: int, after_date: str, conn=None) -> dict | None:
    owns = conn is None
    if owns:
        conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM salary_agreements WHERE employee_id = ? AND effective_from > ? "
            "ORDER BY effective_from ASC, id DESC LIMIT 1",
            (employee_id, after_date),
        ).fetchone()
    finally:
        if owns:
            conn.close()
    return dict(row) if row else None


def list_agreements(employee_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM salary_agreements WHERE employee_id = ? ORDER BY id", (employee_id,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def mirror_fixed_salary(conn, employee_id: int, fixed_salary: int, updated_by: int, now: str) -> None:
    """``salaries.fixed_salary`` ustunini amaldagi kelishuv bilan sinxron ushlaydi (bonus_bank'ga tegmaydi)."""
    conn.execute(
        "INSERT INTO salaries (user_id, fixed_salary, bonus_bank, updated_by, updated_at) VALUES (?, ?, 0, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET fixed_salary = excluded.fixed_salary, "
        "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
        (employee_id, fixed_salary, updated_by, now),
    )
