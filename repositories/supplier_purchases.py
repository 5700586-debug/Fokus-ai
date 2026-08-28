"""Ta'minotchi xaridi uchun xom SQL qatlami. Formula/mantiq bu yerda
emas — ``performance_bot.py``/keyingi bosqichlardagi servis qatlamida.
"""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_purchase(
    product_name: str, quantity: float, unit: str, unit_price: int, purchased_by: int,
    purchase_date: str, price_flagged: bool, price_flag_reason: str | None,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO supplier_purchases "
            "(product_name, quantity, unit, unit_price, purchased_by, purchase_date, "
            "price_flagged, price_flag_reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                product_name, quantity, unit, unit_price, purchased_by, purchase_date,
                1 if price_flagged else 0, price_flag_reason, _now(),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_price_history(product_name: str, unit: str) -> dict | None:
    """Shu ``product_name`` + ``unit`` uchun eng oxirgi xarid qatori —
    birinchi marta olinayotgan mahsulotda ``None`` (tarix yo'q)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM supplier_purchases WHERE product_name = ? AND unit = ? "
            "ORDER BY purchase_date DESC, id DESC LIMIT 1",
            (product_name, unit),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None
