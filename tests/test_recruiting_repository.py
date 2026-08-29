"""Fokus HR DB qatlami (schema/migration + repositories/recruiting.py)
uchun testlar."""

from repositories import recruiting as recruiting_repo
from services import recruiting_privacy


# ------------------------------------------------- vakansiya <-> filial (branch) --


def test_set_vacancy_branches_saves_multiple_branches_with_headcount():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    ok = recruiting_repo.set_vacancy_branches(
        kassir["id"], [{"branch_name": "Filial A", "headcount": 1}, {"branch_name": "Filial C", "headcount": 2}]
    )
    assert ok is True

    branches = recruiting_repo.list_vacancy_branches(kassir["id"])
    by_name = {b["branch_name"]: b["headcount"] for b in branches}
    assert by_name == {"Filial A": 1, "Filial C": 2}


def test_set_vacancy_branches_rejects_unknown_vacancy():
    assert recruiting_repo.set_vacancy_branches(999999, [{"branch_name": "Filial A", "headcount": 1}]) is False


def test_set_vacancy_branches_rejects_non_positive_headcount():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    assert recruiting_repo.set_vacancy_branches(kassir["id"], [{"branch_name": "Filial A", "headcount": 0}]) is False
    assert recruiting_repo.set_vacancy_branches(kassir["id"], [{"branch_name": "Filial A", "headcount": -1}]) is False
    assert recruiting_repo.list_vacancy_branches(kassir["id"]) == []


def test_set_vacancy_branches_rejects_empty_branch_name():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    assert recruiting_repo.set_vacancy_branches(kassir["id"], [{"branch_name": "  ", "headcount": 1}]) is False


def test_set_vacancy_branches_rejects_duplicate_branch_in_same_call():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    ok = recruiting_repo.set_vacancy_branches(
        kassir["id"], [{"branch_name": "Filial A", "headcount": 1}, {"branch_name": "Filial A", "headcount": 2}]
    )
    assert ok is False
    assert recruiting_repo.list_vacancy_branches(kassir["id"]) == []


def test_clear_vacancy_branches_then_set_replaces_old_assignment():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    recruiting_repo.set_vacancy_branches(kassir["id"], [{"branch_name": "Filial A", "headcount": 5}])

    recruiting_repo.clear_vacancy_branches(kassir["id"])
    recruiting_repo.set_vacancy_branches(kassir["id"], [{"branch_name": "Filial B", "headcount": 3}])

    branches = recruiting_repo.list_vacancy_branches(kassir["id"])
    assert len(branches) == 1
    assert branches[0]["branch_name"] == "Filial B"
    assert branches[0]["headcount"] == 3


def test_vacancy_branches_are_independent_per_vacancy():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    sotuvchi = recruiting_repo.get_vacancy_by_key("sotuvchi")
    recruiting_repo.set_vacancy_branches(kassir["id"], [{"branch_name": "Filial A", "headcount": 1}])
    recruiting_repo.set_vacancy_branches(sotuvchi["id"], [{"branch_name": "Filial B", "headcount": 2}])

    assert [b["branch_name"] for b in recruiting_repo.list_vacancy_branches(kassir["id"])] == ["Filial A"]
    assert [b["branch_name"] for b in recruiting_repo.list_vacancy_branches(sotuvchi["id"])] == ["Filial B"]


def test_schema_seeds_two_default_active_vacancies():
    vacancies = recruiting_repo.list_vacancies(active_only=True)
    keys = {v["position_key"] for v in vacancies}
    assert keys == {"kassir", "sotuvchi"}
    assert all(v["is_active"] == 1 for v in vacancies)


def test_set_vacancy_active_toggles_visibility():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    recruiting_repo.set_vacancy_active(kassir["id"], False)

    active = recruiting_repo.list_vacancies(active_only=True)
    assert kassir["id"] not in [v["id"] for v in active]

    all_vacancies = recruiting_repo.list_vacancies(active_only=False)
    assert kassir["id"] in [v["id"] for v in all_vacancies]


def test_application_lifecycle_create_update_answers_assessment():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    retention = recruiting_privacy.compute_retention_expiry()
    application_id = recruiting_repo.create_application(555, kassir["id"], retention)

    application = recruiting_repo.get_application(application_id)
    assert application["status"] == "in_progress"
    assert application["candidate_telegram_id"] == 555

    recruiting_repo.record_consent(application_id)
    recruiting_repo.update_application(application_id, full_name="Ali Valiyev", current_step="phone")

    updated = recruiting_repo.get_application(application_id)
    assert updated["full_name"] == "Ali Valiyev"
    assert updated["current_step"] == "phone"
    assert updated["consent_given_at"] is not None

    recruiting_repo.add_answer(application_id, "kassir_kamomad", "Savol?", "Rahbarga aytaman")
    answers = recruiting_repo.get_answers(application_id)
    assert len(answers) == 1
    assert answers[0]["answer_source"] == "text"


def test_get_in_progress_application_returns_only_in_progress_status():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    retention = recruiting_privacy.compute_retention_expiry()
    application_id = recruiting_repo.create_application(777, kassir["id"], retention)

    assert recruiting_repo.get_in_progress_application(777)["id"] == application_id

    recruiting_repo.cancel_application(application_id)
    assert recruiting_repo.get_in_progress_application(777) is None


def test_increment_follow_up_count_is_sequential():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    application_id = recruiting_repo.create_application(888, kassir["id"], recruiting_privacy.compute_retention_expiry())

    assert recruiting_repo.increment_follow_up_count(application_id) == 1
    assert recruiting_repo.increment_follow_up_count(application_id) == 2


def test_set_founder_decision_marks_reviewed_and_records_actor():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    application_id = recruiting_repo.create_application(999, kassir["id"], recruiting_privacy.compute_retention_expiry())

    recruiting_repo.set_founder_decision(application_id, "interview", decided_by=34213422)

    application = recruiting_repo.get_application(application_id)
    assert application["status"] == "reviewed"
    assert application["founder_decision"] == "interview"
    assert application["founder_decision_by"] == 34213422
    assert application["founder_decision_at"] is not None


def test_save_assessment_sets_status_awaiting_review():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    application_id = recruiting_repo.create_application(111, kassir["id"], recruiting_privacy.compute_retention_expiry())
    rubric_id = recruiting_repo.create_rubric_version("kassir", 1, [{"key": "x", "label": "X"}])

    recruiting_repo.save_assessment(
        application_id, rubric_id, "INTERVIEW_RECOMMENDED", [{"key": "x", "score": 2, "evidence": "y"}], ["y"], [], "xulosa", "ai"
    )

    application = recruiting_repo.get_application(application_id)
    assert application["status"] == "awaiting_review"

    assessment = recruiting_repo.get_assessment(application_id)
    assert assessment["overall_result"] == "INTERVIEW_RECOMMENDED"
    assert assessment["source"] == "ai"


def test_create_rubric_version_is_idempotent_and_returns_same_id():
    first_id = recruiting_repo.create_rubric_version("sotuvchi", 1, [{"key": "a", "label": "A"}])
    second_id = recruiting_repo.create_rubric_version("sotuvchi", 1, [{"key": "a", "label": "A"}])
    assert first_id == second_id


# --------------------------------------------------------------- retention --


def test_purge_application_removes_answers_and_assessment_too():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    application_id = recruiting_repo.create_application(222, kassir["id"], recruiting_privacy.compute_retention_expiry())
    recruiting_repo.add_answer(application_id, "kassir_kamomad", "Savol?", "Javob")
    rubric_id = recruiting_repo.create_rubric_version("kassir", 1, [{"key": "x", "label": "X"}])
    recruiting_repo.save_assessment(application_id, rubric_id, "INTERVIEW_RECOMMENDED", [], [], [], None, "deterministic")

    recruiting_repo.purge_application(application_id)

    assert recruiting_repo.get_application(application_id) is None
    assert recruiting_repo.get_answers(application_id) == []
    assert recruiting_repo.get_assessment(application_id) is None


def test_list_applications_past_retention_only_returns_expired():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    past_id = recruiting_repo.create_application(333, kassir["id"], "2000-01-01T00:00:00+00:00")
    future_id = recruiting_repo.create_application(444, kassir["id"], "2099-01-01T00:00:00+00:00")

    expired = recruiting_repo.list_applications_past_retention()
    expired_ids = {a["id"] for a in expired}

    assert past_id in expired_ids
    assert future_id not in expired_ids


def test_purge_expired_applications_deletes_only_expired_ones():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    past_id = recruiting_repo.create_application(555555, kassir["id"], "2000-01-01T00:00:00+00:00")
    future_id = recruiting_repo.create_application(666666, kassir["id"], "2099-01-01T00:00:00+00:00")

    purged_count = recruiting_privacy.purge_expired_applications()

    assert purged_count >= 1
    assert recruiting_repo.get_application(past_id) is None
    assert recruiting_repo.get_application(future_id) is not None


def test_delete_application_now_removes_regardless_of_retention():
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    application_id = recruiting_repo.create_application(777777, kassir["id"], "2099-01-01T00:00:00+00:00")

    assert recruiting_privacy.delete_application_now(application_id) is True
    assert recruiting_repo.get_application(application_id) is None
    assert recruiting_privacy.delete_application_now(application_id) is False
