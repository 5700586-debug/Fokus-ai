"""``services/recruiting_fit.py`` — "talab mosligi" filtri testlari.
ATAYLAB baholash rubrikasidan alohida: mos kelmaslik axloqiy kamchilik
emas, faqat vakansiyaning e'lon qilingan talabiga texnik moslik."""

from datetime import date

from services import recruiting_fit as fit


def _vacancy(required_shift=None, requires_weekends=False):
    return {"required_shift": required_shift, "requires_weekends": requires_weekends}


# --------------------------------------------------------------------- yosh --


def test_underage_candidate_is_mismatch():
    this_year = date.today().year
    ok, reason = fit.check_min_age(birth_year=this_year - 15, min_age=18)
    assert ok is False
    assert reason is not None


def test_adult_candidate_passes_age_check():
    this_year = date.today().year
    ok, reason = fit.check_min_age(birth_year=this_year - 25, min_age=18)
    assert ok is True
    assert reason is None


def test_missing_birth_year_does_not_force_mismatch():
    """Noaniq holat avtomatik "mos emas" deb hukm qilinmaydi."""
    ok, reason = fit.check_min_age(birth_year=None, min_age=18)
    assert ok is True


# ------------------------------------------------------------------- smena --


def test_shift_mismatch_when_vacancy_requires_specific_shift():
    ok, reason = fit.check_shift("kunduzgi", required_shift="kechki")
    assert ok is False
    assert "kechki" in reason


def test_shift_any_preference_always_matches_required_shift():
    ok, _ = fit.check_shift(fit.SHIFT_ANY, required_shift="kechki")
    assert ok is True


def test_shift_no_requirement_configured_always_matches():
    ok, _ = fit.check_shift("kunduzgi", required_shift=None)
    assert ok is True


def test_shift_missing_candidate_preference_does_not_force_mismatch():
    ok, _ = fit.check_shift(None, required_shift="kechki")
    assert ok is True


# ---------------------------------------------------------------- bayramlar --


def test_weekend_requirement_mismatch_when_candidate_cannot_work_holidays():
    ok, reason = fit.check_weekends(holiday_available=0, requires_weekends=True)
    assert ok is False
    assert reason is not None


def test_weekend_requirement_satisfied_when_candidate_can_work_holidays():
    ok, _ = fit.check_weekends(holiday_available=1, requires_weekends=True)
    assert ok is True


def test_no_weekend_requirement_always_matches():
    ok, _ = fit.check_weekends(holiday_available=0, requires_weekends=False)
    assert ok is True


# ------------------------------------------------------------- compute_fit --


def test_compute_fit_returns_fit_when_all_checks_pass():
    result, reason = fit.compute_fit(
        birth_year=date.today().year - 25,
        shift_preference="kunduzgi",
        holiday_available=1,
        vacancy=_vacancy(),
        min_age=18,
    )
    assert result == fit.FIT
    assert reason is None


def test_compute_fit_returns_mismatch_and_reason_on_age_violation():
    result, reason = fit.compute_fit(
        birth_year=date.today().year - 14,
        shift_preference="kunduzgi",
        holiday_available=1,
        vacancy=_vacancy(),
        min_age=18,
    )
    assert result == fit.MISMATCH
    assert reason


def test_compute_fit_returns_mismatch_on_shift_violation():
    result, reason = fit.compute_fit(
        birth_year=date.today().year - 25,
        shift_preference="kunduzgi",
        holiday_available=1,
        vacancy=_vacancy(required_shift="kechki"),
        min_age=18,
    )
    assert result == fit.MISMATCH
    assert reason
