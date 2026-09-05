"""E2E test avtomatizatsiyasi (real Telegram robot) uchun TO'LIQ
IZOLYATSIYALANGAN mini-oqim — bitta qattiq kodlangan Telegram ID
(``roles.E2E_TESTER_TELEGRAM_ID``) uchun.

Bu modul real kassir/ta'minotchi biznes-mantiq qatlamiga
(``services/cash_shift.py``, ``services/shift_deficiency.py``) UMUMAN
tegmaydi va ulardan HECH NARSA import qilmaydi (faqat o'zgarmas
konstantalar — ``KNOWN_UNITS``, ``CATEGORY_MARKET`` — o'qib
ishlatiladi). Repozitoriya funksiyalarini to'g'ridan-to'g'ri,
``is_test=True`` va shu chaqiruvga xos ``test_run_id`` bilan chaqiradi,
shuning uchun oddiy xodim/ta'minotchi oqimlari BUTUNLAY o'zgarishsiz
qoladi va real ma'lumotga hech qachon aralashmaydi.

Har bir jamoatchilik funksiyasi birinchi qadam sifatida
``tester_id == E2E_TESTER_TELEGRAM_ID`` ekanini tekshiradi — boshqa
HECH KIM (Founder ham) bu orqali test rejimiga kira olmaydi.

Tozalash (`cleanup_test_run`) faqat ANIQ shu ``test_run_id``ni
tashiydigan VA ``is_test=1`` bo'lgan qatorlarni o'chiradi (ikkala shart
ham DB darajasidagi SQL WHERE'da, qarang ``repositories/*.py``) — real
ma'lumotga yoki boshqa test yugurishlariga hech qachon tegmaydi.
"""

import uuid

import company_time
from repositories import cash_shifts as cash_shifts_repo
from repositories import shift_deficiencies as shift_deficiencies_repo
from roles import E2E_TESTER_TELEGRAM_ID
from services.shift_deficiency import CATEGORY_MARKET, KNOWN_UNITS

TEST_BRANCH = "E2E-TEST"


def new_test_run_id() -> str:
    return uuid.uuid4().hex


def start_test_shift(tester_id: int) -> tuple[dict, str] | None:
    """Izolyatsiyalangan test smenasini boshlaydi (mavjud bo'lsa qayta
    ishlatadi, ``repositories.cash_shifts.open_shift`` bilan bir xil
    idempotent naqsh) va shu chaqiruvga xos YANGI ``test_run_id``
    qaytaradi (item'lar aynan shu ID bilan belgilanadi, hatto smena
    qatori qayta ishlatilgan bo'lsa ham)."""
    if tester_id != E2E_TESTER_TELEGRAM_ID:
        return None

    today = company_time.today().isoformat()
    test_run_id = new_test_run_id()
    shift = cash_shifts_repo.open_shift(
        tester_id, TEST_BRANCH, today, opening_balance=0, tolerance=0,
        is_test=True, test_run_id=test_run_id,
    )
    return shift, test_run_id


def add_test_market_items(
    tester_id: int, shift_id: int, test_run_id: str, items: list[dict]
) -> list[int]:
    """Faqat shu tester'ning O'Z (``is_test=1``) smenasiga, faqat
    to'liq validatsiyadan o'tgan pozitsiyalarni yozadi — bitta
    tranzaksiya, hammasi yoki hech biri (qarang
    ``repositories.shift_deficiencies.add_items_bulk``)."""
    if tester_id != E2E_TESTER_TELEGRAM_ID or not test_run_id:
        return []

    shift = cash_shifts_repo.get_shift(shift_id)
    if shift is None or not shift.get("is_test") or shift["employee_id"] != tester_id:
        return []

    valid_items = []
    for item in items:
        name = (item.get("product_name") or "").strip()
        quantity = item.get("quantity")
        unit = item.get("unit")
        if not name or unit not in KNOWN_UNITS or quantity is None or quantity <= 0:
            return []
        valid_items.append({"product_name": name, "quantity": quantity, "unit": unit})

    if not valid_items:
        return []

    return shift_deficiencies_repo.add_items_bulk(
        shift_id, tester_id, shift.get("branch"), CATEGORY_MARKET, valid_items,
        shift["shift_date"], is_test=True, test_run_id=test_run_id,
    )


def get_test_run_market_items(tester_id: int, test_run_id: str) -> list[dict]:
    """Faqat shu ANIQ ``test_run_id``ga tegishli pozitsiyalar — boshqa
    (eski) test yugurishlari yoki real ma'lumot HECH QACHON
    ko'rsatilmaydi."""
    if tester_id != E2E_TESTER_TELEGRAM_ID or not test_run_id:
        return []
    return shift_deficiencies_repo.get_test_market_items(test_run_id)


def finish_test_shift(tester_id: int, shift_id: int) -> bool:
    if tester_id != E2E_TESTER_TELEGRAM_ID:
        return False
    return cash_shifts_repo.close_test_shift(shift_id)


def cleanup_test_run(tester_id: int, test_run_id: str) -> dict:
    """Faqat ``test_run_id``ni tashiydigan VA ``is_test=1`` qatorlarni
    o'chiradi. Avval item'lar (FK: shift_deficiency_items.shift_id ->
    cash_shifts.id), keyin smena qatori — aks holda FK cheklovi
    (Postgres/SQLite ikkalasida ham yoqilgan) o'chirishni rad etadi."""
    if tester_id != E2E_TESTER_TELEGRAM_ID or not test_run_id:
        return {"items_deleted": 0, "shifts_deleted": 0}

    items_deleted = shift_deficiencies_repo.delete_test_items_for_run(test_run_id)
    shifts_deleted = cash_shifts_repo.delete_test_shifts_for_run(test_run_id)
    return {"items_deleted": items_deleted, "shifts_deleted": shifts_deleted}
