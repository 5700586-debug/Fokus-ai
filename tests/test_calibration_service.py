from services import calibration


def test_ensure_session_creates_with_default_start_date_today():
    from datetime import date

    session = calibration.ensure_session(111, "taminotchi")
    assert session["start_date"] == date.today().isoformat()


def test_ensure_session_is_idempotent_and_keeps_first_start_date():
    first = calibration.ensure_session(111, "taminotchi", start_date="2026-01-01")
    second = calibration.ensure_session(111, "taminotchi", start_date="2026-06-01")

    assert first["id"] == second["id"]
    assert second["start_date"] == "2026-01-01"


def test_build_daily_question_plan_respects_quota():
    plan = calibration.build_daily_question_plan(111, "taminotchi", "2026-01-01")
    assert len(plan) in calibration.DAILY_QUESTION_QUOTA_CHOICES


def test_build_daily_question_plan_is_deterministic_for_same_user_and_date():
    plan1 = calibration.build_daily_question_plan(111, "taminotchi", "2026-01-01")
    plan2 = calibration.build_daily_question_plan(111, "taminotchi", "2026-01-01")

    assert plan1 == plan2


def test_build_daily_question_plan_differs_for_different_dates():
    plan1 = calibration.build_daily_question_plan(111, "taminotchi", "2026-01-01")
    plan2 = calibration.build_daily_question_plan(111, "taminotchi", "2026-01-02")

    # Ehtimoli juda yuqori — turli kunlar turli tartib/savol beradi.
    assert plan1 != plan2 or plan1[0]["dimension"] != plan2[0]["dimension"]


def test_build_daily_question_plan_dimensions_from_role_candidates():
    plan = calibration.build_daily_question_plan(111, "taminotchi", "2026-01-01")
    dims = {q["dimension"] for q in plan}
    assert dims <= set(calibration.TAMINOTCHI_KPI_CANDIDATES)


def test_build_daily_question_plan_no_duplicate_dimensions_same_day():
    plan = calibration.build_daily_question_plan(111, "haydovchi", "2026-01-01")
    dims = [q["dimension"] for q in plan]
    assert len(dims) == len(set(dims))


def test_build_daily_question_plan_cross_check_takes_first_slot():
    plan = calibration.build_daily_question_plan(111, "taminotchi", "2026-01-01", cross_check_available=True)

    assert plan[0]["dimension"] == calibration.CROSS_CHECK_DIMENSION
    assert plan[0]["question_text"] == calibration.CROSS_CHECK_QUESTION_TEXT
    assert plan[0]["is_cross_check"] is True


def test_cross_check_question_text_identical_for_both_roles():
    taminotchi_plan = calibration.build_daily_question_plan(1, "taminotchi", "2026-01-01", cross_check_available=True)
    haydovchi_plan = calibration.build_daily_question_plan(2, "haydovchi", "2026-01-01", cross_check_available=True)

    assert taminotchi_plan[0]["question_text"] == haydovchi_plan[0]["question_text"]


def test_is_vague_answer_matches_learning_service():
    assert calibration.is_vague_answer("ha") is True
    assert calibration.is_vague_answer("ok") is True
    assert calibration.is_vague_answer("Bugun 3 ta bozorga bordim va narxlarni solishtirdim") is False


def test_build_follow_up_text_mentions_dimension():
    text = calibration.build_follow_up_text("narx solishtirish")
    assert "narx solishtirish" in text


def test_build_follow_up_text_for_cross_check_dimension():
    text = calibration.build_follow_up_text(calibration.CROSS_CHECK_DIMENSION)
    assert "bozor" in text.lower()


def test_unknown_dimension_falls_back_to_generic_question_text():
    plan = calibration.build_daily_question_plan(111, "moliyachi", "2026-01-01")
    assert plan == []  # get_kpi_candidates noma'lum rol uchun bo'sh ro'yxat qaytaradi
