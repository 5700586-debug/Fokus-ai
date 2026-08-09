"""Xodimning kunlik erkin javoblari (savol/javob juftliklari JSON'da)."""

import json
from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_daily_report(
    employee_id: int, report_date: str, report_type: str, answers: dict, role_key: str | None = None
) -> None:
    content = json.dumps(answers, ensure_ascii=False)

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO employee_daily_reports "
            "(employee_id, report_date, role_key, report_type, content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(employee_id, report_date, report_type) DO UPDATE SET "
            "content = excluded.content, role_key = excluded.role_key",
            (employee_id, report_date, role_key, report_type, content, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_daily_report(employee_id: int, report_date: str, report_type: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM employee_daily_reports "
            "WHERE employee_id = ? AND report_date = ? AND report_type = ?",
            (employee_id, report_date, report_type),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    report = dict(row)
    report["answers"] = json.loads(report["content"])
    return report
