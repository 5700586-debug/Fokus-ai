from services import meal_plan


def test_set_and_get_meal_for_date():
    meal_plan.set_meal_for_date("2026-01-01", "Osh", entered_by=1)

    result = meal_plan.get_meal_for_date("2026-01-01")
    assert result["meal_description"] == "Osh"


def test_is_meal_missing_true_when_unset():
    assert meal_plan.is_meal_missing("2026-01-02") is True


def test_setting_same_date_twice_overwrites():
    meal_plan.set_meal_for_date("2026-01-01", "Osh", entered_by=1)
    meal_plan.set_meal_for_date("2026-01-01", "Lag'mon", entered_by=1)

    result = meal_plan.get_meal_for_date("2026-01-01")
    assert result["meal_description"] == "Lag'mon"
