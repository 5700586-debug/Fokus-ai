"""``Oyligim`` hisobi uchun FAQAT O'QISH: bir oy bo'yicha xodimning ish bahosi, minus va vaqt bonusi manbalari.
Hech narsa yozmaydi; ledger (``bonus_bank_ledger``) yig'ilmaydi — takroriy yozuv hisobga ikki marta kirmasligi uchun
asosiy jadvallardan o'qiladi."""

from db import get_connection


def month_sources(employee_id: int, start: str, end_exclusive: str, conn=None) -> dict:
    owns = conn is None
    if owns:
        conn = get_connection()
    try:
        evaluations = [
            dict(r) for r in conn.execute(
                "SELECT eval_date, grade_points FROM daily_evaluations WHERE employee_id = ? AND eval_date >= ? AND eval_date < ?",
                (employee_id, start, end_exclusive),
            ).fetchall()
        ]
        penalties = [
            dict(r) for r in conn.execute(
                "SELECT amount FROM discipline_penalties WHERE employee_id = ? AND penalty_date >= ? AND penalty_date < ? "
                "AND (appeal_decision IS NULL OR appeal_decision != 'approved')",
                (employee_id, start, end_exclusive),
            ).fetchall()
        ]
        audits = [
            dict(r) for r in conn.execute(
                "SELECT event_type, penalty_amount FROM supervisor_audit WHERE supervisor_id = ? AND audit_date >= ? AND audit_date < ?",
                (employee_id, start, end_exclusive),
            ).fetchall()
        ]
        extra_work = conn.execute(
            "SELECT COALESCE(SUM(stars), 0) AS n FROM extra_work_stars WHERE employee_id = ? AND work_date >= ? AND work_date < ?",
            (employee_id, start, end_exclusive),
        ).fetchone()["n"]
        time_bonus_days = conn.execute(
            "SELECT COUNT(*) AS n FROM time_bonus_grants WHERE employee_id = ? AND grant_date >= ? AND grant_date < ?",
            (employee_id, start, end_exclusive),
        ).fetchone()["n"]
    finally:
        if owns:
            conn.close()
    return {"evaluations": evaluations, "penalties": penalties, "audits": audits, "time_bonus_days": int(time_bonus_days),
            "extra_work": int(extra_work)}
