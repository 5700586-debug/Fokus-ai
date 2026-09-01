import pytest

import company_time
from config import FOUNDER_ID
from repositories import cash_shifts as cash_shifts_repo
from repositories import supplier_purchases as supplier_purchases_repo
from services import shift_deficiency, supplier_purchase
from tests.bot_harness import send, send_callback, texts

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_taminotchi(user_id: int) -> None:
    from roles import set_role

    set_role(user_id, "taminotchi", set_by=FOUNDER_ID)


def _open_shift(employee_id: int, branch: str, shift_date: str) -> dict:
    return cash_shifts_repo.open_shift(employee_id, branch, shift_date, opening_balance=0, tolerance=20000)


def _has_finish_button(sent) -> bool:
    return any(
        getattr(button, "callback_data", None) == "sup_alloc_finish"
        for message in sent if getattr(message, "reply_markup", None)
        for row in message.reply_markup.inline_keyboard for button in row
    )


# ------------------------------------------------------- services/supplier_purchase --


def test_save_allocations_writes_only_positive_quantities():
    purchase_id = supplier_purchases_repo.add_purchase("Pomidor", 75, "kg", 12000, 1, "2026-01-05", False, None)
    supplier_purchase.save_allocations(purchase_id, {"Filial-1": 20, "Filial-2": 0, "Filial-3": 55})

    report = supplier_purchase.get_branch_report_for_date("2026-01-05")
    assert set(report["by_branch"].keys()) == {"Filial-1", "Filial-3"}


def test_branch_report_computes_item_and_grand_totals():
    purchase_id = supplier_purchases_repo.add_purchase("Pomidor", 75, "kg", 12000, 1, "2026-01-05", False, None)
    supplier_purchase.save_allocations(purchase_id, {"Filial-1": 20, "Filial-2": 30, "Filial-3": 25})

    report = supplier_purchase.get_branch_report_for_date("2026-01-05")
    assert report["by_branch"]["Filial-1"]["total"] == 240000
    assert report["by_branch"]["Filial-2"]["total"] == 360000
    assert report["by_branch"]["Filial-3"]["total"] == 300000
    assert report["grand_total"] == 900000


def test_resolve_deficiency_items_marks_only_given_ids():
    shift = _open_shift(1, "Filial-1", "2026-01-05")
    id1 = shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 10, "kg")
    shift_deficiency.add_market_item(shift["id"], 1, "Kartoshka", 5, "kg")

    supplier_purchase.resolve_deficiency_items([id1])

    remaining = shift_deficiency.get_daily_market_shortage()
    names = {p["product_name"] for p in remaining}
    assert names == {"Kartoshka"}


# ------------------------------------------------------------- /xarid allocation UI --


async def test_allocation_branch_can_receive_more_than_requested(bot_dp):
    main, bot = bot_dp
    _make_taminotchi(777)
    today = company_time.today().isoformat()
    shift = _open_shift(1, "Filial-1", today)
    shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 10, "kg")

    await send(main.dp, bot, 777, text="/xarid")
    await send_callback(main.dp, bot, 777, data="sup_pick:0", target_chat_id=777)
    await send(main.dp, bot, 777, text="15")
    sent = await send(main.dp, bot, 777, text="12000")
    assert "Filial-1 — so'ralgan: 10 kg, hozircha: 0 kg" in " ".join(t for t in texts(sent) if t)

    sent = await send_callback(main.dp, bot, 777, data="sup_alloc_branch:0", target_chat_id=777)
    assert "Filial-1 uchun real necha kg berildi?" in " ".join(t for t in texts(sent) if t)

    sent = await send(main.dp, bot, 777, text="11.2")  # so'ralgan (10) dan ko'p
    assert "Filial-1 — so'ralgan: 10 kg, hozircha: 11.2 kg" in " ".join(t for t in texts(sent) if t)


async def test_allocation_total_cannot_exceed_purchased_quantity(bot_dp):
    main, bot = bot_dp
    _make_taminotchi(777)
    today = company_time.today().isoformat()
    shift_a = _open_shift(1, "Filial-1", today)
    shift_b = _open_shift(2, "Filial-2", today)
    shift_deficiency.add_market_item(shift_a["id"], 1, "Pomidor", 20, "kg")
    shift_deficiency.add_market_item(shift_b["id"], 2, "Pomidor", 30, "kg")

    await send(main.dp, bot, 777, text="/xarid")
    await send_callback(main.dp, bot, 777, data="sup_pick:0", target_chat_id=777)
    await send(main.dp, bot, 777, text="40")  # jami xarid 40 kg
    await send(main.dp, bot, 777, text="12000")

    await send_callback(main.dp, bot, 777, data="sup_alloc_branch:0", target_chat_id=777)
    sent = await send(main.dp, bot, 777, text="35")
    assert "Filial-1 — so'ralgan: 20 kg, hozircha: 35 kg" in " ".join(t for t in texts(sent) if t)

    await send_callback(main.dp, bot, 777, data="sup_alloc_branch:1", target_chat_id=777)
    sent = await send(main.dp, bot, 777, text="10")  # 35 + 10 = 45 > 40 -- rad etiladi

    combined = " ".join(t for t in texts(sent) if t)
    assert "oshib ketadi" in combined
    assert "Qoldi: 5" in combined


async def test_allocation_finish_button_hidden_until_fully_distributed(bot_dp):
    main, bot = bot_dp
    _make_taminotchi(777)
    today = company_time.today().isoformat()
    shift = _open_shift(1, "Filial-1", today)
    shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 20, "kg")

    await send(main.dp, bot, 777, text="/xarid")
    await send_callback(main.dp, bot, 777, data="sup_pick:0", target_chat_id=777)
    await send(main.dp, bot, 777, text="20")
    await send(main.dp, bot, 777, text="12000")

    await send_callback(main.dp, bot, 777, data="sup_alloc_branch:0", target_chat_id=777)
    sent = await send(main.dp, bot, 777, text="15")  # qoldi 5

    assert not _has_finish_button(sent)


async def test_allocation_finish_resolves_items_and_shows_branch_report(bot_dp):
    main, bot = bot_dp
    _make_taminotchi(777)
    today = company_time.today().isoformat()
    shift_a = _open_shift(1, "Filial-1", today)
    shift_b = _open_shift(2, "Filial-2", today)
    shift_deficiency.add_market_item(shift_a["id"], 1, "Pomidor", 20, "kg")
    shift_deficiency.add_market_item(shift_b["id"], 2, "Pomidor", 30, "kg")

    await send(main.dp, bot, 777, text="/xarid")
    await send_callback(main.dp, bot, 777, data="sup_pick:0", target_chat_id=777)
    await send(main.dp, bot, 777, text="50")
    await send(main.dp, bot, 777, text="12000")

    await send_callback(main.dp, bot, 777, data="sup_alloc_branch:0", target_chat_id=777)
    await send(main.dp, bot, 777, text="20")
    await send_callback(main.dp, bot, 777, data="sup_alloc_branch:1", target_chat_id=777)
    sent = await send(main.dp, bot, 777, text="30")
    assert _has_finish_button(sent)

    sent = await send_callback(main.dp, bot, 777, data="sup_alloc_finish", target_chat_id=777)
    combined = " ".join(t for t in texts(sent) if t)
    assert "🏢 Filial-1" in combined
    assert "Pomidor — 20 kg × 12 000 = 240 000" in combined
    assert "🏢 Filial-2" in combined
    assert "Pomidor — 30 kg × 12 000 = 360 000" in combined
    assert "Umumiy bozorlik: 600 000" in combined

    # Har filial AYNAN o'z buyurtmasini yopadi -- FIFO/avtomatik taqsimot yo'q.
    assert shift_deficiency.get_daily_market_shortage() == []


async def test_ad_hoc_product_allocation_uses_real_branch_list_not_hardcoded(bot_dp):
    main, bot = bot_dp
    _make_taminotchi(777)

    await send(main.dp, bot, 777, text="/xarid")
    await send_callback(main.dp, bot, 777, data="sup_add_product", target_chat_id=777)
    await send(main.dp, bot, 777, text="Sham")
    await send(main.dp, bot, 777, text="4")
    await send_callback(main.dp, bot, 777, data="sup_new_unit:dona", target_chat_id=777)
    sent = await send(main.dp, bot, 777, text="5000")

    combined = " ".join(t for t in texts(sent) if t)
    from config import RECRUITING_BRANCH_NAMES

    for branch in RECRUITING_BRANCH_NAMES:
        assert f"{branch} — so'ralgan: 0 dona" in combined
