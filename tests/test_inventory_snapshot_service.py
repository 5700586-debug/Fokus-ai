from services import inventory_snapshot as inv


def test_first_snapshot_has_no_gross_difference_and_is_normal():
    outcome = inv.create_snapshot_for_today("Filial-1", "2026-01-01", reported_by_employee_id=1, total_inventory_value=120_000_000, photo_reference="p1")

    assert outcome.already_existed is False
    assert outcome.needs_cause_explanation is False
    assert outcome.snapshot["gross_difference"] is None
    assert outcome.snapshot["status"] == inv.STATUS_NORMAL


def test_second_day_computes_gross_difference():
    inv.create_snapshot_for_today("Filial-1", "2026-01-01", 1, 120_000_000, None)
    outcome = inv.create_snapshot_for_today("Filial-1", "2026-01-02", 1, 126_500_000, None)

    assert outcome.snapshot["gross_difference"] == 6_500_000
    assert outcome.needs_cause_explanation is True


def test_no_change_from_yesterday_is_normal_without_causes():
    inv.create_snapshot_for_today("Filial-1", "2026-01-01", 1, 120_000_000, None)
    outcome = inv.create_snapshot_for_today("Filial-1", "2026-01-02", 1, 120_000_000, None)

    assert outcome.snapshot["gross_difference"] == 0
    assert outcome.needs_cause_explanation is False
    assert outcome.snapshot["status"] == inv.STATUS_NORMAL


def test_duplicate_snapshot_same_day_does_not_overwrite():
    first = inv.create_snapshot_for_today("Filial-1", "2026-01-01", 1, 120_000_000, None)
    second = inv.create_snapshot_for_today("Filial-1", "2026-01-01", 1, 999_000_000, None)

    assert second.already_existed is True
    assert second.snapshot["id"] == first.snapshot["id"]
    assert second.snapshot["total_inventory_value"] == 120_000_000


def test_fully_explained_variance_is_normal():
    inv.create_snapshot_for_today("Filial-1", "2026-01-01", 1, 120_000_000, None)
    outcome = inv.create_snapshot_for_today("Filial-1", "2026-01-02", 1, 126_500_000, None)
    snapshot_id = outcome.snapshot["id"]

    inv.add_cause_and_recompute(snapshot_id, "prixod", 6_000_000, None)
    result = inv.add_cause_and_recompute(snapshot_id, "boshqa", 500_000, "Narx tuzatildi")

    assert result.explained_variance == 6_500_000
    assert result.unexplained_variance == 0
    assert result.status == inv.STATUS_NORMAL


def test_unexplained_within_threshold_needs_review():
    inv.create_snapshot_for_today("Filial-1", "2026-01-01", 1, 120_000_000, None)
    outcome = inv.create_snapshot_for_today("Filial-1", "2026-01-02", 1, 120_500_000, None)  # +500_000

    result = inv.add_cause_and_recompute(outcome.snapshot["id"], "boshqa", 0, "Hali aniqlanmadi")

    assert result.unexplained_variance == 500_000  # threshold(default 1_000_000) ichida
    assert result.status == inv.STATUS_NEEDS_REVIEW


def test_unexplained_beyond_threshold_is_urgent():
    inv.create_snapshot_for_today("Filial-1", "2026-01-01", 1, 120_000_000, None)
    outcome = inv.create_snapshot_for_today("Filial-1", "2026-01-02", 1, 122_400_000, None)  # +2_400_000

    result = inv.add_cause_and_recompute(outcome.snapshot["id"], "boshqa", 0, None)

    assert result.unexplained_variance == 2_400_000  # threshold(1_000_000)dan katta
    assert result.status == inv.STATUS_URGENT_REVIEW


def test_unknown_cause_rejected():
    outcome = inv.create_snapshot_for_today("Filial-1", "2026-01-01", 1, 120_000_000, None)
    inv.create_snapshot_for_today("Filial-1", "2026-01-02", 1, 121_000_000, None)

    import pytest

    with pytest.raises(ValueError):
        inv.add_cause_and_recompute(outcome.snapshot["id"], "sababsiz", 100, None)


def test_different_branches_have_independent_history():
    inv.create_snapshot_for_today("Filial-1", "2026-01-01", 1, 100, None)
    outcome_b = inv.create_snapshot_for_today("Filial-2", "2026-01-01", 2, 999, None)

    assert outcome_b.snapshot["gross_difference"] is None
