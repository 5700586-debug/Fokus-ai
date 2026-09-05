"""E2E test (``Sinovchi``) izolyatsiyasi — ``/sinovsmena`` REAL
``DeficiencyStates`` oqimiga kiradi va REAL ``deficiency_list_confirm``/
``deficiency_list_clarify``/``deficiency_list_edit`` handlerlari orqali
ishlaydi (hech qanday parallel/dublikat mantiq yo'q). Bu fayl aynan shu
real-handler-reuse yo'lini va DB darajasidagi izolyatsiyani tekshiradi.
"""

import pytest

import company_time
import roles
from config import FOUNDER_ID
from repositories import cash_shifts as cash_shifts_repo
from repositories import shift_deficiencies as shift_deficiencies_repo
from repositories import supplier_purchases as supplier_purchases_repo
from services import e2e_test_access, shift_deficiency
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


async def test_confirm_with_inaccessible_callback_message_does_not_crash(bot_dp, capsys):
    """Production robot tomonidan aniqlangan reproduksiya: real
    Telegram'da ``CallbackQuery.message`` har doim to'liq ``Message``
    bo'lavermaydi (``None`` yoki ``InaccessibleMessage`` ham bo'lishi
    mumkin — Bot API kafolati), lekin ``deficiency_list_confirm`` DB
    yozuvidan KEYIN uni shartsiz ``edit_reply_markup``/``answer``
    orqali chaqiradi. Bu testda ``callback.message=None`` bilan aynan
    shu holat qayta hosil qilinadi -- DB yozuvi baribir bajarilishi
    (aynan 2 ta pozitsiya), lekin foydalanuvchiga umumiy
    "Kutilmagan xatolik" ko'rinmasligi kerak."""
    from aiogram.types import CallbackQuery, Update
    from aiogram.types import User as TgUser

    main, bot = bot_dp
    await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    await send(main.dp, bot, _TESTER_ID, text="Pomidor 10 kg\nKaram 2 dona")

    user = TgUser(id=_TESTER_ID, is_bot=False, first_name="Test")
    callback = CallbackQuery(
        id="1", from_user=user, chat_instance="ci", data="csdef_list_confirm", message=None,
    )
    update = Update(update_id=1, callback_query=callback)
    bot.sent = []
    await main.dp.feed_update(bot, update)

    captured = capsys.readouterr()
    combined = " ".join(t for t in texts(bot.sent) if t)
    assert "Kutilmagan xatolik" not in combined, (
        f"aiogram global error handler ishga tushdi -- captured stdout: {captured.out!r}"
    )

    # DB yozuvi BARIBIR bajarilgan bo'lishi kerak (aynan 2 ta pozitsiya)
    # -- muammo faqat POST-SAVE javob berishda, saqlashning o'zida emas.
    today = company_time.today().isoformat()
    shift = cash_shifts_repo.get_open_test_shift(_TESTER_ID, today)
    assert shift is not None
    items = shift_deficiencies_repo.get_test_market_items(shift["test_run_id"])
    assert {i["product_name"] for i in items} == {"Pomidor", "Karam"}


async def test_confirm_survives_expired_callback_after_slow_db_save(bot_dp, monkeypatch, capsys):
    """Ikkinchi, ALOHIDA production reproduksiyasi: ``callback.message``
    bu safar TO'LIQ va mavjud ``Message`` (yuqoridagi
    ``InaccessibleMessage``/``None`` bilan aralashtirilmasin) — muammo
    ``callback.answer()``ning DB saqlashdan KEYIN, sekin so'rovdan
    keyin chaqirilishida: Telegram uni "query is too old and response
    timeout expired or query ID is invalid" (``TelegramBadRequest``)
    bilan rad etadi. Bu yerda DB saqlash sun'iy sekinlashtiriladi va
    ``callback.answer()`` FAQAT shu sekinlashuv boshlangandan KEYIN
    chaqirilsa aynan shu xatoni ko'taradi -- eski (DB'dan KEYIN
    tasdiqlovchi) kod bunga chidamaydi, yangi (DARHOL tasdiqlovchi)
    kod chidashi kerak."""
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import AnswerCallbackQuery

    from services import shift_deficiency as shift_deficiency_module

    main, bot = bot_dp
    bot.db_save_started = False
    original_call = type(bot).__call__

    async def _call_with_expiring_ack(self, method, request_timeout=None):
        if isinstance(method, AnswerCallbackQuery) and self.db_save_started:
            raise TelegramBadRequest(
                method=method,
                message=(
                    "Bad Request: query is too old and response timeout expired "
                    "or query ID is invalid"
                ),
            )
        return await original_call(self, method, request_timeout)

    monkeypatch.setattr(type(bot), "__call__", _call_with_expiring_ack)

    original_add_items_bulk = shift_deficiency_module.add_items_bulk

    def _slow_add_items_bulk(*args, **kwargs):
        bot.db_save_started = True
        return original_add_items_bulk(*args, **kwargs)

    monkeypatch.setattr(shift_deficiency_module, "add_items_bulk", _slow_add_items_bulk)

    await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    await send(main.dp, bot, _TESTER_ID, text="Pomidor 10 kg\nKaram 2 dona")

    bot.sent = []
    sent = await send_callback(main.dp, bot, _TESTER_ID, data="csdef_list_confirm", target_chat_id=_TESTER_ID)

    captured = capsys.readouterr()
    combined = " ".join(t for t in texts(sent) if t)
    assert "Kutilmagan xatolik" not in combined, (
        f"aiogram global error handler ishga tushdi -- captured stdout: {captured.out!r}"
    )
    assert "qo'shildi" in combined

    today = company_time.today().isoformat()
    shift = cash_shifts_repo.get_open_test_shift(_TESTER_ID, today)
    assert shift is not None
    items = shift_deficiencies_repo.get_test_market_items(shift["test_run_id"])
    assert {i["product_name"] for i in items} == {"Pomidor", "Karam"}


def test_cleanup_with_non_tester_id_deletes_nothing():
    from services import e2e_test_access

    result = e2e_test_access.start_test_shift(_TESTER_ID)
    assert result is not None
    _, test_run_id = result

    outcome = e2e_test_access.cleanup_test_run(111222333, test_run_id)
    assert outcome == {"items_deleted": 0, "shifts_deleted": 0}


# --------------------------------------------- interrupted-run tuzatishi --
# DB — yagona haqiqat manbai (FSM faqat vaqtinchalik UI holati). Bu
# bo'lim ``/sinovsmena`` ikkinchi marta bosilganda yoki FSM
# yo'qolganda (bot qayta ishga tushgani kabi) yugurish "yetim"
# qolmasligini, hech qachon yangi ajratilgan ``test_run_id``
# o'ylab topilmasligini tekshiradi.


def test_sinovsmena_twice_returns_same_shift_and_run_id():
    first_shift, first_run = e2e_test_access.start_test_shift(_TESTER_ID)
    second_shift, second_run = e2e_test_access.start_test_shift(_TESTER_ID)

    assert second_shift["id"] == first_shift["id"]
    assert second_run == first_run


async def test_sinovsmena_resumes_persisted_run_after_fsm_loss(bot_dp):
    from aiogram.fsm.storage.base import StorageKey

    main, bot = bot_dp
    await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    # Ro'yxatni to'liq tugatmasdan — FSM hali oraliq ("Pomidor" nomi
    # kutilmoqda) holatda, keyin bot qayta ishga tushgani kabi FSM
    # butunlay tozalanadi.
    await send(main.dp, bot, _TESTER_ID, text="Chala qator nomi")

    key = StorageKey(user_id=_TESTER_ID, chat_id=_TESTER_ID, bot_id=bot.id)
    await main.dp.storage.set_data(key, {})
    await main.dp.storage.set_state(key, None)

    sent = await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    assert "TEST smena boshlandi" in " ".join(t for t in texts(sent) if t)

    await send(main.dp, bot, _TESTER_ID, text="Pomidor 10 kg\nKaram 2 dona")
    await send_callback(main.dp, bot, _TESTER_ID, data="csdef_list_confirm", target_chat_id=_TESTER_ID)

    # Faqat BITTA test smena mavjud bo'lishi kerak (ikkinchisi
    # YARATILMAGAN), va item'lar shu YAGONA smenaning persistlangan
    # test_run_id'siga tegishli.
    today = company_time.today().isoformat()
    shift = cash_shifts_repo.get_open_test_shift(_TESTER_ID, today)
    assert shift is not None
    items = shift_deficiencies_repo.get_test_market_items(shift["test_run_id"])
    assert {i["product_name"] for i in items} == {"Pomidor", "Karam"}


async def test_sinovtugat_resolves_from_db_after_fsm_loss_and_cleans_exact_run(bot_dp):
    from aiogram.fsm.storage.base import StorageKey

    main, bot = bot_dp
    real_shift = _open_real_shift(6, "Filial-1", "2026-01-05")
    shift_deficiency.add_market_item(real_shift["id"], 6, "Behi", 2, "kg")

    await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    await send(main.dp, bot, _TESTER_ID, text="Pomidor 10 kg\nKaram 2 dona")
    await send_callback(main.dp, bot, _TESTER_ID, data="csdef_list_confirm", target_chat_id=_TESTER_ID)

    today = company_time.today().isoformat()
    shift_before = cash_shifts_repo.get_open_test_shift(_TESTER_ID, today)
    test_run_id = shift_before["test_run_id"]

    # Bot qayta ishga tushgani/FSM yo'qolgani simulyatsiyasi.
    key = StorageKey(user_id=_TESTER_ID, chat_id=_TESTER_ID, bot_id=bot.id)
    await main.dp.storage.set_data(key, {})
    await main.dp.storage.set_state(key, None)

    sent = await send(main.dp, bot, _TESTER_ID, text="/sinovtugat")
    combined = " ".join(t for t in texts(sent) if t)
    assert "yakunlandi va tozalandi" in combined
    assert "2 pozitsiya" in combined

    # 4-band: aynan shu test_run_id uchun endi hech qanday qator yo'q.
    assert shift_deficiencies_repo.get_test_market_items(test_run_id) == []
    assert cash_shifts_repo.get_open_test_shift(_TESTER_ID, today) is None

    # 5-band: parallel real smena/pozitsiya tegilmagan.
    products = {p["product_name"]: p for p in shift_deficiency.get_daily_market_shortage()}
    assert products["Behi"]["total_quantity"] == 2


def test_start_test_shift_fails_safely_on_missing_test_run_id_never_invents_one():
    """Kutilmagan/buzilgan DB holati: ``is_test=1`` ochiq smena bor,
    lekin ``test_run_id`` bo'sh — hech qachon yangi ID o'ylab
    topilmaydi, aniq TEST xatosi ko'tariladi."""
    today = company_time.today().isoformat()
    cash_shifts_repo.open_shift(_TESTER_ID, "E2E-TEST", today, opening_balance=0, tolerance=0, is_test=True)

    with pytest.raises(e2e_test_access.TestRunStateError):
        e2e_test_access.start_test_shift(_TESTER_ID)


async def test_sinovsmena_reports_clear_error_on_corrupted_test_run_state(bot_dp):
    main, bot = bot_dp
    today = company_time.today().isoformat()
    cash_shifts_repo.open_shift(_TESTER_ID, "E2E-TEST", today, opening_balance=0, tolerance=0, is_test=True)

    sent = await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    combined = " ".join(t for t in texts(sent) if t)
    assert "TEST xatosi" in combined
    assert "TEST smena boshlandi" not in combined


async def test_other_telegram_id_cannot_read_resume_or_clean_testers_run(bot_dp):
    main, bot = bot_dp
    other_id = 555444333

    await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    await send(main.dp, bot, _TESTER_ID, text="Pomidor 10 kg\nKaram 2 dona")
    await send_callback(main.dp, bot, _TESTER_ID, data="csdef_list_confirm", target_chat_id=_TESTER_ID)

    today = company_time.today().isoformat()
    tester_shift = cash_shifts_repo.get_open_test_shift(_TESTER_ID, today)
    test_run_id = tester_shift["test_run_id"]

    # Boshqa ID uchun test rejimiga kirish/davom ettirish/tozalash —
    # hammasi rad etiladi yoki hech narsaga ta'sir qilmaydi.
    assert e2e_test_access.start_test_shift(other_id) is None
    assert e2e_test_access.finish_active_test_run(other_id) == {
        "items_deleted": 0, "shifts_deleted": 0, "found": False,
    }
    assert e2e_test_access.cleanup_test_run(other_id, test_run_id) == {
        "items_deleted": 0, "shifts_deleted": 0,
    }

    sent = await send(main.dp, bot, other_id, text="/sinovsmena")
    assert "TEST smena boshlandi" not in " ".join(t for t in texts(sent) if t)

    sent = await send(main.dp, bot, other_id, text="/xarid")
    combined = " ".join(t for t in texts(sent) if t)
    assert "Pomidor" not in combined
    assert "Karam" not in combined

    # Tester'ning o'z yugurishi tegilmagan holda qoladi.
    items = shift_deficiencies_repo.get_test_market_items(test_run_id)
    assert {i["product_name"] for i in items} == {"Pomidor", "Karam"}
