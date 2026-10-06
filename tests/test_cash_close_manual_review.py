"""Kassa yopish (qo'lda): 3 rasm + 2 summa -> moliyachi tekshiruvi; AI summa o'qimaydi; rasmlar saqlanmaydi."""

import pytest
from aiogram.methods import DeleteMessage, SendMessage, SendPhoto

import cash_shift_bot
from config import FOUNDER_ID
from db import get_connection
from repositories import cash_shifts as cash_shifts_repo
from services import cash_shift
from tests.bot_harness import send, send_callback
from tests.test_cash_shift_bot_flows import _clear_daily_report_gate, _clear_deficiency_gate, _make_kassir, _open_shift

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("manual_close_review")]

KASSIR, MOLIYACHI = 111, 222


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _texts(sent) -> list[str]:
    return [m.text for m in sent if getattr(m, "text", None)]


def _joined(sent) -> str:
    return "\n".join(_texts(sent))


async def _to_photo_prompt(main, bot):
    _make_kassir(KASSIR)
    from roles import set_role

    set_role(MOLIYACHI, "moliyachi", set_by=FOUNDER_ID)
    await _open_shift(main, bot, KASSIR, "0")
    await send(main.dp, bot, KASSIR, text="/closeshift")
    await _clear_deficiency_gate(main, bot, KASSIR)
    return await _clear_daily_report_gate_and_get_prompt(main, bot)


async def _clear_daily_report_gate_and_get_prompt(main, bot):
    await send_callback(main.dp, bot, KASSIR, data="csdr_prixod:0", target_chat_id=KASSIR)
    await send_callback(main.dp, bot, KASSIR, data="csdr_price:0", target_chat_id=KASSIR)
    return await send_callback(main.dp, bot, KASSIR, data="csdr_staff_no", target_chat_id=KASSIR)


async def _submit_to_moliyachi(main, bot, left="300000"):
    await send(main.dp, bot, KASSIR, photo_file_id="notebook_file")
    await send(main.dp, bot, KASSIR, photo_file_id="pos_file")
    await send(main.dp, bot, KASSIR, photo_file_id="receipts_file")
    await send(main.dp, bot, KASSIR, text=left)
    return await send_callback(main.dp, bot, KASSIR, data="csui_rev_send", target_chat_id=KASSIR)


def _shift():
    return cash_shifts_repo.get_open_shift(KASSIR, __import__("company_time").today().isoformat())


async def test_cashier_is_asked_three_photos_then_only_the_cash_left(bot_dp, monkeypatch):
    main, bot = bot_dp

    async def _boom(*args, **kwargs):  # AI rasmdan summa o'qishga HECH QACHON chaqirilmasligi kerak
        raise AssertionError("AI daftar/POS/chek summalarini o'qimasligi kerak")

    monkeypatch.setattr(cash_shift_bot, "_extract_cash_shift_fields", _boom)

    prompt = await _to_photo_prompt(main, bot)
    text = _joined(prompt)
    assert "📒 Daftar rasmini yuboring." in text
    assert "Hisobot chiroyli yozilgan va rasm tiniq bo'lsin. Yuborishdan oldin o'zingiz tekshiring." in text
    assert (
        "Xira yoki o'qib bo'lmaydigan rasm moliyachi tomonidan qaytarilishi va intizomiy minusga sabab bo'lishi mumkin."
        in text
    )

    sent = await send(main.dp, bot, KASSIR, photo_file_id="notebook_file")
    assert "🖥 Programma/POS rasmini yuboring.\nRaqamlar aniq ko'rinsin. Xira rasm yubormang." in _joined(sent)
    sent = await send(main.dp, bot, KASSIR, photo_file_id="pos_file")
    assert "🧾 Cheklar rasmini yuboring.\nCheklar va summa aniq ko'rinsin. Yuborishdan oldin tekshiring." in _joined(sent)
    sent = await send(main.dp, bot, KASSIR, photo_file_id="receipts_file")
    assert "Kassada qancha naqd qoldiryapsiz?" in _joined(sent)  # FAQAT shu summa
    sent = await send(main.dp, bot, KASSIR, text="300000")

    text = _joined(sent)
    assert "300 000" in text.replace("\u00a0", " ") or "300000" in text
    for forbidden in (
        "qabul qilgan", "Qabul qilingan", "AI o'qigan", "mos kelmadi", "qaysi biri to'g'ri", "karta", "Karta",
        "Boshqa to'lov",
    ):
        assert forbidden not in text


async def test_moliyachi_gets_three_photos_and_cash_left_in_one_review_card(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)

    sent = await _submit_to_moliyachi(main, bot)

    photos = [m for m in sent if isinstance(m, SendPhoto) and m.chat_id == MOLIYACHI]
    assert [p.photo for p in photos] == ["notebook_file", "pos_file", "receipts_file"]
    assert [p.caption for p in photos] == ["📒 Daftar", "🖥 Programma/POS", "🧾 Cheklar"]
    card = next(m for m in sent if isinstance(m, SendMessage) and m.chat_id == MOLIYACHI)
    compact = card.text.replace(" ", "").replace("\u00a0", "")
    assert "Filial:Filial-1" in compact and "Kassir:KassirovAli" in compact and "smena#" in compact
    assert "Kassadaqoldirilgannaqd:300000" in compact
    assert "qabul qilingan" not in card.text
    buttons = [b.callback_data for row in card.reply_markup.inline_keyboard for b in row]
    assert buttons == [f"cashclose_ok:{_shift()['id']}", f"cashclose_no:{_shift()['id']}"]

    kassir_texts = _texts([m for m in sent if getattr(m, "chat_id", None) == KASSIR])
    final = "\n".join(kassir_texts)
    assert "✅ Smena yopildi. Ma'lumot moliyachiga yuborildi." in final
    assert "Bugungi ishingiz uchun rahmat.\nYaxshi dam oling. Saturn jamoasi sizni qadrlaydi." in final
    assert "tasdiqlashini kuting" not in final and "Tasdiqlashni kuting" not in final
    home = [m for m in sent if isinstance(m, SendMessage) and m.chat_id == KASSIR and "Smena yopildi" in m.text][0]
    assert [b.text for row in home.reply_markup.keyboard for b in row] == ["🏠 Asosiy menyu"]

    shift = _shift()
    assert shift["status"] == cash_shift.STATUS_NEEDS_FINANCE_REVIEW
    assert shift["cash_sales"] is None and shift["actual_cash_balance"] == 300000
    assert shift["card_sales"] is None and shift["difference"] is None  # hisoblanmagan: 0 emas, NULL
    assert not shift.get("sales_report_photo_ref") and not shift.get("cash_report_photo_ref")


async def test_without_moliyachi_review_goes_to_founder(bot_dp):
    main, bot = bot_dp
    _make_kassir(KASSIR)
    await _open_shift(main, bot, KASSIR, "0")
    await send(main.dp, bot, KASSIR, text="/closeshift")
    await _clear_deficiency_gate(main, bot, KASSIR)
    await _clear_daily_report_gate_and_get_prompt(main, bot)

    sent = await _submit_to_moliyachi(main, bot)

    assert {m.chat_id for m in sent if isinstance(m, (SendPhoto, SendMessage)) and m.chat_id != KASSIR} == {FOUNDER_ID}


async def test_approval_closes_shift_deletes_photo_messages_and_keeps_no_photo_records(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)
    shift_id = _shift()["id"]

    sent = await send_callback(main.dp, bot, MOLIYACHI, data=f"cashclose_ok:{shift_id}", target_chat_id=MOLIYACHI)

    assert _shift()["status"] == cash_shift.STATUS_CLEAN_CLOSED
    deleted = [m for m in sent if isinstance(m, DeleteMessage)]
    assert {m.chat_id for m in deleted} == {KASSIR, MOLIYACHI}  # kassir va moliyachi chatidagi rasm xabarlari
    assert len(deleted) >= 4
    assert any(m.chat_id == KASSIR and "Moliyachi smenangizni tasdiqladi" in (getattr(m, "text", "") or "") for m in sent)

    conn = get_connection()
    try:
        left = conn.execute(
            "SELECT COUNT(*) AS n FROM bot_workflow_messages WHERE workflow = 'cash_close_review'"
        ).fetchone()["n"]
        decision = conn.execute("SELECT decision FROM cash_shift_approvals WHERE shift_id = ?", (shift_id,)).fetchone()
    finally:
        conn.close()
    assert left == 0
    assert decision["decision"] == "finance_approved"
    row = _shift()
    assert not any("file" in str(value) for key, value in row.items() if key.endswith("_ref"))

    again = await send_callback(main.dp, bot, MOLIYACHI, data=f"cashclose_ok:{shift_id}", target_chat_id=MOLIYACHI)
    assert not any(isinstance(m, DeleteMessage) for m in again)  # takroriy bosish hech narsa qilmaydi
    assert _shift()["status"] == cash_shift.STATUS_CLEAN_CLOSED


async def test_rejection_asks_to_resend_and_photos_are_still_not_stored(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)
    shift_id = _shift()["id"]

    sent = await send_callback(main.dp, bot, MOLIYACHI, data=f"cashclose_no:{shift_id}", target_chat_id=MOLIYACHI)

    assert _shift()["status"] == cash_shift.STATUS_RECHECK_REQUIRED
    assert any(isinstance(m, DeleteMessage) for m in sent)
    assert any(m.chat_id == KASSIR and "qayta yuboring" in (getattr(m, "text", "") or "") for m in sent)

    again = await send(main.dp, bot, KASSIR, text="/closeshift")
    assert "📒 Daftar rasmini yuboring" in _joined(again)  # rasmlar qayta so'raladi
    await send(main.dp, bot, KASSIR, photo_file_id="notebook_2")
    await send(main.dp, bot, KASSIR, photo_file_id="pos_2")
    await send(main.dp, bot, KASSIR, photo_file_id="receipts_2")
    await send(main.dp, bot, KASSIR, text="1600000")
    await send(main.dp, bot, KASSIR, text="350000")
    resent = await send_callback(main.dp, bot, KASSIR, data="csui_rev_send", target_chat_id=KASSIR)
    assert [p.photo for p in resent if isinstance(p, SendPhoto)] == ["notebook_2", "pos_2", "receipts_2"]
    assert _shift()["status"] == cash_shift.STATUS_NEEDS_FINANCE_REVIEW


async def test_only_finance_or_founder_can_decide_and_cashier_waits(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)
    shift_id = _shift()["id"]

    await send_callback(main.dp, bot, KASSIR, data=f"cashclose_ok:{shift_id}", target_chat_id=KASSIR)  # kassirning o'zi
    from roles import set_role

    set_role(333, "nazoratchi", set_by=FOUNDER_ID)
    await send_callback(main.dp, bot, 333, data=f"cashclose_ok:{shift_id}", target_chat_id=333)  # nazoratchi
    assert _shift()["status"] == cash_shift.STATUS_NEEDS_FINANCE_REVIEW

    waiting = await send(main.dp, bot, KASSIR, text="/closeshift")
    assert "allaqachon yopilgan" in _joined(waiting) and "tekshiruvida" not in _joined(waiting)

    await send_callback(main.dp, bot, FOUNDER_ID, data=f"cashclose_ok:{shift_id}", target_chat_id=FOUNDER_ID)
    assert _shift()["status"] == cash_shift.STATUS_CLEAN_CLOSED


async def test_non_photo_and_bad_amount_do_not_advance(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)

    sent = await send(main.dp, bot, KASSIR, text="rasm emas")
    assert "surat (photo) sifatida" in _joined(sent)
    await send(main.dp, bot, KASSIR, photo_file_id="n")
    await send(main.dp, bot, KASSIR, photo_file_id="p")
    await send(main.dp, bot, KASSIR, photo_file_id="r")
    sent = await send(main.dp, bot, KASSIR, text="abc")
    assert "Faqat musbat raqam" in _joined(sent)



async def _fsm_data(main, bot, user_id: int) -> dict:
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey

    context = FSMContext(storage=main.dp.storage, key=StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id))
    return await context.get_data()


_PHOTO_KEYS = ("review_notebook", "review_pos", "review_receipts")


async def test_restart_button_drops_old_file_ids_and_only_new_photos_reach_moliyachi(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await send(main.dp, bot, KASSIR, photo_file_id="old_notebook")
    await send(main.dp, bot, KASSIR, photo_file_id="old_pos")
    await send(main.dp, bot, KASSIR, photo_file_id="old_receipts")
    assert (await _fsm_data(main, bot, KASSIR))["review_notebook"] == "old_notebook"

    sent = await send_callback(main.dp, bot, KASSIR, data="csui_rev_restart", target_chat_id=KASSIR)
    assert "📒 Daftar rasmini yuboring" in _joined(sent)
    data = await _fsm_data(main, bot, KASSIR)
    assert all(data[key] is None for key in _PHOTO_KEYS)

    resent = await _submit_to_moliyachi_with(main, bot, ("new_notebook", "new_pos", "new_receipts"))
    photos = [m.photo for m in resent if isinstance(m, SendPhoto) and m.chat_id == MOLIYACHI]
    assert photos == ["new_notebook", "new_pos", "new_receipts"]
    assert not any("old_" in str(getattr(m, "photo", "")) for m in resent)


async def test_restarting_closeshift_midway_clears_stale_file_ids(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await send(main.dp, bot, KASSIR, photo_file_id="abandoned_notebook")
    assert (await _fsm_data(main, bot, KASSIR))["review_notebook"] == "abandoned_notebook"

    sent = await send(main.dp, bot, KASSIR, text="/closeshift")  # tashlab ketib, qaytadan boshladi

    assert "📒 Daftar rasmini yuboring" in _joined(sent)
    data = await _fsm_data(main, bot, KASSIR)
    assert all(data.get(key) is None for key in _PHOTO_KEYS)

    resent = await _submit_to_moliyachi_with(main, bot, ("n2", "p2", "r2"))
    assert [m.photo for m in resent if isinstance(m, SendPhoto) and m.chat_id == MOLIYACHI] == ["n2", "p2", "r2"]


async def test_no_file_ids_remain_in_fsm_after_send_and_nothing_in_db(bot_dp):
    main, bot = bot_dp
    await _to_photo_prompt(main, bot)
    await _submit_to_moliyachi(main, bot)

    data = await _fsm_data(main, bot, KASSIR)
    assert all(data.get(key) is None for key in _PHOTO_KEYS)
    row = _shift()
    assert not row.get("sales_report_photo_ref") and not row.get("cash_report_photo_ref")
    conn = get_connection()
    try:
        tables = [r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]
        for table in tables:
            for column in conn.execute(f"PRAGMA table_info({table})").fetchall():
                if table == "bot_workflow_messages":
                    continue
                if conn.execute(
                    f"SELECT COUNT(*) AS n FROM {table} WHERE CAST({column['name']} AS TEXT) IN "
                    "('notebook_file', 'pos_file', 'receipts_file')"
                ).fetchone()["n"]:
                    raise AssertionError(f"rasm file_id bazaga tushgan: {table}.{column['name']}")
    finally:
        conn.close()


async def _submit_to_moliyachi_with(main, bot, photos: tuple[str, str, str]):
    for file_id in photos:
        await send(main.dp, bot, KASSIR, photo_file_id=file_id)
    await send(main.dp, bot, KASSIR, text="300000")
    return await send_callback(main.dp, bot, KASSIR, data="csui_rev_send", target_chat_id=KASSIR)
