from services import calibration


def test_day_number_since():
    assert calibration.day_number_since("2026-01-01", today="2026-01-01") == 1
    assert calibration.day_number_since("2026-01-01", today="2026-01-10") == 10


def test_is_within_calibration_window():
    assert calibration.is_within_calibration_window("2026-01-01", today="2026-02-01") is True
    assert calibration.is_within_calibration_window("2026-01-01", today="2026-05-01") is False


def test_is_within_adaptation_window():
    assert calibration.is_within_adaptation_window("2026-01-01", today="2026-01-15") is True
    assert calibration.is_within_adaptation_window("2026-01-01", today="2026-02-15") is False


def test_get_kpi_candidates_by_role():
    assert "bozorni o'rganish" in calibration.get_kpi_candidates("taminotchi")
    assert "avtomobil tozaligi" in calibration.get_kpi_candidates("haydovchi")
    assert calibration.get_kpi_candidates("unknown_role") == []


def test_record_and_get_role_baselines():
    calibration.record_role_baseline("taminotchi", "narx solishtirish", "Bozorda 3 ta do'kondan narx so'radi")

    baselines = calibration.get_role_baselines("taminotchi")
    assert len(baselines) == 1
    assert baselines[0]["dimension"] == "narx solishtirish"


def test_record_and_get_adaptation_profile():
    calibration.record_adaptation_rating(
        user_id=1,
        role_key="haydovchi",
        start_date="2026-01-01",
        dimension="avtomobil tozaligi",
        rating="yaxshi",
        today="2026-01-10",
    )

    profile = calibration.get_adaptation_profile(1)
    assert len(profile) == 1
    assert profile[0]["day_number"] == 10
    assert profile[0]["rating"] == "yaxshi"
