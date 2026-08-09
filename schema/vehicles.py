"""Haydovchi moduli: avtomobillar, kunlik tekshiruv, servis tarixi."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT NOT NULL UNIQUE,
    model TEXT,
    assigned_driver_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vehicle_daily_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    driver_id INTEGER NOT NULL,
    check_date TEXT NOT NULL,
    exterior_photo_ref TEXT,
    interior_photo_ref TEXT,
    start_km INTEGER,
    end_km INTEGER,
    daily_km INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(vehicle_id, driver_id, check_date),
    CHECK (end_km IS NULL OR start_km IS NULL OR end_km >= start_km)
);

CREATE TABLE IF NOT EXISTS vehicle_service_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    service_date TEXT NOT NULL,
    oil_change_km INTEGER,
    service_type TEXT,
    notes TEXT,
    next_service_km INTEGER,
    next_service_date TEXT,
    created_at TEXT NOT NULL
);

INSERT OR IGNORE INTO rules (rule_key, rule_value, updated_by, updated_at) VALUES
    ('vehicle.oil_change_interval_km', '5000', NULL, NULL);
"""
