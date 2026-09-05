"""E2E test (``Sinovchi``) izolyatsiyasi — ``/sinovsmena`` REAL
``DeficiencyStates`` oqimiga kiradi va REAL ``deficiency_list_confirm``/
``deficiency_list_clarify``/``deficiency_list_edit`` handlerlari orqali
ishlaydi (hech qanday parallel/dublikat mantiq yo'q). Bu fayl aynan shu
real-handler-reuse yo'lini va DB darajasidagi izolyatsiyani tekshiradi.
"""

import pytest

import roles
from config import FOUNDER_ID
from repositories import cash_shifts as cash_shifts_repo
from repositories import supplier_purchases as supplier_purchases_repo
from services import shift_deficiency
from tests.bot_harness import send, send_callback, texts

pytestmark = pytest.mark.anyio

_TESTER_ID = roles.E2E_TESTER_TELEGRAM_ID


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _open_real_shift(employee_id: int, branch: str, shift_date: str) -> dict:
    return cash_shifts_repo.open_shift(employee_id, branch, shift_date, opening_balance=0, tolerance=20000)


def _make_taminotchi(user_id: int) -> None:
    from roles import set_role

    set_role(user_id, "taminotchi", set_by=FOUNDER_ID)


async def test_sinovsmena_enters_real_deficiency_states_flow(bot_dp):
    main, bot = bot_dp
    sent = await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    combined = " ".join(t for t in texts(sent) if t)
    assert "TEST smena boshlandi" in combined

    # Ro'yxat yozilganda REAL ``_process_deficiency_list``/
    # ``_advance_deficiency_list`` javobi ko'rinishi kerak (bir xil
    # matn/tugma — hech qanday parallel "TEST ro'yxati" matni yo'q).
    sent = await send(main.dp, bot, _TESTER_ID, text="Pomidor 10 kg\nKaram 2 dona")
    combined = " ".join(t for t in texts(sent) if t)
    assert "Ro'yxat tayyor" in combined
    assert "Tasdiqlaysizmi?" in combined


async def test_real_confirm_handler_tags_test_rows_and_excludes_from_real_view(bot_dp):
    main, bot = bot_dp
    real_shift = _open_real_shift(1, "Filial-1", "2026-01-05")
    shift_deficiency.add_market_item(real_shift["id"], 1, "Un", 5, "quti")

    await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    await send(main.dp, bot, _TESTER_ID, text="Pomidor 10 kg\nKaram 2 dona")
    sent = await send_callback(main.dp, bot, _TESTER_ID, data="csdef_list_confirm", target_chat_id=_TESTER_ID)
    assert "TEST" in " ".join(t for t in texts(sent) if t)

    # Real ko'rinish faqat "Un"ni ko'radi — test qatorlari umuman yo'q.
    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert set(products) == {"Un"}
    assert products["Un"]["total_quantity"] == 5


async def test_duplicate_confirm_does_not_duplicate_test_rows(bot_dp):
    import company_time

    main, bot = bot_dp
    await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    await send(main.dp, bot, _TESTER_ID, text="Pomidor 10 kg\nKaram 2 dona")

    first = await send_callback(main.dp, bot, _TESTER_ID, data="csdef_list_confirm", target_chat_id=_TESTER_ID)
    assert "qo'shildi" in " ".join(t for t in texts(first) if t)

    second = await send_callback(main.dp, bot, _TESTER_ID, data="csdef_list_confirm", target_chat_id=_TESTER_ID)
    assert "qo'shildi" not in " ".join(t for t in texts(second) if t)

    # Ikkinchi (dublikat) confirm hech qanday qo'shimcha qator
    # yozmagan bo'lishi kerak — test smenasidagi item'lar soni
    # aynan 2 ta (Pomidor, Karam) bo'lib qolishi shart.
    test_shift = cash_shifts_repo.get_open_shift(_TESTER_ID, company_time.today().isoformat())
    from repositories import shift_deficiencies as shift_deficiencies_repo

    all_items = shift_deficiencies_repo.get_open_market_items_through(
        company_time.today().isoformat(), is_test=True
    )
    tester_items = [item for item in all_items if item["shift_id"] == test_shift["id"]]
    assert {item["product_name"] for item in tester_items} == {"Pomidor", "Karam"}
    assert len(tester_items) == 2


async def test_existing_xarid_shows_only_testers_exact_run(bot_dp):
    main, bot = bot_dp
    _make_taminotchi(777)
    real_shift = _open_real_shift(2, "Filial-1", "2026-01-05")
    shift_deficiency.add_market_item(real_shift["id"], 2, "Bodring", 6, "kg")

    await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    # 1 qatorli kirim REAL bitta-mahsulot oqimini (alohida miqdor
    # so'rovi) ishga tushiradi, ko'p qatorli AI ro'yxati EMAS — shu
    # sabab bu yerda ATAYLAB 2 qatorli kirim ishlatiladi (real
    # ``_process_deficiency_list``/``csdef_list_confirm`` yo'li).
    await send(main.dp, bot, _TESTER_ID, text="Sinov mahsuloti 3 dona\nYana bir mahsulot 1 dona")
    await send_callback(main.dp, bot, _TESTER_ID, data="csdef_list_confirm", target_chat_id=_TESTER_ID)

    tester_view = " ".join(t for t in texts(await send(main.dp, bot, _TESTER_ID, text="/xarid")) if t)
    assert "Sinov mahsuloti" in tester_view
    assert "Bodring" not in tester_view

    supplier_view = " ".join(t for t in texts(await send(main.dp, bot, 777, text="/xarid")) if t)
    assert "Bodring" in supplier_view
    assert "Sinov mahsuloti" not in supplier_view


async def test_tester_cannot_record_real_supplier_purchase(bot_dp):
    main, bot = bot_dp
    await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    await send(main.dp, bot, _TESTER_ID, text="Sinov mahsuloti 3 dona\nYana bir mahsulot 1 dona")
    await send_callback(main.dp, bot, _TESTER_ID, data="csdef_list_confirm", target_chat_id=_TESTER_ID)

    await send(main.dp, bot, _TESTER_ID, text="/xarid")
    # ``sup_pick:`` ACTION_RECORD_SUPPLIER_PURCHASE talab qiladi — tester
    # bunga ega emas (faqat ACTION_E2E_VIEW_TEST_RUN), shuning uchun
    # real xarid yozish oqimi HECH QACHON ochilmaydi.
    sent = await send_callback(main.dp, bot, _TESTER_ID, data="sup_pick:0", target_chat_id=_TESTER_ID)
    combined = " ".join(t for t in texts(sent) if t)
    assert "Kerak:" not in combined

    assert supplier_purchases_repo.get_price_history("Sinov mahsuloti", "dona") is None


async def test_sinovtugat_cleanup_does_not_delete_real_rows(bot_dp):
    main, bot = bot_dp
    real_shift = _open_real_shift(3, "Filial-1", "2026-01-05")
    shift_deficiency.add_market_item(real_shift["id"], 3, "Sabzi", 4, "kg")

    await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    await send(main.dp, bot, _TESTER_ID, text="Sinov mahsuloti 3 dona\nYana bir mahsulot 1 dona")
    await send_callback(main.dp, bot, _TESTER_ID, data="csdef_list_confirm", target_chat_id=_TESTER_ID)

    await send(main.dp, bot, _TESTER_ID, text="/sinovtugat")

    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert products["Sabzi"]["total_quantity"] == 4

    tester_view = " ".join(t for t in texts(await send(main.dp, bot, _TESTER_ID, text="/xarid")) if t)
    assert "Faol TEST yugurish topilmadi" in tester_view


async def test_repo_defaults_exclude_test_rows_from_real_queries():
    from repositories import shift_deficiencies as shift_deficiencies_repo

    real_shift = _open_real_shift(4, "Filial-1", "2026-01-05")
    shift_deficiencies_repo.add_items_bulk(
        real_shift["id"], 4, "Filial-1", "market",
        [{"product_name": "Real qator", "quantity": 1, "unit": "dona"}], "2026-01-05",
    )
    shift_deficiencies_repo.add_items_bulk(
        real_shift["id"], 4, "Filial-1", "market",
        [{"product_name": "Test qator", "quantity": 1, "unit": "dona"}], "2026-01-05",
        is_test=True, test_run_id="run-x",
    )

    default_view = {row["product_name"] for row in shift_deficiencies_repo.get_open_market_items_through("2026-01-05")}
    assert default_view == {"Real qator"}

    test_view = {row["product_name"] for row in shift_deficiencies_repo.get_open_market_items_through("2026-01-05", is_test=True)}
    assert test_view == {"Test qator"}


def test_cleanup_with_wrong_run_id_never_touches_real_data():
    from services import e2e_test_access

    real_shift = _open_real_shift(5, "Filial-1", "2026-01-05")
    shift_deficiency.add_market_item(real_shift["id"], 5, "Karam", 6, "kg")

    outcome = e2e_test_access.cleanup_test_run(_TESTER_ID, "no-such-run-id")
    assert outcome == {"items_deleted": 0, "shifts_deleted": 0}

    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert products["Karam"]["total_quantity"] == 6


def test_cleanup_with_non_tester_id_deletes_nothing():
    from services import e2e_test_access

    result = e2e_test_access.start_test_shift(_TESTER_ID)
    assert result is not None
    _, test_run_id = result

    outcome = e2e_test_access.cleanup_test_run(111222333, test_run_id)
    assert outcome == {"items_deleted": 0, "shifts_deleted": 0}
