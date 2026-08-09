"""Ta'minotchining bozor razvedkasi kuzatuvlari (MarketObservation)."""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_observation(
    employee_id: int,
    observation_date: str,
    product: str,
    variety: str | None = None,
    photo_reference: str | None = None,
    wholesale_price: str | None = None,
    supplier_seller: str | None = None,
    origin: str | None = None,
    quality: str | None = None,
    minimum_batch: str | None = None,
    notes: str | None = None,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO market_observations "
            "(employee_id, observation_date, product, variety, photo_reference, "
            "wholesale_price, supplier_seller, origin, quality, minimum_batch, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                employee_id,
                observation_date,
                product,
                variety,
                photo_reference,
                wholesale_price,
                supplier_seller,
                origin,
                quality,
                minimum_batch,
                notes,
                _now(),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_recent(limit: int = 20) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM market_observations ORDER BY observation_date DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_price_history(product: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM market_observations WHERE product = ? ORDER BY observation_date",
            (product,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]
