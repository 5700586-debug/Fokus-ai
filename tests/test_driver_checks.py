import pytest

from repositories import vehicles as vehicles_repo
from services import driver_checks


def _make_vehicle(driver_id: int = 1) -> dict:
    vehicle_id = vehicles_repo.create_vehicle("01A123BC", "Damas", driver_id)
    return vehicles_repo.get_vehicle_for_driver(driver_id)


def test_record_daily_check_success():
    vehicle = _make_vehicle()

    result = driver_checks.record_daily_check(
        driver_id=1,
        check_date="2026-01-01",
        exterior_photo_ref="photo_ext",
        interior_photo_ref="photo_int",
        start_km=1000,
        end_km=1050,
    )

    assert result["vehicle"]["id"] == vehicle["id"]
    assert result["check_id"] is not None


def test_record_daily_check_no_vehicle_raises():
    with pytest.raises(ValueError):
        driver_checks.record_daily_check(
            driver_id=999,
            check_date="2026-01-01",
            exterior_photo_ref=None,
            interior_photo_ref=None,
            start_km=None,
            end_km=None,
        )


def test_end_km_less_than_start_km_raises():
    _make_vehicle()

    with pytest.raises(ValueError):
        driver_checks.record_daily_check(
            driver_id=1,
            check_date="2026-01-01",
            exterior_photo_ref=None,
            interior_photo_ref=None,
            start_km=1000,
            end_km=900,
        )


def test_needs_oil_change_reminder():
    vehicle = _make_vehicle()
    driver_checks.record_service(
        vehicle_id=vehicle["id"],
        service_date="2026-01-01",
        oil_change_km=1000,
        service_type="moy almashtirish",
        notes=None,
        next_service_km=None,
        next_service_date=None,
    )

    assert driver_checks.needs_oil_change_reminder(vehicle["id"], current_km=6500) is True
    assert driver_checks.needs_oil_change_reminder(vehicle["id"], current_km=4000) is False
