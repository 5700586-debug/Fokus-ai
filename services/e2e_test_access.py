"""E2E test avtomatizatsiyasi (real Telegram robot) uchun izolyatsiya
yordamchisi — bitta qattiq kodlangan Telegram ID
(``roles.E2E_TESTER_TELEGRAM_ID``) uchun.

Bozor ro'yxatini parse/aniqlashtirish/tasdiqlash REAL kassir
handlerlari (``cash_shift_bot.py``dagi ``deficiency_item_name``,
``_process_deficiency_list``, ``_advance_deficiency_list``,
``deficiency_list_clarify``, ``deficiency_list_confirm``,
``deficiency_list_edit``) orqali, o'zgarishsiz ketadi — bu modul
FAQAT test smenasini boshlash/yakunlash/tozalashni ta'minlaydi.

**DB — yagona haqiqat manbai, FSM faqat vaqtinchalik UI holati.**
``start_test_shift``/``finish_active_test_run`` FSM'ga umuman
tayanmaydi — har doim DB'dan BUGUNGI ochiq TEST smenani to'g'ridan-
to'g'ri qidiradi, shuning uchun FSM yo'qolishi/bot qayta ishga
tushishi/oraliqdagi boshqa buyruq (masalan ``_ClearStaleStateMiddleware``)
davom etayotgan yugurishni hech qachon "yetim" qoldirmaydi va hech
qachon yangi, ajratilgan ``test_run_id`` o'ylab topilmaydi.

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


class TestRunStateError(Exception):
    """DB'da tester uchun bugungi ochiq (``is_test=1``) smena bor,
    lekin uning ``test_run_id`` ustuni bo'sh — kutilmagan, buzilgan
    holat. Chaqiruvchi (``cash_shift_bot.py``) ANIQ TEST xatosini
    ko'rsatishi kerak, hech qachon o'zi yangi ajratilgan ID o'ylab
    topmasin."""


def new_test_run_id() -> str:
    return uuid.uuid4().hex


def start_test_shift(tester_id: int) -> tuple[dict, str] | None:
    """Bugungi ochiq TEST smena DB'da ALLAQACHON mavjud bo'lsa, ANIQ
    o'sha smena va uning persistlangan ``test_run_id``si qaytariladi —
    hech qachon yangi smena qo'shilmaydi yoki yangi ``test_run_id``
    o'ylab topilmaydi, hatto FSM holati yo'qolgan/tozalangan bo'lsa
    ham. Mavjud bo'lmasagina bitta yangi izolyatsiyalangan smena va
    bitta yangi ``test_run_id`` yaratiladi."""
    if tester_id != E2E_TESTER_TELEGRAM_ID:
        return None

    today = company_time.today().isoformat()
    existing = cash_shifts_repo.get_open_test_shift(tester_id, today)
    if existing is not None:
        test_run_id = existing.get("test_run_id")
        if not test_run_id:
            raise TestRunStateError(
                f"TEST smena (id={existing['id']}) mavjud, lekin test_run_id yo'q."
            )
        return existing, test_run_id

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


def finish_active_test_run(tester_id: int) -> dict:
    """``/sinovtugat`` uchun — FSM'dan MUSTAQIL: DB'dagi BUGUNGI ochiq
    TEST smenasini to'g'ridan-to'g'ri topib yakunlaydi va tozalaydi,
    shuning uchun bot qayta ishga tushgan/FSM yo'qolgan holatda ham
    ishlaydi. Faqat topilgan smenaning ANIQ ``test_run_id``siga
    tegishli qatorlarni o'chiradi — hech qachon boshqa yugurishga yoki
    real ma'lumotga tegmaydi. ``found=False`` — bugun faol TEST smena
    umuman yo'q edi (hech narsa o'zgartirilmadi)."""
    if tester_id != E2E_TESTER_TELEGRAM_ID:
        return {"items_deleted": 0, "shifts_deleted": 0, "found": False}

    today = company_time.today().isoformat()
    shift = cash_shifts_repo.get_open_test_shift(tester_id, today)
    if shift is None:
        return {"items_deleted": 0, "shifts_deleted": 0, "found": False}

    test_run_id = shift.get("test_run_id")
    if not test_run_id:
        raise TestRunStateError(
            f"TEST smena (id={shift['id']}) mavjud, lekin test_run_id yo'q."
        )

    cash_shifts_repo.close_test_shift(shift["id"])
    result = cleanup_test_run(tester_id, test_run_id)
    result["found"] = True
    return result
