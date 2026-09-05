"""Kassir smena yopishidan oldingi bozor/firma kamchilik hisoboti va
"kechagi kelmaganlar" holatini kuzatish uchun xom SQL qatlami.
Formula/mantiq bu yerda emas — ``services/shift_deficiency.py``da.
"""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------ shift_deficiency_items --


def add_item(
    shift_id: int, employee_id: int, branch: str | None, category: str,
    product_name: str, quantity: float, unit: str, source_date: str,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO shift_deficiency_items "
            "(shift_id, employee_id, branch, category, product_name, quantity, unit, status, source_date, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)",
            (shift_id, employee_id, branch, category, product_name, quantity, unit, source_date, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def add_items_bulk(
    shift_id: int, employee_id: int, branch: str | None, category: str,
    items: list[dict], source_date: str, is_test: bool = False, test_run_id: str | None = None,
) -> list[int]:
    """Bir nechta pozitsiyani BITTA ulanish/tranzaksiyada yozadi — bitta
    ``commit()`` chaqiruvi, ya'ni hammasi yoki hech biri (oraliqda xato
    chiqsa, ``commit()``ga yetib bormaydi va hech narsa saqlanmaydi).

    ``is_test``/``test_run_id`` — FAQAT ``services/e2e_test_access.py``
    uchun; real chaqiruvchilar (``services/shift_deficiency.py``) bu
    parametrlarni bermaydi, standart qiymat mavjud xatti-harakatni
    AYNAN saqlaydi."""
    conn = get_connection()
    try:
        now = _now()
        ids = []
        for item in items:
            cursor = conn.execute(
                "INSERT INTO shift_deficiency_items "
                "(shift_id, employee_id, branch, category, product_name, quantity, unit, status, source_date, "
                "created_at, is_test, test_run_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)",
                (
                    shift_id, employee_id, branch, category,
                    item["product_name"], item["quantity"], item["unit"], source_date, now,
                    int(is_test), test_run_id,
                ),
            )
            ids.append(cursor.lastrowid)
        conn.commit()
        return ids
    finally:
        conn.close()


def get_test_market_items(test_run_id: str) -> list[dict]:
    """``services/e2e_test_access.py`` uchun — FAQAT aynan shu
    ``test_run_id``ga tegishli (``is_test = 1``) market pozitsiyalari.
    Boshqa yugurish yoki real ma'lumot hech qachon qaytmaydi."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM shift_deficiency_items "
            "WHERE category = 'market' AND is_test = 1 AND test_run_id = ? ORDER BY id",
            (test_run_id,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def delete_test_items_for_run(test_run_id: str) -> int:
    """``services/e2e_test_access.py`` uchun tozalash — FAQAT
    ``is_test = 1`` VA aynan shu ``test_run_id``ga tegishli qatorlar
    (ikkala shart ham DB darajasida), real ma'lumotga hech qachon
    tegmaydi."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM shift_deficiency_items WHERE is_test = 1 AND test_run_id = ?", (test_run_id,)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_open_items_for_branch_before(branch: str | None, before_date: str) -> list[dict]:
    """Filial bo'yicha, ``source_date`` berilgan sanadan OLDIN yozilgan
    va hali ``open`` bo'lgan mahsulotlar — shu SANADA (bugun, boshqa
    smena tomonidan) yozilgan yozuvlar bu ro'yxatga umuman kirmaydi."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM shift_deficiency_items "
            "WHERE branch = ? AND status = 'open' AND source_date < ? "
            "ORDER BY id",
            (branch, before_date),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_open_market_items_through(as_of_date: str, is_test: bool = False) -> list[dict]:
    """Bugun VA undan oldingi barcha ochiq ``market`` bozorlik
    yozuvlari (filialdan qat'i nazar) — ta'minotchining ``/xarid``
    ro'yxati uchun. Allaqachon "arrived" bo'lgan (eski tarix)
    yozuvlar UMUMAN kirmaydi -- faqat ``status = 'open'``.

    ``is_test`` standart holatda ``False`` — real chaqiruvchilar
    (``services/shift_deficiency.py``) hech narsa o'zgartirmaydi,
    natijada test (``is_test=1``) qatorlar AVTOMATIK chiqarib
    tashlanadi."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM shift_deficiency_items "
            "WHERE category = 'market' AND status = 'open' AND source_date <= ? AND is_test = ? "
            "ORDER BY id",
            (as_of_date, int(is_test)),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def mark_item_resolved(item_id: int, resolved_at: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE shift_deficiency_items SET status = 'arrived', resolved_at = ? WHERE id = ?",
            (resolved_at, item_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_market_items_in_range(start_date: str, end_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM shift_deficiency_items "
            "WHERE category = 'market' AND source_date >= ? AND source_date <= ?",
            (start_date, end_date),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


# --------------------------------------------------- shift_deficiency_progress --


def get_progress(shift_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM shift_deficiency_progress WHERE shift_id = ?", (shift_id,)
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def mark_market_done(shift_id: int, done_at: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO shift_deficiency_progress (shift_id, market_done_at) VALUES (?, ?) "
            "ON CONFLICT(shift_id) DO UPDATE SET market_done_at = excluded.market_done_at",
            (shift_id, done_at),
        )
        conn.commit()
    finally:
        conn.close()


def mark_company_done(shift_id: int, done_at: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO shift_deficiency_progress (shift_id, company_done_at) VALUES (?, ?) "
            "ON CONFLICT(shift_id) DO UPDATE SET company_done_at = excluded.company_done_at",
            (shift_id, done_at),
        )
        conn.commit()
    finally:
        conn.close()


def mark_yesterday_review_done(shift_id: int, done_at: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO shift_deficiency_progress (shift_id, yesterday_review_done_at) VALUES (?, ?) "
            "ON CONFLICT(shift_id) DO UPDATE SET yesterday_review_done_at = excluded.yesterday_review_done_at",
            (shift_id, done_at),
        )
        conn.commit()
    finally:
        conn.close()
