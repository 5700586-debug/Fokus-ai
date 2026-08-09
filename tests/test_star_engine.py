from services import star_engine


def _inputs(full_bonus: bool) -> star_engine.MonthInputs:
    if full_bonus:
        return star_engine.MonthInputs(
            avg_supervisor_score=90,
            attendance_ok=True,
            no_serious_violation=True,
            checklist_completed=True,
        )
    return star_engine.MonthInputs(
        avg_supervisor_score=50,
        attendance_ok=False,
        no_serious_violation=True,
        checklist_completed=True,
    )


def test_full_bonus_month_increments_star():
    result = star_engine.process_month(1, "2026-01", _inputs(full_bonus=True))

    assert result.already_processed is False
    assert result.full_bonus_month is True
    assert result.previous_stars == 0
    assert result.new_stars == 1
    assert result.bonus_amount == 50000


def test_failed_month_decrements_star_not_below_zero():
    result = star_engine.process_month(2, "2026-01", _inputs(full_bonus=False))

    assert result.full_bonus_month is False
    assert result.previous_stars == 0
    assert result.new_stars == 0
    assert result.bonus_amount == 0


def test_stars_do_not_exceed_max():
    user_id = 3
    for i in range(7):
        star_engine.process_month(user_id, f"2026-{i + 1:02d}", _inputs(full_bonus=True))

    assert star_engine.get_current_stars(user_id) == 5


def test_processing_same_month_twice_is_idempotent():
    user_id = 4
    first = star_engine.process_month(user_id, "2026-01", _inputs(full_bonus=True))
    second = star_engine.process_month(user_id, "2026-01", _inputs(full_bonus=True))

    assert first.already_processed is False
    assert second.already_processed is True
    assert star_engine.get_current_stars(user_id) == 1


def test_star_and_bonus_history_recorded():
    user_id = 5
    star_engine.process_month(user_id, "2026-01", _inputs(full_bonus=True))

    star_history = star_engine.get_star_history(user_id)
    bonus_history = star_engine.get_bonus_history(user_id)

    assert len(star_history) == 1
    assert star_history[0]["new_stars"] == 1
    assert len(bonus_history) == 1
    assert bonus_history[0]["bonus_amount"] == 50000
