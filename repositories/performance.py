"""Rules, Nazoratchi bahosi, oylik natija va yulduz/bonus tarixi uchun
xom SQL qatlami. Biznes logika (klamplash, bonus hisoblash) bu yerda
emas — ``services/`` da.
"""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- rules --


def get_rule(rule_key: str) -> str | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT rule_value FROM rules WHERE rule_key = ?", (rule_key,)
        ).fetchone()
    finally:
        conn.close()

    return row["rule_value"] if row else None


def set_rule(rule_key: str, rule_value: str, updated_by: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO rules (rule_key, rule_value, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(rule_key) DO UPDATE SET "
            "rule_value = excluded.rule_value, updated_by = excluded.updated_by, "
            "updated_at = excluded.updated_at",
            (rule_key, rule_value, updated_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def list_rules() -> dict[str, str]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT rule_key, rule_value FROM rules ORDER BY rule_key").fetchall()
    finally:
        conn.close()

    return {row["rule_key"]: row["rule_value"] for row in rows}


# ------------------------------------------------------ supervisor_scores --


def record_score(
    user_id: int, scored_by: int, score_date: str, score: int, comment: str | None = None
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO supervisor_scores "
            "(user_id, scored_by, score_date, score, comment, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, score_date) DO UPDATE SET "
            "scored_by = excluded.scored_by, score = excluded.score, "
            "comment = excluded.comment, created_at = excluded.created_at",
            (user_id, scored_by, score_date, score, comment, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_scores_in_range(user_id: int, start_date: str, end_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM supervisor_scores "
            "WHERE user_id = ? AND score_date >= ? AND score_date <= ? "
            "ORDER BY score_date",
            (user_id, start_date, end_date),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


# --------------------------------------------------- monthly_performance --


def get_monthly_performance(user_id: int, year_month: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM monthly_performance WHERE user_id = ? AND year_month = ?",
            (user_id, year_month),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def try_insert_monthly_performance(
    user_id: int,
    year_month: str,
    avg_supervisor_score: float | None,
    attendance_ok: bool,
    no_serious_violation: bool,
    checklist_completed: bool,
    full_bonus_month: bool,
) -> bool:
    """``year_month`` uchun natija allaqachon yozilgan bo'lsa, hech narsa
    qilmaydi va ``False`` qaytaradi (oyni ikki marta qayta ishlashdan
    himoya — idempotency).
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO monthly_performance "
            "(user_id, year_month, avg_supervisor_score, attendance_ok, "
            "no_serious_violation, checklist_completed, full_bonus_month, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                year_month,
                avg_supervisor_score,
                int(attendance_ok),
                int(no_serious_violation),
                int(checklist_completed),
                int(full_bonus_month),
                _now(),
            ),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# --------------------------------------------------------- star_history --


def get_current_stars(user_id: int) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT new_stars FROM star_history WHERE user_id = ? "
            "ORDER BY year_month DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    return row["new_stars"] if row else 0


def try_record_star_change(
    user_id: int, year_month: str, previous_stars: int, new_stars: int, reason: str
) -> bool:
    """``year_month`` uchun allaqachon yozuv bo'lsa, ``False`` qaytaradi."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO star_history "
            "(user_id, year_month, previous_stars, new_stars, change, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                year_month,
                previous_stars,
                new_stars,
                new_stars - previous_stars,
                reason,
                _now(),
            ),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_star_history(user_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM star_history WHERE user_id = ? ORDER BY year_month", (user_id,)
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


# -------------------------------------------------------- bonus_history --


def try_record_bonus(user_id: int, year_month: str, stars: int, bonus_amount: int) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO bonus_history "
            "(user_id, year_month, stars, bonus_amount, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, year_month, stars, bonus_amount, _now()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_bonus_history(user_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM bonus_history WHERE user_id = ? ORDER BY year_month", (user_id,)
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]
