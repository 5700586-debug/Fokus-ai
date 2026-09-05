"""Kassir smena yopishidan oldingi kamchilik hisoboti V1: bozor
(market) va firma (company) zakazlari alohida yoziladi, "kechagi
kelmaganlar" FILIAL bo'yicha davom etadi (``source_date < shift_date``
— bugun boshqa smena yozgan mahsulotlar bu ro'yxatga kirmaydi).

3 qadam (bozor, firma, kechagi ko'rib chiqish) tugamaguncha
``cash_shift_bot.py``dagi ``/closeshift`` davom etmaydi — qarang
``get_next_step``.

KPI/bonus/AI/dashboard ATAYLAB YO'Q — hozircha faqat FAKT.
"""

from datetime import datetime, timezone

import company_time
from repositories import shift_deficiencies as repo
from services import cash_shift

CATEGORY_MARKET = "market"
CATEGORY_COMPANY = "company"
KNOWN_CATEGORIES = (CATEGORY_MARKET, CATEGORY_COMPANY)

STATUS_OPEN = "open"
STATUS_ARRIVED = "arrived"

KNOWN_UNITS = ("kg", "dona", "litr", "quti")

STEP_MARKET = "market"
STEP_COMPANY = "company"
STEP_YESTERDAY = "yesterday"
STEP_DONE = "done"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _add_item(
    shift_id: int, employee_id: int, category: str, product_name: str, quantity: float, unit: str,
) -> int | None:
    shift = cash_shift.get_shift(shift_id)
    name = (product_name or "").strip()
    if shift is None or not name or unit not in KNOWN_UNITS or quantity is None or quantity <= 0:
        return None

    return repo.add_item(
        shift_id, employee_id, shift.get("branch"), category, name, quantity, unit, shift["shift_date"]
    )


def add_market_item(shift_id: int, employee_id: int, product_name: str, quantity: float, unit: str) -> int | None:
    return _add_item(shift_id, employee_id, CATEGORY_MARKET, product_name, quantity, unit)


def add_items_bulk(
    shift_id: int, employee_id: int, category: str, items: list[dict],
    is_test: bool = False, test_run_id: str | None = None,
) -> list[int]:
    """Ko'p qatorli bozor ro'yxati tasdiqlanganda ishlatiladi — BARCHA
    pozitsiyalar bitta tranzaksiyada, aynan bir marta yoziladi.
    Fail-safe: bironta pozitsiya yaroqsiz bo'lsa (nom bo'sh, birlik
    noma'lum yoki miqdor musbat emas), HECH NARSA yozilmaydi.

    ``is_test``/``test_run_id`` — FAQAT ``roles.E2E_TESTER_TELEGRAM_ID``
    uchun (qarang ``cash_shift_bot.py``dagi ``deficiency_list_confirm``);
    real chaqiruvchilar bu parametrlarni bermaydi, standart qiymat
    mavjud xatti-harakatni AYNAN saqlaydi."""
    shift = cash_shift.get_shift(shift_id)
    if shift is None or category not in KNOWN_CATEGORIES:
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

    return repo.add_items_bulk(
        shift_id, employee_id, shift.get("branch"), category, valid_items, shift["shift_date"],
        is_test=is_test, test_run_id=test_run_id,
    )


def add_company_item(shift_id: int, employee_id: int, product_name: str, quantity: float, unit: str) -> int | None:
    return _add_item(shift_id, employee_id, CATEGORY_COMPANY, product_name, quantity, unit)


def mark_market_step_done(shift_id: int) -> None:
    repo.mark_market_done(shift_id, _now())


def mark_company_step_done(shift_id: int) -> None:
    repo.mark_company_done(shift_id, _now())


def mark_yesterday_step_done(shift_id: int) -> None:
    repo.mark_yesterday_review_done(shift_id, _now())


def get_yesterday_open_items(shift_id: int) -> list[dict]:
    shift = cash_shift.get_shift(shift_id)
    if shift is None:
        return []
    return repo.get_open_items_for_branch_before(shift.get("branch"), shift["shift_date"])


def confirm_yesterday_review(shift_id: int, still_missing_item_ids: list[int]) -> None:
    """Ro'yxatdagi ``still_missing_item_ids``da YO'Q har bir item
    "keldi" deb yopiladi (``resolved_at`` yoziladi). Hali kelmagan deb
    belgilanganlar ``open`` holatida qoladi — hech narsa yozilmaydi,
    shuning uchun keyingi kunning ``source_date < shift_date`` filtriga
    avtomatik tushib qoladi (rollover uchun alohida yozuv shart emas)."""
    shift = cash_shift.get_shift(shift_id)
    if shift is None:
        return

    items = repo.get_open_items_for_branch_before(shift.get("branch"), shift["shift_date"])
    still_missing = set(still_missing_item_ids)
    now = _now()
    for item in items:
        if item["id"] not in still_missing:
            repo.mark_item_resolved(item["id"], now)

    mark_yesterday_step_done(shift_id)


def get_next_step(shift_id: int) -> str:
    progress = repo.get_progress(shift_id)
    if progress is None or not progress.get("market_done_at"):
        return STEP_MARKET
    if not progress.get("company_done_at"):
        return STEP_COMPANY
    if not progress.get("yesterday_review_done_at"):
        return STEP_YESTERDAY
    return STEP_DONE


def is_flow_complete(shift_id: int) -> bool:
    return get_next_step(shift_id) == STEP_DONE


def get_daily_market_shortage() -> list[dict]:
    """Bugungi VA oldingi kunlardan qolgan ochiq ``market`` bozorlikni
    (barcha filiallar) mahsulot+birlik bo'yicha jamlaydi. Allaqachon
    "arrived" bo'lgan eski tarixiy mahsulotlar bu ro'yxatga UMUMAN
    kirmaydi (qarang ``repositories.shift_deficiencies.
    get_open_market_items_through`` — faqat ``status='open'``).

    Har element: {"product_name", "unit", "total_quantity",
    "by_branch": {branch: {"quantity": float, "item_ids": [int, ...]}}}.
    """
    items = repo.get_open_market_items_through(company_time.today().isoformat())

    grouped: dict[tuple[str, str], dict] = {}
    for item in items:
        key = (item["product_name"], item["unit"])
        bucket = grouped.setdefault(
            key,
            {"product_name": item["product_name"], "unit": item["unit"], "total_quantity": 0.0, "by_branch": {}},
        )
        bucket["total_quantity"] += item["quantity"]
        branch = item.get("branch") or "-"
        branch_bucket = bucket["by_branch"].setdefault(branch, {"quantity": 0.0, "item_ids": []})
        branch_bucket["quantity"] += item["quantity"]
        branch_bucket["item_ids"].append(item["id"])

    return list(grouped.values())


def get_test_market_shortage(test_run_id: str) -> list[dict]:
    """``roles.E2E_TESTER_TELEGRAM_ID`` uchun — ``get_daily_market_
    shortage()`` bilan bir xil shaklda, lekin FAQAT aynan shu
    ``test_run_id``ga tegishli (``is_test=1``) pozitsiyalar. Real
    ma'lumot yoki boshqa test yugurishlari hech qachon aralashmaydi
    (qarang ``repositories.shift_deficiencies.get_test_market_items``)."""
    if not test_run_id:
        return []

    items = repo.get_test_market_items(test_run_id)

    grouped: dict[tuple[str, str], dict] = {}
    for item in items:
        key = (item["product_name"], item["unit"])
        bucket = grouped.setdefault(
            key,
            {"product_name": item["product_name"], "unit": item["unit"], "total_quantity": 0.0, "by_branch": {}},
        )
        bucket["total_quantity"] += item["quantity"]
        branch = item.get("branch") or "-"
        branch_bucket = bucket["by_branch"].setdefault(branch, {"quantity": 0.0, "item_ids": []})
        branch_bucket["quantity"] += item["quantity"]
        branch_bucket["item_ids"].append(item["id"])

    return list(grouped.values())


def get_supplier_stats(start_date: str, end_date: str) -> dict:
    """FAQAT ``market`` kategoriyasi — ``company`` (firma zakazi) bu
    hisobga kirmaydi, alohida qoladi. Hozircha faqat FAKT: jami
    pozitsiya, keltirilgan, kelmagan, bajarilish foizi."""
    items = repo.get_market_items_in_range(start_date, end_date)
    total = len(items)
    arrived = sum(1 for item in items if item["status"] == STATUS_ARRIVED)
    missing = total - arrived
    completion_rate = round(arrived / total * 100, 1) if total else 0.0
    return {
        "total": total,
        "arrived": arrived,
        "missing": missing,
        "completion_rate": completion_rate,
    }
