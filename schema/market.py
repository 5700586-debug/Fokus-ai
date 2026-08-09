"""Ta'minotchining bozor razvedkasi kuzatuvlari (MarketObservation)."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    observation_date TEXT NOT NULL,
    product TEXT NOT NULL,
    variety TEXT,
    photo_reference TEXT,
    wholesale_price TEXT,
    supplier_seller TEXT,
    origin TEXT,
    quality TEXT,
    minimum_batch TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
"""
