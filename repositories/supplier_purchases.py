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


def get_price_history_batch(product_keys: list[tuple[str, str]]) -> dict[tuple[str, str], dict]:
    """``get_price_history()``ning ko'p mahsulotli, N+1'siz varianti --
    ``/xarid`` ro'yxatini yuklashda har bir mahsulot uchun alohida
    so'rov o'rniga, berilgan barcha (product_name, unit) juftliklari
    uchun eng oxirgi xarid qatorini BITTA ulanish va BITTA SELECT bilan
    qaytaradi. ``ROW_NUMBER() OVER (PARTITION BY ...)`` SQLite (3.25+)
    va Postgres'da bir xil sintaksis -- alohida dialekt tarjimasi shart
    emas. Mahsulot nomi/birlik HECH QACHON SQL matniga interpolatsiya
    qilinmaydi -- faqat parametrlashtirilgan ``?`` o'rin
    egallovchilar orqali. Tarixi yo'q juftlik natija xaritasida umuman
    bo'lmaydi (chaqiruvchi ``.get(key)`` orqali ``None``ga tushadi).
    """
    unique_keys = list(dict.fromkeys(product_keys))
    if not unique_keys:
        return {}

    placeholders = ", ".join("(?, ?)" for _ in unique_keys)
    params: list[str] = [value for pair in unique_keys for value in pair]

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM ("
            "  SELECT *, ROW_NUMBER() OVER ("
            "    PARTITION BY product_name, unit ORDER BY purchase_date DESC, id DESC"
            "  ) AS rn "
            "  FROM supplier_purchases "
            f"  WHERE (product_name, unit) IN ({placeholders})"
            ") ranked WHERE rn = 1",
            params,
        ).fetchall()
    finally:
        conn.close()

    return {(row["product_name"], row["unit"]): dict(row) for row in rows}


def add_allocation(purchase_id: int, branch: str, quantity: float) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO supplier_purchase_allocations (purchase_id, branch, quantity, created_at) "
            "VALUES (?, ?, ?, ?)",
            (purchase_id, branch, quantity, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_allocations_for_date(purchase_date: str) -> list[dict]:
    """Shu sanadagi barcha xaridlarning filiallar bo'yicha taqsimoti —
    filial hisobotini chiqarish uchun, xarid ma'lumotlari (mahsulot
    nomi, birlik narxi) bilan birga."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT a.branch AS branch, a.quantity AS quantity, "
            "p.product_name AS product_name, p.unit AS unit, p.unit_price AS unit_price "
            "FROM supplier_purchase_allocations a "
            "JOIN supplier_purchases p ON p.id = a.purchase_id "
            "WHERE p.purchase_date = ? "
            "ORDER BY a.branch, p.product_name",
            (purchase_date,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]
