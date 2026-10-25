"""``salary_agreements`` (fiks oylik kelishuvi tarixi) uchun xom SQL. Yozish yo'li faqat ``services/salary_agreement.py`` orqali."""

from db import get_connection


def insert_agreement(conn, row: dict) -> int | None:
    """Yangi kelishuv qatori (COMMIT QILMASDAN). ``request_token`` allaqachon mavjud bo'lsa hech narsa yozilmaydi va
    ``None`` qaytadi (takroriy/parallel "Saqlash"). Yangi qator ``id``si qaytadi."""
    cursor = conn.execute(
        "INSERT INTO salary_agreements "
        "(employee_id, fixed_salary, work_days, daily_minutes, effective_from, created_by, created_at, source, request_token, "
        "tariff, result_bonus_cap) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(request_token) DO NOTHING",
        (
            row["employee_id"], row["fixed_salary"], row["work_days"], row["daily_minutes"], row["effective_from"],
            row["created_by"], row["created_at"], row["source"], row["request_token"],
            row.get("tariff"), row.get("result_bonus_cap"),
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


def insert_consent_row(conn, agreement_id: int, employee_id: int) -> None:
    conn.execute(
        "INSERT INTO salary_agreement_consents (agreement_id, employee_id, delivery_status) VALUES (?, ?, 'pending') "
        "ON CONFLICT(agreement_id) DO NOTHING",
        (agreement_id, employee_id),
    )


def get_agreement(agreement_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM salary_agreements WHERE id = ?", (agreement_id,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def get_consent(agreement_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM salary_agreement_consents WHERE agreement_id = ?", (agreement_id,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def has_newer_versioned_agreement(employee_id: int, agreement_id: int) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM salary_agreement_consents WHERE employee_id = ? AND agreement_id > ? LIMIT 1",
            (employee_id, agreement_id),
        ).fetchone()
    finally:
        conn.close()
    return row is not None


def latest_consent_agreement_id(employee_id: int) -> int | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(agreement_id) AS agreement_id FROM salary_agreement_consents WHERE employee_id = ?", (employee_id,)
        ).fetchone()
    finally:
        conn.close()
    return row["agreement_id"] if row and row["agreement_id"] is not None else None


def version_number(employee_id: int, agreement_id: int) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM salary_agreement_consents WHERE employee_id = ? AND agreement_id <= ?",
            (employee_id, agreement_id),
        ).fetchone()
    finally:
        conn.close()
    return int(row["n"])


def set_delivery(agreement_id: int, status: str, at: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE salary_agreement_consents SET delivery_status = ?, delivery_at = ? "
            "WHERE agreement_id = ? AND consented_at IS NULL",
            (status, at, agreement_id),
        )
        conn.commit()
    finally:
        conn.close()


def record_consent(agreement_id: int, user_id: int, at: str) -> bool:
    """Atomik: faqat hali rozilik yozilmagan qatorga. Takroriy bosish ``False`` (hech narsa qo'shilmaydi)."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE salary_agreement_consents SET consented_by = ?, consented_at = ? "
            "WHERE agreement_id = ? AND employee_id = ? AND consented_at IS NULL",
            (user_id, at, agreement_id, user_id),
        )
        changed = cursor.rowcount > 0
        conn.commit()
    finally:
        conn.close()
    return changed


# ----------------------------------------------------- "Tushunmadim" savollari --


def open_issue(agreement_id: int, employee_id: int, branch: str | None, due_date: str, now: str) -> int | None:
    """Versiya uchun savol yo'q bo'lsa yaratadi (id), bor bo'lsa ``None`` (takroriy bosish)."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO salary_agreement_issues (agreement_id, employee_id, branch, status, due_date, opened_at) "
            "VALUES (?, ?, ?, 'open', ?, ?) ON CONFLICT(agreement_id) DO NOTHING",
            (agreement_id, employee_id, branch, due_date, now),
        )
        created = cursor.rowcount > 0
        issue_id = cursor.lastrowid if created else None
        conn.commit()
    finally:
        conn.close()
    return issue_id


def get_issue(issue_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM salary_agreement_issues WHERE id = ?", (issue_id,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def get_issue_for_agreement(agreement_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM salary_agreement_issues WHERE agreement_id = ?", (agreement_id,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def set_issue_notified(issue_id: int, count: int) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE salary_agreement_issues SET notified_count = ? WHERE id = ?", (count, issue_id))
        conn.commit()
    finally:
        conn.close()


def resolve_issue(issue_id: int, user_id: int, outcome: str, at: str) -> bool:
    """Atomik ``open -> resolved``; takroriy yopish ``False``. Rozilik jadvaliga tegmaydi."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE salary_agreement_issues SET status = 'resolved', resolved_by = ?, resolved_at = ?, outcome = ? "
            "WHERE id = ? AND status = 'open'",
            (user_id, at, outcome, issue_id),
        )
        changed = cursor.rowcount > 0
        conn.commit()
    finally:
        conn.close()
    return changed


def list_open_issues() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM salary_agreement_issues WHERE status = 'open' ORDER BY id").fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def mark_reminded(issue_id: int, day: str) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE salary_agreement_issues SET reminded_on = ? WHERE id = ?", (day, issue_id))
        conn.commit()
    finally:
        conn.close()
