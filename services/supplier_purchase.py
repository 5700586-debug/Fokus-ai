"""Ta'minotchining REAL bozor xaridi V1: real miqdor+narx bilan xarid
yozish, narx tarixi asosida SEZILARLI oshishni tor AI chaqiruvi bilan
tekshirish.

KPI/bonus/jarima/dashboard/scheduler ATAYLAB YO'Q. AI hech qachon
yakuniy qaror chiqarmaydi (loyihadagi ``services/discipline_ai.py``
bilan bir xil tamoyil — bitta tor ``client.responses.create`` chaqiruvi,
oddiy fallback).
"""

from openai import AsyncOpenAI

import company_time
from repositories import shift_deficiencies as deficiency_repo
from repositories import supplier_purchases as repo
from services import shift_deficiency

PRICE_INCREASE_MULTIPLIER = 1.20
_AI_MODEL = "gpt-5-mini"


def should_check_price_increase(new_price: int, previous_price: int | None) -> bool:
    """Deterministik oldindan filtr — AI xarajatini tejaydi. Faqat
    ``new_price >= previous_price * 1.20`` bo'lsa ``True`` (tushish/
    teng/kichik oshish AI'ga umuman yuborilmaydi; oldingi narx yo'q
    bo'lsa ham AI chaqirilmaydi)."""
    if previous_price is None or previous_price <= 0:
        return False
    return new_price >= previous_price * PRICE_INCREASE_MULTIPLIER


async def check_price_spike(client: AsyncOpenAI, product_name: str, previous_price: int, new_price: int) -> bool:
    """``services/discipline_ai.py::confirm_rule_match`` bilan bir xil
    uslub: bitta tor AI chaqiruvi, oddiy fallback. Xato/noaniq javobda
    FAIL-SAFE — ta'minotchi bezovta qilinmaydi (``False``)."""
    try:
        response = await client.responses.create(
            model=_AI_MODEL,
            instructions=(
                "Sen Fokus AI xarid nazoratchisisan. Ta'minotchi bir mahsulotni oldingi "
                "xarid narxidan sezilarli qimmatga sotib oldi. Bu oshish NOODATIY/SEZILARLI "
                "darajadami, yoki oddiy bozor tebranishi doirasidami? FAQAT bitta so'z bilan "
                "javob ber: 'HA' (noodatiy, savol berish kerak) yoki 'YOQ' (oddiy tebranish). "
                "Boshqa hech qanday matn yozma."
            ),
            input=(
                f"Mahsulot: {product_name}\n"
                f"Oldingi xarid narxi: {previous_price} so'm\n"
                f"Bugungi xarid narxi: {new_price} so'm"
            ),
        )
        raw = (response.output_text or "").strip().upper()
    except Exception as error:  # noqa: BLE001
        print(f"OpenAI xatosi (check_price_spike): {error!r}")
        return False

    return raw.startswith("HA")


def record_purchase(
    product_name: str, quantity: float, unit: str, unit_price: int, purchased_by: int,
    price_flagged: bool = False, price_flag_reason: str | None = None,
) -> int | None:
    """SO'RALGAN miqdordan kam/teng/ko'p bo'lishidan qat'i nazar —
    hech qanday "requested dan oshmasin" cheklovi yo'q, faqat musbat
    son va bilinadigan birlik talab qilinadi."""
    name = (product_name or "").strip()
    if not name or unit not in shift_deficiency.KNOWN_UNITS or quantity is None or quantity <= 0:
        return None
    if unit_price is None or unit_price <= 0:
        return None

    return repo.add_purchase(
        name, quantity, unit, unit_price, purchased_by, company_time.today().isoformat(),
        price_flagged, price_flag_reason,
    )


def save_allocations(purchase_id: int, allocations: dict[str, float]) -> None:
    """``allocations`` — {branch: real_quantity}. Filial so'ragan
    miqdordan REAL ko'p bo'lishi mumkin — bu yerda hech qanday
    "so'ralgandan oshmasin" cheklovi yo'q (bot qatlamida faqat JAMI
    xarid miqdoridan oshmasligi tekshiriladi). FIFO yo'q — ta'minotchi
    o'zi real kiritgan qiymat aynan shu holicha yoziladi."""
    for branch, quantity in allocations.items():
        if quantity and quantity > 0:
            repo.add_allocation(purchase_id, branch, quantity)


def resolve_deficiency_items(item_ids: list[int]) -> None:
    """Shu filial uchun taqsimot bajarilgan bozorlik item'larini
    "keldi" deb yopadi — mavjud ``shift_deficiency`` naqshi bilan bir
    xil (``repositories.shift_deficiencies.mark_item_resolved``)."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    for item_id in item_ids:
        deficiency_repo.mark_item_resolved(item_id, now)


def get_branch_report_for_date(purchase_date: str) -> dict:
    """Har filial uchun pozitsiyalar + jami, va barcha filiallar
    bo'yicha umumiy summa. ``branch_item_total = real_allocated_qty
    × purchase_unit_price``."""
    rows = repo.get_allocations_for_date(purchase_date)

    by_branch: dict[str, dict] = {}
    grand_total = 0.0
    for row in rows:
        item_total = row["quantity"] * row["unit_price"]
        bucket = by_branch.setdefault(row["branch"], {"items": [], "total": 0.0})
        bucket["items"].append(
            {
                "product_name": row["product_name"], "quantity": row["quantity"],
                "unit": row["unit"], "unit_price": row["unit_price"], "item_total": item_total,
            }
        )
        bucket["total"] += item_total
        grand_total += item_total

    return {"by_branch": by_branch, "grand_total": grand_total}
