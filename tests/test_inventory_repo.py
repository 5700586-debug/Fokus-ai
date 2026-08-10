from repositories import inventory as repo


def test_create_snapshot_first_time_has_no_previous():
    snapshot = repo.create_snapshot(
        "Filial-1", "2026-01-01", reported_by_employee_id=1,
        total_inventory_value=120_000_000, previous_inventory_value=None,
        gross_difference=None, threshold=1_000_000, photo_reference="photo1",
    )

    assert snapshot["previous_inventory_value"] is None
    assert snapshot["status"] == "pending"

    assert repo.get_previous_snapshot("Filial-1", "2026-01-01") is None


def test_create_snapshot_is_idempotent_for_same_day():
    first = repo.create_snapshot(
        "Filial-1", "2026-01-01", reported_by_employee_id=1,
        total_inventory_value=120_000_000, previous_inventory_value=None,
        gross_difference=None, threshold=1_000_000, photo_reference="photo1",
    )
    second = repo.create_snapshot(
        "Filial-1", "2026-01-01", reported_by_employee_id=1,
        total_inventory_value=999_000_000, previous_inventory_value=None,
        gross_difference=None, threshold=1_000_000, photo_reference="photo2",
    )

    assert first["id"] == second["id"]
    assert second["total_inventory_value"] == 120_000_000


def test_get_previous_snapshot_finds_most_recent_before_date():
    repo.create_snapshot(
        "Filial-1", "2026-01-01", reported_by_employee_id=1,
        total_inventory_value=120_000_000, previous_inventory_value=None,
        gross_difference=None, threshold=1_000_000, photo_reference=None,
    )
    repo.create_snapshot(
        "Filial-1", "2026-01-02", reported_by_employee_id=1,
        total_inventory_value=126_500_000, previous_inventory_value=120_000_000,
        gross_difference=6_500_000, threshold=1_000_000, photo_reference=None,
    )

    previous = repo.get_previous_snapshot("Filial-1", "2026-01-02")
    assert previous["total_inventory_value"] == 120_000_000


def test_different_branches_do_not_collide():
    repo.create_snapshot(
        "Filial-1", "2026-01-01", reported_by_employee_id=1,
        total_inventory_value=100, previous_inventory_value=None,
        gross_difference=None, threshold=1_000_000, photo_reference=None,
    )
    snapshot_b = repo.create_snapshot(
        "Filial-2", "2026-01-01", reported_by_employee_id=2,
        total_inventory_value=200, previous_inventory_value=None,
        gross_difference=None, threshold=1_000_000, photo_reference=None,
    )

    assert snapshot_b["total_inventory_value"] == 200


def test_update_snapshot_variance():
    snapshot = repo.create_snapshot(
        "Filial-1", "2026-01-01", reported_by_employee_id=1,
        total_inventory_value=100, previous_inventory_value=None,
        gross_difference=None, threshold=1_000_000, photo_reference=None,
    )

    repo.update_snapshot_variance(snapshot["id"], explained_variance=500_000, unexplained_variance=0, status="normal")

    updated = repo.get_snapshot(snapshot["id"])
    assert updated["explained_variance"] == 500_000
    assert updated["status"] == "normal"


def test_variance_explanations_recorded_in_order():
    snapshot = repo.create_snapshot(
        "Filial-1", "2026-01-01", reported_by_employee_id=1,
        total_inventory_value=100, previous_inventory_value=None,
        gross_difference=None, threshold=1_000_000, photo_reference=None,
    )

    repo.add_variance_explanation(snapshot["id"], "prixod", 5_000_000, None)
    repo.add_variance_explanation(snapshot["id"], "boshqa", 300_000, "Narx tuzatildi")

    explanations = repo.get_variance_explanations(snapshot["id"])
    assert [e["cause"] for e in explanations] == ["prixod", "boshqa"]
    assert sum(e["amount"] for e in explanations) == 5_300_000


def test_variance_review_recorded():
    snapshot = repo.create_snapshot(
        "Filial-1", "2026-01-01", reported_by_employee_id=1,
        total_inventory_value=100, previous_inventory_value=None,
        gross_difference=None, threshold=1_000_000, photo_reference=None,
    )

    repo.record_variance_review(snapshot["id"], reviewed_by=999, decision="approved", comment=None)
    # FK buzilmasdan yozilgani yetarli — o'qish uchun alohida getter hozircha yo'q.
