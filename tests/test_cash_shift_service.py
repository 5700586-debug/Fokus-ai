import pytest

from services import cash_shift


def _open(employee_id: int = 1, shift_date: str = "2026-01-01", manual_opening: int | None = 0) -> dict:
    return cash_shift.open_shift_for_today(employee_id, "Filial-1", shift_date, manual_opening)


def test_opening_balance_does_not_count_as_sales():
    shift = _open(manual_opening=500_000)

    result = cash_shift.submit_close_attempt(
        shift["id"], cash_sales=4_200_000, card_sales=4_100_000, other_payments=150_000,
        cash_expenses=350_000, actual_cash_balance=4_350_000,
    )

    # total_sales kechagi 500_000'ni o'z ichiga olmasligi kerak
    assert result.total_sales == 4_200_000 + 4_100_000 + 150_000


def test_expected_cash_formula_uses_opening_balance():
    shift = _open(manual_opening=500_000)

    result = cash_shift.submit_close_attempt(
        shift["id"], cash_sales=4_200_000, card_sales=4_100_000, other_payments=150_000,
        cash_expenses=350_000, actual_cash_balance=4_350_000,
    )

    assert result.expected_cash_balance == 500_000 + 4_200_000 - 350_000


def test_difference_formula_matches_spec_example():
    shift = _open(manual_opening=500_000)

    result = cash_shift.submit_close_attempt(
        shift["id"], cash_sales=4_200_000, card_sales=0, other_payments=0,
        cash_expenses=350_000, actual_cash_balance=4_320_000,
    )

    assert result.expected_cash_balance == 4_350_000
    assert result.difference == -30_000


def test_zero_difference_is_clean_closed():
    shift = _open(manual_opening=0)

    result = cash_shift.submit_close_attempt(
        shift["id"], cash_sales=100_000, card_sales=0, other_payments=0,
        cash_expenses=0, actual_cash_balance=100_000,
    )

    assert result.difference == 0
    # Toza chiqsa ham smena darhol yopilmaydi — qabul qiluvchi kassir
    # mustaqil sanab tasdiqlagunicha PENDING_HANDOVER'da qoladi.
    assert result.status == cash_shift.STATUS_PENDING_HANDOVER
    assert result.finalized is True


def test_difference_within_tolerance():
    shift = _open(manual_opening=0)
    # default tolerance = 20_000 (rules seed)

    result = cash_shift.submit_close_attempt(
        shift["id"], cash_sales=100_000, card_sales=0, other_payments=0,
        cash_expenses=0, actual_cash_balance=100_000 - 15_000,
    )

    assert result.status == cash_shift.STATUS_PENDING_HANDOVER
    assert result.finalized is True


def test_difference_outside_tolerance_requires_recheck():
    shift = _open(manual_opening=0)

    result = cash_shift.submit_close_attempt(
        shift["id"], cash_sales=100_000, card_sales=0, other_payments=0,
        cash_expenses=0, actual_cash_balance=100_000 - 50_000,
    )

    assert result.status == cash_shift.STATUS_RECHECK_REQUIRED
    assert result.finalized is False
    assert result.retries_left == 2  # retry_limit(3) - 1


def test_negative_difference():
    shift = _open(manual_opening=0)

    result = cash_shift.submit_close_attempt(
        shift["id"], cash_sales=100_000, card_sales=0, other_payments=0,
        cash_expenses=0, actual_cash_balance=90_000,
    )

    assert result.difference == -10_000


def test_positive_difference():
    shift = _open(manual_opening=0)

    result = cash_shift.submit_close_attempt(
        shift["id"], cash_sales=100_000, card_sales=0, other_payments=0,
        cash_expenses=0, actual_cash_balance=110_000,
    )

    assert result.difference == 10_000


def test_retry_limit_escalates_to_supervisor():
    shift = _open(manual_opening=0)

    for _ in range(3):
        result = cash_shift.submit_close_attempt(
            shift["id"], cash_sales=100_000, card_sales=0, other_payments=0,
            cash_expenses=0, actual_cash_balance=100_000 - 50_000,
        )

    assert result.status == cash_shift.STATUS_NEEDS_SUPERVISOR_APPROVAL
    assert result.needs_supervisor is True


def test_kassir_cannot_retry_after_escalated_to_supervisor():
    shift = _open(manual_opening=0)
    for _ in range(3):
        cash_shift.submit_close_attempt(
            shift["id"], cash_sales=100_000, card_sales=0, other_payments=0,
            cash_expenses=0, actual_cash_balance=50_000,
        )

    with pytest.raises(ValueError):
        cash_shift.submit_close_attempt(
            shift["id"], cash_sales=100_000, card_sales=0, other_payments=0,
            cash_expenses=0, actual_cash_balance=100_000,
        )


def test_supervisor_approve_finalizes_shift():
    shift = _open(manual_opening=0)
    for _ in range(3):
        cash_shift.submit_close_attempt(
            shift["id"], cash_sales=100_000, card_sales=0, other_payments=0,
            cash_expenses=0, actual_cash_balance=50_000,
        )

    cash_shift.apply_supervisor_decision(shift["id"], reviewed_by=999, decision="approved", comment="OK")

    updated = cash_shift.get_shift(shift["id"])
    assert updated["status"] == cash_shift.STATUS_APPROVED_BY_SUPERVISOR
    assert updated["closed_at"] is not None


def test_supervisor_recheck_lets_kassir_try_again():
    shift = _open(manual_opening=0)
    for _ in range(3):
        cash_shift.submit_close_attempt(
            shift["id"], cash_sales=100_000, card_sales=0, other_payments=0,
            cash_expenses=0, actual_cash_balance=50_000,
        )

    cash_shift.apply_supervisor_decision(shift["id"], reviewed_by=999, decision="recheck", comment="Qayta tekshiring")

    result = cash_shift.submit_close_attempt(
        shift["id"], cash_sales=100_000, card_sales=0, other_payments=0,
        cash_expenses=0, actual_cash_balance=100_000,
    )
    assert result.finalized is True
    assert result.status == cash_shift.STATUS_PENDING_HANDOVER


def test_duplicate_close_after_finalized_raises():
    shift = _open(manual_opening=0)
    cash_shift.submit_close_attempt(
        shift["id"], cash_sales=100_000, card_sales=0, other_payments=0,
        cash_expenses=0, actual_cash_balance=100_000,
    )

    with pytest.raises(ValueError):
        cash_shift.submit_close_attempt(
            shift["id"], cash_sales=100_000, card_sales=0, other_payments=0,
            cash_expenses=0, actual_cash_balance=100_000,
        )


def test_opening_shift_twice_same_day_reuses_shift():
    first = _open(manual_opening=0)
    second = cash_shift.open_shift_for_today(1, "Filial-1", "2026-01-01", 999_999)

    assert first["id"] == second["id"]
    assert second["opening_balance"] == 0


def test_next_day_opening_balance_carries_forward_from_yesterday_actual():
    yesterday = _open(1, "2026-01-01", manual_opening=500_000)
    cash_shift.submit_close_attempt(
        yesterday["id"], cash_sales=100_000, card_sales=0, other_payments=0,
        cash_expenses=0, actual_cash_balance=600_000,
    )

    assert cash_shift.is_first_ever_shift("Filial-1") is False

    today = cash_shift.open_shift_for_today(1, "Filial-1", "2026-01-02")
    assert today["opening_balance"] == 600_000


def test_is_first_ever_shift_true_before_any_closed_shift():
    assert cash_shift.is_first_ever_shift("Filial-Nonexistent") is True
