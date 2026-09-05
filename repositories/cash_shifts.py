"""Kassir smena, xarajat, qayta-tekshiruv va supervisor tasdig'i uchun
xom SQL qatlami. Formula/status hisoblash bu yerda emas — ``services/
cash_shift.py`` va ``services/cash_expense.py`` da.
"""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------ cash_shifts --


def get_open_shift(employee_id: int, shift_date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cash_shifts WHERE employee_id = ? AND shift_date = ?",
            (employee_id, shift_date),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def open_shift(
    employee_id: int, branch: str | None, shift_date: str, opening_balance: int, tolerance: int,
    received_cash_balance: int | None = None, is_test: bool = False, test_run_id: str | None = None,
) -> dict:
    """``employee_id``+``shift_date`` uchun smena allaqachon mavjud bo'lsa,
    yangisini yaratmasdan mavjudini qaytaradi (duplicate open'dan himoya).

    ``is_test``/``test_run_id`` — FAQAT ``services/e2e_test_access.py``
    uchun (qarang shu modul docstringi); real chaqiruvchilar bu
    parametrlarni bermaydi, standart qiymat (``False``/``None``)
    mavjud xatti-harakatni AYNAN saqlaydi.
    """
    existing = get_open_shift(employee_id, shift_date)
    if existing is not None:
        return existing

    now = _now()
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO cash_shifts "
            "(employee_id, branch, shift_date, opening_balance, received_cash_balance, tolerance, status, "
            "opened_at, created_at, updated_at, is_test, test_run_id) "
            "VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)",
            (
                employee_id, branch, shift_date, opening_balance, received_cash_balance, tolerance,
                now, now, now, int(is_test), test_run_id,
            ),
        )
        conn.commit()
        shift_id = cursor.lastrowid
    finally:
        conn.close()

    return get_shift(shift_id)


def get_open_test_shift(employee_id: int, shift_date: str) -> dict | None:
    """``services/e2e_test_access.py`` uchun — FAQAT shu tester'ning
    BUGUNGI hali OCHIQ (``status='open'``) TEST (``is_test=1``)
    smenasi. Parametrlangan SQL; ``employee_id`` HECH QACHON yolg'iz
    ishlatilmaydi — doim ``is_test``/``shift_date``/``status`` bilan
    birga (real ma'lumotga tasodifiy mos kelishning oldini oladi)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cash_shifts WHERE is_test = 1 AND employee_id = ? "
            "AND shift_date = ? AND status = 'open'",
            (employee_id, shift_date),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def close_test_shift(shift_id: int) -> bool:
    """``services/e2e_test_access.py`` uchun — FAQAT ``is_test = 1``
    smenani yopadi (ikkinchi shart DB darajasidagi ``WHERE``da), real
    smenaga hech qachon tegmaydi."""
    conn = get_connection()
    try:
        now = _now()
        cursor = conn.execute(
            "UPDATE cash_shifts SET status = 'closed', closed_at = ?, updated_at = ? "
            "WHERE id = ? AND is_test = 1",
            (now, now, shift_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_test_shifts_for_run(test_run_id: str) -> int:
    """``services/e2e_test_access.py`` uchun tozalash — FAQAT
    ``is_test = 1`` VA aynan shu ``test_run_id``ga tegishli qatorlar
    (ikkala shart ham DB darajasida), real ma'lumotga hech qachon
    tegmaydi. Chaqiruvchi bundan OLDIN tegishli
    ``shift_deficiency_items`` qatorlarini o'chirishi kerak (FK).

    Bir kunda bir nechta test yugurish AYNAN shu smena qatorini qayta
    ishlatishi mumkin (``cash_shifts.UNIQUE(employee_id, shift_date)``)
    — agar boshqa (hali tozalanmagan) yugurish item'lari hamon shu
    qatorga FK orqali bog'liq bo'lsa, o'chirish xavfsiz tarzda
    o'tkazib yuboriladi (xato ko'tarilmaydi, real ma'lumotga hech
    qanday ta'sir yo'q)."""
    from db import IntegrityError

    conn = get_connection()
    try:
        try:
            cursor = conn.execute(
                "DELETE FROM cash_shifts WHERE is_test = 1 AND test_run_id = ?", (test_run_id,)
            )
            conn.commit()
            return cursor.rowcount
        except IntegrityError:
            return 0
    finally:
        conn.close()


def get_shift(shift_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM cash_shifts WHERE id = ?", (shift_id,)).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def get_last_closed_shift(branch: str | None) -> dict | None:
    """Oxirgi yopilgan (``open`` emas) smena — FILIAL bo'yicha (xodim
    emas), chunki haqiqiy topshirish/qabul qilish odatda ikki XIL kassir
    orasida bo'ladi (masalan tungi va ertalabgi). Ertangi/keyingi kassir
    uchun ``opening_balance`` shu smenaning ``actual_cash_balance``idan
    olinadi. Bir kunda bir nechta kassir bo'lishi mumkin bo'lgani uchun
    ``id`` bo'yicha ham tartiblanadi (eng oxirgi yaratilgani g'olib).
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM cash_shifts WHERE branch = ? AND status != 'open' "
            "ORDER BY shift_date DESC, id DESC LIMIT 1",
            (branch,),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def get_shifts_for_branch_date(branch: str | None, shift_date: str) -> list[dict]:
    """Shu filial va sanadagi barcha smenalar (statusidan qat'i nazar —
    ``open`` ham) — Founder'ning "🏬 Do'konlar" filial kartasi uchun
    (faqat o'qish)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM cash_shifts WHERE branch = ? AND shift_date = ? ORDER BY id DESC",
            (branch, shift_date),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def set_sales_report_photo(shift_id: int, photo_ref: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE cash_shifts SET sales_report_photo_ref = ?, updated_at = ? WHERE id = ?",
            (photo_ref, _now(), shift_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_cash_report_photo(shift_id: int, photo_ref: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE cash_shifts SET cash_report_photo_ref = ?, updated_at = ? WHERE id = ?",
            (photo_ref, _now(), shift_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_received_cash_balance(shift_id: int, amount: int) -> None:
    """Qabul qiluvchi kassir "Yana sanayman" bilan qayta kiritganda —
    smena qatori ``open_shift``da allaqachon yaratilgan bo'lgani uchun
    (idempotent), qiymatni shu yerda yangilaydi."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE cash_shifts SET received_cash_balance = ?, updated_at = ? WHERE id = ?",
            (amount, _now(), shift_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_discrepancy_reason(shift_id: int, reason: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE cash_shifts SET discrepancy_reason_text = ?, updated_at = ? WHERE id = ?",
            (reason, _now(), shift_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_shift_result(
    shift_id: int,
    cash_sales: int,
    card_sales: int,
    other_payments: int,
    total_sales: int,
    cash_expenses: int,
    expected_cash_balance: int,
    actual_cash_balance: int,
    difference: int,
    status: str,
    close: bool,
) -> None:
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE cash_shifts SET "
            "cash_sales = ?, card_sales = ?, other_payments = ?, total_sales = ?, "
            "cash_expenses = ?, expected_cash_balance = ?, actual_cash_balance = ?, "
            "difference = ?, status = ?, updated_at = ?, "
            "closed_at = CASE WHEN ? THEN ? ELSE closed_at END "
            "WHERE id = ?",
            (
                cash_sales,
                card_sales,
                other_payments,
                total_sales,
                cash_expenses,
                expected_cash_balance,
                actual_cash_balance,
                difference,
                status,
                now,
                close,
                now,
                shift_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def set_shift_status(shift_id: int, status: str, close: bool, reset_retry: bool = False) -> None:
    """Supervisor qarori (approve/reject/recheck) yoki retry-limit
    eskalatsiyasi uchun — savdo/xarajat raqamlarini qayta yubormasdan
    faqat statusni (va kerak bo'lsa ``retry_count``ni) yangilaydi.
    """
    now = _now()
    conn = get_connection()
    try:
        if reset_retry:
            conn.execute(
                "UPDATE cash_shifts SET status = ?, retry_count = 0, updated_at = ?, "
                "closed_at = CASE WHEN ? THEN ? ELSE closed_at END WHERE id = ?",
                (status, now, close, now, shift_id),
            )
        else:
            conn.execute(
                "UPDATE cash_shifts SET status = ?, updated_at = ?, "
                "closed_at = CASE WHEN ? THEN ? ELSE closed_at END WHERE id = ?",
                (status, now, close, now, shift_id),
            )
        conn.commit()
    finally:
        conn.close()


def set_shift_status_if(
    shift_id: int, expected_status: str, status: str, close: bool, reset_retry: bool = False
) -> bool:
    """``set_shift_status`` bilan bir xil, lekin FAQAT joriy status
    ``expected_status``ga teng bo'lsagina yangilaydi (atomic
    ``UPDATE ... WHERE id = ? AND status = ?``) — parallel ikkita so'rov
    (masalan ikki marta bosilgan tugma) bir smenani ikki marta
    o'zgartirmasligi uchun. Qaytadi: ``True`` — yangilandi, ``False`` —
    joriy status kutilganidan farq qilgani uchun hech narsa
    o'zgarmadi (boshqa so'rov allaqachon bajargan).
    """
    now = _now()
    conn = get_connection()
    try:
        if reset_retry:
            cursor = conn.execute(
                "UPDATE cash_shifts SET status = ?, retry_count = 0, updated_at = ?, "
                "closed_at = CASE WHEN ? THEN ? ELSE closed_at END WHERE id = ? AND status = ?",
                (status, now, close, now, shift_id, expected_status),
            )
        else:
            cursor = conn.execute(
                "UPDATE cash_shifts SET status = ?, updated_at = ?, "
                "closed_at = CASE WHEN ? THEN ? ELSE closed_at END WHERE id = ? AND status = ?",
                (status, now, close, now, shift_id, expected_status),
            )
        conn.commit()
        updated = cursor.rowcount > 0
    finally:
        conn.close()

    return updated


def increment_retry_count(shift_id: int) -> int:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE cash_shifts SET retry_count = retry_count + 1, updated_at = ? WHERE id = ?",
            (_now(), shift_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT retry_count FROM cash_shifts WHERE id = ?", (shift_id,)
        ).fetchone()
    finally:
        conn.close()

    return row["retry_count"]


# --------------------------------------------------- cash_difference_reviews --


def record_difference_review(
    shift_id: int, attempt_number: int, actual_cash_balance: int, difference: int, status_after: str
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO cash_difference_reviews "
            "(shift_id, attempt_number, actual_cash_balance, difference, status_after, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (shift_id, attempt_number, actual_cash_balance, difference, status_after, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_difference_reviews(shift_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM cash_difference_reviews WHERE shift_id = ? ORDER BY attempt_number",
            (shift_id,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


# ----------------------------------------------------- cash_shift_approvals --


def record_shift_approval(shift_id: int, reviewed_by: int, decision: str, comment: str | None) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO cash_shift_approvals (shift_id, reviewed_by, decision, comment, reviewed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (shift_id, reviewed_by, decision, comment, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


# ------------------------------------------------------------- cash_expenses --


def add_expense(
    shift_id: int, employee_id: int, branch: str | None, category: str, amount: int,
    description: str | None, expense_date: str,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO cash_expenses "
            "(shift_id, employee_id, branch, category, amount, description, expense_date, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (shift_id, employee_id, branch, category, amount, description, expense_date, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_expenses_for_shift(shift_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM cash_expenses WHERE shift_id = ? ORDER BY created_at", (shift_id,)
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_expense_history(employee_id: int, category: str, before_date: str, limit: int = 30) -> list[dict]:
    """Baseline hisoblash uchun — ``before_date``dan oldingi (bugungisiz)
    shu xodim/kategoriya bo'yicha eng so'nggi xarajatlar.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM cash_expenses WHERE employee_id = ? AND category = ? "
            "AND expense_date < ? ORDER BY expense_date DESC LIMIT ?",
            (employee_id, category, before_date, limit),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]
