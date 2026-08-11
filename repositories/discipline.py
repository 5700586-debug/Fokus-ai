"""BOS (fiks oylik/bonus banki, nizomlar, kunlik baholash, jarima,
nazoratchi audit) uchun xom SQL qatlami. Biznes logika ``services/discipline.py``da.
"""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------- salaries --


def upsert_fixed_salary(user_id: int, fixed_salary: int, updated_by: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO salaries (user_id, fixed_salary, bonus_bank, updated_by, updated_at) "
            "VALUES (?, ?, 0, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "fixed_salary = excluded.fixed_salary, updated_by = excluded.updated_by, "
            "updated_at = excluded.updated_at",
            (user_id, fixed_salary, updated_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_salary(user_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM salaries WHERE user_id = ?", (user_id,)).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def adjust_bonus_bank(
    user_id: int, delta: int, reason: str, ref_type: str, ref_id: int | None
) -> int:
    """``salaries`` qatori yo'q bo'lsa ``fixed_salary=0`` bilan yaratadi,
    yangi balansni yozadi va ``bonus_bank_ledger``ga audit yozuvi qo'shadi.
    Yangi balansni qaytaradi.
    """
    now = _now()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT bonus_bank FROM salaries WHERE user_id = ?", (user_id,)
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO salaries (user_id, fixed_salary, bonus_bank, updated_by, updated_at) "
                "VALUES (?, 0, 0, NULL, ?)",
                (user_id, now),
            )
            current_balance = 0
        else:
            current_balance = row["bonus_bank"]

        new_balance = current_balance + delta
        conn.execute(
            "UPDATE salaries SET bonus_bank = ?, updated_at = ? WHERE user_id = ?",
            (new_balance, now, user_id),
        )
        conn.execute(
            "INSERT INTO bonus_bank_ledger "
            "(user_id, change_amount, balance_after, reason, ref_type, ref_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, delta, new_balance, reason, ref_type, ref_id, now),
        )
        conn.commit()
        return new_balance
    finally:
        conn.close()


def get_bonus_ledger(user_id: int, limit: int = 20) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM bonus_bank_ledger WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


# --------------------------------------------------------- company rules --


def create_rule(rule_number: int, title: str, content: str, created_by: int) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO company_rules "
            "(rule_number, title, content, is_active, created_by, created_at) "
            "VALUES (?, ?, ?, 1, ?, ?)",
            (rule_number, title, content, created_by, _now()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_rule_by_number(rule_number: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM company_rules WHERE rule_number = ? AND is_active = 1",
            (rule_number,),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def list_active_rules() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM company_rules WHERE is_active = 1 ORDER BY rule_number"
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


# --------------------------------------------------------- daily grading --


def get_daily_evaluation(employee_id: int, eval_date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM daily_evaluations WHERE employee_id = ? AND eval_date = ?",
            (employee_id, eval_date),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def upsert_daily_evaluation(
    employee_id: int, supervisor_id: int, eval_date: str, grade_key: str, grade_points: int
) -> None:
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO daily_evaluations "
            "(employee_id, supervisor_id, eval_date, grade_key, grade_points, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(employee_id, eval_date) DO UPDATE SET "
            "supervisor_id = excluded.supervisor_id, grade_key = excluded.grade_key, "
            "grade_points = excluded.grade_points, updated_at = excluded.updated_at",
            (employee_id, supervisor_id, eval_date, grade_key, grade_points, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_evaluations_for_date(eval_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM daily_evaluations WHERE eval_date = ? "
            "ORDER BY grade_points DESC, employee_id ASC",
            (eval_date,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_points_totals(start_date: str, end_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT employee_id, SUM(grade_points) AS total_points FROM daily_evaluations "
            "WHERE eval_date >= ? AND eval_date <= ? GROUP BY employee_id",
            (start_date, end_date),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_penalty_totals(start_date: str, end_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT employee_id, SUM(amount) AS total_penalty FROM discipline_penalties "
            "WHERE penalty_date >= ? AND penalty_date <= ? GROUP BY employee_id",
            (start_date, end_date),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


# ------------------------------------------------------------- penalties --


def create_penalty(
    employee_id: int,
    supervisor_id: int,
    penalty_date: str,
    amount: int,
    rule_number: int,
    comment: str | None,
    ai_note: str | None,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO discipline_penalties "
            "(employee_id, supervisor_id, penalty_date, amount, rule_number, comment, "
            "ai_note, appeal_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'none', ?)",
            (employee_id, supervisor_id, penalty_date, amount, rule_number, comment, ai_note, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_penalty(penalty_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM discipline_penalties WHERE id = ?", (penalty_id,)
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def list_penalties_by_status(employee_id: int, appeal_status: str, limit: int = 10) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM discipline_penalties WHERE employee_id = ? AND appeal_status = ? "
            "ORDER BY id DESC LIMIT ?",
            (employee_id, appeal_status, limit),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def set_penalty_appeal(penalty_id: int, reason: str, voice_file_id: str | None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE discipline_penalties SET appeal_status = 'pending', "
            "appeal_reason = ?, appeal_voice_file_id = ? WHERE id = ?",
            (reason, voice_file_id, penalty_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_penalty_appeal_brief(penalty_id: int, brief: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE discipline_penalties SET appeal_ai_brief = ? WHERE id = ?",
            (brief, penalty_id),
        )
        conn.commit()
    finally:
        conn.close()


def decide_penalty_appeal(penalty_id: int, decision: str, decided_by: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE discipline_penalties SET appeal_status = 'resolved', "
            "appeal_decision = ?, appeal_decided_by = ?, appeal_decided_at = ? WHERE id = ?",
            (decision, decided_by, _now(), penalty_id),
        )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------- day closures --


def try_close_day(supervisor_id: int, closure_date: str, evaluated_count: int, total_count: int) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO daily_closures "
            "(supervisor_id, closure_date, evaluated_count, total_count, closed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (supervisor_id, closure_date, evaluated_count, total_count, _now()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_closure(supervisor_id: int, closure_date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM daily_closures WHERE supervisor_id = ? AND closure_date = ?",
            (supervisor_id, closure_date),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


# -------------------------------------------------------- supervisor audit --


def try_record_supervisor_audit(
    supervisor_id: int, audit_date: str, event_type: str, penalty_amount: int
) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO supervisor_audit "
            "(supervisor_id, audit_date, event_type, penalty_amount, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (supervisor_id, audit_date, event_type, penalty_amount, _now()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
