"""Fokus HR (rekruting) uchun xom SQL qatlami — vakansiya, ariza,
javob, rubrika va tahlil."""

import json
from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- vakansiya --


def list_vacancies(active_only: bool = True) -> list[dict]:
    conn = get_connection()
    try:
        if active_only:
            rows = conn.execute(
                "SELECT * FROM recruiting_vacancies WHERE is_active = 1 ORDER BY id"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM recruiting_vacancies ORDER BY id").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_vacancy(vacancy_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM recruiting_vacancies WHERE id = ?", (vacancy_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_vacancy_by_key(position_key: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM recruiting_vacancies WHERE position_key = ?", (position_key,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_vacancy_active(vacancy_id: int, is_active: bool) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE recruiting_vacancies SET is_active = ?, updated_at = ? WHERE id = ?",
            (1 if is_active else 0, _now(), vacancy_id),
        )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------- ariza --


def create_application(candidate_telegram_id: int, vacancy_id: int, retention_expires_at: str) -> int:
    now = _now()
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO recruiting_applications "
            "(candidate_telegram_id, vacancy_id, status, retention_expires_at, created_at, updated_at) "
            "VALUES (?, ?, 'in_progress', ?, ?, ?)",
            (candidate_telegram_id, vacancy_id, retention_expires_at, now, now),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_application(application_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM recruiting_applications WHERE id = ?", (application_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_in_progress_application(candidate_telegram_id: int) -> dict | None:
    """Nomzodning tugallanmagan (davom ettirilishi mumkin bo'lgan)
    arizasi — worker restart yoki uzoq tanaffusdan keyin ham davom
    ettirish uchun."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM recruiting_applications "
            "WHERE candidate_telegram_id = ? AND status = 'in_progress' "
            "ORDER BY id DESC LIMIT 1",
            (candidate_telegram_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


_UPDATABLE_APPLICATION_FIELDS = {
    "full_name",
    "phone",
    "experience_text",
    "leave_reason_text",
    "availability_text",
    "start_date_text",
    "motivation_text",
    "current_step",
    "status",
}


def update_application(application_id: int, **fields) -> None:
    updates = {key: value for key, value in fields.items() if key in _UPDATABLE_APPLICATION_FIELDS}
    if not updates:
        return

    set_clause = ", ".join(f"{key} = ?" for key in updates)
    params = list(updates.values()) + [_now(), application_id]

    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE recruiting_applications SET {set_clause}, updated_at = ? WHERE id = ?", params
        )
        conn.commit()
    finally:
        conn.close()


def record_consent(application_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE recruiting_applications SET consent_given_at = ?, updated_at = ? WHERE id = ?",
            (_now(), _now(), application_id),
        )
        conn.commit()
    finally:
        conn.close()


def cancel_application(application_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE recruiting_applications SET status = 'cancelled', cancelled_at = ?, updated_at = ? "
            "WHERE id = ?",
            (_now(), _now(), application_id),
        )
        conn.commit()
    finally:
        conn.close()


def increment_follow_up_count(application_id: int) -> int:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE recruiting_applications SET follow_up_count = follow_up_count + 1, updated_at = ? "
            "WHERE id = ?",
            (_now(), application_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT follow_up_count FROM recruiting_applications WHERE id = ?", (application_id,)
        ).fetchone()
        return row["follow_up_count"] if row else 0
    finally:
        conn.close()


def set_founder_decision(application_id: int, decision: str, decided_by: int) -> None:
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE recruiting_applications SET founder_decision = ?, founder_decision_by = ?, "
            "founder_decision_at = ?, status = 'reviewed', updated_at = ? WHERE id = ?",
            (decision, decided_by, now, now, application_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_applications_past_retention(now_iso: str | None = None) -> list[dict]:
    now_iso = now_iso or _now()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM recruiting_applications WHERE retention_expires_at IS NOT NULL "
            "AND retention_expires_at <= ?",
            (now_iso,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def purge_application(application_id: int) -> None:
    """Nomzod ma'lumotlarini butunlay o'chiradi (javoblar, tahlil, ariza)
    — retention muddati o'tganda yoki admin so'rovi bo'yicha."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM recruiting_answers WHERE application_id = ?", (application_id,))
        conn.execute("DELETE FROM recruiting_assessments WHERE application_id = ?", (application_id,))
        conn.execute("DELETE FROM recruiting_applications WHERE id = ?", (application_id,))
        conn.commit()
    finally:
        conn.close()


# -------------------------------------------------------------------- javob --


def add_answer(
    application_id: int,
    question_key: str,
    question_text: str,
    answer_text: str,
    answer_source: str = "text",
    is_follow_up: bool = False,
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO recruiting_answers "
            "(application_id, question_key, question_text, answer_text, answer_source, "
            "is_follow_up, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                application_id,
                question_key,
                question_text,
                answer_text,
                answer_source,
                1 if is_follow_up else 0,
                _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_answers(application_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM recruiting_answers WHERE application_id = ? ORDER BY id",
            (application_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ----------------------------------------------------------------- rubrika --


def create_rubric_version(position_key: str, version: int, criteria: list[dict]) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO recruiting_rubric_versions "
            "(position_key, version, criteria_json, created_at) VALUES (?, ?, ?, ?)",
            (position_key, version, json.dumps(criteria, ensure_ascii=False), _now()),
        )
        conn.commit()
        if cursor.lastrowid:
            return cursor.lastrowid
        existing = conn.execute(
            "SELECT id FROM recruiting_rubric_versions WHERE position_key = ? AND version = ?",
            (position_key, version),
        ).fetchone()
        return existing["id"] if existing else 0
    finally:
        conn.close()


def get_latest_rubric_version(position_key: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM recruiting_rubric_versions WHERE position_key = ? "
            "ORDER BY version DESC LIMIT 1",
            (position_key,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ----------------------------------------------------------------- tahlil --


def save_assessment(
    application_id: int,
    rubric_version_id: int,
    overall_result: str,
    criteria_scores: list[dict],
    strengths: list[str],
    risks: list[dict],
    ai_summary: str | None,
    source: str,
) -> None:
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM recruiting_assessments WHERE application_id = ?", (application_id,)
        )
        conn.execute(
            "INSERT INTO recruiting_assessments "
            "(application_id, rubric_version_id, overall_result, criteria_scores_json, "
            "strengths_json, risks_json, ai_summary, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                application_id,
                rubric_version_id,
                overall_result,
                json.dumps(criteria_scores, ensure_ascii=False),
                json.dumps(strengths, ensure_ascii=False),
                json.dumps(risks, ensure_ascii=False),
                ai_summary,
                source,
                now,
            ),
        )
        conn.execute(
            "UPDATE recruiting_applications SET status = 'awaiting_review', updated_at = ? WHERE id = ?",
            (now, application_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_assessment(application_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM recruiting_assessments WHERE application_id = ?", (application_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
