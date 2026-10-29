from repositories import discipline as discipline_repo
from services import payroll_view as pv
from tests.test_payroll_view import _agreement, _evaluation, EMP, MONTH


def test_ungraded_day_does_not_reduce_bonus_and_zero_is_a_real_record(temp_db):
    _agreement()
    _evaluation("2026-09-02", 3)
    initial = pv.month_view(EMP, MONTH)
    assert initial["work_bonus"] == 3
    assert discipline_repo.count_graded_dates("2026-09-01", "2026-10-01") == 1
    _evaluation("2026-09-03", 0)
    updated = pv.month_view(EMP, MONTH)
    assert updated["work_bonus"] == 3
    assert discipline_repo.count_graded_dates("2026-09-01", "2026-10-01") == 2
    assert discipline_repo.count_graded_dates("2026-09-04", "2026-10-01") == 0
