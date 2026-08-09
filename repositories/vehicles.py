"""Haydovchi moduli: avtomobillar, kunlik tekshiruv, servis tarixi."""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_vehicle(plate_number: str, model: str | None, assigned_driver_id: int | None) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO vehicles (plate_number, model, assigned_driver_id, created_at) "
            "VALUES (?, ?, ?, ?)",
            (plate_number, model, assigned_driver_id, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_vehicle_for_driver(driver_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM vehicles WHERE assigned_driver_id = ?", (driver_id,)
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def record_daily_check(
    vehicle_id: int,
    driver_id: int,
    check_date: str,
    exterior_photo_ref: str | None,
    interior_photo_ref: str | None,
    start_km: int | None,
    end_km: int | None,
    notes: str | None = None,
) -> int:
    """``end_km < start_km`` bo'lsa ``ValueError`` ko'taradi — DB'dagi
    ``CHECK`` constraint bilan bir xil qoidani servis darajasida ham
    aniq xato bilan bloklaydi.
    """
    if start_km is not None and end_km is not None and end_km < start_km:
        raise ValueError("end_km start_km dan kichik bo'lishi mumkin emas")

    daily_km = end_km - start_km if start_km is not None and end_km is not None else None

    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO vehicle_daily_checks "
            "(vehicle_id, driver_id, check_date, exterior_photo_ref, interior_photo_ref, "
            "start_km, end_km, daily_km, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(vehicle_id, driver_id, check_date) DO UPDATE SET "
            "exterior_photo_ref = excluded.exterior_photo_ref, "
            "interior_photo_ref = excluded.interior_photo_ref, "
            "start_km = excluded.start_km, end_km = excluded.end_km, "
            "daily_km = excluded.daily_km, notes = excluded.notes",
            (
                vehicle_id,
                driver_id,
                check_date,
                exterior_photo_ref,
                interior_photo_ref,
                start_km,
                end_km,
                daily_km,
                notes,
                _now(),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def record_service(
    vehicle_id: int,
    service_date: str,
    oil_change_km: int | None,
    service_type: str | None,
    notes: str | None,
    next_service_km: int | None,
    next_service_date: str | None,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO vehicle_service_history "
            "(vehicle_id, service_date, oil_change_km, service_type, notes, "
            "next_service_km, next_service_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                vehicle_id,
                service_date,
                oil_change_km,
                service_type,
                notes,
                next_service_km,
                next_service_date,
                _now(),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_latest_service(vehicle_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM vehicle_service_history WHERE vehicle_id = ? "
            "ORDER BY service_date DESC LIMIT 1",
            (vehicle_id,),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None
