"""E2E test avtomatizatsiyasi (real Telegram robot) uchun izolyatsiya
yordamchisi — bitta qattiq kodlangan Telegram ID
(``roles.E2E_TESTER_TELEGRAM_ID``) uchun.

Bozor ro'yxatini parse/aniqlashtirish/tasdiqlash REAL kassir
handlerlari (``cash_shift_bot.py``dagi ``deficiency_item_name``,
``_process_deficiency_list``, ``_advance_deficiency_list``,
``deficiency_list_clarify``, ``deficiency_list_confirm``,
``deficiency_list_edit``) orqali, o'zgarishsiz ketadi — bu modul
FAQAT test smenasini boshlash/yakunlash/tozalashni ta'minlaydi.

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
