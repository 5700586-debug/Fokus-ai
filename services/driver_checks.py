"""Haydovchi kunlik nazorati va avtomobil servis tarixi."""

from repositories import vehicles as vehicles_repo
from services import rules as rules_service


def record_daily_check(
    driver_id: int,
    check_date: str,
    exterior_photo_ref: str | None,
    interior_photo_ref: str | None,
    start_km: int | None,
    end_km: int | None,
    notes: str | None = None,
) -> dict:
    vehicle = vehicles_repo.get_vehicle_for_driver(driver_id)
    if vehicle is None:
        raise ValueError("Bu haydovchiga biriktirilgan avtomobil topilmadi")

    check_id = vehicles_repo.record_daily_check(
        vehicle_id=vehicle["id"],
        driver_id=driver_id,
        check_date=check_date,
        exterior_photo_ref=exterior_photo_ref,
        interior_photo_ref=interior_photo_ref,
        start_km=start_km,
        end_km=end_km,
        notes=notes,
    )
    return {"check_id": check_id, "vehicle": vehicle}


def record_service(
    vehicle_id: int,
    service_date: str,
    oil_change_km: int | None,
    service_type: str | None,
    notes: str | None = None,
    next_service_km: int | None = None,
    next_service_date: str | None = None,
) -> int:
    return vehicles_repo.record_service(
        vehicle_id=vehicle_id,
        service_date=service_date,
        oil_change_km=oil_change_km,
        service_type=service_type,
        notes=notes,
        next_service_km=next_service_km,
        next_service_date=next_service_date,
    )


def needs_oil_change_reminder(vehicle_id: int, current_km: int) -> bool:
    """Oxirgi moy almashtirilgan km'dan beri konfiguratsiyadagi interval
    (``vehicle.oil_change_interval_km``) bosib o'tilgan bo'lsa ``True``.
    """
    latest_service = vehicles_repo.get_latest_service(vehicle_id)
    if latest_service is None or latest_service.get("oil_change_km") is None:
        return False

    interval = rules_service.get_oil_change_interval_km()
    return current_km - latest_service["oil_change_km"] >= interval
