"""Kunlik ombor snapshot, tafovut sabablari va Nazoratchi/Founder
tekshiruvi uchun xom SQL qatlami. Hisoblash mantiqi bu yerda emas —
``services/inventory_snapshot.py`` da.
"""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------- inventory_daily_snapshots --


def get_snapshot_for_date(branch: str | None, snapshot_date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM inventory_daily_snapshots WHERE branch IS ? AND snapshot_date = ?",
            (branch, snapshot_date),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def get_previous_snapshot(branch: str | None, before_date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM inventory_daily_snapshots WHERE branch IS ? AND snapshot_date < ? "
            "ORDER BY snapshot_date DESC LIMIT 1",
            (branch, before_date),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def create_snapshot(
    branch: str | None,
    snapshot_date: str,
    reported_by_employee_id: int,
    total_inventory_value: int,
    previous_inventory_value: int | None,
    gross_difference: int | None,
    threshold: int,
    photo_reference: str | None,
) -> dict:
    """``branch``+``snapshot_date`` uchun snapshot allaqachon mavjud bo'lsa,
    yangisini yaratmasdan mavjudini qaytaradi (duplicate kunlik
    yuborishdan himoya).
    """
    existing = get_snapshot_for_date(branch, snapshot_date)
    if existing is not None:
        return existing

    now = _now()
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO inventory_daily_snapshots "
            "(branch, snapshot_date, reported_by_employee_id, total_inventory_value, "
            "previous_inventory_value, gross_difference, threshold, status, photo_reference, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
            (
                branch,
                snapshot_date,
                reported_by_employee_id,
                total_inventory_value,
                previous_inventory_value,
                gross_difference,
                threshold,
                photo_reference,
                now,
                now,
            ),
        )
        conn.commit()
        snapshot_id = cursor.lastrowid
    finally:
        conn.close()

    return get_snapshot(snapshot_id)


def get_snapshot(snapshot_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM inventory_daily_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def update_snapshot_variance(
    snapshot_id: int, explained_variance: int, unexplained_variance: int, status: str
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE inventory_daily_snapshots SET "
            "explained_variance = ?, unexplained_variance = ?, status = ?, updated_at = ? "
            "WHERE id = ?",
            (explained_variance, unexplained_variance, status, _now(), snapshot_id),
        )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------- inventory_variance_explanations --


def add_variance_explanation(snapshot_id: int, cause: str, amount: int, comment: str | None) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO inventory_variance_explanations (snapshot_id, cause, amount, comment, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (snapshot_id, cause, amount, comment, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_variance_explanations(snapshot_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM inventory_variance_explanations WHERE snapshot_id = ? ORDER BY created_at",
            (snapshot_id,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


# -------------------------------------------------- inventory_variance_reviews --


def record_variance_review(snapshot_id: int, reviewed_by: int, decision: str, comment: str | None) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO inventory_variance_reviews (snapshot_id, reviewed_by, decision, comment, reviewed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (snapshot_id, reviewed_by, decision, comment, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()
