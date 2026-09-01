from datetime import date

import company_time
from repositories import discipline as discipline_repo
from repositories import rule_learning as rule_learning_repo
from services import rule_learning

EMPLOYEE_ID = 501


def _add_rule(rule_number: int, title: str | None = None, content: str | None = None) -> None:
    discipline_repo.create_rule(
        rule_number,
        title or f"Band {rule_number}",
        content or f"Matn {rule_number}",
        created_by=1,
    )


def _freeze_date(monkeypatch, value: date) -> None:
    monkeypatch.setattr(company_time, "today", lambda: value)


def _complete_current(employee_id: int = EMPLOYEE_ID) -> dict:
    progress = rule_learning.get_current_rule(employee_id)
    assert progress is not None
    assert rule_learning.confirm_read(progress["id"]) is True
    assert rule_learning.confirm_understood(employee_id, progress["id"]) is True
    return progress


def test_enroll_is_not_duplicated():
    assert rule_learning.enroll(EMPLOYEE_ID) is True
    assert rule_learning.enroll(EMPLOYEE_ID) is False

    enrollment = rule_learning.get_enrollment(EMPLOYEE_ID)
    assert enrollment is not None
    assert enrollment["finished_at"] is None


def _deactivate_rule(rule_number: int) -> None:
    import db

    conn = db.get_connection()
    try:
        conn.execute(
            "UPDATE company_rules SET is_active = 0 WHERE rule_number = ?", (rule_number,)
        )
        conn.commit()
    finally:
        conn.close()


def test_rules_are_served_active_and_ascending():
    _add_rule(3)
    _add_rule(1)
    _add_rule(2)
    _deactivate_rule(2)
    rule_learning.enroll(EMPLOYEE_ID)

    assert rule_learning.get_current_rule(EMPLOYEE_ID)["rule_number"] == 1
    _complete_current()
    assert rule_learning.get_current_rule(EMPLOYEE_ID)["rule_number"] == 3


def test_snapshot_is_immutable_and_survives_rule_edit():
    _add_rule(1, "Eski sarlavha", "Eski matn")
    rule_learning.enroll(EMPLOYEE_ID)

    progress = rule_learning.get_current_rule(EMPLOYEE_ID)
    assert progress["title_snapshot"] == "Eski sarlavha"

    import db

    conn = db.get_connection()
    try:
        conn.execute(
            "UPDATE company_rules SET title = 'Yangi', content = 'Yangi matn' "
            "WHERE rule_number = 1"
        )
        conn.commit()
    finally:
        conn.close()

    again = rule_learning.get_current_rule(EMPLOYEE_ID)
    assert again["id"] == progress["id"]
    assert again["title_snapshot"] == "Eski sarlavha"
    assert again["content_snapshot"] == "Eski matn"


def test_pending_rule_continues_after_deactivation():
    _add_rule(1)
    _add_rule(2)
    rule_learning.enroll(EMPLOYEE_ID)

    progress = rule_learning.get_current_rule(EMPLOYEE_ID)
    assert progress["rule_number"] == 1

    _deactivate_rule(1)

    still = rule_learning.get_current_rule(EMPLOYEE_ID)
    assert still is not None
    assert still["rule_number"] == 1


def test_mark_read_is_idempotent():
    _add_rule(1)
    rule_learning.enroll(EMPLOYEE_ID)
    progress = rule_learning.get_current_rule(EMPLOYEE_ID)

    assert rule_learning.confirm_read(progress["id"]) is True
    assert rule_learning.confirm_read(progress["id"]) is False


def test_not_understood_does_not_complete_rule():
    _add_rule(1)
    _add_rule(2)
    rule_learning.enroll(EMPLOYEE_ID)
    progress = rule_learning.get_current_rule(EMPLOYEE_ID)
    rule_learning.confirm_read(progress["id"])

    assert rule_learning.report_not_understood(progress["id"]) is True

    stored = rule_learning.get_progress(progress["id"])
    assert stored["not_understood_at"] is not None
    assert stored["completed_at"] is None
    assert rule_learning.get_current_rule(EMPLOYEE_ID)["rule_number"] == 1


def test_understood_requires_read_confirmation():
    _add_rule(1)
    rule_learning.enroll(EMPLOYEE_ID)
    progress = rule_learning.get_current_rule(EMPLOYEE_ID)

    assert rule_learning.confirm_understood(EMPLOYEE_ID, progress["id"]) is False
    assert rule_learning.get_progress(progress["id"])["completed_at"] is None


def test_understood_double_click_is_idempotent():
    _add_rule(1)
    _add_rule(2)
    rule_learning.enroll(EMPLOYEE_ID)
    progress = rule_learning.get_current_rule(EMPLOYEE_ID)
    rule_learning.confirm_read(progress["id"])

    assert rule_learning.confirm_understood(EMPLOYEE_ID, progress["id"]) is True
    assert rule_learning.confirm_understood(EMPLOYEE_ID, progress["id"]) is False


def test_daily_limit_is_five(monkeypatch):
    _freeze_date(monkeypatch, date(2026, 9, 1))
    for number in range(1, 8):
        _add_rule(number)
    rule_learning.enroll(EMPLOYEE_ID)

    for _ in range(5):
        _complete_current()

    assert rule_learning.completed_today(EMPLOYEE_ID) == 5
    assert rule_learning.get_current_rule(EMPLOYEE_ID) is None


def test_limit_resets_on_next_company_date(monkeypatch):
    _freeze_date(monkeypatch, date(2026, 9, 1))
    for number in range(1, 8):
        _add_rule(number)
    rule_learning.enroll(EMPLOYEE_ID)

    for _ in range(5):
        _complete_current()
    assert rule_learning.get_current_rule(EMPLOYEE_ID) is None

    _freeze_date(monkeypatch, date(2026, 9, 2))
    assert rule_learning.get_current_rule(EMPLOYEE_ID)["rule_number"] == 6


def test_enrollment_is_finished_when_all_active_rules_done():
    _add_rule(1)
    _add_rule(2)
    rule_learning.enroll(EMPLOYEE_ID)

    _complete_current()
    assert rule_learning.get_enrollment(EMPLOYEE_ID)["finished_at"] is None

    _complete_current()

    assert rule_learning.get_enrollment(EMPLOYEE_ID)["finished_at"] is not None
    assert rule_learning.get_current_rule(EMPLOYEE_ID) is None


def test_enrollment_is_not_finished_without_active_rules():
    rule_learning.enroll(EMPLOYEE_ID)

    assert rule_learning.get_current_rule(EMPLOYEE_ID) is None
    assert rule_learning.get_enrollment(EMPLOYEE_ID)["finished_at"] is None


def test_only_one_incomplete_progress_at_a_time():
    _add_rule(1)
    _add_rule(2)
    _add_rule(3)
    rule_learning.enroll(EMPLOYEE_ID)

    rule_learning.get_current_rule(EMPLOYEE_ID)
    rule_learning.get_current_rule(EMPLOYEE_ID)

    assert rule_learning_repo.list_started_rule_numbers(EMPLOYEE_ID) == [1]


def test_mark_sent_is_recorded_once():
    _add_rule(1)
    rule_learning.enroll(EMPLOYEE_ID)
    progress = rule_learning.get_current_rule(EMPLOYEE_ID)

    assert rule_learning.mark_sent(progress["id"]) is True
    assert rule_learning.mark_sent(progress["id"]) is False
    assert rule_learning.get_progress(progress["id"])["sent_at"] is not None


def test_no_rule_without_enrollment():
    _add_rule(1)

    assert rule_learning.get_current_rule(EMPLOYEE_ID) is None
    assert rule_learning_repo.list_started_rule_numbers(EMPLOYEE_ID) == []
