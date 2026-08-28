import pytest

import company_time
from config import FOUNDER_ID
from repositories import cash_shifts as cash_shifts_repo
from services import shift_daily_report
from tests.bot_harness import send, send_callback, texts

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_kassir(user_id: int, branch: str = "Filial-1") -> None:
    from roles import set_role
    import employees

    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {
            "familiya": "Kassirov", "ism": "Ali", "otasining_ismi": "Vali",
            "branch": branch, "role_key": "kassir", "contacts": [],
        },
    )


async def _open_shift(main, bot, user_id: int, opening_balance: str = "0") -> None:
    await send(main.dp, bot, user_id, text="/openshift")
    await send(main.dp, bot, user_id, text=opening_balance)


async def _clear_deficiency_gate(main, bot, user_id: int):
    await send_callback(main.dp, bot, user_id, data="csdef_none", target_chat_id=user_id)
    return await send_callback(main.dp, bot, user_id, data="csdef_none", target_chat_id=user_id)


async def _answer_no_prixod_and_price(main, bot, user_id: int, no_prixod_data="csdr_prixod:0", price_data="csdr_price:0"):
    await send_callback(main.dp, bot, user_id, data=no_prixod_data, target_chat_id=user_id)
    return await send_callback(main.dp, bot, user_id, data=price_data, target_chat_id=user_id)


async def test_daily_report_starts_after_deficiency_gate(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")

    sent = await _clear_deficiency_gate(main, bot, 111)

    combined = " ".join(t for t in texts(sent) if t)
    assert "prixodi chiqmagan" in combined
    assert "rasmini yuboring" not in combined


async def test_no_prixod_direct_value_moves_to_price_question(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)

    sent = await send_callback(main.dp, bot, 111, data="csdr_prixod:3", target_chat_id=111)

    combined = " ".join(t for t in texts(sent) if t)
    assert "narxi qimmat" in combined


async def test_no_prixod_6plus_asks_exact_number_then_validates(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)

    sent = await send_callback(main.dp, bot, 111, data="csdr_prixod:6plus", target_chat_id=111)
    assert "Aniq nechta" in " ".join(t for t in texts(sent) if t)

    sent = await send(main.dp, bot, 111, text="besh")
    assert "❌" in " ".join(t for t in texts(sent) if t)

    sent = await send(main.dp, bot, 111, text="5")
    assert "❌" in " ".join(t for t in texts(sent) if t)  # 5 < 6, rad etiladi

    sent = await send(main.dp, bot, 111, text="8")
    assert "narxi qimmat" in " ".join(t for t in texts(sent) if t)


async def test_no_prixod_5_or_more_sends_signal_to_founder(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)

    sent = await send_callback(main.dp, bot, 111, data="csdr_prixod:5", target_chat_id=111)

    founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID and getattr(m, "text", None)]
    assert len(founder_messages) == 1
    assert "5 ta" in founder_messages[0].text


async def test_no_prixod_below_threshold_sends_no_signal(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)

    sent = await send_callback(main.dp, bot, 111, data="csdr_prixod:4", target_chat_id=111)

    founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert founder_messages == []


async def test_no_prixod_6plus_exact_value_signals_founder(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)
    await send_callback(main.dp, bot, 111, data="csdr_prixod:6plus", target_chat_id=111)

    sent = await send(main.dp, bot, 111, text="9")

    founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID and getattr(m, "text", None)]
    assert len(founder_messages) == 1
    assert "9 ta" in founder_messages[0].text


async def test_price_complaint_bucket_moves_to_staff_question(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)

    sent = await _answer_no_prixod_and_price(main, bot, 111, price_data="csdr_price:6-10")

    combined = " ".join(t for t in texts(sent) if t)
    assert "xaridor shikoyat" in combined


async def test_staff_complaint_none_completes_gate_and_reaches_photo_prompt(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)
    await _answer_no_prixod_and_price(main, bot, 111)

    sent = await send_callback(main.dp, bot, 111, data="csdr_staff_no", target_chat_id=111)

    combined = " ".join(t for t in texts(sent) if t)
    assert "rasmini yuboring" in combined

    shift = cash_shifts_repo.get_open_shift(111, company_time.today().isoformat())
    assert shift_daily_report.is_flow_complete(shift["id"]) is True


async def test_staff_complaint_yes_employee_and_known_type_completes_gate(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)
    await _answer_no_prixod_and_price(main, bot, 111)

    sent = await send_callback(main.dp, bot, 111, data="csdr_staff_yes", target_chat_id=111)
    assert any(
        button.callback_data == "csdr_staff_emp:111"
        for message in sent if getattr(message, "reply_markup", None)
        for row in message.reply_markup.inline_keyboard for button in row
    )

    sent = await send_callback(main.dp, bot, 111, data="csdr_staff_emp:111", target_chat_id=111)
    combined = " ".join(t for t in texts(sent) if t)
    assert "Shikoyat turini tanlang" in combined

    sent = await send_callback(main.dp, bot, 111, data="csdr_staff_type:rude", target_chat_id=111)
    combined = " ".join(t for t in texts(sent) if t)
    assert "rasmini yuboring" in combined

    shift = cash_shifts_repo.get_open_shift(111, company_time.today().isoformat())
    from repositories import shift_daily_report as repo

    row = repo.get(shift["id"])
    assert row["staff_complaint_occurred"] == 1
    assert row["staff_complaint_employee_id"] == 111
    assert row["staff_complaint_type"] == shift_daily_report.COMPLAINT_TYPE_RUDE
    assert row["staff_complaint_note"] is None


async def test_staff_complaint_other_type_requires_free_text_note(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)
    await _answer_no_prixod_and_price(main, bot, 111)
    await send_callback(main.dp, bot, 111, data="csdr_staff_yes", target_chat_id=111)
    await send_callback(main.dp, bot, 111, data="csdr_staff_emp:111", target_chat_id=111)

    sent = await send_callback(main.dp, bot, 111, data="csdr_staff_type:other", target_chat_id=111)
    assert "Qisqacha yozing" in " ".join(t for t in texts(sent) if t)

    sent = await send(main.dp, bot, 111, text="   ")
    assert "Bo'sh matn" in " ".join(t for t in texts(sent) if t)

    sent = await send(main.dp, bot, 111, text="Ovqat hidi yoqmadi")
    assert "rasmini yuboring" in " ".join(t for t in texts(sent) if t)

    shift = cash_shifts_repo.get_open_shift(111, company_time.today().isoformat())
    from repositories import shift_daily_report as repo

    row = repo.get(shift["id"])
    assert row["staff_complaint_type"] == shift_daily_report.COMPLAINT_TYPE_OTHER
    assert row["staff_complaint_note"] == "Ovqat hidi yoqmadi"


async def test_daily_report_completes_once_then_closeshift_retry_skips_it(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)
    await _answer_no_prixod_and_price(main, bot, 111)
    await send_callback(main.dp, bot, 111, data="csdr_staff_no", target_chat_id=111)

    shift = cash_shifts_repo.get_open_shift(111, company_time.today().isoformat())
    assert shift_daily_report.is_flow_complete(shift["id"]) is True

    sent = await send(main.dp, bot, 111, text="/closeshift")
    combined = " ".join(t for t in texts(sent) if t)
    assert "prixodi chiqmagan" not in combined
    assert "narxi qimmat" not in combined
    assert "rasmini yuboring" in combined


async def test_full_flow_deficiency_then_daily_report_then_close_succeeds(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111)
    await send(main.dp, bot, 111, text="/closeshift")
    await _clear_deficiency_gate(main, bot, 111)
    await _answer_no_prixod_and_price(main, bot, 111)
    await send_callback(main.dp, bot, 111, data="csdr_staff_no", target_chat_id=111)

    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    await send_callback(main.dp, bot, 111, data="csui_close_start_yes", target_chat_id=111)
    await send(main.dp, bot, 111, text="100000")
    sent = await send_callback(main.dp, bot, 111, data="csui_close_amount_ok", target_chat_id=111)

    combined = " ".join(t for t in texts(sent) if t)
    assert "KASSA — KUN YAKUNI" in combined
