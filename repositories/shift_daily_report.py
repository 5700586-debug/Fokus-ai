"""Kassir kunlik 3 savollik hisobot (prixodsiz tovar / narx shikoyati
/ xodim shikoyati) uchun xom SQL qatlami. Formula/mantiq bu yerda
emas — ``services/shift_daily_report.py``da.
"""

from db import get_connection


def get(shift_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM shift_daily_report WHERE shift_id = ?", (shift_id,)
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def set_no_prixod_count(shift_id: int, branch: str | None, shift_date: str, count: int, now: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO shift_daily_report (shift_id, branch, shift_date, no_prixod_count, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(shift_id) DO UPDATE SET "
            "no_prixod_count = excluded.no_prixod_count, updated_at = excluded.updated_at",
            (shift_id, branch, shift_date, count, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def set_price_complaint_bucket(shift_id: int, branch: str | None, shift_date: str, bucket: str, now: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO shift_daily_report (shift_id, branch, shift_date, price_complaint_bucket, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(shift_id) DO UPDATE SET "
            "price_complaint_bucket = excluded.price_complaint_bucket, updated_at = excluded.updated_at",
            (shift_id, branch, shift_date, bucket, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def set_staff_complaint(
    shift_id: int, branch: str | None, shift_date: str, occurred: int,
    employee_id: int | None, complaint_type: str | None, note: str | None, now: str,
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO shift_daily_report "
            "(shift_id, branch, shift_date, staff_complaint_occurred, staff_complaint_employee_id, "
            "staff_complaint_type, staff_complaint_note, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(shift_id) DO UPDATE SET "
            "staff_complaint_occurred = excluded.staff_complaint_occurred, "
            "staff_complaint_employee_id = excluded.staff_complaint_employee_id, "
            "staff_complaint_type = excluded.staff_complaint_type, "
            "staff_complaint_note = excluded.staff_complaint_note, "
            "updated_at = excluded.updated_at",
            (shift_id, branch, shift_date, occurred, employee_id, complaint_type, note, now, now),
        )
        conn.commit()
    finally:
        conn.close()
