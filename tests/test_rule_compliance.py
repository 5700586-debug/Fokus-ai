"""Jarima (``discipline_penalties``) va nizom o'qish auditi
(``rule_learning_progress``) orasidagi READ-ONLY bog'lanish:
``repositories/rule_learning.py::get_progress_for_rule`` va
``services/discipline.py::get_penalty_learning_context``.

Yozuv/UI/AI/xabar/avtomatik jazo YO'Q -- faqat mavjud ikkita jadvalni
o'qib holatni hisoblaydi."""

import db
from repositories import discipline as discipline_repo
from repositories import rule_learning as rule_learning_repo
from services import discipline
from services import rule_learning

EMPLOYEE_ID = 601
SUPERVISOR_ID = 1


def _add_rule(rule_number: int, title: str | None = None, content: str | None = None) -> None:
    discipline_repo.create_rule(
        rule_number,
        title or f"Band {rule_number}",
        content or f"Matn {rule_number}",
        created_by=SUPERVISOR_ID,
    )


def _create_penalty(rule_number: int, employee_id: int = EMPLOYEE_ID) -> int:
    return discipline_repo.create_penalty(
        employee_id, SUPERVISOR_ID, "2026-09-02", 10, rule_number, None, None
    )


def _set_penalty_created_at(penalty_id: int, value: str) -> None:
    conn = db.get_connection()
    try:
        conn.execute("UPDATE discipline_penalties SET created_at = ? WHERE id = ?", (value, penalty_id))
        conn.commit()
    finally:
        conn.close()


def _set_progress_completed_at(progress_id: int, value: str) -> None:
    conn = db.get_connection()
    try:
        conn.execute(
            "UPDATE rule_learning_progress SET completed_at = ?, understood_confirmed_at = ? WHERE id = ?",
            (value, value, progress_id),
        )
        conn.commit()
    finally:
        conn.close()


def _complete_rule(employee_id: int = EMPLOYEE_ID) -> dict:
    progress = rule_learning.get_current_rule(employee_id)
    assert progress is not None
    assert rule_learning.confirm_read(progress["id"]) is True
    assert rule_learning.confirm_understood(employee_id, progress["id"]) is True
    return rule_learning_repo.get_progress(progress["id"])


# --------------------------------------------- get_progress_for_rule --


def test_get_progress_for_rule_returns_none_when_not_started():
    _add_rule(1)

    assert rule_learning_repo.get_progress_for_rule(EMPLOYEE_ID, 1) is None


def test_get_progress_for_rule_returns_the_single_row():
    _add_rule(1)
    rule_learning.enroll(EMPLOYEE_ID)
    started = rule_learning.get_current_rule(EMPLOYEE_ID)

    found = rule_learning_repo.get_progress_for_rule(EMPLOYEE_ID, 1)

    assert found is not None
    assert found["id"] == started["id"]
    assert found["employee_id"] == EMPLOYEE_ID
    assert found["rule_number"] == 1


# ---------------------------------------- get_penalty_learning_context --


def test_missing_penalty_returns_none():
    assert discipline.get_penalty_learning_context(999999) is None


def test_status_not_learned_when_no_progress_exists():
    _add_rule(1)
    penalty_id = _create_penalty(1)

    context = discipline.get_penalty_learning_context(penalty_id)

    assert context["status"] == "not_learned"
    assert context["penalty_id"] == penalty_id
    assert context["employee_id"] == EMPLOYEE_ID
    assert context["rule_number"] == 1
    assert context["title_snapshot"] is None
    assert context["content_snapshot"] is None
    assert context["understood_at"] is None
    assert context["penalty_created_at"] is not None


def test_status_learning_incomplete_when_not_yet_understood():
    _add_rule(1)
    rule_learning.enroll(EMPLOYEE_ID)
    rule_learning.get_current_rule(EMPLOYEE_ID)  # progress qatori yaratiladi, hali tugallanmagan
    penalty_id = _create_penalty(1)

    context = discipline.get_penalty_learning_context(penalty_id)

    assert context["status"] == "learning_incomplete"
    assert context["title_snapshot"] == "Band 1"
    assert context["content_snapshot"] == "Matn 1"
    assert context["understood_at"] is None


def test_status_understood_before_penalty():
    _add_rule(1)
    rule_learning.enroll(EMPLOYEE_ID)
    progress = _complete_rule()
    _set_progress_completed_at(progress["id"], "2026-01-01T00:00:00+00:00")

    penalty_id = _create_penalty(1)
    _set_penalty_created_at(penalty_id, "2026-01-02T00:00:00+00:00")

    context = discipline.get_penalty_learning_context(penalty_id)

    assert context["status"] == "understood_before_penalty"
    assert context["understood_at"] == "2026-01-01T00:00:00+00:00"


def test_status_understood_after_penalty():
    _add_rule(1)
    penalty_id = _create_penalty(1)
    _set_penalty_created_at(penalty_id, "2026-01-01T00:00:00+00:00")

    rule_learning.enroll(EMPLOYEE_ID)
    progress = _complete_rule()
    _set_progress_completed_at(progress["id"], "2026-01-02T00:00:00+00:00")

    context = discipline.get_penalty_learning_context(penalty_id)

    assert context["status"] == "understood_after_penalty"


def test_context_has_exactly_the_specified_fields():
    _add_rule(1)
    penalty_id = _create_penalty(1)

    context = discipline.get_penalty_learning_context(penalty_id)

    assert set(context.keys()) == {
        "penalty_id", "employee_id", "rule_number", "status",
        "title_snapshot", "content_snapshot", "understood_at", "penalty_created_at",
    }
