from repositories import cash_shifts as cash_shifts_repo
from services import shift_daily_report


def _open_shift(employee_id: int, branch: str, shift_date: str) -> dict:
    return cash_shifts_repo.open_shift(employee_id, branch, shift_date, opening_balance=0, tolerance=20000)


def test_save_no_prixod_count_zero_for_none_option():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    assert shift_daily_report.save_no_prixod_count(shift["id"], 0) is True

    row = shift_daily_report.get_next_step(shift["id"])
    assert row == shift_daily_report.STEP_PRICE_COMPLAINT


def test_save_no_prixod_count_direct_1_to_5():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    assert shift_daily_report.save_no_prixod_count(shift["id"], 3) is True


def test_save_no_prixod_count_rejects_negative():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    assert shift_daily_report.save_no_prixod_count(shift["id"], -1) is False


def test_save_no_prixod_count_unknown_shift_returns_false():
    assert shift_daily_report.save_no_prixod_count(999999, 3) is False


def test_is_no_prixod_signal_threshold():
    assert shift_daily_report.is_no_prixod_signal(4) is False
    assert shift_daily_report.is_no_prixod_signal(5) is True
    assert shift_daily_report.is_no_prixod_signal(12) is True


def test_save_price_complaint_bucket_valid_and_invalid():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    assert shift_daily_report.save_price_complaint_bucket(shift["id"], "6-10") is True
    assert shift_daily_report.save_price_complaint_bucket(shift["id"], "invalid") is False


def test_save_staff_complaint_none():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    assert shift_daily_report.save_staff_complaint_none(shift["id"]) is True


def test_save_staff_complaint_rejects_unknown_type():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    assert shift_daily_report.save_staff_complaint(shift["id"], 2, "unknown_type") is False


def test_save_staff_complaint_other_requires_note():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    assert shift_daily_report.save_staff_complaint(
        shift["id"], 2, shift_daily_report.COMPLAINT_TYPE_OTHER, note="   "
    ) is False
    assert shift_daily_report.save_staff_complaint(
        shift["id"], 2, shift_daily_report.COMPLAINT_TYPE_OTHER, note="Erta ketib qoldi"
    ) is True


def test_save_staff_complaint_known_type_ignores_note():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    assert shift_daily_report.save_staff_complaint(shift["id"], 2, shift_daily_report.COMPLAINT_TYPE_RUDE) is True


def test_get_next_step_progresses_through_all_three_questions():
    shift = _open_shift(1, "Filial-1", "2026-01-05")

    assert shift_daily_report.get_next_step(shift["id"]) == shift_daily_report.STEP_NO_PRIXOD
    shift_daily_report.save_no_prixod_count(shift["id"], 0)

    assert shift_daily_report.get_next_step(shift["id"]) == shift_daily_report.STEP_PRICE_COMPLAINT
    shift_daily_report.save_price_complaint_bucket(shift["id"], "0")

    assert shift_daily_report.get_next_step(shift["id"]) == shift_daily_report.STEP_STAFF_COMPLAINT
    shift_daily_report.save_staff_complaint_none(shift["id"])

    assert shift_daily_report.get_next_step(shift["id"]) == shift_daily_report.STEP_DONE
    assert shift_daily_report.is_flow_complete(shift["id"]) is True


def test_is_flow_complete_false_until_all_three_answered():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    assert shift_daily_report.is_flow_complete(shift["id"]) is False

    shift_daily_report.save_no_prixod_count(shift["id"], 0)
    shift_daily_report.save_price_complaint_bucket(shift["id"], "0")
    assert shift_daily_report.is_flow_complete(shift["id"]) is False  # xodim shikoyati hali yo'q


def test_no_prixod_answer_does_not_overwrite_other_answers():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    shift_daily_report.save_no_prixod_count(shift["id"], 7)
    shift_daily_report.save_price_complaint_bucket(shift["id"], "10+")
    shift_daily_report.save_staff_complaint(shift["id"], 5, shift_daily_report.COMPLAINT_TYPE_SLOW)

    from repositories import shift_daily_report as repo

    row = repo.get(shift["id"])
    assert row["no_prixod_count"] == 7
    assert row["price_complaint_bucket"] == "10+"
    assert row["staff_complaint_occurred"] == 1
    assert row["staff_complaint_employee_id"] == 5
    assert row["staff_complaint_type"] == shift_daily_report.COMPLAINT_TYPE_SLOW
    assert row["staff_complaint_note"] is None


def test_each_shift_has_its_own_independent_report():
    shift_a = _open_shift(1, "Filial-1", "2026-01-05")
    shift_b = _open_shift(2, "Filial-1", "2026-01-06")

    shift_daily_report.save_no_prixod_count(shift_a["id"], 9)

    assert shift_daily_report.get_next_step(shift_a["id"]) == shift_daily_report.STEP_PRICE_COMPLAINT
    assert shift_daily_report.get_next_step(shift_b["id"]) == shift_daily_report.STEP_NO_PRIXOD
